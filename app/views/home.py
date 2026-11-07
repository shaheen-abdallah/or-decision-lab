"""Home: the catalogue, grouped like the OR-Tools guides."""

import streamlit as st

import describe_ui

from orlab.registry import FAMILIES, PROBLEMS

st.title("One car plant, nine decisions")
st.markdown("Plant West builds Sedans and SUVs. Every week its managers face the decisions below. "
            "Each page states the question, shows the data, lets **Google OR-Tools** solve it, "
            "and explains the model in words, math and code.")

describe_ui.card()

cols = st.columns(3)
i = 0
for family in FAMILIES:
    for p in (p for p in PROBLEMS if p.family == family):
        with cols[i % 3].container(border=True):
            st.markdown(f"##### {p.question}")
            st.caption(f"{p.family} · {p.model} · {p.solver}")
            if p.live:
                st.page_link(f"views/{p.key}.py", label="Open", icon=":material/arrow_forward:")
            else:
                st.caption(":material/schedule: Coming next")
        i += 1

st.caption("Built with Python, Google OR-Tools, SimPy and Streamlit. Source on GitHub.")
