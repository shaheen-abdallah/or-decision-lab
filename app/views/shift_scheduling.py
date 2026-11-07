import altair as alt
import pandas as pd
import streamlit as st

import guide
from orlab.registry import problem

P = problem("shift_scheduling")


def chart(data, sol):
    days = sol.extra["days"]
    rows = [{"operator": r["operator"], "day": d, "shift": r[d],
             "broken": (r["operator"], d) in sol.extra["missed"]}
            for r in sol.tables["roster"] for d in days if r[d] != "–"]
    df = pd.DataFrame(rows)
    base = alt.Chart(df).encode(x=alt.X("day:N", sort=days, title=None), y=alt.Y("operator:N", title=None))
    cells = base.mark_rect().encode(color=alt.Color("shift:N", scale=alt.Scale(domain=["early", "late"],
                                                                               range=["#ffd92f", "#4c78a8"]), title=None))
    marks = base.mark_text(fontWeight="bold").encode(
        text=alt.condition("datum.broken", alt.value("✕"), alt.value("")), color=alt.value("#d62728"))
    st.altair_chart((cells + marks).properties(height=240, title="The roster (✕ = a day-off request broken)"),
                    use_container_width=True)


def whatif(data, rev):
    c1, c2 = st.columns(2)
    sick = c1.selectbox("Who is on sick leave all week?", ["nobody"] + [o["operator"] for o in data["operators"]],
                        key=f"shift_sick_{rev}")
    extra = c2.slider("Extra operators needed on the Friday late shift", 0, 3, 0, key=f"shift_fri_{rev}")
    if sick == "nobody" and extra == 0:
        return None
    data["operators"] = [o for o in data["operators"] if o["operator"] != sick]
    data["demand"][1]["Fri"] += extra
    return data


guide.page(P, [
    ("Operators: shift limits and days-off requests", "operators",
     {"days off wanted": st.column_config.TextColumn("days off wanted (Mon, Tue, …)")}),
    ("Operators needed per shift and day", "demand", {}),
], chart=chart, whatif=whatif,
    context="The skilled stations need certified operators on both shifts, five days a week. "
            "The team leader wants to honour as many days-off requests as the rules allow.")
