"""Knapsack (KnapsackSolver) on a 3-item case solved by hand.

Projects p (cost 5, gain 10), q (4, 7), r (3, 4); budget 7.
Greedy by gain per k€: p 2.0, q 1.75, r 1.33 -> p (5 left 2), q and r do not fit -> 10.
Best: q + r costs 7, gains 11 > 10. Budget 2: nothing fits.
"""

from orlab.registry import problem

P = problem("knapsack")
ITEMS = [{"project": "p", "cost k€": 5, "gain €/week": 10}, {"project": "q", "cost k€": 4, "gain €/week": 7},
         {"project": "r", "cost k€": 3, "gain €/week": 4}]


def test_hand_solved_beats_greedy():
    s = P.solve({"projects": ITEMS, "budget": [{"budget k€": 7}]})
    assert s.ok and s.objective == 11 and s.extra["chosen"] == ["q", "r"] and s.extra["spent"] == 7
    assert "€1 more" in s.bullets[1]


def test_nothing_fits():
    assert P.solve({"projects": ITEMS, "budget": [{"budget k€": 2}]}).status == "infeasible"


def test_plant_example():
    s = P.solve(P.example)
    assert s.ok and s.extra["spent"] <= 400 and s.objective >= 18_000
