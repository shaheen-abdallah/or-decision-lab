"""Parts transportation (LP): ship seat sets from suppliers to plants at minimum freight cost.

    x[i,j] = seat sets per week from supplier i to plant j

    min   sum_ij cost[i][j] * x[i,j]
    s.t.  sum_i x[i,j] == demand[j]      every plant gets what it builds   (enough supply)
          sum_j x[i,j] <= supply[i]      no supplier ships more than it can
          x[i,j] == 0                    blocked routes (supplier not approved for that plant)

If supply is short, the roles flip: suppliers ship everything, plants get <= demand.
Dual values: a plant's demand dual is the freight cost of one more set there;
a full supplier's dual is the saving from one more set of its capacity.
"""

from dataclasses import dataclass

from docplex.mp.model import Model

from plantlab.optimize.report import eur, table
from plantlab.plant import load_plant


@dataclass
class TransportResult:
    status: str
    cost: float
    flows: dict           # (supplier, plant) -> sets per week
    spare: dict           # supplier -> unused capacity
    shortage: dict        # plant -> sets it does not get (short supply only)
    plant_marginal: dict  # plant -> freight cost of one more set there
    supplier_value: dict  # supplier -> saving from one more set of capacity
    part: str = "part"
    summary: str = ""

    def report(self):
        if not self.flows:
            return self.summary
        suppliers = list(dict.fromkeys(i for i, _ in self.flows))
        plants = list(dict.fromkeys(j for _, j in self.flows))
        rows = [[i] + [f"{self.flows[i, j]:,.0f}" for j in plants] + [f"{self.spare[i]:,.0f}"]
                for i in suppliers]
        return table(["Supplier"] + plants + ["spare"], rows) + "\n\n" + self.summary


def solve(suppliers, plants, supply, demand, cost, blocked=(), part="part"):
    m = Model('parts_transport')

    x = m.continuous_var_matrix(suppliers, plants, name='x')

    m.minimize(m.sum(x[i, j] * cost[i][j] for i in suppliers for j in plants))

    enough = sum(supply.values()) >= sum(demand.values())
    if enough:
        dem = m.add_constraints(m.sum(x[i, j] for i in suppliers) == demand[j] for j in plants)
        sup = m.add_constraints(m.sum(x[i, j] for j in plants) <= supply[i] for i in suppliers)
    else:
        dem = m.add_constraints(m.sum(x[i, j] for i in suppliers) <= demand[j] for j in plants)
        sup = m.add_constraints(m.sum(x[i, j] for j in plants) == supply[i] for i in suppliers)

    for i, j in blocked:
        m.add_constraint(x[i, j] == 0)

    sol = m.solve()
    if sol is None:
        return TransportResult(status=str(m.solve_details.status), cost=0.0, flows={}, spare={},
                               shortage={}, plant_marginal={}, supplier_value={}, part=part,
                               summary="No shipping plan works: the blocked routes leave a plant "
                                       "without enough approved suppliers.")

    flows = {(i, j): x[i, j].solution_value for i in suppliers for j in plants}
    result = TransportResult(
        status=str(m.solve_details.status),
        cost=sol.objective_value,
        flows=flows,
        spare={i: supply[i] - sum(flows[i, j] for j in plants) for i in suppliers},
        shortage={j: demand[j] - sum(flows[i, j] for i in suppliers) for j in plants},
        plant_marginal={j: ct.dual_value for j, ct in zip(plants, dem)},
        supplier_value={i: -ct.dual_value for i, ct in zip(suppliers, sup)},
        part=part,
    )
    result.summary = summarise(result, enough)
    return result


def summarise(r, enough):
    used = [f"{i} → {j} {v:,.0f}" for (i, j), v in r.flows.items() if v > 1e-6]
    lines = [f"Cheapest {r.part} flows: {eur(r.cost)} freight a week. " + "; ".join(used) + "."]
    if not enough:
        short = ", ".join(f"{j} {v:,.0f}" for j, v in r.shortage.items() if v > 1e-6)
        lines.append(f"Supply is short: plants missing {r.part}s: {short}.")
    full = [i for i, v in r.spare.items() if v < 1e-6]
    if full:
        lines.append("Full suppliers: " + ", ".join(full) + ". " + " ".join(
            f"Each extra {r.part} {i} could ship saves {eur(r.supplier_value[i])}."
            for i in full if r.supplier_value[i] > 1e-6))
    spare = [f"{i} ({v:,.0f})" for i, v in r.spare.items() if v > 1e-6]
    if spare:
        lines.append("Spare supplier capacity: " + ", ".join(spare) + ".")
    if enough:
        lines.append("One more " + r.part + " costs in freight: "
                     + ", ".join(f"{j} {eur(v)}" for j, v in r.plant_marginal.items()) + ".")
    return "\n".join(lines)


def solve_plant(plant=None, plan=None):
    """Plant West's demand is its weekly plan (one set per car); sister plants are fixed."""
    from plantlab.optimize import production_mix

    plant = plant or load_plant()
    cfg = plant["parts_transport"]
    demand = {}
    for j, d in cfg["plants"].items():
        if d["demand"] == "plan":
            if plan is None:
                plan = production_mix.solve_plant(plant).plan
            demand[j] = round(sum(plan.values()))
        else:
            demand[j] = d["demand"]
    return solve(
        suppliers=list(cfg["suppliers"]),
        plants=list(cfg["plants"]),
        supply={i: s["capacity"] for i, s in cfg["suppliers"].items()},
        demand=demand,
        cost=cfg["cost_eur"],
        blocked=[tuple(b) for b in cfg.get("blocked", [])],
        part=cfg["part"],
    )
