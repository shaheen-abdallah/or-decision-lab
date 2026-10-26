"""OR models for decision makers: the app.

    streamlit run app/Home.py

Home (one card per business question) · Where should I ship from? (transport builder) ·
the car plant as a worked example (Plan, Simulate, What-if, Ask). Pages live in `pages/`
and `car_plant.py`; the maths in `plantlab.engine` and `plantlab.models`.
"""

import streamlit as st

import car_plant

st.set_page_config(page_title="OR decision lab", page_icon="🧭", layout="wide")

pages = {
    "Decide": [st.Page("pages/home.py", title="Home", icon=":material/home:", default=True),
               st.Page("pages/transport.py", title="Where should I ship from?", icon=":material/local_shipping:",
                       url_path="transport")],
    "Worked example: a car plant": car_plant.pages(),
}

with st.sidebar:
    st.markdown("**OR decision lab**  \nBuild a decision model without code; IBM CPLEX solves it "
                "and explains the answer in plain words.")
    st.caption("Abdallah Shaheen · all data is invented · city list: GeoNames (CC BY 4.0)")
st.navigation(pages).run()
