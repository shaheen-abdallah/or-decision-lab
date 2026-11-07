import altair as alt
import pandas as pd
import streamlit as st

import guide
from orlab.registry import problem

P = problem("min_cost_flow")


def chart(data, sol):
    rows = [{"lane": k, "supplier": k.split(" → ")[0], "plant": k.split(" → ")[1], "units": v}
            for k, v in sol.extra["flows"].items() if v > 0]
    df = pd.DataFrame(rows)
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("units:Q", title=f"{data.get('part', 'unit')}s a week"),
        y=alt.Y("plant:N", title=None),
        color=alt.Color("supplier:N", title="from"),
        tooltip=["lane", "units"])
    st.altair_chart(bars.properties(height=180, title="Who supplies each plant"), use_container_width=True)


def whatif(data, rev):
    c1, c2 = st.columns(2)
    west = c1.slider("Plant West builds (cars a week)", 500, 1100, int(data["plants"][0]["demand"]), 10,
                     key=f"flow_west_{rev}")
    cap = c2.slider("Saarbrücken capacity", 300, 1000, int(data["suppliers"][0]["capacity"]), 50,
                    key=f"flow_cap_{rev}")
    if west == data["plants"][0]["demand"] and cap == data["suppliers"][0]["capacity"]:
        return None
    data["plants"][0]["demand"], data["suppliers"][0]["capacity"] = west, cap
    return data


guide.page(P, [
    ("Suppliers: capacity and freight € per seat set to each plant (empty = not approved)", "suppliers", {}),
    ("Plants: seat sets needed a week", "plants", {}),
], chart=chart, whatif=whatif,
    context="Every car needs one seat set. Three suppliers serve the group's three plants; "
            "Plant West's demand is this week's production plan (840 cars).")
