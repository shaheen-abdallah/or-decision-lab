"""Shift scheduling, job shop (CP-SAT) and vehicle routing on cases solved by hand.

Shifts: operators A and B, days Mon and Tue, one early shift a day, both want Tue off, max 1 shift
each -> somebody must work Tue: exactly 1 broken request. Rest rule: demand Mon late + Tue early,
only A can work (B max 0) -> late then early is forbidden -> infeasible.

Job shop: J1 = M1 3 then M2 2; J2 = M1 2 then M2 4. J2 first: M1 0-2, M2 2-6; J1 M1 2-5, M2 6-8
-> makespan 8. J1 first gives 9. Optimum 8; M2 works 6 min, so the bound 6 is not reachable.

Routing: depot (0,0), dealers P (0,3), Q (4,3), R (4,0), 2 pallets each. One van, capacity 6:
the round depot-P-Q-R-depot = 3+4+3+4 = 14 km. Two vans of capacity 4: best split is P alone
(6 km) and Q+R (5+3+4 = 12 km) = 18 km (any other split is 20).
"""

from orlab.registry import problem


def test_shift_scheduling_hand_case():
    P = problem("shift_scheduling")
    ops = [{"operator": "A", "min shifts": 0, "max shifts": 1, "max late": 1, "days off wanted": "Tue"},
           {"operator": "B", "min shifts": 0, "max shifts": 1, "max late": 1, "days off wanted": "Tue"}]
    s = P.solve({"operators": ops, "demand": [{"shift": "early", "Mon": 1, "Tue": 1}, {"shift": "late", "Mon": 0, "Tue": 0}]})
    assert s.ok and s.objective == 1 and len(s.extra["missed"]) == 1
    ops = [{"operator": "A", "min shifts": 0, "max shifts": 2, "max late": 1, "days off wanted": ""},
           {"operator": "B", "min shifts": 0, "max shifts": 0, "max late": 1, "days off wanted": ""}]
    s = P.solve({"operators": ops, "demand": [{"shift": "early", "Mon": 0, "Tue": 1}, {"shift": "late", "Mon": 1, "Tue": 0}]})
    assert s.status == "infeasible"
    s = P.solve(P.example)
    assert s.ok and s.objective == 1          # three want Friday off, Friday needs 5 of 7


def test_job_shop_hand_case():
    P = problem("job_shop")
    s = P.solve({"batches": [{"batch": "J1", "M1": 3, "M2": 2}, {"batch": "J2", "M1": 2, "M2": 4}]})
    assert s.ok and s.objective == 8 and s.extra["lower_bound"] == 6
    first = min(s.tables["schedule"], key=lambda r: r["start"])
    assert first["batch"] == "J2" and first["station"] == "M1"
    s = P.solve(P.example)
    assert s.ok and s.objective >= s.extra["lower_bound"]


def test_vehicle_routing_hand_case():
    P = problem("vehicle_routing")
    stops = [{"stop": "depot", "x": 0, "y": 0, "pallets": 0}, {"stop": "P", "x": 0, "y": 3, "pallets": 2},
             {"stop": "Q", "x": 4, "y": 3, "pallets": 2}, {"stop": "R", "x": 4, "y": 0, "pallets": 2}]
    s = P.solve({"stops": stops, "fleet": [{"vans": 1, "pallets per van": 6}], "ms": 200})
    assert s.ok and s.objective == 14
    s = P.solve({"stops": stops, "fleet": [{"vans": 2, "pallets per van": 4}], "ms": 200})
    assert s.objective == 18 and len(s.extra["routes"]) == 2
    s = P.solve({"stops": stops, "fleet": [{"vans": 1, "pallets per van": 4}]})
    assert s.status == "infeasible"
    s = P.solve(P.example)
    assert s.ok and len(s.extra["routes"]) == 3 and s.objective < 450
