r"""Assignment: which certified operator runs which skilled station on the early shift
(assignment problem, OR-Tools `LinearSumAssignment`).

**Decide** $x_{ij} \in \{0, 1\}$: operator $i$ takes station $j$.

$$\min \sum_{i,j} c_{ij}\, x_{ij} \qquad c_{ij} = \text{minutes of rework per shift expected from } i \text{ on } j$$
$$\sum_j x_{ij} \le 1 \quad \forall i \qquad\text{(one station per operator)}$$
$$\sum_i x_{ij} = 1 \quad \forall j \qquad\text{(every station staffed)}$$

The constraint matrix is totally unimodular, so the LP relaxation is already integral;
the dedicated solver (a cost-scaling push-relabel algorithm) is faster still.
An empty cost means the operator is not certified for that station.
"""

from ortools.graph.python import linear_sum_assignment

from orlab.core import Solution, num

EXAMPLE = {
    # expected minutes of rework per shift (lower is better); empty = not certified
    "operators": [
        {"operator": "Amal", "Paint shop": 12, "Paint inspection": 20, "End-of-line test": 25, "SUV off-road calibration": None},
        {"operator": "Bekir", "Paint shop": 18, "Paint inspection": 10, "End-of-line test": 22, "SUV off-road calibration": 30},
        {"operator": "Clara", "Paint shop": 15, "Paint inspection": 16, "End-of-line test": 12, "SUV off-road calibration": 14},
        {"operator": "Dmitri", "Paint shop": None, "Paint inspection": 24, "End-of-line test": 15, "SUV off-road calibration": 11},
        {"operator": "Elif", "Paint shop": 14, "Paint inspection": 18, "End-of-line test": 19, "SUV off-road calibration": 16},
    ],
}


def _stations(data):
    return [k for k in data["operators"][0] if k != "operator"]


def explain(data):
    return {
        "decide": "Which operator takes which skilled station this shift.",
        "goal": "The fewest expected minutes of rework in total.",
        "limits": [f"Every station gets exactly one operator ({len(_stations(data))} stations)",
                   f"Every operator takes at most one station ({len(data['operators'])} operators)",
                   "An operator can only take a station they are certified for"],
    }


def solve(data):
    operators, stations = data["operators"], _stations(data)
    if len(operators) < len(stations):
        return Solution("infeasible", None,
                        f"{len(stations)} stations but only {len(operators)} operators: "
                        f"{len(stations) - len(operators)} would stay unstaffed.", ["Add an operator."])

    # 1. Declare the solver; 2. the arcs are the variables (one per certified pairing).
    lsa = linear_sum_assignment.SimpleLinearSumAssignment()
    arcs = {}
    for i, o in enumerate(operators):
        for j, s in enumerate(stations):
            c = o.get(s)
            if c is None or c != c:
                continue
            arcs[i, j] = lsa.add_arc_with_cost(i, j, int(round(c)))
    # spare operators get a dummy "off station" at zero cost so the problem stays square
    for i in range(len(operators)):
        for d in range(len(operators) - len(stations)):
            lsa.add_arc_with_cost(i, len(stations) + d, 0)

    # 3.–5. One per row and column is built in; solve.
    status = lsa.solve()
    if status != lsa.OPTIMAL:
        return Solution("infeasible", None, "No full staffing exists: some station has no certified operator left.",
                        ["Certify another operator for the station with the fewest options."])

    # 6. Read the matching.
    rows, total = [], lsa.optimal_cost()
    for i, o in enumerate(operators):
        j = lsa.right_mate(i)
        if j < len(stations):
            rows.append({"operator": o["operator"], "station": stations[j], "rework min/shift": o[stations[j]]})
        else:
            rows.append({"operator": o["operator"], "station": "— (not needed)", "rework min/shift": 0})
    staffed = [r for r in rows if not r["station"].startswith("—")]
    best = min(staffed, key=lambda r: r["rework min/shift"])
    free = [r["operator"] for r in rows if r["station"].startswith("—")]
    bullets = [f"**{num(total)} minutes of rework a shift** in total, "
               f"{total / len(stations):.0f} per station on average.",
               f"Best fit: {best['operator']} on {best['station']} ({best['rework min/shift']} min)."]
    if free:
        bullets.append(f"{', '.join(free)} {'stays' if len(free) == 1 else 'stay'} free for the late shift or as a floater.")
    return Solution("optimal", float(total),
                    "; ".join(f"{r['operator']} → {r['station']}" for r in staffed) + ".",
                    bullets, {"assignment": rows}, solver="LinearSumAssignment",
                    extra={"match": {r["operator"]: r["station"] for r in staffed}})
