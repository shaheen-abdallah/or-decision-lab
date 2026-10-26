"""Home: question-first cards, one per model type (live ones open their builder)."""

import streamlit as st

import car_plant
from plantlab.models.registry import CARDS

st.title("Which decision are you facing?")
st.markdown("Pick the question closest to yours. Each one opens on an example you can change: "
            "drag, type or paste from Excel. **IBM CPLEX** finds the best answer and explains it in plain words.")

for group in dict.fromkeys(c.group for c in CARDS):
    st.subheader(group)
    cards = [c for c in CARDS if c.group == group]
    cols = st.columns(4)
    for col, c in zip(cols, cards):
        with col.container(border=True, height=290):
            st.markdown(f"#### {c.question}")
            st.caption(c.or_name)
            if c.live:
                st.page_link(c.page, label="Open the builder", icon=":material/arrow_forward:")
            else:
                st.caption(":material/schedule: Coming next")
            st.write(c.blurb)

st.subheader("Not sure? Describe your problem")
st.text_area("Your problem in a few sentences", disabled=True, label_visibility="collapsed",
             placeholder="e.g. We have three warehouses and twelve stores. Trucks cost about €1.50 a km. "
                         "Which warehouse should serve which store?")
st.caption("Coming in the next version: the AI suggests the model and fills in the builder. "
           "You check it in plain words before anything is solved.")

st.subheader("Worked example: a car plant")
st.write("Plan a mixed-model car assembly plant with four CPLEX models, then stress-test the plan "
         "with a SimPy simulation.")
cols = st.columns(4)
for col, page in zip(cols, car_plant.pages()):
    col.page_link(page, label=page.title, icon=page.icon)
