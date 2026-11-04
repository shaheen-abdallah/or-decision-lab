r"""Simulation: does the weekly plan survive real-world variability
(discrete-event simulation of the line in SimPy; nothing is optimised, the plan is tested).

The plan from the product-mix page assumes every station runs at its standard time, 90 % of the
time. The simulation lets the times vary (log-normal station times fitted to invented time
studies), lets units break down and be repaired, limits the buffers between stations, and sends
SUVs that fail the off-road test back for rework. It replays one week $n$ times with different
random numbers and reports a confidence interval:

$$\bar{x} \pm t_{n-1,\,0.975}\; \frac{s}{\sqrt{n}}$$

Breakdowns keep the plan's availability on average, only in random chunks:

$$\text{availability} = \frac{\text{MTBF}}{\text{MTBF} + \text{MTTR}} = 0.90$$

The bottleneck is the station that is active (working or down) the largest share of the time;
the station before it is *blocked* when it has nowhere to put a finished car. That is what a
linear program cannot see: it has no queues.
"""

import copy

from orlab.core import Solution, num
from orlab.plant import load_plant
from orlab.simulate.experiment import run_experiment

EXAMPLE = {
    "plan": [{"product": "sedan", "cars per week": 300},     # the product-mix optimum
             {"product": "suv", "cars per week": 540}],
    "settings": [{"replications": 10, "buffer size": 3, "off-road calibration units": 1}],
}


def explain(data):
    s = data["settings"][0]
    return {
        "decide": "Nothing is optimised here: you choose the plan, the buffer size and the number of "
                  "replications; the simulation shows what the line really delivers.",
        "goal": "Know whether the plan's cars per week hold up, and which station limits them.",
        "limits": [f"Random station times, breakdowns and 6 % SUV rework (seed fixed, {int(s['replications'])} replications)",
                   f"Buffers of {int(s['buffer size'])} cars between stations (paint shop 6)",
                   "One week warm-up, then one measured week per replication"],
    }


def solve(data):
    s = data["settings"][0]
    plant = copy.deepcopy(load_plant())
    plant["simulation"]["buffer_size"] = int(s["buffer size"])
    for st in plant["stations"]:
        if st["id"] == "offroad":
            st["units"] = int(s["off-road calibration units"])
    plan = {r["product"]: float(r["cars per week"]) for r in data["plan"]}
    if sum(plan.values()) <= 0:
        return Solution("error", None, "Plan at least one car.", [])

    # 1.-5. Build the SimPy line from plant.yaml, run n replications (warm-up + measured week).
    e = run_experiment(plant, plan, reps=max(2, int(s["replications"])))

    # 6. Read the KPIs back with their confidence intervals.
    cars, half = e.kpi("cars")
    planned = sum(plan.values())
    gap = cars / planned - 1
    kpis = [{"KPI": "Cars built per week", "mean": round(cars), "± 95 %": round(half), "plan": round(planned)}]
    for p in plan:
        m, h = e.kpi(f"cars_{p}")
        kpis.append({"KPI": f"  {e.names[p]}s", "mean": round(m), "± 95 %": round(h), "plan": round(plan[p])})
    margin, mh = e.kpi("margin")
    kpis += [{"KPI": "Margin per week (€)", "mean": round(margin), "± 95 %": round(mh), "plan": None},
             {"KPI": "Cycle time (working h)", "mean": round(e.kpi("cycle_time_h")[0], 1), "± 95 %": round(e.kpi("cycle_time_h")[1], 1), "plan": None},
             {"KPI": "Cars in process (WIP)", "mean": round(e.kpi("wip")[0]), "± 95 %": round(e.kpi("wip")[1]), "plan": None}]
    stations = [{"station": e.names[st], "working": e.station(st, "working")[0], "down": e.station(st, "down")[0],
                 "blocked": e.station(st, "blocked")[0], "active": e.station(st, "active")[0],
                 "queue (cars)": round(e.station(st, "queue")[0], 1), "bottleneck": st == e.bottleneck}
                for st in e.order]
    b = e.bottleneck
    i = e.order.index(b)
    before = e.names[e.order[i - 1]] if 0 < i < len(e.order) - 1 else None
    bullets = [f"**{num(cars)} ± {num(half)} cars a week** against a plan of {num(planned)} ({gap:+.1%}): "
               + ("the plan holds." if abs(gap) < 0.03 else "the paper plan is optimistic." if gap < 0 else "the line beats the plan."),
               f"Bottleneck: **{e.names[b]}**, active {e.station(b, 'active')[0]:.0%} of the time "
               f"(busiest in {e.bottleneck_votes} of {len(e.runs)} replications)"
               + (f"; {before} is blocked {e.station(e.order[i - 1], 'blocked')[0]:.0%} of the time behind it." if before else "."),
               f"A car spends {e.kpi('cycle_time_h')[0]:.1f} working hours in the plant; "
               f"{e.kpi('wip')[0]:.0f} cars are in process; {e.kpi('rework_rate')[0]:.1%} of SUVs need rework."]
    return Solution("optimal", float(round(cars)),
                    f"The line delivers about {num(cars)} of the {num(planned)} planned cars a week.",
                    bullets, {"KPIs": kpis, "stations": stations}, solver="SimPy",
                    extra={"bottleneck": e.names[b], "gap": gap, "replications": len(e.runs)})
