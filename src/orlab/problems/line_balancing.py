r"""Line balancing: how few stations does the wiring-and-trim line need at the planned takt
(SALBP-1, a mixed-integer program solved by SCIP through OR-Tools' linear solver wrapper).

**Decide** $x_{ik} \in \{0, 1\}$: task $i$ is done at station $k$; $y_k \in \{0, 1\}$: station $k$ is used.

$$\min \sum_k y_k$$
$$\sum_k x_{ik} = 1 \quad \forall i \qquad\text{(every task goes to exactly one station)}$$
$$\sum_i t_i\, x_{ik} \le c\, y_k \quad \forall k \qquad\text{(a station's work fits the cycle time } c)$$
$$\sum_k k\, x_{ik} \le \sum_k k\, x_{jk} \quad \forall\, i \prec j \qquad\text{(a task is never ahead of its predecessor)}$$
$$y_k \ge y_{k+1} \qquad\text{(use stations 1, 2, 3 … without gaps)}$$

A second solve keeps that number of stations and minimises the busiest station's load $L$
($\sum_i t_i x_{ik} \le L$), so the work is spread evenly instead of piled on the first stations.
The lower bound $\lceil \sum_i t_i / c \rceil$ says how far from perfect the answer can be.
"""

import math

from ortools.linear_solver import pywraplp

from orlab.core import Solution

EXAMPLE = {
    # seconds per car: average of the Sedan and SUV times at the planned 60/40 mix
    "tasks": [
        {"id": "T01", "task": "Remove doors",                 "seconds": 52,  "after": ""},
        {"id": "T02", "task": "Floor wiring harness",         "seconds": 132, "after": "T01"},
        {"id": "T03", "task": "Cockpit wiring harness",       "seconds": 108, "after": "T01"},
        {"id": "T04", "task": "Roof harness and antenna",     "seconds": 66,  "after": "T01"},
        {"id": "T05", "task": "Rear wiring and tail lights",  "seconds": 86,  "after": "T02"},
        {"id": "T06", "task": "Engine-bay harness",           "seconds": 112, "after": "T02"},
        {"id": "T07", "task": "Sound insulation",             "seconds": 64,  "after": "T02"},
        {"id": "T08", "task": "Carpet",                       "seconds": 74,  "after": "T07"},
        {"id": "T09", "task": "Headliner",                    "seconds": 84,  "after": "T04"},
        {"id": "T10", "task": "Cockpit module",               "seconds": 154, "after": "T03"},
        {"id": "T11", "task": "Steering column",              "seconds": 52,  "after": "T10"},
        {"id": "T12", "task": "Centre console",               "seconds": 64,  "after": "T10, T08"},
        {"id": "T13", "task": "Front seats",                  "seconds": 94,  "after": "T12"},
        {"id": "T14", "task": "Rear seats",                   "seconds": 68,  "after": "T08"},
        {"id": "T15", "task": "Door trim panels",             "seconds": 84,  "after": "T01"},
        {"id": "T16", "task": "Refit doors",                  "seconds": 64,  "after": "T15, T05, T06, T09, T11, T13, T14"},
    ],
    "line": [{"cycle time (s)": 330}],   # one car leaves the line every 330 s (about 170 cars a day)
}


def _read(data):
    tasks = [t["id"] for t in data["tasks"]]
    times = {t["id"]: float(t["seconds"]) for t in data["tasks"]}
    pred = {t["id"]: [p.strip() for p in str(t.get("after") or "").split(",") if p.strip()]
            for t in data["tasks"]}
    cycle = float(data["line"][0]["cycle time (s)"])
    return tasks, times, pred, cycle


def explain(data):
    tasks, times, pred, cycle = _read(data)
    return {
        "decide": f"Which of the {len(tasks)} tasks each station does, and how many stations the line has.",
        "goal": "The fewest stations; among those, the most even workload.",
        "limits": [f"A station's tasks must fit the cycle time of {cycle:.0f} s",
                   f"Precedence: {sum(len(v) for v in pred.values())} 'A before B' rules "
                   "(you cannot fit the seats before the carpet)",
                   "Every task is done exactly once"],
    }


def _balance(tasks, times, pred, cycle, n_stations, smooth):
    """One MIP. smooth=False: minimise the number of stations used out of n_stations.
    smooth=True: use exactly n_stations and minimise the busiest station's load."""
    # 1. Declare the solver.
    solver = pywraplp.Solver.CreateSolver("SCIP")
    stations = range(1, n_stations + 1)

    # 2. Variables.
    x = {(i, k): solver.BoolVar(f"x_{i}_{k}") for i in tasks for k in stations}
    y = {k: solver.BoolVar(f"y_{k}") for k in stations}
    load = solver.NumVar(0, cycle, "busiest")

    # 3. Constraints.
    for i in tasks:
        solver.Add(sum(x[i, k] for k in stations) == 1)
    for k in stations:
        solver.Add(sum(times[i] * x[i, k] for i in tasks) <= cycle * y[k])
        solver.Add(sum(times[i] * x[i, k] for i in tasks) <= load)
        if k + 1 in y:
            solver.Add(y[k] >= y[k + 1])
    for j in tasks:
        for i in pred[j]:
            solver.Add(sum(k * x[i, k] for k in stations) <= sum(k * x[j, k] for k in stations))

    # 4. Objective.
    if smooth:
        solver.Add(sum(y[k] for k in stations) == n_stations)
        solver.Minimize(load)
    else:
        solver.Minimize(sum(y[k] for k in stations))

    # 5. Solve.
    status = solver.Solve()
    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return None
    # 6. Read back: tasks per station in line order.
    used = [k for k in stations if y[k].solution_value() > 0.5]
    return [[i for i in tasks if x[i, k].solution_value() > 0.5] for k in used]


def solve(data):
    tasks, times, pred, cycle = _read(data)
    unknown = sorted({p for ps in pred.values() for p in ps} - set(tasks))
    if unknown:
        return Solution("error", None, f"Unknown task id in 'after': {', '.join(unknown)}.",
                        ["Use the ids from the id column."])
    total = sum(times.values())
    lower = math.ceil(total / cycle - 1e-9)
    too_long = [i for i in tasks if times[i] > cycle]
    if too_long:
        return Solution("infeasible", None,
                        f"No balance possible: {', '.join(too_long)} alone take longer than the {cycle:.0f} s cycle.",
                        ["Split the task or slow the line down."])

    plan = _balance(tasks, times, pred, cycle, len(tasks), smooth=False)     # one task per station always fits
    if plan is None:
        return Solution("infeasible", None, "No balance found (check the precedence rules for a cycle).", [])
    plan = _balance(tasks, times, pred, cycle, len(plan), smooth=True) or plan

    names = {t["id"]: t["task"] for t in data["tasks"]}
    rows = [{"station": f"Station {k}", "tasks": ", ".join(names[i] for i in grp),
             "load (s)": sum(times[i] for i in grp), "of cycle": sum(times[i] for i in grp) / cycle}
            for k, grp in enumerate(plan, start=1)]
    n = len(plan)
    busiest = max(r["load (s)"] for r in rows)
    efficiency = total / (n * cycle)
    bullets = [f"**{n} stations** for {total:.0f} s of work at a {cycle:.0f} s takt: the lower bound "
               f"⌈{total:.0f} / {cycle:.0f}⌉ = {lower} is {'reached' if n == lower else 'not reached: precedence rules cost ' + str(n - lower) + ' station' + ('s' if n - lower > 1 else '')}.",
               f"Line efficiency **{efficiency:.0%}**: the average station waits {(1 - efficiency) * cycle:.0f} s per car.",
               f"Busiest station carries {busiest:.0f} s ({busiest / cycle:.0%} of the cycle); "
               f"the line could run at a {busiest:.0f} s takt with the same stations."]
    return Solution("optimal", float(n), f"{n} stations, {efficiency:.0%} line efficiency.", bullets,
                    {"stations": rows}, solver="SCIP (MIP)",
                    extra={"assignment": {i: k for k, grp in enumerate(plan, start=1) for i in grp},
                           "lower_bound": lower, "cycle": cycle, "busiest": busiest})
