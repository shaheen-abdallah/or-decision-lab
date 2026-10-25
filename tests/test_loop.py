"""The plan-vs-reality loop: scenario changes, the rework-aware LP, the base-plan bottleneck."""

import pytest

from plantlab.loop import SCENARIOS, apply_changes, rework_aware, run_scenario
from plantlab.optimize import production_mix
from plantlab.plant import load_plant


def test_apply_changes_by_dotted_path():
    plant = load_plant()
    changed = apply_changes(plant, {"stations.offroad.units": 2, "simulation.buffer_size": 6})
    assert next(s for s in changed["stations"] if s["id"] == "offroad")["units"] == 2
    assert changed["simulation"]["buffer_size"] == 6
    assert next(s for s in plant["stations"] if s["id"] == "offroad")["units"] == 1   # copy
    with pytest.raises(KeyError):
        apply_changes(plant, {"stations.nosuch.units": 2})


def test_rework_aware_plan():
    """6% of off-road tests fail, so an SUV needs 1 / 0.94 tests: 8 / 0.94 = 8.511 minutes.

    Hand calculation (both constraints binding):
      off-road: 8.511 x SUV <= 4,320  ->  SUV = 507.6
      paint:    9 x Sedan + 11 x SUV <= 8,640  ->  Sedan = (8,640 - 5,583.6) / 9 = 339.6
    """
    mix = production_mix.solve_plant(rework_aware(load_plant()))
    assert mix.plan["suv"] == pytest.approx(4320 * 0.94 / 8, abs=0.1)
    assert mix.plan["sedan"] == pytest.approx((8640 - 11 * 4320 * 0.94 / 8) / 9, abs=0.1)
    assert "rework" in mix.stations


def test_base_plan_falls_short_at_the_test_cell():
    """The LP loads off-road calibration to 100% but rework adds 6% more tests: the simulation
    builds fewer cars than planned and names off-road calibration as the bottleneck."""
    r = run_scenario(load_plant(), SCENARIOS[0], reps=3)
    assert r.sim.bottleneck == "offroad"
    assert r.sim.kpi("cars")[0] < 0.97 * sum(r.mix.plan.values())
    assert "Paper (LP)" in r.gap_table()
