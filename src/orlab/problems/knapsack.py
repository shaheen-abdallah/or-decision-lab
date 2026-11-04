r"""Knapsack: which improvement projects fit this year's budget
(0-1 knapsack, OR-Tools `KnapsackSolver`, branch and bound).

**Decide** $x_p \in \{0, 1\}$: project $p$ is funded.

$$\max \sum_p g_p\, x_p \qquad g_p = \text{€ saved per week by project } p$$
$$\sum_p c_p\, x_p \le B \qquad\text{(the one-off costs } c_p \text{ fit the budget } B)$$

The greedy rule "best gain per euro first" is a good start but not always optimal: the last
project it picks may leave money on the table that two smaller ones would use. Branch and bound
tries the promising combinations and proves the best one; the solver works on integers, so costs
are in thousands of euros and gains in euros a week.
"""

from ortools.algorithms.python import knapsack_solver

from orlab.core import Solution, eur

EXAMPLE = {
    "projects": [
        {"project": "Second paint robot programme",         "cost k€": 180, "gain €/week": 9_000},
        {"project": "Automated screwing in cockpit module", "cost k€": 95,  "gain €/week": 4_200},
        {"project": "Andon boards on the trim line",        "cost k€": 25,  "gain €/week": 1_300},
        {"project": "Predictive maintenance, body shop",    "cost k€": 140, "gain €/week": 6_100},
        {"project": "Kitting carts for wiring",             "cost k€": 40,  "gain €/week": 2_200},
        {"project": "AGVs for seat delivery",               "cost k€": 160, "gain €/week": 6_600},
        {"project": "Paint inspection camera",              "cost k€": 70,  "gain €/week": 3_500},
        {"project": "Operator cross-training",              "cost k€": 30,  "gain €/week": 1_400},
    ],
    "budget": [{"budget k€": 400}],
}


def explain(data):
    return {
        "decide": f"Which of the {len(data['projects'])} projects to fund this year (yes or no each).",
        "goal": "The largest total saving per week.",
        "limits": [f"The one-off costs must fit the budget of {eur(data['budget'][0]['budget k€'] * 1000)}",
                   "A project is funded in full or not at all"],
    }


def solve(data):
    projects, budget = data["projects"], int(data["budget"][0]["budget k€"])
    gains = [int(round(p["gain €/week"])) for p in projects]
    costs = [[int(round(p["cost k€"])) for p in projects]]

    # 1. Declare the solver (branch and bound, exact).
    solver = knapsack_solver.KnapsackSolver(
        knapsack_solver.SolverType.KNAPSACK_MULTIDIMENSION_BRANCH_AND_BOUND_SOLVER, "projects")
    # 2.-4. Items are the variables; the single capacity is the constraint; value is the objective.
    solver.init(gains, costs, [budget])
    # 5. Solve.
    total = solver.solve()
    # 6. Read back.
    chosen = [i for i in range(len(projects)) if solver.best_solution_contains(i)]
    spent = sum(costs[0][i] for i in chosen)
    rows = [{"project": p["project"], "cost k€": p["cost k€"], "gain €/week": p["gain €/week"],
             "€/week per k€": round(p["gain €/week"] / p["cost k€"], 1), "funded": i in chosen}
            for i, p in enumerate(projects)]
    if not chosen:
        return Solution("infeasible", 0.0, "Nothing fits the budget.", ["Raise the budget or split a project."],
                        {"projects": rows})

    # The greedy answer, for the bullet that explains why a solver was needed.
    greedy, left = [], budget
    for i in sorted(range(len(projects)), key=lambda i: -gains[i] / costs[0][i]):
        if costs[0][i] <= left:
            greedy.append(i); left -= costs[0][i]
    greedy_gain = sum(gains[i] for i in greedy)
    skipped = [rows[i]["project"] for i in range(len(projects)) if i not in chosen]
    bullets = [f"**{eur(total)} a week** ({eur(total * 48)} a year) for {eur(spent * 1000)} of the "
               f"{eur(budget * 1000)} budget; payback {spent * 1000 / total:.0f} weeks.",
               (f"Greedy 'best gain per euro first' gets {eur(greedy_gain)}: the solver finds "
                f"{eur(total - greedy_gain)} more." if total > greedy_gain
                else "Here the greedy rule 'best gain per euro first' happens to find the same set."),
               f"Left out: {', '.join(skipped) if skipped else 'nothing'}; {eur((budget - spent) * 1000)} unspent."]
    return Solution("optimal", float(total),
                    f"Fund {len(chosen)} projects: " + "; ".join(rows[i]["project"] for i in chosen) + ".",
                    bullets, {"projects": rows}, solver="KnapsackSolver",
                    extra={"chosen": [rows[i]["project"] for i in chosen], "spent": spent, "budget": budget})
