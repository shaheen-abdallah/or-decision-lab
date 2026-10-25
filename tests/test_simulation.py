"""Simulation checks: queueing theory, flow conservation, input analysis, reproducibility."""

import numpy as np
import simpy
from scipy import stats

from plantlab.plant import load_plant, minutes_per_week
from plantlab.simulate.experiment import ci, run_experiment
from plantlab.simulate.fitting import fit_best, fit_plant
from plantlab.simulate.model import Line, Sampler, StationSpec, build_line, stream

PLAN = {"sedan": 300, "suv": 540}


def run_mm1(rep, lam=0.8, mu=1.0, warmup=2_000, horizon=22_000, seed=7):
    env = simpy.Environment()
    service = Sampler(stats.expon(scale=1 / mu), stream(seed, rep, "service"))
    station = StationSpec("s", "Single server", units=1, buffer=None, process={"car": service})
    line = Line(env, [station], warmup=warmup, seed=seed, rep=rep)
    arrivals = Sampler(stats.expon(scale=1 / lam), stream(seed, rep, "arrivals"))
    env.process(line.launch(arrivals, lambda: "car"))
    env.run(until=horizon)
    st = line.stations["s"]
    return st.busy.mean(), float(np.mean(st.waits))


def test_mm1_matches_queueing_formulas():
    """M/M/1 with lambda = 0.8 and mu = 1 car per minute, one unit, unlimited buffer.

    Hand calculation: rho = lambda / mu = 0.8; mean wait in the queue
    Wq = rho / (mu - lambda) = 0.8 / 0.2 = 4.0 minutes.
    Both true values must lie inside the 95% CI of 10 replications (20,000 minutes each).
    """
    runs = [run_mm1(rep) for rep in range(10)]
    rho, rho_half = ci([r[0] for r in runs])
    wq, wq_half = ci([r[1] for r in runs])
    assert abs(rho - 0.8) <= rho_half
    assert abs(wq - 4.0) <= wq_half


def test_flow_conservation():
    """Cars in = cars out + change in WIP, and every car in the plant sits at exactly one station."""
    plant = load_plant()
    week = minutes_per_week(plant)
    t0, t1 = week / 2, week
    env = simpy.Environment()
    line = build_line(env, plant, PLAN, fit_plant(plant), seed=1, rep=0, warmup=t0)
    env.run(until=t1)

    def in_plant(t):
        return sum(c.launched <= t and (c.finished is None or c.finished > t) for c in line.cars)

    cars_in = sum(c.launched > t0 for c in line.cars)
    cars_out = sum(c.finished is not None and c.finished > t0 for c in line.cars)
    assert cars_in == cars_out + in_plant(t1) - in_plant(t0)
    assert line.wip.level == in_plant(t1) > 0

    # waiting in a buffer, worked on, under repair or blocked on a unit: one place per car
    located = sum(st.queue.level + st.busy.level + st.down.level + st.blocked.level
                  for st in line.stations.values())
    assert located == line.wip.level
    for st in line.stations.values():
        assert st.busy.level + st.down.level + st.blocked.level <= st.spec.units


def test_fixed_seed_is_reproducible():
    plant = load_plant()
    a = run_experiment(plant, PLAN, reps=2, seed=11, warmup_weeks=0.2, run_weeks=0.4)
    b = run_experiment(plant, PLAN, reps=2, seed=11, warmup_weeks=0.2, run_weeks=0.4)
    c = run_experiment(plant, PLAN, reps=2, seed=12, warmup_weeks=0.2, run_weeks=0.4)
    assert [r.kpi for r in a.runs] == [r.kpi for r in b.runs]
    assert [r.kpi for r in a.runs] != [r.kpi for r in c.runs]


def test_fitting_recovers_a_known_distribution():
    """Gamma(shape 4, scale 2) data (mean 8): the best fit passes the KS test and keeps the mean;
    an exponential fit to the same data is rejected (its shape is wrong)."""
    rng = np.random.default_rng(3)
    data = rng.gamma(4, 2, 400)
    fits = fit_best(data)
    best = fits[0]
    assert best.p_value > 0.05
    assert abs(best.dist.mean() - 8) < 0.4
    assert next(f for f in fits if f.family == "Exponential").p_value < 0.05


def test_plant_fits_are_not_rejected():
    fits = fit_plant(load_plant())
    assert len(fits.fits) == 29          # 18 station times + 10 repair times + rework bay
    assert all(f.p_value > 0.05 for f in fits.fits.values())
