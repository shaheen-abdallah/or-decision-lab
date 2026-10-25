"""Workforce IP on cases solved by hand."""

import pytest

from plantlab.optimize import workforce

COST = {"permanent": 1000, "temporary": 900, "floater": 1100}


def test_floaters_pool_fractions():
    # need 2.5 and 1.5, no temps: alone = 3 + 2 = 5 people (5000);
    # with a floater: 2 + 1 permanent + 1 floater covering 0.5 + 0.5 = 4100
    r = workforce.solve(["A", "B"], ["early"], {("A", "early"): 2.5, ("B", "early"): 1.5},
                        skilled={}, cost=COST, shift_premium={}, max_temp_share=0.0)
    assert r.cost == pytest.approx(4100)
    assert r.floaters["early"] == 1
    assert r.cost_without_floaters == pytest.approx(5000)
    assert r.headcount_without_floaters == 5


def test_temp_cap_and_buddy_rule():
    # need 4 at one station, temps cheaper but at most half the staff and <= permanents: 2 + 2
    r = workforce.solve(["A"], ["early"], {("A", "early"): 4}, skilled={}, cost=COST,
                        shift_premium={}, max_temp_share=0.5)
    assert r.permanent["A", "early"] == 2 and r.temporary["A", "early"] == 2
    assert r.cost == pytest.approx(3800)


def test_plant_rules_hold():
    plant = workforce.load_plant()
    r = workforce.solve_plant(plant)
    skilled = {s["id"] for s in plant["stations"] if s["skilled"]}
    for (s, h), need in r.need.items():
        assert r.permanent[s, h] + r.temporary[s, h] + r.floater_cover[s, h] >= need - 1e-6
        assert r.temporary[s, h] <= r.permanent[s, h]
        if s in skilled:
            assert r.temporary[s, h] == 0
    assert r.temporary_share <= plant["workforce"]["max_temporary_share"] + 1e-9
    assert r.cost <= r.cost_without_floaters
