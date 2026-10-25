"""Line balancing (IP, SALBP-1): put the tasks of one line onto as few stations as possible.

    x[i,k] = 1 if task i is done at station k,  y[k] = 1 if station k is used

    min   sum_k y[k]
    s.t.  sum_k x[i,k] = 1                              every task gets one station
          sum_i t[i] * x[i,k] <= c * y[k]               station load fits the cycle time c
          sum_k k * x[i,k] <= sum_k k * x[j,k]          task i comes before j (i is a predecessor of j)
          y[k] >= y[k+1]                                use stations 1, 2, 3 ... without gaps

Stage 2 (smooth=True) keeps that number of stations and minimises the busiest
station's load, so the work is spread evenly instead of piled on the first stations.
"""

import math
from dataclasses import dataclass

from docplex.mp.model import Model

from plantlab.optimize.report import pct, table
from plantlab.plant import available_minutes_per_unit, load_plant


@dataclass
class BalanceResult:
    status: str
    cycle_time: float
    n_stations: int
    lower_bound: int              # ceil(total work / cycle time)
    stations: list                # [(tasks, load)] in line order
    total_work: float
    names: dict
    line: str = "Line"
    summary: str = ""

    @property
    def efficiency(self):
        return self.total_work / (self.n_stations * self.cycle_time) if self.n_stations else 0.0

    @property
    def busiest(self):
        return max(load for _, load in self.stations) if self.stations else 0.0

    def report(self):
        if not self.stations:
            return self.summary
        rows = [[f"Station {k}", ", ".join(tasks), f"{load:.0f} s", pct(load / self.cycle_time)]
                for k, (tasks, load) in enumerate(self.stations, start=1)]
        return table(["", "Tasks", "Load", "of cycle"], rows) + "\n\n" + self.summary


def solve(tasks, times, predecessors, cycle_time, smooth=True, names=None, line="Line"):
    names = names or {}
    total = sum(times[i] for i in tasks)
    lower_bound = math.ceil(total / cycle_time - 1e-9)

    too_long = [i for i in tasks if times[i] > cycle_time]
    if too_long:
        return BalanceResult(status="infeasible", cycle_time=cycle_time, n_stations=0,
                             lower_bound=lower_bound, stations=[], total_work=total, names=names,
                             line=line,
                             summary=f"No balance possible: {', '.join(too_long)} take longer "
                                     f"than the {cycle_time:.0f} s cycle time on their own.")

    stations = range(1, len(tasks) + 1)   # one task per station is always enough

    m = Model('line_balancing')

    x = m.binary_var_matrix(tasks, stations, name='x')
    y = m.binary_var_dict(stations, name='y')

    m.minimize(m.sum(y[k] for k in stations))

    m.add_constraints(m.sum(x[i, k] for k in stations) == 1 for i in tasks)
    m.add_constraints(m.sum(times[i] * x[i, k] for i in tasks) <= cycle_time * y[k]
                      for k in stations)
    m.add_constraints(m.sum(k * x[i, k] for k in stations) <= m.sum(k * x[j, k] for k in stations)
                      for j in tasks for i in predecessors.get(j, []))
    m.add_constraints(y[k] >= y[k + 1] for k in stations if k + 1 in stations)

    sol = m.solve()
    if sol is None:
        return BalanceResult(status=str(m.solve_details.status), cycle_time=cycle_time,
                             n_stations=0, lower_bound=lower_bound, stations=[], total_work=total,
                             names=names, line=line, summary="The solver found no balance.")
    n = round(sol.objective_value)

    if smooth:
        c_max = m.continuous_var(name='c_max')
        m.add_constraint(m.sum(y[k] for k in stations) <= n)
        m.add_constraints(m.sum(times[i] * x[i, k] for i in tasks) <= c_max for k in stations)
        m.minimize(c_max)
        sol = m.solve()

    plan = []
    for k in stations:
        assigned = [i for i in tasks if x[i, k].solution_value > 0.5]
        if assigned:
            plan.append((assigned, sum(times[i] for i in assigned)))

    result = BalanceResult(status=str(m.solve_details.status), cycle_time=cycle_time,
                           n_stations=len(plan), lower_bound=lower_bound, stations=plan,
                           total_work=total, names=names, line=line)
    result.summary = summarise(result)
    return result


def summarise(r):
    lines = [f"{r.line}: {r.n_stations} stations at a {r.cycle_time:.0f} s cycle time "
             f"(lower bound {r.lower_bound}), balance efficiency {pct(r.efficiency)}."]
    if r.n_stations > r.lower_bound:
        lines.append("Task order and task sizes force more stations than the total work alone "
                     "suggests.")
    idle = r.n_stations * r.cycle_time - r.total_work
    lines.append(f"Busiest station: {r.busiest:.0f} s of {r.cycle_time:.0f} s. "
                 f"Idle time: {idle:.0f} s per car across the line.")
    return "\n".join(lines)


def solve_plant(plant=None, plan=None):
    """Balance the plant's line. The cycle time is the takt of the weekly plan:
    available seconds per week / cars per week (unless plant.yaml fixes it)."""
    from plantlab.optimize import production_mix

    plant = plant or load_plant()
    if plan is None:
        plan = production_mix.solve_plant(plant).plan
    cars = sum(plan.values())
    cfg = plant["line_balancing"]
    cycle_time = cfg.get("cycle_time_s") or math.floor(available_minutes_per_unit(plant) * 60 / cars)

    tasks = [t["id"] for t in cfg["tasks"]]
    share = {p: plan[p] / cars for p in plan}
    # mixed-model line: balance on the mix-weighted average task time
    times = {t["id"]: sum(share[p] * t["seconds"][p] for p in plan) for t in cfg["tasks"]}
    predecessors = {t["id"]: t["after"] for t in cfg["tasks"]}
    names = {t["id"]: t["name"] for t in cfg["tasks"]}

    result = solve(tasks, times, predecessors, cycle_time, names=names, line=cfg["line"])
    if result.stations:
        weekly_s = available_minutes_per_unit(plant) * 60
        mix = ", ".join(f"{pct(share[p])} {plant['products'][p]['name']}" for p in plan)
        result.summary += (f"\nTakt from the weekly plan: {cars:,.0f} cars → {cycle_time:.0f} s per car. "
                           f"This balance could run up to {weekly_s / result.busiest:,.0f} cars a week "
                           f"before the busiest station limits it.\n"
                           f"Task times are mix-weighted averages ({mix}); a run of the slower "
                           f"model can still overload a station, which the simulation (phase 2) checks.")
    return result
