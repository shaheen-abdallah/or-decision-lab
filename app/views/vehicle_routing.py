import altair as alt
import pandas as pd
import streamlit as st

import guide
from orlab.registry import problem

P = problem("vehicle_routing")


def chart(data, sol):
    stops = data["stops"]
    pts = pd.DataFrame(stops)
    pts["kind"] = ["depot"] + ["dealer"] * (len(stops) - 1)
    legs = pd.DataFrame([{"van": f"Van {r['van']}", "order": n, "x": stops[i]["x"], "y": stops[i]["y"]}
                         for r in sol.extra["routes"] for n, i in enumerate(r["path"])])
    lines = alt.Chart(legs).mark_line(point=False).encode(x=alt.X("x:Q", title="km east"), y=alt.Y("y:Q", title="km north"),
                                                        order="order:Q", color=alt.Color("van:N", title=None))
    dots = alt.Chart(pts).mark_point(filled=True, size=120).encode(
        x="x:Q", y="y:Q", shape=alt.Shape("kind:N", legend=None), tooltip=["stop", "pallets"],
        color=alt.value("black"))
    names = dots.mark_text(dy=-12, fontSize=11).encode(text="stop:N")
    st.altair_chart((lines + dots + names).properties(height=380, title="Routes on the map"),
                    use_container_width=True)


def whatif(data, rev):
    c1, c2 = st.columns(2)
    vans = c1.slider("Vans available", 1, 5, int(data["fleet"][0]["vans"]), key=f"vrp_vans_{rev}")
    cap = c2.slider("Pallets per van", 6, 20, int(data["fleet"][0]["pallets per van"]), key=f"vrp_cap_{rev}")
    if vans == data["fleet"][0]["vans"] and cap == data["fleet"][0]["pallets per van"]:
        return None
    data["fleet"][0].update({"vans": vans, "pallets per van": cap})
    return data


guide.page(P, [("Stops: map position (km) and pallets ordered", "stops", {}), ("Fleet", "fleet", {})],
           chart=chart, whatif=whatif,
           context="Every morning the parts depot sends vans with service parts to the dealers around the plant. "
                   "Fewer kilometres mean fewer vans and earlier deliveries.")
