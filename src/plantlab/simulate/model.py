"""SimPy model of the mixed-model line: the weekly plan meets random times, breakdowns and rework.

How the model works, in plain words:
- Clock: working minutes. The plant runs 07:00-23:00 (960 minutes a day), 5 days a week. At
  23:00 the line freezes with its cars in place and restarts at 07:00, so nights and weekends
  are skipped: minute 960 is Tuesday 07:00, one week is 4,800 minutes.
- Launch: cars enter at the plan's pace (one every 4,800 / planned cars minutes) in a levelled
  Sedan/SUV sequence (heijunka). If the first buffer is full, the launch waits; that slot is lost.
- Station: `units` parallel workplaces with an input buffer for `buffer` cars. A car waits in
  the buffer for a free unit and is worked on for a time drawn from the fitted distribution.
  Before it can leave it needs a place in the next station's buffer; while that is full the
  unit holds the car and is blocked (blocking after service).
- Breakdowns: each unit fails after an exponential amount of running time (mean MTBF); the car
  on it waits for the repair (fitted repair-time distribution). Failures count running time
  only (Arena's "busy time" failures), so availability = MTBF / (MTBF + MTTR) = 90%, the same
  share of time the plan deducts.
- Rework: an SUV that fails off-road calibration (6% of tests) goes to the rework bay and back
  to off-road calibration for a new test. The rework bay has unlimited parking, so the test
  cell can always hand a car on and the loop cannot deadlock.

Every station / model / purpose gets its own random stream, so a scenario that changes one
station leaves the other stations' draws unchanged (common random numbers).
"""

import zlib
from dataclasses import dataclass

import numpy as np
import simpy

from plantlab.plant import minutes_per_week


class Sampler:
    """Draws from a frozen scipy distribution in batches (one rvs call per 512 values is fast)."""

    def __init__(self, dist, rng, batch=512):
        self.dist, self.rng, self.batch = dist, rng, batch
        self.values, self.i = np.empty(0), 0

    def __call__(self):
        if self.i >= len(self.values):
            # station times are positive; a fitted normal could in theory draw <= 0
            self.values = np.maximum(self.dist.rvs(size=self.batch, random_state=self.rng), 0.01)
            self.i = 0
        self.i += 1
        return float(self.values[self.i - 1])


def stream(seed, rep, name):
    """Random stream for one purpose ("paint/suv", "paint/failures", ...) in one replication."""
    return np.random.default_rng([seed, rep, zlib.crc32(name.encode())])


class Level:
    """A level that changes over time (cars in a buffer, busy units); time-average from t0 on."""

    def __init__(self, env, t0):
        self.env, self.t0 = env, t0
        self.level, self.last, self.area = 0, 0.0, 0.0

    def add(self, delta):
        now = self.env.now
        start = max(self.last, self.t0)
        if now > start:
            self.area += self.level * (now - start)
        self.last = now
        self.level += delta

    def mean(self):
        self.add(0)
        span = self.env.now - self.t0
        return self.area / span if span > 0 else 0.0


@dataclass
class StationSpec:
    id: str
    name: str
    units: int
    buffer: int | None              # cars that fit in front (None = unlimited)
    process: dict                   # model -> Sampler of station minutes; other models skip it
    repair: Sampler | None = None   # repair minutes; None = never breaks down
    mtbf: float | None = None       # mean running minutes between breakdowns


@dataclass
class Rework:
    product: str
    found_at: str                   # station where the fault shows up
    rate: float                     # share of tests that fail
    bay: str                        # station that fixes it


@dataclass
class Car:
    id: int
    product: str
    route: list
    launched: float
    finished: float | None = None
    reworks: int = 0


class Unit:
    """One workplace; remembers how much running time is left until its next breakdown."""

    def __init__(self, rng, mtbf):
        self.rng, self.mtbf = rng, mtbf
        self.to_failure = rng.exponential(mtbf) if mtbf else np.inf


class Station:
    def __init__(self, env, spec, t0, seed, rep):
        self.spec = spec
        self.slots = None if spec.buffer is None else simpy.Resource(env, capacity=spec.buffer)
        self.free = simpy.Store(env)
        failures = stream(seed, rep, f"{spec.id}/failures")
        self.free.items.extend(Unit(failures, spec.mtbf) for _ in range(spec.units))
        # cars in the buffer, units working, under repair, holding a finished car
        self.queue, self.busy, self.down, self.blocked = (Level(env, t0) for _ in range(4))
        self.waits = []             # buffer minutes of cars that started work after t0
        self.failures = 0


class Line:
    def __init__(self, env, specs, rework=None, warmup=0.0, seed=0, rep=0):
        self.env, self.t0, self.rework = env, warmup, rework
        self.stations = {s.id: Station(env, s, warmup, seed, rep) for s in specs}
        self.order = [s.id for s in specs if not rework or s.id != rework.bay]
        self.rework_rng = stream(seed, rep, "rework")
        self.cars = []
        self.wip = Level(env, warmup)

    def route(self, product):
        return [s for s in self.order if product in self.stations[s].spec.process]

    def next_station(self, car, here):
        rw = self.rework
        if rw and here == rw.bay:
            return rw.found_at                                  # fixed: test again
        if (rw and here == rw.found_at and car.product == rw.product
                and self.rework_rng.random() < rw.rate):
            car.reworks += 1
            return rw.bay
        i = car.route.index(here) + 1
        return car.route[i] if i < len(car.route) else None    # None = leaves the plant

    def take_slot(self, station):
        if station.slots is None:
            return None
        slot = station.slots.request()
        yield slot
        return slot

    def launch(self, interarrival, sequence):
        """Release cars at the planned pace; a full first buffer holds the launch back."""
        while True:
            yield self.env.timeout(interarrival())
            product = sequence()
            route = self.route(product)
            slot = yield from self.take_slot(self.stations[route[0]])
            car = Car(len(self.cars), product, route, launched=self.env.now)
            self.cars.append(car)
            self.wip.add(1)
            self.env.process(self.flow(car, slot))

    def flow(self, car, slot):
        here = car.route[0]
        while here is not None:
            st = self.stations[here]
            arrived = self.env.now
            st.queue.add(1)
            unit = yield st.free.get()
            st.queue.add(-1)
            if slot is not None:
                st.slots.release(slot)                          # leaves the buffer
            if self.env.now >= self.t0:
                st.waits.append(self.env.now - arrived)
            yield from self.work(st, unit, st.spec.process[car.product]())
            here = self.next_station(car, here)
            slot = None
            if here is not None:
                st.blocked.add(1)
                slot = yield from self.take_slot(self.stations[here])
                st.blocked.add(-1)
            st.free.put(unit)
        car.finished = self.env.now
        self.wip.add(-1)

    def work(self, st, unit, minutes):
        """Work `minutes` on the car; a breakdown on the way adds a repair."""
        while unit.to_failure < minutes:
            minutes -= unit.to_failure
            yield from self.timed(st.busy, unit.to_failure)
            st.failures += self.env.now >= self.t0
            yield from self.timed(st.down, st.spec.repair())
            unit.to_failure = unit.rng.exponential(unit.mtbf)
        unit.to_failure -= minutes
        yield from self.timed(st.busy, minutes)

    def timed(self, level, minutes):
        level.add(1)
        yield self.env.timeout(minutes)
        level.add(-1)


def levelled_sequence(cars):
    """Heijunka: each launch takes the model furthest behind its share (e.g. S U U S U U ...)."""
    total = sum(cars.values())
    launched = dict.fromkeys(cars, 0)
    k = 0

    def next_model():
        nonlocal k
        k += 1
        p = max(cars, key=lambda p: cars[p] / total * k - launched[p])
        launched[p] += 1
        return p

    return next_model


def build_line(env, plant, plan, fits, seed, rep, warmup):
    """The plant's line, launching the weekly `plan` ({model: cars}) with the fitted times."""
    sim = plant["simulation"]
    availability = plant["plant"]["availability"]
    specs = []
    for st in plant["stations"]:
        s, var = st["id"], sim["stations"][st["id"]]
        specs.append(StationSpec(
            id=s, name=st["name"], units=st["units"],
            buffer=var.get("buffer", sim["buffer_size"]),
            process={p: Sampler(fits.dist((s, p)), stream(seed, rep, f"{s}/{p}"))
                     for p, minutes in st["minutes"].items() if minutes > 0},
            repair=Sampler(fits.dist((s, "repair")), stream(seed, rep, f"{s}/repair")),
            mtbf=var["mttr"] * availability / (1 - availability),
        ))
    rw, bay = sim["rework"], sim["rework"]["bay"]
    specs.append(StationSpec(
        id=bay["id"], name=bay["name"], units=bay["units"], buffer=None,
        process={rw["product"]: Sampler(fits.dist((bay["id"], rw["product"])),
                                        stream(seed, rep, f"{bay['id']}/{rw['product']}"))},
    ))
    line = Line(env, specs, Rework(rw["product"], rw["found_at"], rw["rate"], bay["id"]),
                warmup, seed, rep)
    cars = {p: round(n) for p, n in plan.items() if round(n) > 0}
    takt = minutes_per_week(plant) / sum(cars.values())
    env.process(line.launch(lambda: takt, levelled_sequence(cars)))
    return line
