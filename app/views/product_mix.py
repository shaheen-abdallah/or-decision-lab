import altair as alt
import pandas as pd
import streamlit as st

import guide
from orlab.registry import problem

P = problem("product_mix")


def chart(data, sol):
    df = pd.DataFrame(sol.tables["stations"])
    df["status"] = ["bottleneck" if s in sol.extra["bottlenecks"] else "spare" for s in df["station"]]
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("load:Q", title="hours used ÷ hours available", axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0, 1.05])),
        y=alt.Y("station:N", sort=None, title=None),
        color=alt.Color("status:N", scale=alt.Scale(domain=["bottleneck", "spare"], range=["#d62728", "#4c78a8"]),
                        legend=None),
        tooltip=["station", "hours used", "hours available", "value of one more hour"])
    st.altair_chart(bars.properties(height=260, title="Station load (red = full, limits the plan)"),
                    use_container_width=True)


def whatif(data, rev):
    c1, c2 = st.columns(2)
    station = c1.selectbox("Add overtime at", [s["station"] for s in data["stations"]],
                           index=2, key=f"mix_station_{rev}")
    extra = c1.slider("Extra hours a week", 0, 40, 0, key=f"mix_hours_{rev}")
    suv_max = c2.slider("SUVs sales can sell", 300, 800, int(data["products"][1]["max"]), 20, key=f"mix_suv_{rev}")
    if extra == 0 and suv_max == data["products"][1]["max"]:
        return None
    for s in data["stations"]:
        if s["station"] == station:
            s["hours"] += extra
    data["products"][1]["max"] = suv_max
    return data


guide.page(P, [
    ("Products", "products", {"margin": st.column_config.NumberColumn("margin €/car"),
                              "min": st.column_config.NumberColumn("contracts (min)"),
                              "max": st.column_config.NumberColumn("demand (max)")}),
    ("Stations: hours a week and minutes per car", "stations", {"hours": st.column_config.NumberColumn("hours/week")}),
], chart=chart, whatif=whatif,
    context="Plant West runs ten stations on two shifts. Sales caps how many of each model it can sell; "
            "fleet contracts set a minimum. Which weekly mix earns the most?")
