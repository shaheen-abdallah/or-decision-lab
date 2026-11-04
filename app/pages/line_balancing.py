import altair as alt
import pandas as pd
import streamlit as st

import guide
from orlab.registry import problem

P = problem("line_balancing")


def chart(data, sol):
    rows = [{"station": f"Station {sol.extra['assignment'][t['id']]}", "task": t["task"], "seconds": t["seconds"]}
            for t in data["tasks"]]
    df = pd.DataFrame(rows)
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("sum(seconds):Q", title="seconds per car", scale=alt.Scale(domain=[0, sol.extra["cycle"] * 1.05])),
        y=alt.Y("station:N", title=None),
        color=alt.Color("task:N", legend=None),
        order=alt.Order("task:N"),
        tooltip=["task", "seconds"])
    takt = alt.Chart(pd.DataFrame({"c": [sol.extra["cycle"]]})).mark_rule(color="#d62728", strokeDash=[4, 4]).encode(x="c:Q")
    st.altair_chart((bars + takt).properties(height=200, title="Work per station (dashed line = cycle time)"),
                    use_container_width=True)


def whatif(data, rev):
    c1, c2 = st.columns(2)
    cycle = c1.slider("Cycle time (s): faster line = more stations", 200, 450,
                      int(data["line"][0]["cycle time (s)"]), 10, key=f"lb_cycle_{rev}")
    ids = [t["id"] for t in data["tasks"]]
    faster = c2.selectbox("A kaizen makes one task 30 s faster", ["none"] + ids, key=f"lb_kaizen_{rev}")
    if cycle == data["line"][0]["cycle time (s)"] and faster == "none":
        return None
    data["line"][0]["cycle time (s)"] = cycle
    for t in data["tasks"]:
        if t["id"] == faster:
            t["seconds"] = max(10, t["seconds"] - 30)
    return data


guide.page(P, [
    ("Tasks: seconds per car and which tasks must come first", "tasks",
     {"after": st.column_config.TextColumn("after (ids)")}),
    ("Line", "line", {}),
], chart=chart, whatif=whatif,
    context="The wiring-and-trim line is a paced line: every car moves one station further each cycle. "
            "Sixteen tasks with precedence rules must be grouped into stations so that no station "
            "needs more than the cycle time. Every station saved is a crew and a workplace.")
