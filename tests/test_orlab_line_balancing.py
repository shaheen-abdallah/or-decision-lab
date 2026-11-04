"""Line balancing (SCIP) on a 4-task case solved by hand.

Tasks A 5 s, B 4 s, C 3 s, D 2 s; A before B and C, B and C before D; cycle 6 s.
Total 14 s -> lower bound ceil(14/6) = 3. A fills a station alone (B or C would exceed 6).
B and C together are 7 > 6, so they split; D must follow both: {A}, {B}, {C, D} = 3 stations,
loads 5/4/5, busiest 5 (the alternative {A}, {C}, {B, D} has busiest 6, so smoothing picks 5).
Cycle 4 s: A alone exceeds it -> infeasible. Cycle 14 s and no precedence: everything on one station.
"""

from orlab.registry import problem

P = problem("line_balancing")
TASKS = [{"id": "A", "task": "a", "seconds": 5, "after": ""}, {"id": "B", "task": "b", "seconds": 4, "after": "A"},
         {"id": "C", "task": "c", "seconds": 3, "after": "A"}, {"id": "D", "task": "d", "seconds": 2, "after": "B, C"}]


def small(cycle=6, tasks=TASKS):
    return P.solve({"tasks": tasks, "line": [{"cycle time (s)": cycle}]})


def test_hand_solved_three_stations_smoothed():
    s = small()
    assert s.ok and s.objective == 3 and s.extra["lower_bound"] == 3 and s.extra["busiest"] == 5
    assert s.extra["assignment"]["A"] == 1 and s.extra["assignment"]["D"] == 3


def test_infeasible_and_one_station():
    assert small(cycle=4).status == "infeasible"
    s = small(cycle=14, tasks=[dict(t, after="") for t in TASKS])
    assert s.objective == 1 and s.tables["stations"][0]["load (s)"] == 14


def test_plant_example_reaches_lower_bound():
    s = P.solve(P.example)
    assert s.ok and s.objective == 5 == s.extra["lower_bound"] and s.extra["busiest"] <= 276
