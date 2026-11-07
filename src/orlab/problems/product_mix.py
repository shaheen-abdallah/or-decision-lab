r"""Product mix: how many cars of each model to build this week (linear program, GLOP).

**Decide** $x_p \ge 0$: cars of product $p$ built per week.

**Maximise** the contribution margin
$$\max \sum_p m_p\, x_p$$

**Subject to**, for every station $s$ with $h_s$ available hours and $t_{sp}$ minutes per car:
$$\sum_p \frac{t_{sp}}{60}\, x_p \le h_s \qquad\text{(station hours)}$$
$$d^{\min}_p \le x_p \le d^{\max}_p \qquad\text{(fleet contracts, what sales can sell)}$$

The dual value $y_s$ of a station's hours is what one more hour there is worth in margin
per week (its shadow price); it is zero at stations with spare hours. Cars are continuous
in the LP and rounded for the plan, which is fine at hundreds of cars a week.
"""

from ortools.linear_solver import pywraplp

from orlab.core import Solution, eur, num

EXAMPLE = {
    "products": [
        {"product": "Sedan", "margin": 2300, "min": 120, "max": 600},
        {"product": "SUV", "margin": 3400, "min": 80, "max": 600},
    ],
    # hours = units x 2 shifts x 8 h x 5 days x 90 % availability; minutes per car by product
    "stations": [
        {"station": "Body welding", "hours": 144, "Sedan": 7.5, "SUV": 9.0},
        {"station": "SUV underbody reinforcement", "hours": 72, "Sedan": 0.0, "SUV": 5.0},
        {"station": "Paint shop", "hours": 144, "Sedan": 9.0, "SUV": 11.0},
        {"station": "Paint inspection", "hours": 72, "Sedan": 3.5, "SUV": 4.5},
        {"station": "Wiring harness", "hours": 144, "Sedan": 8.5, "SUV": 10.5},
        {"station": "Interior trim", "hours": 216, "Sedan": 12.5, "SUV": 14.5},
        {"station": "Powertrain marriage", "hours": 144, "Sedan": 7.0, "SUV": 9.0},
        {"station": "Final assembly", "hours": 144, "Sedan": 8.0, "SUV": 9.0},
        {"station": "End-of-line test", "hours": 72, "Sedan": 3.5, "SUV": 4.0},
        {"station": "SUV off-road calibration", "hours": 72, "Sedan": 0.0, "SUV": 8.0},
    ],
}


def explain(data):
    products = [p["product"] for p in data["products"]]
    return {
        "decide": f"How many {', '.join(products)} to build per week.",
        "goal": "The highest total contribution margin (margin per car × cars).",
        "limits": [f"{s['station']}: at most {num(s['hours'])} hours a week" for s in data["stations"]]
                  + [f"{p['product']}: between {num(p['min'])} (contracts) and {num(p['max'])} (demand)"
                     for p in data["products"]],
    }


def solve(data):
    products, stations = data["products"], data["stations"]

    # 1. Declare the solver: GLOP, Google's LP solver.
    solver = pywraplp.Solver.CreateSolver("GLOP")

    # 2. Variables: cars per week of each product, between contracts and demand.
    x = {p["product"]: solver.NumVar(float(p["min"]), float(p["max"]), p["product"]) for p in products}

    # 3. Constraints: every station's hours.
    hours = {}
    for s in stations:
        ct = solver.Constraint(-solver.infinity(), float(s["hours"]), s["station"])
        for p in products:
            ct.SetCoefficient(x[p["product"]], float(s[p["product"]]) / 60)
        hours[s["station"]] = ct

    # 4. Objective: total margin.
    solver.Maximize(sum(float(p["margin"]) * x[p["product"]] for p in products))

    # 5. Solve.
    status = solver.Solve()
    if status != pywraplp.Solver.OPTIMAL:
        return Solution("infeasible", None,
                        "No weekly plan meets the fleet contracts within the station hours.",
                        ["Lower a contract minimum or add hours at the station in red."], solver="GLOP")

    # 6. Read the solution: the plan, how loaded each station is, what an extra hour is worth.
    plan = {p: round(v.solution_value()) for p, v in x.items()}
    margin = solver.Objective().Value()
    rows, bottlenecks, spare = [], [], []
    for s in stations:
        used = sum(float(s[p]) / 60 * x[p].solution_value() for p in plan)
        dual = hours[s["station"]].dual_value()
        load = used / float(s["hours"]) if s["hours"] else 0
        rows.append({"station": s["station"], "hours used": round(used, 1), "hours available": s["hours"],
                     "load": round(load, 3), "value of one more hour": round(dual)})
        (bottlenecks if dual > 1e-6 else spare).append((s["station"], dual, float(s["hours"]) - used))
    plan_rows = [{"product": p["product"], "cars per week": plan[p["product"]], "margin per car": p["margin"],
                  "margin": plan[p["product"]] * p["margin"], "demand cap": p["max"]} for p in products]

    bullets = []
    if bottlenecks:
        b = max(bottlenecks, key=lambda t: t[1])
        bullets.append(f"**{b[0]} is the bottleneck.** One more hour there is worth {eur(b[1])} a week"
                       + (f"; {', '.join(others)} also {'runs' if len(others) == 1 else 'run'} full."
                          if (others := [n for n, _, _ in bottlenecks if n != b[0]]) else "."))
    if spare:
        most = max(spare, key=lambda t: t[2])
        bullets.append(f"{len(spare)} stations have spare hours; {most[0]} has the most ({num(most[2], 1)} h).")
    capped = [p["product"] for p in products if plan[p["product"]] >= p["max"]]
    if capped:
        bullets.append(f"{', '.join(capped)} hit the demand cap: selling more would pay before adding capacity.")
    headline = (f"Build {' + '.join(f'{num(plan[p])} {p}s' for p in plan)} a week for "
                f"{eur(margin / 1e6, 2)} M contribution margin.")
    return Solution("optimal", margin, headline, bullets, {"plan": plan_rows, "stations": rows},
                    solver="GLOP", extra={"plan": plan, "bottlenecks": [n for n, _, _ in bottlenecks]})
