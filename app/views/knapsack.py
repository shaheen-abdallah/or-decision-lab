import altair as alt
import pandas as pd
import streamlit as st

import guide
from orlab.registry import problem

P = problem("knapsack")


def chart(data, sol):
    df = pd.DataFrame(sol.tables["projects"])
    df["status"] = df["funded"].map({True: "funded", False: "not funded"})
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("gain €/week:Q", title="saving (€/week)"),
        y=alt.Y("project:N", title=None, sort=alt.EncodingSortField("€/week per k€", order="descending")),
        color=alt.Color("status:N", scale=alt.Scale(domain=["funded", "not funded"], range=["#2ca02c", "#bbbbbb"]),
                        title=None),
        tooltip=["project", "cost k€", "gain €/week", "€/week per k€"])
    st.altair_chart(bars.properties(height=260, title="Saving per project, best gain per k€ on top (green = funded)"),
                    use_container_width=True)


def whatif(data, rev):
    budget = st.slider("Budget (k€)", 100, 800, int(data["budget"][0]["budget k€"]), 10, key=f"ks_budget_{rev}")
    if budget == data["budget"][0]["budget k€"]:
        return None
    data["budget"][0]["budget k€"] = budget
    return data


guide.page(P, [("Improvement projects: one-off cost and weekly saving", "projects", {}),
               ("Budget", "budget", {})], chart=chart, whatif=whatif,
           context="The plant manager has eight proposals from the shop floor and one investment budget. "
                   "Each project is funded in full or not at all.")
