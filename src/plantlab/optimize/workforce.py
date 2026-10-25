"""Workforce (IP): how many operators each station needs per shift, at minimum weekly cost.

    perm[s,h], temp[s,h]   permanent / temporary operators at station s in shift h (integer)
    floaters[h]            cross-trained operators in shift h who cover any station (integer)
    cover[s,h]             share of floater time spent at station s (continuous, <= 1)

    min   sum cost_perm[h] * perm + cost_temp[h] * temp + cost_float[h] * floaters
    s.t.  perm[s,h] + temp[s,h] + cover[s,h] >= need[s,h]      every station and shift is staffed
          sum_s cover[s,h] <= floaters[h]                       floaters are shared within a shift
          temp[s,h] = 0                     at skilled stations (certified staff only)
          perm[s,h] >= 1                    every staffed station keeps one permanent owner
          temp[s,h] <= perm[s,h]            buddy rule: each temporary works next to a permanent
          sum temp <= max_share * (sum perm + sum temp + sum floaters)   works council cap

need[s,h] is a fraction of a person (workload / net shift time, plus absence).
Without floaters every station rounds up on its own; floaters pool those fractions.
"""

from dataclasses import dataclass

from docplex.mp.model import Model

from plantlab.optimize.report import eur, pct, table
from plantlab.plant import load_plant


@dataclass
class WorkforceResult:
    status: str
    cost: float
    need: dict            # (station, shift) -> people needed (fraction)
    permanent: dict       # (station, shift) -> int
    temporary: dict       # (station, shift) -> int
    floater_cover: dict   # (station, shift) -> share of a floater
    floaters: dict        # shift -> int
    names: dict
    cost_without_floaters: float | None = None
    headcount_without_floaters: int | None = None
    summary: str = ""

    @property
    def headcount(self):
        return (sum(self.permanent.values()) + sum(self.temporary.values())
                + sum(self.floaters.values()))

    def shift_headcount(self, h):
        return (sum(v for (_, hh), v in self.permanent.items() if hh == h)
                + sum(v for (_, hh), v in self.temporary.items() if hh == h) + self.floaters[h])

    @property
    def temporary_share(self):
        return sum(self.temporary.values()) / self.headcount if self.headcount else 0.0

    def report(self):
        if not self.permanent:
            return self.summary
        shifts = list(self.floaters)
        stations = list(dict.fromkeys(s for s, _ in self.need))
        rows = []
        for s in stations:
            row = [self.names.get(s, s)]
            for h in shifts:
                row += [f"{self.need[s, h]:.2f}", self.permanent[s, h], self.temporary[s, h],
                        f"{self.floater_cover[s, h]:.2f}"]
            rows.append(row)
        rows.append(["Floaters"] + sum([["", "", "", self.floaters[h]] for h in shifts], []))
        headers = ["Station"] + sum([[f"{h}: need", "perm", "temp", "float"] for h in shifts], [])
        return table(headers, rows) + "\n\n" + self.summary


def solve(stations, shifts, need, skilled, cost, shift_premium, max_temp_share,
          max_cover_per_station=1.0, allow_floaters=True, names=None, compare=True):
    names = names or {}
    keys = [(s, h) for s in stations for h in shifts]

    def weekly(kind, h):
        return cost[kind] * (1 + shift_premium.get(h, 0.0))

    m = Model('workforce')

    perm = m.integer_var_dict(keys, name='perm')
    temp = m.integer_var_dict(keys, name='temp')
    cover = m.continuous_var_dict(keys, ub=max_cover_per_station, name='cover')
    floaters = m.integer_var_dict(shifts, name='floaters')

    m.minimize(m.sum(weekly('permanent', h) * perm[s, h] + weekly('temporary', h) * temp[s, h]
                     for s, h in keys)
               + m.sum(weekly('floater', h) * floaters[h] for h in shifts))

    m.add_constraints(perm[s, h] + temp[s, h] + cover[s, h] >= need[s, h] for s, h in keys)
    m.add_constraints(m.sum(cover[s, h] for s in stations) <= floaters[h] for h in shifts)
    m.add_constraints(temp[s, h] == 0 for s, h in keys if skilled.get(s))
    m.add_constraints(perm[s, h] >= 1 for s, h in keys if need[s, h] > 0)
    m.add_constraints(temp[s, h] <= perm[s, h] for s, h in keys)
    m.add_constraint(m.sum(temp[k] for k in keys)
                     <= max_temp_share * (m.sum(perm[k] + temp[k] for k in keys)
                                          + m.sum(floaters[h] for h in shifts)))
    if not allow_floaters:
        m.add_constraints(floaters[h] == 0 for h in shifts)

    sol = m.solve()
    if sol is None:
        return WorkforceResult(status=str(m.solve_details.status), cost=0.0, need=need,
                               permanent={}, temporary={}, floater_cover={}, floaters={},
                               names=names, summary="No staffing plan meets the rules.")

    result = WorkforceResult(
        status=str(m.solve_details.status),
        cost=sol.objective_value,
        need=need,
        permanent={k: round(perm[k].solution_value) for k in keys},
        temporary={k: round(temp[k].solution_value) for k in keys},
        floater_cover={k: cover[k].solution_value for k in keys},
        floaters={h: round(floaters[h].solution_value) for h in shifts},
        names=names,
    )
    if compare and allow_floaters:
        alone = solve(stations, shifts, need, skilled, cost, shift_premium, max_temp_share,
                      max_cover_per_station, allow_floaters=False, compare=False)
        result.cost_without_floaters = alone.cost
        result.headcount_without_floaters = alone.headcount
    result.summary = summarise(result, max_temp_share)
    return result


def summarise(r, max_temp_share):
    perm = sum(r.permanent.values())
    temp = sum(r.temporary.values())
    flo = sum(r.floaters.values())
    per_shift = ", ".join(f"{h} {r.shift_headcount(h)}" for h in r.floaters)
    cap_reached = temp + 1 > max_temp_share * r.headcount
    lines = [f"Staffing: {r.headcount} people ({perm} permanent, {temp} temporary, {flo} floaters) "
             f"for {eur(r.cost)} a week. Per shift: {per_shift}.",
             f"Temporary share {pct(r.temporary_share)} (cap {pct(max_temp_share)})"
             + (": the cap is what stops more (cheaper) temporary staff."
                if cap_reached else ".")]
    if r.cost_without_floaters is not None:
        saved = r.cost_without_floaters - r.cost
        fewer = r.headcount_without_floaters - r.headcount
        lines.append(f"Without floaters every station rounds up on its own: "
                     f"{r.headcount_without_floaters} people, {eur(r.cost_without_floaters)}. "
                     f"Cross-training {flo} floaters saves {eur(saved)} a week ({fewer} people).")
    return "\n".join(lines)


def solve_plant(plant=None, plan=None):
    """People needed = cars per shift x station minutes x crew / net shift minutes / (1 - absence)."""
    from plantlab.optimize import production_mix

    plant = plant or load_plant()
    if plan is None:
        plan = production_mix.solve_plant(plant).plan
    p, wf = plant["plant"], plant["workforce"]
    stations = [s["id"] for s in plant["stations"]]
    shifts = list(p["shifts"])
    need = {}
    for st in plant["stations"]:
        for h, sh in p["shifts"].items():
            cars = {q: plan[q] * sh["volume_share"] / p["days_per_week"] for q in plan}
            work = sum(cars[q] * st["minutes"][q] for q in plan) * st["crew"]
            need[st["id"], h] = work / wf["net_minutes_per_shift"] / (1 - wf["absence_rate"])
    return solve(
        stations=stations,
        shifts=shifts,
        need=need,
        skilled={s["id"]: s["skilled"] for s in plant["stations"]},
        cost=wf["weekly_cost_eur"],
        shift_premium={h: sh["wage_premium"] for h, sh in p["shifts"].items()},
        max_temp_share=wf["max_temporary_share"],
        max_cover_per_station=wf["max_floater_share_per_station"],
        names={s["id"]: s["name"] for s in plant["stations"]},
    )
