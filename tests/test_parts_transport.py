"""Transportation model on 2 x 2 cases solved by hand (u_i + v_j method)."""

import pytest

from plantlab.optimize import parts_transport

COST = {"S1": {"P1": 4, "P2": 6}, "S2": {"P1": 5, "P2": 3}}
DEMAND = {"P1": 25, "P2": 25}


def run(supply, blocked=()):
    return parts_transport.solve(["S1", "S2"], ["P1", "P2"], supply, DEMAND, COST, blocked)


def test_hand_solved_optimum_and_duals():
    # S1 -> P1 20, S2 -> P1 5, S2 -> P2 25: 80 + 25 + 75 = 180; S2 keeps 10 spare
    r = run({"S1": 20, "S2": 40})
    assert r.cost == pytest.approx(180)
    assert r.flows["S1", "P1"] == pytest.approx(20)
    assert r.flows["S2", "P2"] == pytest.approx(25)
    assert r.spare["S2"] == pytest.approx(10)
    assert r.plant_marginal == pytest.approx({"P1": 5, "P2": 3})   # next set comes from S2
    assert r.supplier_value["S1"] == pytest.approx(1)              # 1 more at S1 replaces S2 at P1


def test_blocked_route():
    # S1 may not ship to P1: S2 -> P1 25, S2 -> P2 15, S1 -> P2 10 = 125 + 45 + 60 = 230
    r = run({"S1": 20, "S2": 40}, blocked=[("S1", "P1")])
    assert r.flows["S1", "P1"] == pytest.approx(0)
    assert r.cost == pytest.approx(230)


def test_short_supply_ships_everything():
    # 40 sets for 50 demand: S1 -> P1 20, S2 -> P2 20 = 140; each plant misses 5
    r = run({"S1": 20, "S2": 20})
    assert r.cost == pytest.approx(140)
    assert r.shortage == pytest.approx({"P1": 5, "P2": 5})
    assert "Supply is short" in r.summary
