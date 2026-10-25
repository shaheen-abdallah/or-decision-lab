"""Paper vs reality: OR plan -> simulation -> gap table, for the base plan and what-if scenarios.

    1. Plan       the production-mix LP (phase 1) picks the weekly Sedan/SUV mix on the
                  (changed) plant.
    2. Simulate   the SimPy line builds that plan: random station times, breakdowns, finite
                  buffers, the SUV rework loop (20 replications, 95% CIs).
    3. Compare    paper vs reality: cars, margin, bottleneck, cycle time, WIP, rework.

On paper a car takes only its work content (sum of station times on its route) and WIP follows
from Little's law: WIP = throughput x cycle time. Scenarios use common random numbers (same
seeds per station), so the margin difference to the base plan gets a paired confidence interval:
CI of (scenario - base) per replication, much tighter than comparing two separate CIs.

A scenario is a plain dict (JSON-ready, so the phase 3 assistant can write one):
    {"name": ..., "question": ..., "changes": {"stations.offroad.units": 2},
     "plan_with_rework": False, "note": ...}
`changes` patch plant.yaml by dotted path (list items by their id).
`plan_with_rework` lets the LP see the rework loop: each SUV needs 1 / (1 - rate) off-road tests
and rate / (1 - rate) visits to the rework bay. The simulation always runs the real plant.
"""

import copy
from dataclasses import dataclass

from plantlab.optimize import production_mix
from plantlab.optimize.report import eur, table
from plantlab.plant import minutes_per_week
from plantlab.simulate.experiment import ci, run_experiment
from plantlab.simulate.fitting import fit_plant

SCENARIOS = [
    {"name": "Base plan",
     "question": "Does the LP's weekly plan survive variability, breakdowns and rework?",
     "changes": {}},
    {"name": "Rework-aware plan",
     "question": "What if the LP planned with the rework loop (6% of SUVs are tested twice)?",
     "changes": {}, "plan_with_rework": True},
    {"name": "2nd off-road cell",
     "question": "What if we install a second SUV off-road calibration cell?",
     "changes": {"stations.offroad.units": 2},
     "note": "investment cost not included: compare the extra margin with the cell's cost"},
    {"name": "Double buffers",
     "question": "Do twice the buffer places between stations close the gap?",
     "changes": {"simulation.buffer_size": 6, "simulation.stations.paint.buffer": 12}},
]


def apply_changes(plant, changes):
    """Copy of the plant with dotted-path changes, e.g. {"stations.offroad.units": 2}."""
    plant = copy.deepcopy(plant)
    for path, value in changes.items():
        *parents, last = path.split(".")
        node = plant
        try:
            for key in parents:
                node = (next(item for item in node if item["id"] == key)
                        if isinstance(node, list) else node[key])
        except (KeyError, StopIteration):
            raise KeyError(f"unknown plant setting: {path}") from None
        node[last] = value
    return plant


def rework_aware(plant):
    """The plant as the LP should see it once it knows the rework loop."""
    plant = copy.deepcopy(plant)
    rw = plant["simulation"]["rework"]
    visits = 1 / (1 - rw["rate"])
    test = next(s for s in plant["stations"] if s["id"] == rw["found_at"])
    test["minutes"][rw["product"]] *= visits
    bay = rw["bay"]
    plant["stations"].append({
        "id": bay["id"], "name": bay["name"], "units": bay["units"],
        "minutes": {p: bay["minutes"] * (visits - 1) if p == rw["product"] else 0
                    for p in plant["products"]},
        "crew": 1, "skilled": False, "overtime_eur_per_h": bay["overtime_eur_per_h"]})
    return plant


def work_content(plant, plan):
    """Mix-weighted minutes of pure work per car (no waiting, no breakdowns, no rework)."""
    total = sum(plan.values())
    return sum(st["minutes"][p] * plan[p] for st in plant["stations"] for p in plan) / total


@dataclass
class ScenarioResult:
    scenario: dict
    plant: dict           # the real (changed) plant the simulation ran
    mix: object           # production_mix.MixResult (the paper plan)
    sim: object           # experiment.Experiment, None if the LP found no plan

    @property
    def name(self):
        return self.scenario["name"]

    def paper_bottlenecks(self):
        return [s.name for s in self.mix.stations.values() if s.binding]

    def gap_table(self):
        return table(*self.gap_rows())

    def gap_rows(self):
        """(headers, rows) of the paper-vs-reality table, as text cells."""
        mix, sim, names = self.mix, self.sim, self.sim.names
        planned = sum(mix.plan.values())
        touch = work_content(self.plant, mix.plan)

        def cars(key, paper):
            mean, half = sim.kpi(key)
            return [f"{paper:,.0f}", f"{mean:,.0f} ± {half:,.0f}", f"{mean / paper - 1:+.1%}"]

        rows = [["Cars per week", *cars("cars", planned)]]
        rows += [[f"  {names[p]}s", *cars(f"cars_{p}", x)] for p, x in mix.plan.items() if x > 0.5]
        margin, half = sim.kpi("margin")
        rows.append(["Margin per week", eur(mix.margin), f"{eur(margin)} ± {eur(half)}",
                     eur(margin - mix.margin).replace("€-", "-€")])
        rows.append(["Bottleneck", ", ".join(self.paper_bottlenecks()) or "none",
                     names[sim.bottleneck], ""])
        ct, half = sim.kpi("cycle_time_h")
        rows.append(["Cycle time (working h)", f"{touch / 60:.2f} (work only)", f"{ct:.2f} ± {half:.2f}",
                     f"x{ct * 60 / touch:.1f}"])
        wip, half = sim.kpi("wip")
        paper_wip = planned / minutes_per_week(self.plant) * touch
        rows.append(["WIP (cars)", f"{paper_wip:.0f} (Little)", f"{wip:.0f} ± {half:.0f}",
                     f"x{wip / paper_wip:.1f}"])
        rw, half = sim.kpi("rework_rate")
        planned_rw = (f"{self.plant['simulation']['rework']['rate']:.0%}"
                      if self.scenario.get("plan_with_rework") else "not planned")
        rows.append(["Rework rate (SUVs)", planned_rw, f"{rw:.1%} ± {half:.1%}", ""])
        return ["", "Paper (LP)", "Reality (simulation)", "Gap"], rows

    def station_table(self):
        return table(*self.station_rows())

    def station_rows(self):
        rows = []
        for s in self.sim.order:
            lp = self.mix.stations.get(s)
            active, half = self.sim.station(s, "active")
            rows.append([self.sim.names[s], f"{lp.utilisation:.0%}" if lp else "not planned",
                         f"{active:.0%} ± {half:.1%}", f"{self.sim.station(s, 'blocked')[0]:.0%}",
                         f"{self.sim.station(s, 'queue')[0]:.1f}"])
        return ["Station", "Load on paper", "Active in simulation", "Blocked", "Queue"], rows


def explain(r):
    """One or two plain-English lines on why paper and reality differ."""
    sim, mix = r.sim, r.mix
    cars, half = sim.kpi("cars")
    planned = sum(mix.plan.values())
    lines = [f"{r.name}: the LP plans {planned:,.0f} cars ({eur(mix.margin)}); the simulation builds "
             f"{cars:,.0f} ± {half:,.0f} ({cars / planned - 1:+.1%}), bottleneck "
             f"{sim.names[sim.bottleneck]}."]
    rw = r.plant["simulation"]["rework"]
    if sim.bottleneck == rw["found_at"] and not r.scenario.get("plan_with_rework"):
        load = mix.stations[rw["found_at"]].utilisation
        lines.append(f"  The LP does not see the rework loop: failed tests come back, so "
                     f"{sim.names[rw['found_at']]} really needs about {load / (1 - rw['rate']):.0%} "
                     f"of its capacity, not {load:.0%}.")
    if r.scenario.get("note"):
        lines.append(f"  Note: {r.scenario['note']}.")
    return "\n".join(lines)


@dataclass
class LoopResult:
    results: list
    summary: str = ""

    def comparison(self):
        return table(*self.comparison_rows())

    def comparison_rows(self):
        base = self.results[0]
        rows = []
        for r in self.results:
            if r.sim is None:
                rows.append([r.name, "no plan", "", "", "", "", ""])
                continue
            planned = sum(r.mix.plan.values())
            cars, half = r.sim.kpi("cars")
            margin = r.sim.kpi("margin")[0]
            diff, dhalf = ci([a.kpi["margin"] - b.kpi["margin"]
                              for a, b in zip(r.sim.runs, base.sim.runs)])
            rows.append([r.name, f"{planned:,.0f}", f"{cars:,.0f} ± {half:,.0f}",
                         f"{cars / planned - 1:+.1%}", eur(margin),
                         "-" if r is base else f"{eur(diff)} ± {eur(dhalf)}".replace("€-", "-€"),
                         r.sim.names[r.sim.bottleneck]])
        return ["Scenario", "Plan cars", "Simulated cars", "Gap", "Simulated margin",
                "vs base (paired CI)", "Bottleneck"], rows

    def report(self):
        parts = []
        for i, r in enumerate(self.results):
            parts.append(f"--- {r.name}: {r.scenario['question']}")
            if r.sim is None:
                parts.append(r.mix.summary)
                continue
            parts.append(r.gap_table())
            if i == 0:
                parts.append(r.station_table())
        parts += ["--- All scenarios", self.comparison(), self.summary]
        return "\n\n".join(parts)


def run_scenario(plant, scenario, **sim_kwargs):
    real = apply_changes(plant, scenario.get("changes", {}))
    planning = rework_aware(real) if scenario.get("plan_with_rework") else real
    mix = production_mix.solve_plant(planning)
    if not mix.plan:
        return ScenarioResult(scenario, real, mix, None)
    sim = run_experiment(real, mix.plan, fits=fit_plant(real), **sim_kwargs)
    return ScenarioResult(scenario, real, mix, sim)


def run_loop(plant, scenarios=None, **sim_kwargs):
    """Run each scenario (the first is the base for the paired comparison)."""
    results = [run_scenario(plant, s, **sim_kwargs) for s in scenarios or SCENARIOS]
    return LoopResult(results, summarise(results))


def summarise(results):
    """Plain-English lines for each scenario + the best one by simulated margin."""
    done = [r for r in results if r.sim is not None]
    lines = [explain(r) for r in done]
    if len(done) > 1:
        base = done[0]
        best = max(done, key=lambda r: r.sim.kpi("margin")[0])
        if best is base:
            lines.append(f"Best by simulated margin: the {base.name.lower()} itself.")
        else:
            diff, half = ci([a.kpi["margin"] - b.kpi["margin"] for a, b in zip(best.sim.runs, base.sim.runs)])
            paper = best.mix.margin - base.mix.margin
            lines.append(f"Best by simulated margin: {best.name}, {eur(diff)} ± {eur(half)} a week "
                         f"more than the base plan really earns (the LP alone promised "
                         f"{eur(paper)}).".replace("€-", "-€"))
    return "\n".join(lines)
