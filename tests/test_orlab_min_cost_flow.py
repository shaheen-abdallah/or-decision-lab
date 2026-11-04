"""Transportation (SimpleMinCostFlow) on a 2 x 2 case solved by hand.

Suppliers A (cap 10), B (cap 10); plants X (needs 8), Y (needs 6).
Costs A->X 1, A->Y 5, B->X 4, B->Y 2.  Cheapest: A->X 8, B->Y 6 = 8 + 12 = 20; A spare 2, B spare 4.
Block A->X: B->X 8 (32), then Y is cheapest from B (2 left, 4) and A (4 x 5 = 20) = 56.
Demand 25 > capacity 20: infeasible, short by 5.
"""

from orlab.registry import problem

P = problem("min_cost_flow")


def small(**over):
    data = {"part": "u", "suppliers": [{"supplier": "A", "capacity": 10, "X": 1, "Y": 5},
                                       {"supplier": "B", "capacity": 10, "X": 4, "Y": 2}],
            "plants": [{"plant": "X", "demand": 8}, {"plant": "Y", "demand": 6}]}
    data.update(over)
    return P.solve(data)


def test_hand_solved_plan():
    s = small()
    assert s.ok and s.objective == 20
    assert s.extra["flows"] == {"A → X": 8, "A → Y": 0, "B → X": 0, "B → Y": 6}
    assert {r["supplier"]: r["spare"] for r in s.tables["flows"]} == {"A": 2, "B": 4}


def test_blocked_route_changes_the_plan():
    s = small(suppliers=[{"supplier": "A", "capacity": 10, "X": None, "Y": 5},
                         {"supplier": "B", "capacity": 10, "X": 4, "Y": 2}])
    assert s.objective == 56 and s.extra["flows"] == {"A → Y": 4, "B → X": 8, "B → Y": 2}


def test_short_supply_is_explained():
    s = small(plants=[{"plant": "X", "demand": 19}, {"plant": "Y", "demand": 6}])
    assert s.status == "infeasible" and "short by 5" in s.headline


def test_plant_example():
    s = P.solve(P.example)
    assert s.objective == 18_170 and s.extra["flows"]["Saarbrücken → Plant West"] == 600
