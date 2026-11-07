import altair as alt
import pandas as pd
import streamlit as st

import guide
from orlab.registry import problem

P = problem("simulation")


def chart(data, sol):
    df = pd.DataFrame(sol.tables["stations"]).melt(id_vars=["station", "bottleneck"], value_vars=["working", "down", "blocked"],
                                                   var_name="state", value_name="share")
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("share:Q", title="share of the time", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1.3])),
        y=alt.Y("station:N", sort=None, title=None),
        color=alt.Color("state:N", scale=alt.Scale(domain=["working", "down", "blocked"],
                                                   range=["#4c78a8", "#d62728", "#ff7f0e"]), title=None),
        order=alt.Order("state:N"), tooltip=["station", "state", alt.Tooltip("share:Q", format=".0%")])
    st.altair_chart(bars.properties(height=300, title=f"What each station does with its time (bottleneck: {sol.extra['bottleneck']})"),
                    use_container_width=True)


def whatif(data, rev):
    c1, c2 = st.columns(2)
    buf = c1.slider("Buffer size between stations (cars)", 1, 10, int(data["settings"][0]["buffer size"]), key=f"sim_buf_{rev}")
    units = c2.slider("Off-road calibration cells", 1, 3, int(data["settings"][0]["off-road calibration units"]), key=f"sim_units_{rev}")
    s = data["settings"][0]
    if buf == s["buffer size"] and units == s["off-road calibration units"]:
        return None
    s["buffer size"], s["off-road calibration units"] = buf, units
    return data


guide.page(P, [("The weekly plan to test", "plan", {}), ("Simulation settings", "settings", {})],
           chart=chart, whatif=whatif,
           context="The product-mix page says 300 Sedans and 540 SUVs a week. That plan assumes standard times "
                   "and 90 % availability at every station. A SimPy model of the same line adds random times, "
                   "breakdowns, limited buffers and rework, and replays the week ten times.")
