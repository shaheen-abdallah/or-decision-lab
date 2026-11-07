import altair as alt
import pandas as pd
import streamlit as st

import guide
from orlab.registry import problem

P = problem("assignment")


def chart(data, sol):
    stations = [k for k in data["operators"][0] if k != "operator"]
    rows = [{"operator": o["operator"], "station": s, "rework": o[s],
             "chosen": sol.extra["match"].get(o["operator"]) == s}
            for o in data["operators"] for s in stations if o.get(s) is not None]
    df = pd.DataFrame(rows)
    base = alt.Chart(df).encode(x=alt.X("station:N", title=None), y=alt.Y("operator:N", title=None))
    heat = base.mark_rect().encode(color=alt.Color("rework:Q", scale=alt.Scale(scheme="blues", reverse=True),
                                                   title="rework min"))
    text = base.mark_text(fontWeight="bold").encode(
        text="rework:Q", color=alt.condition("datum.chosen", alt.value("#d62728"), alt.value("black")))
    st.altair_chart((heat + text).properties(height=220, title="Rework minutes per pairing (red = chosen)"),
                    use_container_width=True)


def whatif(data, rev):
    names = [o["operator"] for o in data["operators"]]
    out = st.selectbox("Who is off sick today?", ["nobody"] + names, key=f"asg_sick_{rev}")
    if out == "nobody":
        return None
    data["operators"] = [o for o in data["operators"] if o["operator"] != out]
    return data


guide.page(P, [("Operators: expected rework minutes per shift at each station (empty = not certified)",
                "operators", {})], chart=chart, whatif=whatif,
           context="Four skilled stations need a certified operator on the early shift. The team leader "
                   "knows from the quality records how much rework each person causes where.")
