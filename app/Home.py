"""OR Decision Lab: one car plant, nine decisions, each solved by Google OR-Tools.

    streamlit run app/Home.py
"""

import streamlit as st

from orlab.registry import PROBLEMS

st.set_page_config(page_title="OR Decision Lab", page_icon="🧭", layout="wide")

pages = {"": [st.Page("pages/home.py", title="Home", icon=":material/home:", default=True)]}
for p in PROBLEMS:
    if p.live:
        pages.setdefault(p.family, []).append(
            st.Page(f"pages/{p.key}.py", title=p.question, icon=p.icon, url_path=p.key))

with st.sidebar:
    st.markdown("**OR Decision Lab**  \nOne car plant, nine decisions. Google OR-Tools solves each one; "
                "every page shows the question, the data, the answer and the model.")
    st.caption("Abdallah Shaheen · all data is invented")
st.navigation(pages).run()
