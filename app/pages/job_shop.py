import altair as alt
import pandas as pd
import streamlit as st

import guide
from orlab.registry import problem

P = problem("job_shop")


def chart(data, sol):
    df = pd.DataFrame(sol.tables["schedule"])
    gantt = alt.Chart(df).mark_bar().encode(
        x=alt.X("start:Q", title="minutes from the start of the shift"), x2="end:Q",
        y=alt.Y("station:N", sort=sol.extra["stations"], title=None),
        color=alt.Color("batch:N", title=None),
        tooltip=["batch", "station", "start", "end", "minutes"])
    st.altair_chart(gantt.properties(height=180, title=f"Gantt chart: makespan {sol.objective:.0f} min"),
                    use_container_width=True)


def whatif(data, rev):
    c1, c2 = st.columns(2)
    oven = c1.slider("Curing oven minutes per batch, change by", -20, 20, 0, 5, key=f"js_oven_{rev}")
    rush = c2.checkbox("A rush batch: 4 more SUVs, black (35 / 60 / 45 min)", key=f"js_rush_{rev}")
    if oven == 0 and not rush:
        return None
    for b in data["batches"]:
        if b.get("Curing oven"):
            b["Curing oven"] = max(5, b["Curing oven"] + oven)
    if rush:
        data["batches"].append({"batch": "Rush SUV, black (4 cars)", **{k: v for k, v in zip(
            [k for k in data["batches"][0] if k != "batch"], [35, 60, 45])}})
    return data


guide.page(P, [("Batches: minutes at each station, visited left to right (0 = skipped)", "batches", {})],
           chart=chart, whatif=whatif,
           context="Five batches of car bodies wait for the paint shop, whose three stations each take one batch "
                   "at a time. The sequence decides when the last batch is done.")
