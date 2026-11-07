"""One layout for every problem page, in the order of an OR-Tools guide:

    the question -> the data -> the answer -> what if -> how it's modelled (words, math, code, solver)

A page gives the problem, which tables are editable, an optional chart and optional what-if sliders.
"""

import copy

import pandas as pd
import streamlit as st

from orlab.core import num

S = st.session_state


def _state(problem):
    key = f"data_{problem.key}"
    if key not in S:
        S[key] = {"data": copy.deepcopy(problem.example), "rev": 0}
    return S[key]


def page(problem, tables, chart=None, whatif=None, context=""):
    st.title(problem.question)
    st.caption(f"{problem.family} · {problem.model} · solved by **{problem.solver}**")
    if context:
        st.markdown(context)
    state = _state(problem)
    data, rev = state["data"], state["rev"]

    left, right = st.columns([5, 7], gap="large")
    with left:
        st.subheader("The data")
        for title, key, config in tables:
            st.markdown(f"**{title}**")
            df = pd.DataFrame(data[key])
            edited = st.data_editor(df, key=f"{problem.key}_{key}_{rev}", hide_index=True,
                                    column_config=config, use_container_width=True)
            data[key] = edited.where(pd.notna(edited), None).to_dict("records")
        if st.button("Reset to the example", key=f"{problem.key}_reset"):
            state["data"], state["rev"] = copy.deepcopy(problem.example), rev + 1
            st.rerun()

    sol = problem.solve(data)
    with right:
        st.subheader("The answer")
        if sol.ok:
            st.success(f"**{sol.headline}**")
        else:
            st.error(f"**{sol.headline}**")
        for b in sol.bullets:
            st.markdown(f"- {b}")
        if sol.ok and chart:
            chart(data, sol)
        for name, rows in sol.tables.items():
            with st.expander(name[:1].upper() + name[1:], expanded=(name == next(iter(sol.tables)))):
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    if whatif and sol.ok:
        st.subheader("What if…")
        st.caption("Change a setting; the solver re-runs in milliseconds.")
        changed = whatif(copy.deepcopy(data), rev)
        if changed is not None:
            alt = problem.solve(changed)
            c1, c2 = st.columns([4, 8])
            if alt.ok:
                delta = alt.objective - sol.objective
                c1.metric("Objective with your change", problem.fmt(alt.objective),
                          delta=problem.delta_text(delta),
                          delta_color="normal" if problem.sense == "max" else "inverse")
                c2.markdown(f"**{alt.headline}**")
                for b in alt.bullets:
                    c2.markdown(f"- {b}")
            else:
                c2.error(alt.headline)

    st.subheader("How it's modelled")
    words, math, code, solver = st.tabs(["In words", "The math", "The code", "The solver"])
    with words:
        w = problem.explain(data)
        st.markdown(f"**You decide:** {w['decide']}  \n**You want:** {w['goal']}  \n**You are limited by:**")
        for line in w["limits"]:
            st.markdown(f"- {line}")
    with math:
        st.markdown(problem.math)
    with code:
        st.caption("The exact Python that solved this page (OR-Tools).")
        st.code(problem.code, language="python", line_numbers=True)
    with solver:
        st.markdown(f"**{problem.solver}** · {problem.why_solver}")
        st.markdown(f"Solved in **{sol.seconds * 1000:.1f} ms** · status: {sol.status} · "
                    f"objective: {num(sol.objective) if sol.objective is not None else '–'}")
    return data, sol
