"""Production mix LP on a 2-product case solved by hand.

max 40 s + 70 u  s.t.  P: 2s + 3u <= 120,  Q: 2s + u <= 80,  u <= 30 (sales)
Corner (15, 30): margin 2700. P and the SUV sales cap bind, Q has 20 min slack.
Duals: 2 yP = 40 -> yP = 20 per min; 3 yP + yD = 70 -> yD = 10 per car.
P stays the bottleneck for 90 <= P <= 140 (s = (P - 90) / 2 >= 0; Q: 2s + 30 <= 80).
"""

import pytest

from plantlab.optimize import production_mix


def small(**overrides):
    data = dict(
        products=["s", "u"],
        stations=["P", "Q"],
        margin={"s": 40, "u": 70},
        minutes={"P": {"s": 2, "u": 3}, "Q": {"s": 2, "u": 1}},
        capacity={"P": 120, "Q": 80},
        demand_min={"s": 0, "u": 0},
        demand_max={"s": 1000, "u": 30},
    )
    data.update(overrides)
    return production_mix.solve(**data)


def test_hand_solved_optimum():
    r = small()
    assert r.plan["s"] == pytest.approx(15)
    assert r.plan["u"] == pytest.approx(30)
    assert r.margin == pytest.approx(2700)


def test_shadow_prices_and_ranges():
    r = small()
    assert r.stations["P"].binding and not r.stations["Q"].binding
    assert r.stations["P"].shadow_price_per_h == pytest.approx(20 * 60)
    assert r.stations["Q"].shadow_price_per_h == pytest.approx(0)
    assert r.stations["P"].extra_hours_valid == pytest.approx((140 - 120) / 60)
    assert r.demand_value["u"] == pytest.approx(10)
    assert r.margin_range["s"] == pytest.approx((0, 140 / 3))   # s margin may rise to 46.67


def test_contract_that_cannot_be_built_is_infeasible():
    r = small(demand_min={"s": 0, "u": 50})   # 50 SUVs need 150 min at P > 120
    assert not r.plan
    assert "No weekly plan fits" in r.summary


def test_plant_plan():
    # by hand: off-road calibration caps SUVs at 4320 / 8 = 540;
    # paint then leaves (8640 - 11 * 540) / 9 = 300 Sedans
    r = production_mix.solve_plant()
    assert r.status == "optimal"
    assert r.plan["suv"] == pytest.approx(540)
    assert r.plan["sedan"] == pytest.approx(300)
    assert {s for s, st in r.stations.items() if st.binding} == {"paint", "offroad"}
    assert r.stations["paint"].shadow_price_per_h == pytest.approx(2300 / 9 * 60)
    assert "Paint shop" in r.summary
