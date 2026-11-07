r"""Shift scheduling: who works which shift next week
(employee scheduling with coverage, rest and fairness rules, CP-SAT).

**Decide** $x_{ods} \in \{0, 1\}$: operator $o$ works shift $s$ on day $d$.

$$\min \sum_{(o,d) \in R} \sum_s x_{ods} \qquad R = \text{the days-off requests}$$
$$\sum_o x_{ods} = n_{ds} \quad \forall d, s \qquad\text{(every shift has the crew it needs)}$$
$$\sum_s x_{ods} \le 1 \quad \forall o, d \qquad\text{(one shift a day)}$$
$$x_{o,d,\text{late}} + x_{o,d+1,\text{early}} \le 1 \quad \forall o, d \qquad\text{(a late shift is never followed by an early one: 11 h rest)}$$
$$\underline{m}_o \le \sum_{d,s} x_{ods} \le \overline{m}_o, \qquad \sum_d x_{o,d,\text{late}} \le \overline{l}_o \quad \forall o$$

Every rule is a logical statement about yes/no decisions, which is what constraint programming
is for: CP-SAT propagates them and proves the schedule with the fewest broken requests optimal.
"""

from ortools.sat.python import cp_model

from orlab.core import Solution

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
SHIFTS = ["early", "late"]

EXAMPLE = {
    "operators": [
        {"operator": "Amal",   "min shifts": 3, "max shifts": 4, "max late": 2, "days off wanted": "Fri"},
        {"operator": "Bekir",  "min shifts": 3, "max shifts": 4, "max late": 2, "days off wanted": "Mon, Tue"},
        {"operator": "Clara",  "min shifts": 3, "max shifts": 4, "max late": 2, "days off wanted": ""},
        {"operator": "Dmitri", "min shifts": 3, "max shifts": 4, "max late": 2, "days off wanted": "Wed"},
        {"operator": "Elif",   "min shifts": 3, "max shifts": 4, "max late": 2, "days off wanted": "Fri"},
        {"operator": "Farid",  "min shifts": 3, "max shifts": 4, "max late": 2, "days off wanted": "Thu"},
        {"operator": "Gül",    "min shifts": 3, "max shifts": 4, "max late": 2, "days off wanted": "Fri"},
    ],
    # operators needed on the skilled stations per shift and day
    "demand": [{"shift": "early", "Mon": 3, "Tue": 3, "Wed": 3, "Thu": 3, "Fri": 3},
               {"shift": "late",  "Mon": 2, "Tue": 2, "Wed": 2, "Thu": 2, "Fri": 2}],
}


def _days(data):
    return [d for d in data["demand"][0] if d != "shift"]


def _requests(op):
    return [d.strip() for d in str(op.get("days off wanted") or "").split(",") if d.strip()]


def explain(data):
    days = _days(data)
    need = sum(int(r[d]) for r in data["demand"] for d in days)
    return {
        "decide": f"For each of the {len(data['operators'])} operators, which of the {len(days) * 2} shifts they work.",
        "goal": "As few broken days-off requests as possible.",
        "limits": [f"Coverage: {need} operator-shifts are needed over the week",
                   "One shift a day; never a late shift followed by an early one (11 h rest)",
                   "Each operator's minimum and maximum shifts, and a cap on late shifts"],
    }


def solve(data):
    ops, days = data["operators"], _days(data)
    demand = {(r["shift"], d): int(r[d]) for r in data["demand"] for d in days}
    need, can = sum(demand.values()), sum(int(o["max shifts"]) for o in ops)
    if need > can:
        return Solution("infeasible", None, f"{need} operator-shifts needed but the team can give at most {can}.",
                        ["Hire, allow more shifts per person, or lower the demand."])
    for d in days:                                    # one shift a day: a day can't need more people than the team
        if sum(demand[s, d] for s in SHIFTS) > len(ops):
            return Solution("infeasible", None,
                            f"{d} needs {sum(demand[s, d] for s in SHIFTS)} operators but the team has {len(ops)}.",
                            ["Each operator works at most one shift a day: lower that day's demand or add an operator."])
    late_need, late_can = sum(demand["late", d] for d in days), sum(int(o["max late"]) for o in ops)
    if late_need > late_can:
        return Solution("infeasible", None, f"{late_need} late shifts needed but the late-shift caps allow {late_can}.",
                        ["Raise someone's 'max late' or lower the late-shift demand."])

    # 1. Declare the model.
    m = cp_model.CpModel()
    # 2. Variables.
    x = {(o["operator"], d, s): m.NewBoolVar(f"x_{o['operator']}_{d}_{s}") for o in ops for d in days for s in SHIFTS}
    # 3. Constraints.
    for d in days:
        for s in SHIFTS:
            m.Add(sum(x[o["operator"], d, s] for o in ops) == demand[s, d])
    for o in ops:
        name = o["operator"]
        for i, d in enumerate(days):
            m.Add(sum(x[name, d, s] for s in SHIFTS) <= 1)
            if i + 1 < len(days):
                m.Add(x[name, d, "late"] + x[name, days[i + 1], "early"] <= 1)
        total = sum(x[name, d, s] for d in days for s in SHIFTS)
        m.Add(total >= int(o["min shifts"]))
        m.Add(total <= int(o["max shifts"]))
        m.Add(sum(x[name, d, "late"] for d in days) <= int(o["max late"]))
    # 4. Objective: broken days-off requests.
    broken = [x[o["operator"], d, s] for o in ops for d in _requests(o) if d in days for s in SHIFTS]
    m.Minimize(sum(broken))
    # 5. Solve.
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Solution("infeasible", None, "No schedule satisfies every rule.",
                        ["Every day has enough people, so the rest rule (no late shift before an early one) "
                         "or the minimum / maximum shifts per person bite: relax one and re-solve."])
    # 6. Read back.
    rows, late_counts = [], {}
    for o in ops:
        name = o["operator"]
        row = {"operator": name}
        for d in days:
            row[d] = next((s for s in SHIFTS if solver.Value(x[name, d, s])), "–")
        row["shifts"] = sum(v in SHIFTS for v in row.values())
        late_counts[name] = sum(v == "late" for v in row.values())
        rows.append(row)
    missed = [(o["operator"], d) for o in ops for d in _requests(o) if d in days
              if any(solver.Value(x[o["operator"], d, s]) for s in SHIFTS)]
    n_req = sum(len([d for d in _requests(o) if d in days]) for o in ops)
    bullets = [f"**{len(missed)} of {n_req} days-off requests broken**"
               + (": " + ", ".join(f"{o} works {d}" for o, d in missed) if missed else "") + ".",
               f"{need} shifts spread over {len(ops)} operators: "
               f"{min(r['shifts'] for r in rows)}–{max(r['shifts'] for r in rows)} shifts each, "
               f"at most {max(late_counts.values())} late shifts.",
               f"Status: {'proven optimal' if status == cp_model.OPTIMAL else 'feasible, not proven optimal'} "
               f"in {solver.WallTime():.2f} s."]
    return Solution("optimal" if status == cp_model.OPTIMAL else "feasible", float(len(missed)),
                    f"{len(missed)} broken request{'s' if len(missed) != 1 else ''} for {need} shifts.",
                    bullets, {"roster": rows}, solver="CP-SAT",
                    extra={"missed": missed, "days": days})
