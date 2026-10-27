"""Network models on one canvas: shortest route ('What's the cheapest way from A to B?') and maximum
flow ('How much can my network carry at most?'). `pages/shortest.py` and `pages/maxflow.py` call `page()`.

Picture on top (network canvas + map), the answer in words below, then tabs: build · live sliders ·
teach (Dijkstra step by step / the minimum cut) · what limits you · rules · beat the solver · scenarios.
"""

import json
import math

import pandas as pd
import pydeck as pdk
import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState

from lab import Lab, metric_delta
from plantlab import engine, geo
from plantlab.engine.core import TOL, num
from plantlab.models import network as N

S = st.session_state

TEXT = {
    "shortest": {"title": "What's the cheapest way from A to B?",
                 "caption": "Shortest route (LP; Dijkstra by hand in the Teach tab) · solved with IBM CPLEX · "
                            "places from the GeoNames city list (CC BY 4.0), road km ≈ straight line × 1.25",
                 "scenario": "e.g. Today / Roadworks Kassel / avoid Berlin"},
    "maxflow": {"title": "How much can my network carry at most?",
                "caption": "Maximum flow + minimum cut (LP) · solved with IBM CPLEX · "
                           "places from the GeoNames city list (CC BY 4.0)",
                "scenario": "e.g. Today / +20 trucks Kassel → Nuremberg / Frankfurt closed"},
}


@st.cache_resource
def city_index():
    return {c.label: c for c in geo.cities()}


def page(kind):
    mt = N.MODELS[kind]
    short = kind == "shortest"
    unit = lambda inputs: mt.unit(inputs)
    lab = Lab({"shortest": "sr", "maxflow": "mf"}[kind], mt, lambda: N.template(kind, "germany"),
              lambda v: f"{num(round(v, 2))} {mt.unit(lab.inputs)}")
    k = lab.key

    # ---------- callbacks

    def load_template():
        key = S[f"{k}_template"]
        lab.reset(N.template(kind, key), f"template: {N.TEMPLATES[kind][key]}")

    def set_end(which):
        inputs, _ = lab.work()
        inputs[which] = S[lab.w(which)]
        lab.commit(inputs, note=f"{which} → {inputs[which]}")
        lab.s["step"] = None

    def set_text(field):
        inputs, _ = lab.work()
        inputs[field] = S[lab.w(field)].strip() or inputs[field]
        lab.commit(inputs, note=field)

    def set_two_way():
        inputs, rules = lab.work()
        inputs["two_way"] = S[lab.w("two_way")]
        lab.commit(inputs, keep(rules, inputs), note="two-way roads" if inputs["two_way"] else "one-way roads")

    def add_place():
        choice = S.get(f"{k}_city")
        if not choice:
            return
        city = city_index().get(choice) or geo.lookup(choice)
        name = city.name if city else choice.strip()
        inputs, _ = lab.work()
        if N.find_place(inputs, name):
            S[f"{k}_msg"] = f"{name} is already there."
            return
        inputs["places"].append(N.place(name, city=city))
        frm = S.get(f"{k}_link")
        if frm and N.find_place(inputs, frm):
            N.add_route(inputs, frm, name, capacity=None if short else 10)
        lab.commit(inputs, note=f"+ {name}")
        S[f"{k}_msg"] = f"Added {name}." + ("" if city else " It is not in the city list: type its road lengths by hand.")
        S[f"{k}_city"] = None

    def edit_roads(key):
        ed, (inputs, rules) = S[key], lab.work()
        old = list(inputs["routes"])
        field = "length" if short else "capacity"
        col = "Length" if short else "Capacity"
        for i, ch in ed["edited_rows"].items():
            r = old[int(i)]
            if col in ch:
                v = ch[col]
                blank = v is None or (isinstance(v, float) and math.isnan(v))
                r[field] = (0.0 if short else None) if blank else float(v)
        for i in sorted(ed["deleted_rows"], reverse=True):
            inputs["routes"].remove(old[i])
        for row in ed["added_rows"]:
            if row.get("From") and row.get("To"):
                v = row.get(col)
                N.add_route(inputs, row["From"], row["To"], length=v if short else None, capacity=None if short else v)
        lab.commit(inputs, keep(rules, inputs), note="roads table")

    def edit_places(key):
        ed, (inputs, rules) = S[key], lab.work()
        names = [p["name"] for p in inputs["places"]]
        for i, ch in ed["edited_rows"].items():
            new = (ch.get("Place") or "").strip()
            if new and new != names[int(i)] and not N.find_place(inputs, new):
                old = names[int(i)]
                N.rename_place(inputs, old, new)
                for rule in rules:
                    a, b = rule["decision"].split(" → ")
                    rule["decision"] = N.route_key(new if a == old else a, new if b == old else b)
        for i in sorted(ed["deleted_rows"], reverse=True):
            N.remove_place(inputs, names[i])
        for row in ed["added_rows"]:
            name = (row.get("Place") or "").strip()
            if name and not N.find_place(inputs, name):
                inputs["places"].append(N.place(name))
        lab.commit(inputs, keep(rules, inputs), note="places table")

    def read_paste():
        inputs, msg = N.from_paste(lab.inputs, S[f"{k}_paste"], kind)
        S[f"{k}_msg"] = msg
        if inputs is not lab.inputs:
            lab.commit(inputs, keep(lab.rules, inputs), note="pasted roads")

    def set_road(key_, slider):
        inputs, _ = lab.work()
        r = N.find_route(inputs, key_)
        field = "length" if short else "capacity"
        before = r[field]
        if before is not None and abs(float(S[slider]) - before) < 1e-9:
            return
        r[field] = float(S[slider])
        lab.commit(inputs, note=f"{N.route_key(r['from'], r['to'])} {num(before) if before is not None else 'no limit'} "
                                f"→ {num(r[field])} {mt.unit(inputs)}")

    def keep(rules, inputs):
        keys = {a for a, *_ in N.arcs(inputs)}
        return [r for r in rules if r["decision"] in keys]

    # ---------- canvas

    def positions(inputs):
        """Places with a spot on the map are drawn where they are; the rest in layers from the start."""
        placed = [p for p in inputs["places"] if p["lat"] is not None]
        pos = {}
        if placed:
            lats, lons = [p["lat"] for p in placed], [p["lon"] for p in placed]
            # schematic: fill the canvas (the true shapes are on the map next to it)
            w, h = max(max(lons) - min(lons), 0.5), max(max(lats) - min(lats), 0.5)
            for p in placed:
                pos[p["name"]] = ((p["lon"] - min(lons)) / w * 640 + 10, (max(lats) - p["lat"]) / h * 420 + 10)
        rest = [p["name"] for p in inputs["places"] if p["name"] not in pos]
        if rest:
            depth = {inputs.get("start"): 0}
            nxt = {}
            for _, a, b, _ in N.arcs(inputs):
                nxt.setdefault(a, []).append(b)
            todo = [inputs.get("start")]
            while todo:
                a = todo.pop(0)
                for b in nxt.get(a, []):
                    if b not in depth:
                        depth[b] = depth[a] + 1
                        todo.append(b)
            row = {}
            for n in rest:
                d = depth.get(n, max(depth.values(), default=0) + 1)
                pos[n] = (20 + 150 * d, 30 + 110 * row.get(d, 0))
                row[d] = row.get(d, 0) + 1
        return pos

    def flow_state(inputs, result, solved, teach):
        pos = positions(inputs) | {n: v for n, v in lab.s["pos"].items() if v}
        plan = result.plan if (solved and result.ok) else {}
        cut = set(N.min_cut(inputs, plan)[1]) if (not short and plan) else set()
        reach = N.min_cut(inputs, plan)[0] if (not short and plan) else set()
        route = N.path(inputs, plan) if (short and plan) else []
        on_route = {N.route_key(a, b) for a, b in zip(route, route[1:])}
        biggest = max((v for kk, v in plan.items() if kk != "total"), default=0) or 1
        nodes = []
        for p in inputs["places"]:
            n = p["name"]
            fill = "#ffffff"
            extra = ""
            if n == inputs.get("start"):
                fill, extra = "#dbeafe", "  \nstart"
            elif n == inputs.get("end"):
                fill, extra = "#fde2e2", "  \nend"
            if teach:
                d = teach["dist"].get(n)
                extra = "  \n" + (f"**{num(round(d, 1))}**" if d is not None else "∞")
                if n in teach["done"]:
                    fill = "#d1fae5"
                if n == teach["settle"]:
                    fill = "#fde68a"
            elif cut and n in reach:
                fill = "#dbeafe"
            nodes.append(StreamlitFlowNode(
                n, pos[n], {"content": f"**{n}**{extra}"}, node_type="default",
                source_position="right", target_position="left", connectable=True, draggable=True,
                style={"background": fill, "fontSize": "15px", "width": "118px", "padding": "4px"}))
        edges = []
        shown = set()
        for key_, a, b, r in N.arcs(inputs):
            if inputs.get("two_way"):
                pair = frozenset((a, b))
                if pair in shown:
                    continue
                shown.add(pair)
            back = N.route_key(b, a)
            if short:
                used = key_ in on_route or (inputs.get("two_way") and back in on_route)
                label = f"{num(r['length'])}"
                if teach:   # Dijkstra's tree so far: the road each place was last reached by
                    used = teach["prev"].get(b) == a or teach["prev"].get(a) == b
                    style = {"stroke": "#16a34a" if used else "#b0b0b0", "strokeWidth": 4 if used else 1.3}
                else:
                    style = {"stroke": "#1f6feb" if used else "#b0b0b0", "strokeWidth": 5 if used else 1.3,
                             "strokeDasharray": "" if used or not plan else "4 4"}
                edges.append(StreamlitFlowEdge(
                    key_, r["from"], r["to"], edge_type="default", animated=bool(used), deletable=True,
                    focusable=True, label=label, label_show_bg=True,
                    label_style={"fontSize": "14px", "fontWeight": 700 if used else 400},
                    label_bg_style={"fill": "#ffffff", "fillOpacity": 0.85},
                    marker_end={"type": "arrowclosed"}, style=style,
                    marker_start={"type": "arrowclosed"} if inputs.get("two_way") else {"type": ""}))
            else:
                flow = plan.get(key_, 0.0)
                cap = r.get("capacity")
                is_cut = key_ in cut
                label = (f"{num(round(flow, 2))} / {num(cap) if cap is not None else '∞'}" if plan
                         else (num(cap) if cap is not None else "∞"))
                edges.append(StreamlitFlowEdge(
                    key_, a, b, edge_type="default", animated=flow > TOL, deletable=True, focusable=True,
                    label=label, label_show_bg=True,
                    label_style={"fontSize": "14px", "fontWeight": 700 if is_cut else 400,
                                 "fill": "#b91c1c" if is_cut else "#222"},
                    label_bg_style={"fill": "#ffffff", "fillOpacity": 0.85}, marker_end={"type": "arrowclosed"},
                    style={"stroke": "#dc2626" if is_cut else "#1f6feb" if flow > TOL else "#b0b0b0",
                           "strokeWidth": (1.5 + 5 * flow / biggest) if flow > TOL else 1.3,
                           "strokeDasharray": "6 3" if is_cut else ""}))
        return StreamlitFlowState(nodes, edges)

    def canvas(inputs, result, solved, teach):
        sig = json.dumps([inputs, result.plan if solved else {}, teach], sort_keys=True, default=str)
        if S.get(f"{k}_flow_sig") != sig:
            S[f"{k}_flow"] = flow_state(inputs, result, solved, teach)
            S[f"{k}_flow_sig"] = sig
        sent = S[f"{k}_flow"]
        got = streamlit_flow(f"{k}_canvas", sent, height=470, fit_view=True, allow_new_edges=True,
                             get_edge_on_click=True, enable_edge_menu=True, show_minimap=False,
                             hide_watermark=True, min_zoom=0.2, allow_zoom=False)
        if got.timestamp <= sent.timestamp:
            return
        for n in got.nodes:
            lab.s["pos"][n.id] = (n.position["x"], n.position["y"])
        if got.selected_id and got.selected_id in {e.id for e in sent.edges}:
            lab.s["selected"] = got.selected_id
        drawn = {(e.source, e.target) for e in got.edges}
        have = {(r["from"], r["to"]) for r in inputs["routes"]}
        if drawn != have:
            new, rules = lab.work()
            for a, b in drawn - have:
                N.add_route(new, a, b, capacity=None if short else 10)
            new["routes"] = [r for r in new["routes"] if (r["from"], r["to"]) in drawn]
            lab.commit(new, keep(rules, new), note=f"canvas: +{len(drawn - have)} / −{len(have - drawn)} roads")
            st.rerun()

    def map_view(inputs, result, solved):
        located = {p["name"]: p for p in inputs["places"] if p["lat"] is not None}
        if not located:
            st.info("Places you add from the city list appear on a map here.")
            return
        plan = result.plan if (solved and result.ok) else {}
        cut = set(N.min_cut(inputs, plan)[1]) if (not short and plan) else set()
        route = N.path(inputs, plan) if (short and plan) else []
        on_route = {frozenset(x) for x in zip(route, route[1:])}
        biggest = max((v for kk, v in plan.items() if kk != "total"), default=0) or 1
        role = lambda n: [31, 119, 180] if n == inputs.get("start") else [214, 39, 40] if n == inputs.get("end") \
            else [90, 90, 90]
        pts = [{"name": n, "lon": p["lon"], "lat": p["lat"], "color": role(n), "tip": n} for n, p in located.items()]
        lines = []
        for key_, a, b, r in N.arcs(inputs):
            pa, pb = located.get(a), located.get(b)
            if not (pa and pb):
                continue
            if short:
                used = frozenset((a, b)) in on_route
                if inputs.get("two_way") and (r["from"], r["to"]) != (a, b):
                    continue
                w, color = (7, [31, 111, 235, 230]) if used else (2, [150, 150, 150, 140])
                tip = f"{N.route_key(r['from'], r['to'])}: {num(r['length'])} {mt.unit(inputs)}"
            else:
                flow = plan.get(key_, 0.0)
                w = 2 + 10 * flow / biggest if flow > TOL else 1.5
                color = [220, 38, 38, 230] if key_ in cut else [31, 111, 235, 220] if flow > TOL else [150, 150, 150, 140]
                cap = r.get("capacity")
                tip = f"{key_}: {num(round(flow, 2))} of {num(cap) if cap is not None else 'no limit'}"
            lines.append({"from": [pa["lon"], pa["lat"]], "to": [pb["lon"], pb["lat"]], "w": w, "color": color,
                          "tip": tip})
        lats, lons = [p["lat"] for p in pts], [p["lon"] for p in pts]
        span = max(max(lats) - min(lats), (max(lons) - min(lons)) * math.cos(math.radians(sum(lats) / len(lats))), 0.5)
        deck = pdk.Deck(
            layers=[pdk.Layer("LineLayer", lines, get_source_position="from", get_target_position="to",
                              get_width="w", get_color="color", pickable=True, width_units=pdk.types.String("pixels")),
                    pdk.Layer("ScatterplotLayer", pts, get_position=["lon", "lat"], get_fill_color="color",
                              get_radius=9000, radius_min_pixels=6, radius_max_pixels=14, pickable=True,
                              stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=1.5),
                    pdk.Layer("TextLayer", pts, get_position=["lon", "lat"], get_text="name", get_size=15,
                              get_pixel_offset=[0, -20], get_color=[30, 30, 30], font_weight=600,
                              character_set=pdk.types.String("auto"))],
            initial_view_state=pdk.ViewState(latitude=(max(lats) + min(lats)) / 2, longitude=(max(lons) + min(lons)) / 2,
                                             zoom=max(2.0, min(10.0, math.log2(360 / span) - 1.1))),
            views=[pdk.View(type="MapView", controller={"scrollZoom": False})],
            map_style=pdk.map_styles.CARTO_LIGHT, tooltip={"text": "{tip}"})
        st.pydeck_chart(deck, height=470)

    # ---------- header

    inputs, rules = lab.inputs, lab.rules
    st.title(TEXT[kind]["title"])
    st.caption(TEXT[kind]["caption"])
    names = [p["name"] for p in inputs["places"]]
    c1, c2, c3, c4, c5 = st.columns([2, 1.2, 1.2, 1.1, 1], vertical_alignment="bottom")
    c1.selectbox("Start from", list(N.TEMPLATES[kind]), format_func=N.TEMPLATES[kind].get, key=f"{k}_template",
                 index=None, placeholder="Load an example …", on_change=load_template)
    for col, which, label in ((c2, "start", "From"), (c3, "end", "To")):
        col.selectbox(label, names, index=names.index(inputs[which]) if inputs.get(which) in names else None,
                      key=lab.w(which), on_change=set_end, args=(which,), placeholder="pick a place")
    if short:
        c4.toggle("Two-way roads", value=inputs["two_way"], key=lab.w("two_way"), on_change=set_two_way)
    else:
        c4.text_input("Unit", value=inputs["unit"], key=lab.w("unit"), on_change=set_text, args=("unit",))
    show_math = c5.toggle("Show the math", key=f"{k}_math")

    result = lab.solve()
    solved = lab.s["solved"]
    steps = N.dijkstra(inputs) if short and result.status != "invalid" else []
    teach = steps[lab.s["step"]] if (short and lab.s["step"] is not None and lab.s["step"] < len(steps)) else None

    left, right = st.columns([1.15, 1])
    with left:
        canvas(inputs, result, solved, teach)
        st.caption("Drag places to tidy up. **Draw a road:** drag from a place's right dot to another place. "
                   "**Delete a road:** right-click it. Click a road to pick it for a rule or a slider."
                   + (" Labels: flow / capacity; red dashed = the bottleneck (minimum cut)." if not short else ""))
    with right:
        map_view(inputs, result, solved)
        st.caption(":blue[●] start · :red[●] end · " + ("thick blue = the best route" if short else
                                                        "line width = flow · red = the bottleneck"))

    # ---------- the answer

    if not solved:
        st.button("Solve with CPLEX", type="primary", icon=":material/play_arrow:", on_click=lab.solve_now,
                  key=f"{k}_solve")
        st.caption("Change the network first if you like. After the first solve, every change re-solves at once.")
    elif lab.answer_problems(result):
        d, note = lab.delta(result)
        fmt = lab.fmt
        m1, m2, m3 = st.columns(3)
        if short:
            route = N.path(inputs, result.plan)
            m1.metric(f"Shortest route ({unit(inputs)})", num(round(result.objective, 2)),
                      delta=metric_delta(d, fmt), delta_color="inverse",
                      help=f"vs before your last change ({note})" if note else None)
            m2.metric("Roads on the route", len(route) - 1)
            m3.metric("Stops", " → ".join(route) if len(route) <= 4 else f"{route[0]} → … → {route[-1]}")
        else:
            _, cut, cap = N.min_cut(inputs, result.plan)
            m1.metric(f"Maximum flow ({unit(inputs)})", num(round(result.objective, 2)),
                      delta=metric_delta(d, fmt), help=f"vs before your last change ({note})" if note else None)
            m2.metric("Bottleneck roads (min cut)", len(cut))
            m3.metric("Roads used", f"{sum(v > TOL for kk, v in result.plan.items() if kk != 'total')} of "
                                    f"{len(result.plan) - 1}")
        if note and d is not None:
            st.caption(f"Last change: {note}")
        lab.summary(result)
    if solved and result.warnings:
        st.info("  \n".join(result.warnings), icon=":material/info:")

    if show_math:
        lab.math(result, "An LP gives a whole-number answer here by itself: the constraint matrix is totally unimodular."
                 + (" The duals of the balance rows are the distances Dijkstra finds." if short else
                    " Max-flow = min-cut: the LP's dual is the cheapest cut."))

    # ---------- tabs

    labels = [":material/construction: Build", ":material/tune: Live sliders",
              ":material/school: " + ("Dijkstra step by step" if short else "The bottleneck (min cut)"),
              ":material/search: What limits you?", ":material/lock: Rules",
              ":material/target: Beat the solver", ":material/compare: Scenarios"]
    t_build, t_live, t_teach, t_limits, t_rules, t_guess, t_scn = lab.tabs(labels)
    keys = [a for a, *_ in N.arcs(inputs)]

    with t_build:
        a, b = st.columns([1, 2.2])
        with a:
            st.markdown("**Add a place**")
            st.selectbox("City", list(city_index()), key=f"{k}_city", index=None, accept_new_options=True,
                         placeholder="Type a city …", help="From the bundled city list. A name that is not a city "
                                                           "still works, without a spot on the map.")
            st.selectbox("Road from (optional)", names, key=f"{k}_link", index=None, placeholder="no road yet")
            st.button("Add place", icon=":material/add_location:", on_click=add_place, width="stretch",
                      key=f"{k}_add")
            if S.get(f"{k}_msg"):
                st.caption(S[f"{k}_msg"])
        with b:
            st.markdown("**Places**")
            pdf = pd.DataFrame([{"Place": p["name"], "On map": "✓" if p["lat"] is not None else "—"}
                                for p in inputs["places"]], columns=["Place", "On map"])
            st.data_editor(pdf, key=lab.w("places"), num_rows="dynamic", width="stretch", hide_index=True,
                           on_change=edit_places, args=(lab.w("places"),),
                           column_config={"On map": st.column_config.TextColumn(disabled=True, width="small")})
            st.markdown("**Roads**")
            col = "Length" if short else "Capacity"
            rdf = pd.DataFrame([{"From": r["from"], "To": r["to"], "Road km": r["km"],
                                 col: r["length"] if short else r.get("capacity")} for r in inputs["routes"]],
                               columns=["From", "To", "Road km", col])
            st.data_editor(rdf, key=lab.w("roads"), num_rows="dynamic", width="stretch", hide_index=True,
                           on_change=edit_roads, args=(lab.w("roads"),),
                           column_config={"From": st.column_config.SelectboxColumn(options=names),
                                          "To": st.column_config.SelectboxColumn(options=names),
                                          "Road km": st.column_config.NumberColumn(disabled=True, format="%.0f"),
                                          col: st.column_config.NumberColumn(
                                              min_value=0, help=f"in {unit(inputs)}" + ("" if short else "; blank = no limit"))})
            if short:
                a2, b2 = st.columns(2)
                a2.text_input("Length is measured in", value=inputs["measure"], key=lab.w("measure"),
                              on_change=set_text, args=("measure",), help="km, minutes, € … (road km by default)")
            with st.expander("Paste roads from Excel or CSV"):
                st.markdown(f"One road per row: **from, to, {'length' if short else 'capacity'}**. "
                            "New places are added. German number format is fine.")
                st.text_area("Paste here", key=f"{k}_paste", height=120, placeholder="Hamburg\tHannover\t160\nHannover\tKassel\t165")
                st.button("Read the roads", on_click=read_paste, key=f"{k}_read")

    with t_live:
        if not solved:
            st.info("Solve first; then every slider re-solves at once.")
        elif keys:
            st.markdown("Pick a road (or click it on the canvas) and move its slider: CPLEX re-solves at once.")
            road_keys = [N.route_key(r["from"], r["to"]) for r in inputs["routes"]]
            sel = lab.s["selected"]
            sel = sel if sel in road_keys else (N.route_key(*sel.split(" → ")[::-1]) if sel and
                                                N.route_key(*sel.split(" → ")[::-1]) in road_keys else None)
            if sel is None and result.ok:   # default: a road that matters now
                if short:
                    route = N.path(inputs, result.plan)
                    on = [N.route_key(a, b) for a, b in zip(route, route[1:])]
                    sel = next((r for r in road_keys if r in on or N.route_key(*r.split(" → ")[::-1]) in on), None)
                else:
                    cut = N.min_cut(inputs, result.plan)[1]
                    sel = cut[0] if cut and cut[0] in road_keys else None
            pick = st.selectbox("Road", road_keys, index=road_keys.index(sel) if sel in road_keys else 0,
                                key=lab.w("live_pick"))
            r = N.find_route(inputs, pick)
            now = r["length"] if short else (r.get("capacity") or 0.0)
            top = float(max(10, math.ceil(now * 2 / 10) * 10))
            sk = lab.w("live")
            st.slider(f"{pick}: {'length' if short else 'capacity'} ({unit(inputs)})", 0.0, top, float(now), 1.0,
                      key=sk, format="%.0f", on_change=set_road, args=(pick, sk))
            if result.ok:
                dec = result.decisions.get(pick)
                if short and dec:
                    if dec.value > 0.5 and dec.cost_high < 1e19:
                        st.caption(f"This road is on the best route: it stays there up to {num(round(dec.cost_high, 2))} "
                                   f"{unit(inputs)}.")
                    elif dec.value < 0.5 and dec.reduced_cost > TOL:
                        st.caption(f"Not on the best route: it would have to get {num(round(dec.reduced_cost, 2))} "
                                   f"{unit(inputs)} shorter to join it.")
                elif not short:
                    lim = result.limit(f"cap:{pick}")
                    if lim and lim.binding and abs(lim.dual) > TOL:
                        st.caption(f"Full, and on the bottleneck: one more {unit(inputs).split('/')[0].rstrip('s')} "
                                   f"of room adds {num(round(lim.dual, 2))} to the maximum (up to "
                                   f"{num(round(lim.rhs_high, 2))}).")
                    elif lim and lim.slack > TOL:
                        st.caption(f"{num(round(lim.slack, 2))} {unit(inputs)} of room left: not a bottleneck.")

    with t_teach:
        if short:
            st.markdown("#### Dijkstra, step by step")
            st.caption("The hand method: settle the closest open place, then update its neighbours. "
                       "Watch the canvas: yellow = settled now, green = settled, numbers = best distance so far.")
            if not steps:
                st.info("Complete the network first.")
            else:
                a, b, c = st.columns([1, 1, 3], vertical_alignment="center")
                i = lab.s["step"]
                if a.button("◀ Back", disabled=i is None, key=f"{k}_back"):
                    lab.s["step"] = None if i in (None, 0) else i - 1
                    st.rerun()
                if b.button("Next ▶" if i is not None else "Start", type="primary",
                            disabled=i is not None and i >= len(steps) - 1, key=f"{k}_next"):
                    lab.s["step"] = 0 if i is None else i + 1
                    st.rerun()
                if i is not None:
                    s_ = steps[i]
                    upd = ", ".join(f"{u} → {num(round(s_['dist'][u], 2))} (via {s_['prev'][u]})" for u in s_["updated"])
                    c.markdown(f"**Step {i + 1} of {len(steps)}:** settle **{s_['settle']}** at "
                               f"{num(round(s_['dist'][s_['settle']], 2))}. " + (f"Updated: {upd}." if upd else
                                                                                   "Nothing to update."))
                    rows = [{"Place": n, "Best so far": num(round(s_["dist"][n], 2)) if n in s_["dist"] else "∞",
                             "Via": s_["prev"].get(n, "—"), "Settled": "✓" if n in s_["done"] else ""}
                            for n in names]
                    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
                    if i == len(steps) - 1:
                        st.success(f"Done: {' → '.join(N.dijkstra_path(steps, inputs['end']))}, "
                                   f"{num(round(s_['dist'][inputs['end']], 2))} {unit(inputs)}. "
                                   "Same answer as the LP (CPLEX)." if result.ok and abs(
                                       s_['dist'][inputs['end']] - result.objective) < 1e-6 else "Done.")
                    st.button("Leave teach mode", key=f"{k}_leave", on_click=lambda: lab.s.update(step=None))
        else:
            st.markdown("#### The bottleneck: maximum flow = minimum cut")
            if not (solved and result.ok):
                st.info("Solve first.")
            else:
                reach, cut, cap = N.min_cut(inputs, result.plan)
                st.markdown(f"Draw a line around the places the network can still reach from **{inputs['start']}** "
                            f"through roads with room left: **{', '.join(sorted(reach))}** (blue on the canvas). "
                            f"Every road leaving that group is full: **{', '.join(cut)}**. "
                            f"Their capacities add up to **{num(round(cap, 2))}**, exactly the maximum flow.")
                st.markdown("Everything sent must cross that line, so no plan can beat it. That's the max-flow "
                            "min-cut theorem: the LP and the cut give the same number.")
                st.dataframe(pd.DataFrame([{"Cut road": c_, "Capacity": num(N.find_route(inputs, c_).get("capacity") or 0)}
                                           for c_ in cut]), hide_index=True, width="stretch")
                st.caption("Several cuts can tie: then more room on one of them alone may not help (the next one holds).")

    with t_limits:
        if not (solved and result.ok):
            st.info("Solve a model that works to see what limits it.")
        elif short:
            st.markdown("#### How sure is this route?")
            rows = []
            for d in result.decisions.values():
                if d.value > 0.5:
                    rows.append({"Road": d.label, "On the route": "✓", "Length": num(d.cost),
                                 "Route stays best up to": "any length" if d.cost_high >= 1e19 else num(round(d.cost_high, 2))})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            close = sorted((d for d in result.decisions.values() if d.value < 0.5 and d.reduced_cost > TOL),
                           key=lambda d: d.reduced_cost)[:6]
            if close:
                st.markdown("**Closest alternatives** (how much shorter each road would have to be to join the route):")
                for d in close:
                    st.markdown(f"• {d.label}: {num(round(d.reduced_cost, 2))} {unit(inputs)} shorter")
        else:
            st.markdown("#### What limits you?")
            st.caption("Shadow prices (CPLEX duals): what one more unit of room on a road adds to the maximum.")
            full = [l for l in result.limits if l.kind == "capacity" and l.binding]
            for l in sorted(full, key=lambda l: -abs(l.dual)):
                st.markdown(f"• **{l.words}** (full) " + (f"→ one more adds {num(round(l.dual, 2))}" if abs(l.dual) > TOL
                                                        else "→ more room alone adds nothing"))
            spare = [l for l in result.limits if l.kind == "capacity" and l.slack > TOL]
            if spare:
                st.markdown("**Room left:** " + "; ".join(f"{l.label.replace('room on ', '')} {num(round(l.slack, 2))}"
                                                          for l in spare) + ".")

    with t_rules:
        lab.rules_tab(result, keys, "trips" if short else unit(inputs), step=1.0, what="road")
        if short:
            st.caption("Ban a road (roadworks, a toll you avoid) or force one (a stop on the way: at least 1).")

    with t_guess:
        st.markdown("#### Beat the solver")
        if short:
            st.caption("Guess first: pick the places of your route in order, from start to end. Then reveal the optimum.")
            with st.form(f"{k}_guess_form", border=False):
                pick = st.multiselect("Your route", names, default=lab.s["guess"].get("_stops", [inputs.get("start")]
                                                                                       if inputs.get("start") else []),
                                      key=lab.w("guess"))
                score, reveal = lab.reveal_buttons()
            plan = {"_stops": pick}
            plan.update({N.route_key(a, b): 1.0 for a, b in zip(pick, pick[1:])})
            lab.after_guess(score, reveal, plan)
            if lab.s["scored"]:
                guess = lab.s["guess"]
                stops = guess.get("_stops", [])
                missing = [N.route_key(a, b) for a, b in zip(stops, stops[1:]) if N.route_key(a, b) not in keys]
                if missing:
                    st.error("There is no road " + ", ".join(missing) + ".")
                else:
                    ev = engine.evaluate(mt, inputs, rules, {kk: v for kk, v in guess.items() if kk != "_stops"},
                                         result if lab.s["revealed"] else None)
                    lab.guess_feedback(ev, result)
        else:
            st.caption("Guess first: how much goes on each road? The total is what leaves the start. "
                       "Score it, then reveal the optimum.")
            gdf = pd.DataFrame([{"Road": kk, "Capacity": r.get("capacity"), "Your plan": lab.s["guess"].get(kk, 0.0)}
                                for kk, _, _, r in N.arcs(inputs)], columns=["Road", "Capacity", "Your plan"])
            with st.form(f"{k}_guess_form", border=False):
                ed = st.data_editor(gdf, key=lab.w("guess"), hide_index=True, width="stretch",
                                    column_config={"Road": st.column_config.TextColumn(disabled=True),
                                                   "Capacity": st.column_config.NumberColumn(disabled=True),
                                                   "Your plan": st.column_config.NumberColumn(min_value=0, step=1)})
                score, reveal = lab.reveal_buttons()
            plan = {r["Road"]: 0.0 if pd.isna(r["Your plan"]) else float(r["Your plan"]) for r in ed.to_dict("records")}
            s_ = inputs.get("start")
            plan["total"] = sum(v for kk, v in plan.items() if kk.split(" → ")[0] == s_) - \
                sum(v for kk, v in plan.items() if kk.split(" → ")[-1] == s_)
            lab.after_guess(score, reveal, plan)
            if lab.s["scored"]:
                ev = engine.evaluate(mt, inputs, rules, lab.s["guess"], result if lab.s["revealed"] else None)
                lab.guess_feedback(ev, result)

    with t_scn:
        lab.scenarios_tab(TEXT[kind]["scenario"], money_sign="")
