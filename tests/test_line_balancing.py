"""SALBP-1 on cases small enough to balance by hand."""

from plantlab.optimize import line_balancing


def test_two_stations_meet_the_lower_bound():
    # A(4) B(3) -> C(5) -> D(2), cycle 7: total 14 -> 2 stations, {A,B} and {C,D}
    r = line_balancing.solve(["A", "B", "C", "D"], {"A": 4, "B": 3, "C": 5, "D": 2},
                             {"C": ["A", "B"], "D": ["C"]}, cycle_time=7)
    assert r.n_stations == r.lower_bound == 2
    assert [sorted(t) for t, _ in r.stations] == [["A", "B"], ["C", "D"]]
    assert r.efficiency == 1.0


def test_task_sizes_beat_the_lower_bound():
    # three 5 s tasks in a chain, cycle 8: total 15 suggests 2, but no two tasks fit together
    r = line_balancing.solve(["A", "B", "C"], {"A": 5, "B": 5, "C": 5},
                             {"B": ["A"], "C": ["B"]}, cycle_time=8)
    assert r.lower_bound == 2
    assert r.n_stations == 3


def test_task_longer_than_cycle_time():
    r = line_balancing.solve(["A", "B"], {"A": 9, "B": 3}, {}, cycle_time=8)
    assert r.status == "infeasible" and "A" in r.summary


def test_plant_line_respects_precedence_and_takt():
    r = line_balancing.solve_plant()
    station_of = {t: k for k, (tasks, _) in enumerate(r.stations) for t in tasks}
    plant_tasks = line_balancing.load_plant()["line_balancing"]["tasks"]
    assert len(station_of) == len(plant_tasks)
    for t in plant_tasks:
        for before in t["after"]:
            assert station_of[before] <= station_of[t["id"]]
    assert all(load <= r.cycle_time + 1e-6 for _, load in r.stations)
    assert r.n_stations >= r.lower_bound
