"""Product mix (GLOP) on a 2-product case solved by hand.

max 40 s + 70 u  s.t.  P: 2s + 3u <= 120 min,  Q: 2s + u <= 80 min,  u <= 30 (demand)
Corner (15, 30): margin 2,700. P and the SUV cap bind, Q has 20 min spare.
Duals (per minute): 2 yP = 40 -> yP = 20, so one more hour at P is worth 60 x 20 = 1,200.
"""

import pytest

from orlab.registry import problem

P = problem("product_mix")


def small(**over):
    data = {"products": [{"product": "s", "margin": 40, "min": 0, "max": 1000},
                         {"product": "u", "margin": 70, "min": 0, "max": 30}],
            "stations": [{"station": "P", "hours": 2, "s": 2, "u": 3},
                         {"station": "Q", "hours": 80 / 60, "s": 2, "u": 1}]}
    data.update(over)
    return P.solve(data)


def test_hand_solved_optimum_and_duals():
    s = small()
    assert s.ok and s.objective == pytest.approx(2700)
    assert s.extra["plan"] == {"s": 15, "u": 30}
    by = {r["station"]: r for r in s.tables["stations"]}
    assert by["P"]["value of one more hour"] == pytest.approx(1200)
    assert by["Q"]["value of one more hour"] == 0 and by["Q"]["load"] == pytest.approx(60 / 80, abs=1e-3)
    assert s.extra["bottlenecks"] == ["P"] and "P is the bottleneck" in s.bullets[0]


def test_infeasible_when_contracts_exceed_hours():
    s = small(products=[{"product": "s", "margin": 40, "min": 100, "max": 1000},
                        {"product": "u", "margin": 70, "min": 0, "max": 30}])
    assert s.status == "infeasible" and s.objective is None


def test_plant_example_matches_v1():
    s = P.solve(P.example)
    assert s.extra["plan"] == {"Sedan": 300, "SUV": 540}
    assert s.objective == pytest.approx(2_526_000)
    assert s.extra["bottlenecks"] == ["Paint shop", "SUV off-road calibration"]
