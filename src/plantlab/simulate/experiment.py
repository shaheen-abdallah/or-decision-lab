"""Experiments: run the line many times and report KPIs with 95% confidence intervals.

One replication = the line starts empty, runs `warmup_weeks` (not measured), then `run_weeks`
that are measured. Each replication has its own random streams. For every KPI x over n
replications:

    95% CI = mean(x) +/- t(0.975, n - 1) * s / sqrt(n)      (s = sample standard deviation)

KPIs: cars per week (total and per model), weekly margin of the built cars, cycle time (launch
to exit, working hours), WIP (time-average cars in the plant), rework rate (share of finished
SUVs that needed rework); per station: working, down, blocked share of unit time, average
queue (cars in the buffer) and wait.

Bottleneck: the station whose units are active (working or under repair) the largest share of
the time, the classic utilisation method. Supporting evidence: the station before it is often
blocked (no room to hand cars on) and the stations after it are starved.
"""

from collections import Counter
from dataclasses import dataclass

import numpy as np
import simpy
from scipy import stats

from plantlab.optimize.report import eur, pct, table
from plantlab.plant import minutes_per_week
from plantlab.simulate.fitting import fit_plant
from plantlab.simulate.model import build_line


def ci(values, level=0.95):
    """(mean, half-width) of the t confidence interval."""
    v = np.asarray(values, dtype=float)
    if len(v) < 2:
        return float(v.mean()), float("nan")
    half = stats.t.ppf((1 + level) / 2, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v))
    return float(v.mean()), float(half)


@dataclass
class Run:
    kpi: dict             # name -> value for this replication
    stations: dict        # station -> {working, down, blocked, active, queue, wait}
    launched: int         # cars launched since t = 0
    finished: int         # cars that left the plant since t = 0
    in_plant: int         # cars still in the plant at the end


def measure(line, plant, warmup, run_weeks):
    products = plant["products"]
    done = [c for c in line.cars if c.finished is not None and c.finished >= warmup]
    kpi = {"cars": len(done) / run_weeks,
           "launched": sum(c.launched >= warmup for c in line.cars) / run_weeks}
    for p in products:
        kpi[f"cars_{p}"] = sum(c.product == p for c in done) / run_weeks
    kpi["margin"] = sum(kpi[f"cars_{p}"] * products[p]["margin_eur"] for p in products)
    kpi["cycle_time_h"] = (np.mean([c.finished - c.launched for c in done]) / 60
                           if done else float("nan"))
    kpi["wip"] = line.wip.mean()
    rw = line.rework
    checked = [c for c in done if rw and c.product == rw.product]
    kpi["rework_rate"] = (sum(c.reworks > 0 for c in checked) / len(checked)) if checked else 0.0
    st_kpi = {}
    for s, st in line.stations.items():
        units = st.spec.units
        working, down, blocked = st.busy.mean() / units, st.down.mean() / units, st.blocked.mean() / units
        st_kpi[s] = {"working": working, "down": down, "blocked": blocked, "active": working + down,
                     "queue": st.queue.mean(),
                     "wait": float(np.mean(st.waits)) if st.waits else 0.0}
    finished = sum(c.finished is not None for c in line.cars)
    return Run(kpi, st_kpi, len(line.cars), finished, line.wip.level)


def run_replication(plant, plan, fits, seed, rep, warmup_weeks, run_weeks):
    week = minutes_per_week(plant)
    warmup = warmup_weeks * week
    env = simpy.Environment()
    line = build_line(env, plant, plan, fits, seed, rep, warmup)
    env.run(until=warmup + run_weeks * week)
    return measure(line, plant, warmup, run_weeks)


@dataclass
class Experiment:
    plan: dict            # model -> planned cars per week
    runs: list
    names: dict
    order: list           # stations in line order, rework bay last
    warmup_weeks: float
    run_weeks: float
    bottleneck: str = ""
    bottleneck_votes: int = 0
    summary: str = ""

    def kpi(self, key):
        return ci([r.kpi[key] for r in self.runs])

    def station(self, s, key):
        return ci([r.stations[s][key] for r in self.runs])

    def report(self):
        def fmt(key, f):
            mean, half = self.kpi(key)
            return [f(mean), "± " + f(half)]

        num = "{:,.0f}".format
        rows = [["Cars launched per week", *fmt("launched", num)],
                ["Cars built per week", *fmt("cars", num)]]
        rows += [[f"  {self.names[p]}s", *fmt(f"cars_{p}", num)] for p in self.plan]
        rows += [["Margin per week", *fmt("margin", eur)],
                 ["Cycle time (working h)", *fmt("cycle_time_h", "{:.2f}".format)],
                 ["WIP (cars in the plant)", *fmt("wip", "{:.1f}".format)],
                 ["Rework rate (SUVs)", *fmt("rework_rate", "{:.1%}".format)]]
        kpis = table(["KPI", "Mean", "95% CI"], rows)

        st_rows = []
        for s in self.order:
            active, half = self.station(s, "active")
            mark = "  <- bottleneck" if s == self.bottleneck else ""
            st_rows.append([self.names[s] + mark, pct(self.station(s, "working")[0]), pct(self.station(s, "down")[0]),
                            pct(self.station(s, "blocked")[0]), f"{active:.0%} ± {half:.1%}",
                            f"{self.station(s, 'queue')[0]:.1f}", f"{self.station(s, 'wait')[0]:.1f}"])
        stations = table(["Station", "Working", "Down", "Blocked", "Active (95% CI)", "Queue",
                          "Wait min"], st_rows)
        return kpis + "\n\n" + stations + "\n\n" + self.summary


def summarise(e):
    n, reps = e.names, len(e.runs)
    planned = sum(e.plan.values())
    cars, half = e.kpi("cars")
    lines = [f"{reps} replications of {e.run_weeks:g} week(s) after a {e.warmup_weeks:g}-week warm-up: "
             f"the line builds {cars:,.0f} ± {half:,.0f} cars a week against a plan of {planned:,.0f} "
             f"({cars / planned - 1:+.1%})."]
    for p, target in e.plan.items():
        got = e.kpi(f"cars_{p}")[0]
        lines.append(f"- {n[p]}s: {got:,.0f} of {target:,.0f} planned.")
    b = e.bottleneck
    lines.append(f"Bottleneck: {n[b]}, active {e.station(b, 'active')[0]:.0%} of the time "
                 f"(busiest station in {e.bottleneck_votes} of {reps} replications).")
    i = e.order.index(b)
    if 0 < i < len(e.order) - 1:                   # the rework bay (last) has no fixed feeder
        before = e.order[i - 1]
        lines.append(f"The station before it, {n[before]}, is blocked "
                     f"{e.station(before, 'blocked')[0]:.0%} of the time waiting for space.")
    ct, wip = e.kpi("cycle_time_h")[0], e.kpi("wip")[0]
    lines.append(f"A car spends {ct:.1f} working hours in the plant on average; "
                 f"{wip:.0f} cars are in process (WIP); {e.kpi('rework_rate')[0]:.1%} of SUVs need rework.")
    return "\n".join(lines)


def run_experiment(plant, plan, reps=None, seed=None, warmup_weeks=None, run_weeks=None, fits=None):
    """Simulate the weekly `plan` ({model: cars}) `reps` times; returns an Experiment."""
    sim = plant["simulation"]
    reps = reps or sim["replications"]
    seed = sim["seed"] if seed is None else seed
    warmup_weeks = sim["warmup_weeks"] if warmup_weeks is None else warmup_weeks
    run_weeks = run_weeks or sim["run_weeks"]
    fits = fits or fit_plant(plant)
    runs = [run_replication(plant, plan, fits, seed, rep, warmup_weeks, run_weeks) for rep in range(reps)]

    bay = sim["rework"]["bay"]
    names = {s["id"]: s["name"] for s in plant["stations"]}
    names[bay["id"]] = bay["name"]
    names.update({p: plant["products"][p]["name"] for p in plant["products"]})
    order = [s["id"] for s in plant["stations"]] + [bay["id"]]
    e = Experiment({p: round(x) for p, x in plan.items()}, runs, names, order, warmup_weeks, run_weeks)

    votes = Counter(max(r.stations, key=lambda s: r.stations[s]["active"]) for r in runs)
    e.bottleneck, e.bottleneck_votes = max(votes.items(), key=lambda kv: (kv[1], e.station(kv[0], "active")[0]))
    e.summary = summarise(e)
    return e
