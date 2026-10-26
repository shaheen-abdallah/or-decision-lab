"""Worked example: the car plant (the first version of the lab, kept as an example).

Pages: Plan (the four CPLEX models) · Simulate (the plan on a SimPy line, paper vs reality) ·
What-if (the three built-in scenarios + your own) · Ask (Claude turns a question into a scenario;
only shown when ANTHROPIC_API_KEY is set). Every number comes from the same code as the CLI
(`python -m plantlab ...`); the app only runs it and shows the results. `Home.py` adds the pages.
"""

import json

import altair as alt
import pandas as pd
import streamlit as st

from plantlab import loop
from plantlab.ai import assistant
from plantlab.optimize import line_balancing, parts_transport, production_mix, workforce
from plantlab.optimize.report import eur
from plantlab.plant import load_plant
from plantlab.simulate.experiment import ci
from plantlab.simulate.fitting import fit_plant

PLANT = load_plant()
BASE = loop.SCENARIOS[0]


# ---------- cached runs (CPLEX solves in < 1 s, one simulated scenario takes about 2 s)

@st.cache_resource(show_spinner="CPLEX is planning the week ...")
def plan_week():
    mix = production_mix.solve_plant(PLANT)
    return (mix, line_balancing.solve_plant(PLANT, mix.plan), workforce.solve_plant(PLANT, mix.plan),
            parts_transport.solve_plant(PLANT, mix.plan))


@st.cache_resource(show_spinner="CPLEX re-plans, SimPy builds the plan 20 times ...", max_entries=40)
def _run(scenario_json):
    return loop.run_scenario(PLANT, json.loads(scenario_json))


def run(scenario):
    return _run(json.dumps(scenario, sort_keys=True))


# ---------- small helpers

def frame(headers, rows):
    """Text table (headers, rows) from the lab -> DataFrame with the first column as index."""
    return pd.DataFrame(rows, columns=headers).set_index(headers[0])


def lines(text):
    """The lab's plain-English summaries keep their line breaks in Markdown."""
    st.markdown(text.replace("\n", "  \n"))


def signed_eur(value):
    return eur(value).replace("€-", "-€")


def thousands(value):
    """+€227k / -€5k: short enough for a KPI tile."""
    return f"{'-' if value < 0 else '+'}€{abs(value) / 1000:,.0f}k"


def fact(col, label, value, note=""):
    """A KPI tile for text (station names) that st.metric would cut off."""
    col.markdown(f"<div style='font-size:0.875rem'>{label}</div>"
                 f"<div style='font-size:1.5rem;line-height:1.3;margin:0.2rem 0'>{value}</div>"
                 f"<div style='font-size:0.8rem;opacity:0.65'>{note}</div>", unsafe_allow_html=True)


def vs_base(r, base, key):
    """Paired CI (scenario - base) over replications with the same random numbers."""
    return ci([a.kpi[key] - b.kpi[key] for a, b in zip(r.sim.runs, base.sim.runs)])


def show_scenario(r, base):
    """Result block for one what-if: deltas vs base, comparison, gap table, explanation."""
    if r.sim is None:
        st.error(r.mix.summary)
        return
    cars, cars_half = vs_base(r, base, "cars")
    margin, margin_half = vs_base(r, base, "margin")
    c = st.columns(4)
    c[0].metric("Cars / week vs base", f"{cars:+,.0f} ± {cars_half:.0f}")
    c[1].metric("Margin / week vs base", thousands(margin),
                f"± {thousands(margin_half)[1:]} (paired 95% CI)", delta_color="off")
    fact(c[2], "Bottleneck", r.sim.names[r.sim.bottleneck],
         f"was {base.sim.names[base.sim.bottleneck]}")
    c[3].metric("WIP (cars)", f"{r.sim.kpi('wip')[0]:.0f}",
                f"{r.sim.kpi('wip')[0] - base.sim.kpi('wip')[0]:+.0f} vs base", delta_color="inverse")
    st.dataframe(frame(*loop.LoopResult([base, r]).comparison_rows()))
    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Paper (LP) vs reality (simulation)**")
        st.dataframe(frame(*r.gap_rows()))
    with right:
        lines(loop.explain(r))
        with st.expander("The scenario as JSON (the format the Ask assistant writes)"):
            st.json(r.scenario)


# ---------- pages

def plan_page():
    mix, bal, staff, parts = plan_week()
    st.title("Plan: the week on paper")
    st.caption(f"Four optimisation models (docplex + IBM CPLEX) plan {PLANT['plant']['name']}, a "
               "fictional two-model car plant. The production mix drives the other three: it sets "
               "the takt, the staffing need and the seat demand. All data is invented.")
    if not mix.plan:
        st.error(mix.summary)
        return
    c = st.columns(4)
    for col, p in zip(c, mix.plan):
        col.metric(f"{mix.names[p]}s / week", f"{mix.plan[p]:,.0f}")
    c[2].metric("Contribution margin / week", eur(mix.margin))
    c[3].metric("Bottleneck stations",
                f"{sum(s.binding for s in mix.stations.values())} of {len(mix.stations)}")

    tabs = st.tabs(["Production mix (LP)", "Line balancing (IP)", "Workforce (IP)",
                    "Parts transport (LP)"])
    with tabs[0]:
        left, right = st.columns([3, 2])
        load = pd.DataFrame({"Station": [s.name for s in mix.stations.values()],
                             "Load": [s.utilisation for s in mix.stations.values()],
                             "Limit": ["bottleneck" if s.binding else "spare capacity"
                                       for s in mix.stations.values()]})
        left.altair_chart(alt.Chart(load, title="Station load in the optimal plan").mark_bar().encode(
            x=alt.X("Load:Q", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("Station:N", sort=None, title=None, axis=alt.Axis(labelLimit=220)),
            color=alt.Color("Limit:N", scale=alt.Scale(range=["#c0392b", "#7f8c8d"]),
                            legend=alt.Legend(orient="bottom", title=None))),
            width="stretch")
        with right:
            lines(mix.summary)
        st.dataframe(pd.DataFrame(
            [[s.name, s.used_min, s.capacity_min, s.utilisation,
              s.shadow_price_per_h if s.binding else None,
              s.extra_hours_valid if s.binding else None, s.overtime_eur_per_h]
             for s in mix.stations.values()],
            columns=["Station", "Used min", "Capacity min", "Load", "€ per extra hour (shadow price)",
                     "… valid for the next h", "Overtime €/h"]).set_index("Station").style.format(
            {"Used min": "{:,.0f}", "Capacity min": "{:,.0f}", "Load": "{:.0%}",
             "€ per extra hour (shadow price)": "€{:,.0f}", "… valid for the next h": "{:.1f}",
             "Overtime €/h": "€{:,.0f}"}, na_rep="-"))

    with tabs[1]:
        c = st.columns(4)
        c[0].metric("Stations", bal.n_stations, f"lower bound {bal.lower_bound}", delta_color="off")
        c[1].metric("Cycle time (takt)", f"{bal.cycle_time:.0f} s")
        c[2].metric("Balance efficiency", f"{bal.efficiency:.0%}")
        c[3].metric("Busiest station", f"{bal.busiest:.0f} s")
        loads = pd.DataFrame({"Station": [f"Station {k}" for k in range(1, bal.n_stations + 1)],
                              "Seconds": [load for _, load in bal.stations],
                              "Tasks": [", ".join(bal.names[t] for t in tasks)
                                        for tasks, _ in bal.stations]})
        bars = alt.Chart(loads, title=f"{bal.line}: work per station vs the takt").mark_bar(
            color="#2c7fb8").encode(x=alt.X("Station:N", sort=None, title=None),
                                    y=alt.Y("Seconds:Q"), tooltip=["Station", "Tasks", "Seconds"])
        takt = alt.Chart(pd.DataFrame({"takt": [bal.cycle_time]})).mark_rule(
            color="#c0392b", strokeDash=[6, 3]).encode(y="takt:Q")
        st.altair_chart(bars + takt, width="stretch")
        st.dataframe(loads.set_index("Station").style.format({"Seconds": "{:.0f}"}))
        lines(bal.summary)

    with tabs[2]:
        c = st.columns(4)
        c[0].metric("People", staff.headcount)
        c[1].metric("Cost / week", eur(staff.cost))
        c[2].metric("Floaters (cross-trained)", sum(staff.floaters.values()))
        if staff.cost_without_floaters is not None:
            c[3].metric("Saved by floaters / week", eur(staff.cost_without_floaters - staff.cost))
        shifts = list(staff.floaters)
        stations = list(dict.fromkeys(s for s, _ in staff.need))
        st.dataframe(pd.DataFrame(
            [[staff.names.get(s, s)] + sum([[staff.need[s, h], staff.permanent[s, h],
                                             staff.temporary[s, h], staff.floater_cover[s, h]]
                                            for h in shifts], []) for s in stations],
            columns=["Station"] + [f"{h}: {k}" for h in shifts
                                   for k in ("need", "permanent", "temporary", "floater share")]
        ).set_index("Station").style.format("{:.2f}", subset=[f"{h}: {k}" for h in shifts
                                                               for k in ("need", "floater share")]))
        lines(staff.summary)

    with tabs[3]:
        c = st.columns(3)
        c[0].metric("Freight / week", eur(parts.cost))
        c[1].metric(f"{parts.part.capitalize()}s shipped", f"{sum(parts.flows.values()):,.0f}")
        c[2].metric("Spare supplier capacity", f"{sum(parts.spare.values()):,.0f}")
        suppliers = list(dict.fromkeys(s for s, _ in parts.flows))
        plants = list(dict.fromkeys(p for _, p in parts.flows))
        st.markdown(f"**{parts.part.capitalize()}s per week, supplier → plant**")
        blocked = {tuple(route) for route in PLANT["parts_transport"].get("blocked", [])}
        st.dataframe(pd.DataFrame([[None if (s, p) in blocked else parts.flows.get((s, p)) for p in plants]
                                   for s in suppliers],
                                  index=suppliers, columns=plants).style.format("{:,.0f}", na_rep="blocked"))
        lines(parts.summary)


def simulate_page():
    base = run(BASE)
    sim, mix = base.sim, base.mix
    st.title("Simulate: does the plan survive the shop floor?")
    st.caption("A SimPy model builds the CPLEX plan on the same line, with what the LP leaves out: "
               "random station times (fitted to time studies, KS test), breakdowns, small buffers "
               "that block, and SUVs that fail the off-road test and come back for rework. "
               f"{len(sim.runs)} replications of one week after a one-week warm-up, 95% confidence intervals.")
    planned = sum(mix.plan.values())
    cars, half = sim.kpi("cars")
    margin = sim.kpi("margin")[0]
    ct = sim.kpi("cycle_time_h")[0]
    c = st.columns(4)
    c[0].metric("Cars built / week", f"{cars:,.0f} ± {half:.0f}", f"{cars / planned - 1:+.1%} vs plan {planned:,.0f}")
    c[1].metric("Margin / week", eur(margin), f"{signed_eur(margin - mix.margin)} vs paper")
    c[2].metric("Cycle time", f"{ct:.1f} h", f"x{ct * 60 / loop.work_content(base.plant, mix.plan):.1f} "
                "the work content", delta_color="off")
    fact(c[3], "Bottleneck", sim.names[sim.bottleneck],
         f"busiest in {sim.bottleneck_votes} of {len(sim.runs)} replications")

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Paper (LP) vs reality (simulation)**")
        st.dataframe(frame(*base.gap_rows()))
    with right:
        lines(loop.explain(base))
    measures = ["Load on paper (LP)", "Active in simulation", "Blocked in simulation"]
    rows = []
    for s in sim.order:
        lp = mix.stations.get(s)
        rows.append({"Station": sim.names[s], "Measure": "Load on paper (LP)",
                     "Share": lp.utilisation if lp else 0})
        rows.append({"Station": sim.names[s], "Measure": "Active in simulation",
                     "Share": sim.station(s, "active")[0]})
        rows.append({"Station": sim.names[s], "Measure": "Blocked in simulation",
                     "Share": sim.station(s, "blocked")[0]})
    st.altair_chart(alt.Chart(pd.DataFrame(rows), title="Paper load vs simulated reality").mark_bar().encode(
        x=alt.X("Share:Q", axis=alt.Axis(format="%"), title=None),
        y=alt.Y("Station:N", sort=None, title=None, axis=alt.Axis(labelLimit=220)),
        yOffset=alt.YOffset("Measure:N", sort=measures),
        color=alt.Color("Measure:N", scale=alt.Scale(domain=measures,
                                                     range=["#7f8c8d", "#2c7fb8", "#e67e22"]),
                        legend=alt.Legend(orient="bottom", title=None))).properties(height=520),
        width="stretch")

    with st.expander("All KPIs and station statistics"):
        st.code(sim.report(), language=None)
    with st.expander("Input analysis: fitted time distributions (scipy.stats, KS test)"):
        fits = fit_plant(PLANT)
        st.dataframe(pd.DataFrame(
            [[f"{sim.names.get(s, s)} / {what}", fits.standard[s, what], f.sample_mean, f.describe(),
              f.ks, f.p_value] for (s, what), f in fits.fits.items()],
            columns=["Station / time", "Standard min", "Observed mean", "Best fit", "KS D", "p"]
        ).set_index("Station / time").style.format(
            {"Standard min": "{:.1f}", "Observed mean": "{:.2f}", "KS D": "{:.3f}", "p": "{:.2f}"},
            na_rep="-"))
        st.caption(fits.summary)


def what_if_page():
    st.title("What-if: change the plant, re-plan, re-simulate")
    st.caption("Each scenario changes the plant, CPLEX re-plans the week, SimPy builds that plan. "
               "All scenarios use the same random numbers per station (common random numbers), so "
               "the difference to the base plan gets a tight paired confidence interval.")
    results = [run(s) for s in loop.SCENARIOS]
    base = results[0]
    st.subheader("Three built-in questions")
    st.dataframe(frame(*loop.LoopResult(results).comparison_rows()))
    lines(loop.summarise(results))

    st.subheader("Your own what-if")
    sim_cfg, rw = PLANT["simulation"], PLANT["simulation"]["rework"]
    units = {s["id"]: s["units"] for s in PLANT["stations"]}
    with st.form("what_if"):
        c = st.columns(3)
        paint = c[0].number_input("Paint shop units", 1, 4, units["paint"])
        offroad = c[1].number_input("Off-road calibration cells", 1, 3, units["offroad"])
        buffer = c[2].number_input("Buffer places between stations", 1, 10, sim_cfg["buffer_size"])
        c = st.columns(3)
        rate = c[0].slider("SUV rework rate", 0.0, 0.15, float(rw["rate"]), 0.01, format="%.2f")
        availability = c[1].slider("Station availability (breakdowns)", 0.80, 0.98,
                                   float(PLANT["plant"]["availability"]), 0.01, format="%.2f")
        with c[2]:
            st.write("")
            aware = st.checkbox("Let the LP plan with the rework loop")
        submitted = st.form_submit_button("Run what-if", type="primary")
    if submitted:
        changes = {}
        for path, value, default in [
            ("stations.paint.units", paint, units["paint"]),
            ("stations.offroad.units", offroad, units["offroad"]),
            ("simulation.buffer_size", buffer, sim_cfg["buffer_size"]),
            ("simulation.rework.rate", round(rate, 2), rw["rate"]),
            ("plant.availability", round(availability, 2), PLANT["plant"]["availability"])]:
            if value != default:
                changes[path] = value
        st.session_state.my_scenario = {"name": "Your what-if", "question": "Built on the What-if page",
                                    "changes": changes, "plan_with_rework": aware}
    if "my_scenario" in st.session_state:
        show_scenario(run(st.session_state.my_scenario), base)


def ask_page():
    st.title("Ask: a what-if in plain words")
    st.caption(f"Claude ({assistant.MODEL}) turns your question into a scenario through a strict "
               "tool schema, the lab runs it with CPLEX + SimPy, and Claude explains the numbers. "
               "The model never does the maths itself.")
    examples = ["What if we add a third paint unit?",
                "What if the SUV rework rate drops to 2%?",
                "What if breakdowns get worse and stations only run 85% of the time?"]
    c = st.columns(len(examples))
    for col, q in zip(c, examples):
        if col.button(q, width="stretch"):
            st.session_state.question = q
    with st.form("ask"):
        question = st.text_input("Your question", key="question",
                                 placeholder="What if we double the buffers in front of paint?")
        asked = st.form_submit_button("Ask", type="primary")
    if asked and question:
        import anthropic

        base = run(BASE)
        try:
            with st.spinner("Claude writes the scenario, CPLEX + SimPy run it ..."):
                st.session_state.answer = assistant.ask(question, PLANT, base,
                                                        run=lambda plant, s: run(s))
        except anthropic.APIError as e:
            st.error(f"The Claude API call failed: {e}")
    answer = st.session_state.get("answer")
    if answer:
        st.markdown(answer.text)
        if answer.result is not None:
            show_scenario(answer.result, run(BASE))


def pages():
    """The car plant pages for st.navigation (Ask only with an API key)."""
    out = [st.Page(plan_page, title="Plan (OR)", icon=":material/factory:", url_path="plan"),
           st.Page(simulate_page, title="Simulate", icon=":material/timeline:", url_path="simulate"),
           st.Page(what_if_page, title="What-if", icon=":material/science:", url_path="what-if")]
    if assistant.available():
        out.append(st.Page(ask_page, title="Ask", icon=":material/chat:", url_path="ask"))
    return out
