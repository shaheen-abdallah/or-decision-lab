r"""Job shop: in what order should the car batches go through the paint shop
(job shop scheduling, minimum makespan, CP-SAT with interval variables).

**Decide** start times $s_{bk}$ of batch $b$ on station $k$ (an interval of fixed length $p_{bk}$),
and the makespan $C$.

$$\min C$$
$$s_{b,k+1} \ge s_{bk} + p_{bk} \quad \forall b, k \qquad\text{(a batch visits the stations in order)}$$
$$\text{NoOverlap}\{[s_{bk}, s_{bk} + p_{bk}) : b\} \quad \forall k \qquad\text{(a station holds one batch at a time)}$$
$$C \ge s_{bK} + p_{bK} \quad \forall b$$

In a MIP the "one at a time" rule needs big-M disjunctions; CP-SAT has interval variables and
a `NoOverlap` constraint built in and finds the optimal sequence by propagation and search.
"""

from ortools.sat.python import cp_model

from orlab.core import Solution

EXAMPLE = {
    # minutes per batch at each paint-shop station, visited in this column order (0 = skipped)
    "batches": [
        {"batch": "Sedan, white (6 cars)",  "Pre-treatment": 40, "Paint booth": 55, "Curing oven": 45},
        {"batch": "SUV, black (4 cars)",    "Pre-treatment": 35, "Paint booth": 60, "Curing oven": 45},
        {"batch": "Sedan, red (3 cars)",    "Pre-treatment": 20, "Paint booth": 50, "Curing oven": 30},
        {"batch": "SUV, silver (5 cars)",   "Pre-treatment": 45, "Paint booth": 65, "Curing oven": 50},
        {"batch": "Rework (2 cars)",        "Pre-treatment": 0,  "Paint booth": 25, "Curing oven": 30},
    ],
}


def _stations(data):
    return [k for k in data["batches"][0] if k != "batch"]


def explain(data):
    return {
        "decide": f"When each of the {len(data['batches'])} batches starts at each of the "
                  f"{len(_stations(data))} stations.",
        "goal": "The shortest time until the last batch leaves the oven (the makespan).",
        "limits": ["A batch visits the stations in order and cannot start a step before the previous one ends",
                   "A station handles one batch at a time",
                   "Processing times are fixed"],
    }


def solve(data):
    batches, stations = data["batches"], _stations(data)
    horizon = int(sum(int(b[k] or 0) for b in batches for k in stations))
    # 1. Declare the model.
    m = cp_model.CpModel()
    # 2. Variables: one interval per (batch, station) step.
    start, end, interval = {}, {}, {}
    for b in batches:
        for k in stations:
            p = int(b[k] or 0)
            start[b["batch"], k] = m.NewIntVar(0, horizon, f"s_{b['batch']}_{k}")
            end[b["batch"], k] = m.NewIntVar(0, horizon, f"e_{b['batch']}_{k}")
            interval[b["batch"], k] = m.NewIntervalVar(start[b["batch"], k], p, end[b["batch"], k], f"i_{b['batch']}_{k}")
    makespan = m.NewIntVar(0, horizon, "makespan")
    # 3. Constraints.
    for b in batches:
        for k1, k2 in zip(stations, stations[1:]):
            m.Add(start[b["batch"], k2] >= end[b["batch"], k1])
        m.Add(makespan >= end[b["batch"], stations[-1]])
    for k in stations:
        m.AddNoOverlap([interval[b["batch"], k] for b in batches if int(b[k] or 0) > 0])
    # 4. Objective.
    m.Minimize(makespan)
    # 5. Solve.
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Solution("error", None, "No schedule found.", [])
    # 6. Read back the Gantt rows.
    rows = [{"batch": b["batch"], "station": k, "start": solver.Value(start[b["batch"], k]),
             "end": solver.Value(end[b["batch"], k]), "minutes": int(b[k] or 0)}
            for b in batches for k in stations if int(b[k] or 0) > 0]
    total = solver.Value(makespan)
    busiest = max(stations, key=lambda k: sum(int(b[k] or 0) for b in batches))
    work = sum(int(b[busiest] or 0) for b in batches)
    first = [r["batch"] for r in sorted(rows, key=lambda r: r["start"]) if r["station"] == stations[0]][:1]
    order = [r["batch"] for r in sorted((r for r in rows if r["station"] == busiest), key=lambda r: r["start"])]
    bullets = [f"**Makespan {total} min** ({total / 60:.1f} h); the {busiest} is busy {work} min of it, "
               f"so no schedule can beat {work} min.",
               f"Order at the {busiest}: " + " → ".join(order) + ".",
               f"Status: {'proven optimal' if status == cp_model.OPTIMAL else 'feasible'} in {solver.WallTime():.2f} s"
               + (f"; start with {first[0]}." if first else ".")]
    return Solution("optimal" if status == cp_model.OPTIMAL else "feasible", float(total),
                    f"All batches done in {total} minutes.", bullets, {"schedule": rows}, solver="CP-SAT",
                    extra={"stations": stations, "lower_bound": work})
