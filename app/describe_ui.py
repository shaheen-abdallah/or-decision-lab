"""The "Not sure? Describe your problem" card on the home page.

Words in -> the AI suggests one of the nine models and fills its tables -> the user reads the model
in plain words, edits the tables -> Confirm opens that page pre-filled. Nothing is solved here.
Without an API key the card only says how to switch it on.
"""

import copy

import pandas as pd
import streamlit as st

from orlab import describe
from orlab.registry import PROBLEMS, problem

S = st.session_state
PLACEHOLDER = ("e.g. We have two warehouses, in Hamburg and Munich, and four shops. Hamburg can ship 300 "
               "boxes a week, Munich 250. Each shop needs about 120 boxes. Trucking costs differ by lane. "
               "How should we ship to keep freight low?")


def card():
    with st.container(border=True):
        st.markdown("##### Not sure which model? Describe your problem")
        key = describe.api_key(st.secrets)
        if not key:
            st.caption(":material/key: This needs an AI API key (OpenRouter), which is not set up here; "
                       "see the README. Pick a page below meanwhile.")
            return
        st.caption("Write a few sentences. An AI picks the model that fits and fills in your numbers; "
                   "you check it in plain words and confirm. Nothing is solved before you confirm.")
        text = st.text_area("Your problem", placeholder=PLACEHOLDER, height=110, label_visibility="collapsed")
        if st.button("Suggest a model", icon=":material/auto_awesome:"):
            with st.spinner("Reading your problem…"):
                S["describe"] = describe.ask(text, key)
            S["describe_rev"] = S.get("describe_rev", 0) + 1
        if "describe" in S:
            _show(S["describe"], S.get("describe_rev", 0))


def _show(sug, rev):
    if sug.status == "error":
        st.warning(sug.note)
        return
    if sug.status == "none":
        st.info(f"**None of the nine models fits this well.** {sug.why}")
        if not sug.key:
            return
        st.markdown(f"The closest is **{problem(sug.key).question}**; it opens with its own example.")
    elif sug.status == "unsure":
        st.warning(f"**Probably:** {problem(sug.key).model}. {sug.why} Another page could fit too: check below.")
    else:
        st.success(f"**Suggested:** {problem(sug.key).model}. {sug.why}")
    if sug.note:
        st.caption(f":material/info: {sug.note}")

    keys = [p.key for p in PROBLEMS]
    key = st.selectbox("Model", keys, index=keys.index(sug.key), key=f"describe_page_{rev}",
                       format_func=lambda k: f"{problem(k).question} ({problem(k).model})")
    p = problem(key)
    start = sug.data if (key == sug.key and sug.data) else copy.deepcopy(p.example)
    words = st.container()

    with st.expander("Your numbers (edit them here or later on the page)", expanded=False):
        data = {}
        for table, value in start.items():
            if isinstance(value, str):
                data[table] = st.text_input(table, value, key=f"describe_{key}_{table}_{rev}")
                continue
            st.markdown(f"**{table.capitalize()}**")
            edited = st.data_editor(pd.DataFrame(value), key=f"describe_{key}_{table}_{rev}",
                                    hide_index=True, num_rows="dynamic", use_container_width=True)
            data[table] = edited.astype(object).where(pd.notna(edited), None).to_dict("records")

    problems = describe.check(key, data)
    with words:
        if problems:
            st.error("These tables don't fit the model yet: " + "; ".join(problems) + ".")
        else:
            w = p.explain(data)
            st.markdown(f"**You decide:** {w['decide']}  \n**You want:** {w['goal']}  \n**You are limited by:**")
            for line in w["limits"][:6]:
                st.markdown(f"- {line}")
            if len(w["limits"]) > 6:
                st.caption(f"… and {len(w['limits']) - 6} more")

    if st.button("Confirm and open the page", type="primary", disabled=bool(problems),
                 icon=":material/arrow_forward:"):
        S.setdefault("prefill", {})[key] = data
        st.switch_page(f"pages/{key}.py")
