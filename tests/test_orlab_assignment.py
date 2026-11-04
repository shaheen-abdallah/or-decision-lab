"""Assignment (LinearSumAssignment) on a 3 x 2 case solved by hand.

Operators a, b, c; stations X, Y. Costs a: 1/9, b: 2/2, c: 9/1. One spare operator.
Best: a->X (1), c->Y (1) = 2, b free. If c is sick: a->X 1 + b->Y 2 = 3.
With only a and b certified nowhere for Y except b, and b sick: Y unstaffed -> infeasible.
"""

from orlab.registry import problem

P = problem("assignment")


def small(ops=None):
    return P.solve({"operators": ops or [{"operator": "a", "X": 1, "Y": 9}, {"operator": "b", "X": 2, "Y": 2},
                                         {"operator": "c", "X": 9, "Y": 1}]})


def test_hand_solved_matching():
    s = small()
    assert s.ok and s.objective == 2 and s.extra["match"] == {"a": "X", "c": "Y"}
    assert "b stays free" in s.bullets[2]


def test_sick_operator_and_uncertified():
    s = small([{"operator": "a", "X": 1, "Y": 9}, {"operator": "b", "X": 2, "Y": 2}])
    assert s.objective == 3
    s = small([{"operator": "a", "X": 1, "Y": None}, {"operator": "d", "X": 3, "Y": None}])
    assert s.status == "infeasible"


def test_plant_example():
    s = P.solve(P.example)
    assert s.ok and s.objective == 45 and s.extra["match"]["Dmitri"] == "SUV off-road calibration"
