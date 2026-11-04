r"""Transportation problem: ship seat sets from suppliers to plants at the lowest freight cost
(minimum-cost flow, OR-Tools `SimpleMinCostFlow`).

**Decide** $x_{ij} \ge 0$: seat sets per week from supplier $i$ to plant $j$.

$$\min \sum_{i,j} c_{ij}\, x_{ij}$$
$$\sum_i x_{ij} = d_j \quad \forall j \qquad\text{(every plant gets what it builds)}$$
$$\sum_j x_{ij} \le s_i \quad \forall i \qquad\text{(no supplier ships more than its capacity)}$$
$$x_{ij} = 0 \quad \text{for blocked routes (supplier not approved for that plant)}$$

As a flow network: each supplier is a source node with supply $s_i$, each plant a sink with
demand $d_j$, each allowed route an arc with capacity $s_i$ and unit cost $c_{ij}$. Spare
capacity drains into an "unused" node at zero cost so the flow balances. The network
simplex solver returns integer flows directly, so no rounding is needed.
"""

from ortools.graph.python import min_cost_flow

from orlab.core import Solution, eur, num

EXAMPLE = {
    "part": "seat set",
    "suppliers": [
        {"supplier": "Saarbrücken", "capacity": 600, "Plant West": 8, "Plant East": 22, "Plant South": 18},
        {"supplier": "Plzeň", "capacity": 700, "Plant West": 19, "Plant East": 9, "Plant South": 12},
        {"supplier": "Poznań", "capacity": 500, "Plant West": 26, "Plant East": 13, "Plant South": None},
    ],  # freight cost in € per seat set; None = route not approved
    "plants": [
        {"plant": "Plant West", "demand": 840},
        {"plant": "Plant East", "demand": 450},
        {"plant": "Plant South", "demand": 300},
    ],
}


def explain(data):
    part = data.get("part", "unit")
    return {
        "decide": f"How many {part}s each supplier sends to each plant per week.",
        "goal": "The lowest total freight bill.",
        "limits": [f"{p['plant']} needs {num(p['demand'])} {part}s" for p in data["plants"]]
                  + [f"{s['supplier']} can ship at most {num(s['capacity'])}" for s in data["suppliers"]]
                  + ["Routes marked as not approved carry nothing"],
    }


def solve(data):
    suppliers, plants, part = data["suppliers"], data["plants"], data.get("part", "unit")
    supply = sum(int(s["capacity"]) for s in suppliers)
    demand = sum(int(p["demand"]) for p in plants)
    if supply < demand:
        return Solution("infeasible", None,
                        f"Suppliers can ship {num(supply)} {part}s a week but the plants need {num(demand)}: "
                        f"short by {num(demand - supply)}.",
                        ["Raise a supplier's capacity or lower a plant's demand."])

    # 1. Declare the solver and number the nodes: suppliers, plants, one "unused" sink.
    smcf = min_cost_flow.SimpleMinCostFlow()
    node = {s["supplier"]: i for i, s in enumerate(suppliers)}
    node.update({p["plant"]: len(suppliers) + j for j, p in enumerate(plants)})
    unused = len(node)

    # 2. Arcs (the variables): every approved route, plus supplier -> unused at zero cost.
    arcs = {}
    for s in suppliers:
        for p in plants:
            cost = s.get(p["plant"])
            if cost is None or cost != cost:          # None or NaN: route not approved
                continue
            arcs[s["supplier"], p["plant"]] = smcf.add_arc_with_capacity_and_unit_cost(
                node[s["supplier"]], node[p["plant"]], int(s["capacity"]), int(round(cost)))
        smcf.add_arc_with_capacity_and_unit_cost(node[s["supplier"]], unused, int(s["capacity"]), 0)

    # 3. Constraints: node balances (supplies positive, demands negative).
    for s in suppliers:
        smcf.set_node_supply(node[s["supplier"]], int(s["capacity"]))
    for p in plants:
        smcf.set_node_supply(node[p["plant"]], -int(p["demand"]))
    smcf.set_node_supply(unused, -(supply - demand))

    # 4.–5. Objective is the sum of arc costs; solve.
    status = smcf.solve()
    if status != smcf.OPTIMAL:
        return Solution("infeasible", None,
                        "No shipping plan covers every plant: an approved-route gap leaves a plant short.",
                        ["Approve another route or raise a capacity."])

    # 6. Read the flows back.
    flows = {k: smcf.flow(a) for k, a in arcs.items()}
    cost = smcf.optimal_cost()
    rows = [{"supplier": s["supplier"], **{p["plant"]: flows.get((s["supplier"], p["plant"]), 0) for p in plants},
             "shipped": sum(flows.get((s["supplier"], p["plant"]), 0) for p in plants),
             "capacity": s["capacity"]} for s in suppliers]
    for r in rows:
        r["spare"] = r["capacity"] - r["shipped"]
    used = [(k, f) for k, f in flows.items() if f > 0]
    biggest = max(used, key=lambda t: t[1])
    spare = [(r["supplier"], r["spare"]) for r in rows if r["spare"] > 0]
    bullets = [f"**{biggest[0][0]} → {biggest[0][1]}** is the main lane: {num(biggest[1])} {part}s a week.",
               f"{len(used)} of {len(arcs)} approved routes are used; the plan ships {num(demand)} {part}s "
               f"for {eur(cost / demand, 2)} each on average."]
    if spare:
        bullets.append("Spare capacity: " + ", ".join(f"{n} {num(v)}" for n, v in spare) + ".")
    return Solution("optimal", float(cost), f"Freight costs {eur(cost)} a week with {len(used)} lanes.",
                    bullets, {"flows": rows}, solver="SimpleMinCostFlow",
                    extra={"flows": {f"{i} → {j}": f for (i, j), f in flows.items()}})
