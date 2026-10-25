"""Production mix (LP): how many cars of each model to build per week.

    max   sum_p margin[p] * x[p]
    s.t.  sum_p minutes[s][p] * x[p] <= capacity[s]    every station s (minutes per week)
          x[p] >= demand_min[p]                         fleet contracts
          x[p] <= demand_max[p]                         what sales can sell
          x[p] >= 0

The shadow price (dual value) of a station constraint is the extra weekly margin
from one more minute at that station. CPLEX's sensitivity ranging says how many
extra minutes that price holds before another constraint takes over.
"""

import math
from dataclasses import dataclass

from docplex.mp.model import Model

from plantlab.optimize.report import eur, pct, table
from plantlab.plant import available_minutes_per_unit, load_plant

INF = 1e20  # CPLEX's "no limit"


@dataclass
class StationResult:
    name: str
    used_min: float
    capacity_min: float
    shadow_price_per_h: float   # extra weekly margin from one more hour at the station
    extra_hours_valid: float    # how many extra hours that shadow price holds
    overtime_eur_per_h: float | None

    @property
    def utilisation(self):
        return self.used_min / self.capacity_min if self.capacity_min else 0.0

    @property
    def binding(self):
        return self.capacity_min - self.used_min < 1e-6


@dataclass
class MixResult:
    status: str
    plan: dict            # product -> cars per week
    margin: float         # weekly contribution margin
    stations: dict        # station -> StationResult
    demand_value: dict    # product -> € per extra car of demand (max) or per car of contract (min)
    margin_range: dict    # product -> (low, high) margin per car that keeps this plan
    names: dict
    summary: str = ""

    def report(self):
        if not self.plan:
            return self.summary
        rows = [[s.name, f"{s.used_min:,.0f}", f"{s.capacity_min:,.0f}", pct(s.utilisation),
                 eur(s.shadow_price_per_h) if s.binding else "-"]
                for s in self.stations.values()]
        return (table(["Station", "Used min", "Capacity", "Load", "€ per extra h"], rows)
                + "\n\n" + self.summary)


def solve(products, stations, margin, minutes, capacity, demand_min, demand_max,
          names=None, overtime_eur_per_h=None):
    names = names or {}
    overtime_eur_per_h = overtime_eur_per_h or {}

    m = Model('production_mix')

    x = m.continuous_var_dict(products, name='x')

    m.maximize(m.sum(margin[p] * x[p] for p in products))

    cap = {s: m.add_constraint(m.sum(minutes[s][p] * x[p] for p in products) <= capacity[s],
                               ctname=f'capacity_{s}')
           for s in stations}
    dmin = {p: m.add_constraint(x[p] >= demand_min[p], ctname=f'contract_{p}') for p in products}
    dmax = {p: m.add_constraint(x[p] <= demand_max[p], ctname=f'sales_{p}') for p in products}

    sol = m.solve()
    if sol is None:
        return MixResult(status=str(m.solve_details.status), plan={}, margin=0.0, stations={},
                         demand_value={}, margin_range={}, names=names,
                         summary="No weekly plan fits: the fleet contracts need more capacity "
                                 "than the stations have.")

    sens = m.get_cplex().solution.sensitivity
    rhs_range = dict(zip(stations, sens.rhs([cap[s].index for s in stations])))
    obj_range = dict(zip(products, sens.objective([x[p].index for p in products])))

    station_results = {}
    for s in stations:
        high = rhs_range[s][1]
        station_results[s] = StationResult(
            name=names.get(s, s),
            used_min=capacity[s] - cap[s].slack_value,
            capacity_min=capacity[s],
            shadow_price_per_h=cap[s].dual_value * 60,
            extra_hours_valid=math.inf if high >= INF else (high - capacity[s]) / 60,
            overtime_eur_per_h=overtime_eur_per_h.get(s),
        )

    # a binding sales cap has a positive dual (more demand = more margin);
    # a binding contract has a negative one (forced cars cost margin)
    demand_value = {p: dmax[p].dual_value + dmin[p].dual_value for p in products}

    result = MixResult(
        status=str(m.solve_details.status),
        plan={p: x[p].solution_value for p in products},
        margin=sol.objective_value,
        stations=station_results,
        demand_value=demand_value,
        margin_range={p: tuple(obj_range[p]) for p in products},
        names=names,
    )
    result.summary = summarise(result, demand_min, demand_max)
    return result


def summarise(r, demand_min, demand_max):
    n = r.names
    cars = sum(r.plan.values())
    mix = " + ".join(f"{r.plan[p]:,.0f} {n.get(p, p)}s" for p in r.plan)
    lines = [f"Best weekly plan: {mix} = {cars:,.0f} cars, contribution margin {eur(r.margin)}."]

    bottlenecks = [s for s in r.stations.values() if s.binding]
    if bottlenecks:
        lines.append("Bottlenecks (100% loaded): " + ", ".join(s.name for s in bottlenecks) + ".")
    for s in sorted(bottlenecks, key=lambda s: -s.shadow_price_per_h):
        holds = ("" if math.isinf(s.extra_hours_valid)
                 else f" for the next {s.extra_hours_valid:.1f} h")
        line = f"- {s.name}: one more hour is worth {eur(s.shadow_price_per_h)} a week{holds}."
        if s.overtime_eur_per_h is not None:
            worth = s.shadow_price_per_h > s.overtime_eur_per_h
            line += (f" Overtime costs about {eur(s.overtime_eur_per_h)}/h, so "
                     + ("overtime here pays off." if worth else "overtime here does not pay."))
        lines.append(line)

    idle = [s for s in r.stations.values() if s.capacity_min and not s.binding]
    if idle:
        most = min(idle, key=lambda s: s.utilisation)
        free_h = (most.capacity_min - most.used_min) / 60
        lines.append(f"Most spare capacity: {most.name} ({pct(most.utilisation)} loaded, "
                     f"{free_h:.0f} h free a week). Extra capacity there earns nothing.")

    for p, value in r.demand_value.items():
        name = n.get(p, p)
        if value > 1e-6:
            lines.append(f"Sales is a limit for the {name}: each extra car sold adds {eur(value)}.")
        elif value < -1e-6:
            lines.append(f"The {name} fleet contract ({demand_min[p]} cars) costs "
                         f"{eur(-value)} margin per contracted car.")
        elif r.plan[p] < demand_max[p] - 1e-6:
            lines.append(f"Sales could take {demand_max[p] - r.plan[p]:,.0f} more {name}s; "
                         f"capacity, not demand, is the limit.")

    for p, (low, high) in r.margin_range.items():
        if high >= INF:
            lines.append(f"The plan stays the same as long as the {n.get(p, p)} margin is "
                         f"above {eur(low)} per car.")
        else:
            lines.append(f"The plan stays the same while the {n.get(p, p)} margin is between "
                         f"{eur(low)} and {eur(high)} per car.")
    return "\n".join(lines)


def solve_plant(plant=None):
    plant = plant or load_plant()
    products = list(plant["products"])
    stations = [s["id"] for s in plant["stations"]]
    unit_minutes = available_minutes_per_unit(plant)
    by_id = {s["id"]: s for s in plant["stations"]}
    names = {s: by_id[s]["name"] for s in stations}
    names.update({p: plant["products"][p]["name"] for p in products})
    return solve(
        products=products,
        stations=stations,
        margin={p: plant["products"][p]["margin_eur"] for p in products},
        minutes={s: by_id[s]["minutes"] for s in stations},
        capacity={s: by_id[s]["units"] * unit_minutes for s in stations},
        demand_min={p: plant["products"][p]["demand_min"] for p in products},
        demand_max={p: plant["products"][p]["demand_max"] for p in products},
        names=names,
        overtime_eur_per_h={s: by_id[s]["overtime_eur_per_h"] for s in stations},
    )
