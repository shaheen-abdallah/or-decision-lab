"""Where should I ship from? The transport builder (transportation + transshipment, min-cost flow).

Picture (network canvas + map) on top, the answer in words below, then tabs: build · live sliders ·
what limits you · rules (price of a rule) · beat the solver · scenarios. "Show the math" puts the
formulation next to the words. Every change goes through `commit()`, which re-solves (cached, ~40 ms).
"""

import copy
import json
import math

import pandas as pd
import pydeck as pdk
import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState

from plantlab import engine, geo
from plantlab.engine import latex, scenarios, words
from plantlab.engine.core import TOL, num, rule_words
from plantlab.engine.words import money
from plantlab.models import transport as T

M = T.MODEL
S = st.session_state
ROLE_LABEL = {"supplier": "Supplier (ships out)", "customer": "Customer (needs)", "hub": "Hub (passes on)"}
ROLE_COLOR = {"supplier": [31, 119, 180], "customer": [214, 39, 40], "hub": [120, 120, 120]}
ROLE_FILL = {"supplier": "#dbeafe", "customer": "#fde2e2", "hub": "#eeeeee"}
OPS = ["ban", "exactly", "at least", "at most"]


# ---------- state: one dict, every change through commit()

if "tp" not in S:
    S.tp = {"inputs": T.template("3x4"), "rules": [], "rev": 0, "solved": False, "pos": {},
            "scenarios": [], "delta": None, "selected": None, "guess": {}, "scored": False, "revealed": False}
tp = S.tp


@st.cache_data(max_entries=300, show_spinner=False)
def _solve(inputs_json, rules_json):
    return engine.solve(M, json.loads(inputs_json), json.loads(rules_json))


def solve(inputs=None, rules=None):
    inputs = tp["inputs"] if inputs is None else inputs
    rules = tp["rules"] if rules is None else rules
    return _solve(json.dumps(inputs, sort_keys=True), json.dumps(rules, sort_keys=True))


def commit(inputs=None, rules=None, note=""):
    """Apply a change; remember the objective before it so the page can show the difference."""
    before = solve()
    tp["delta"] = (note, before.objective if before.ok else None)
    if inputs is not None:
        tp["inputs"] = inputs
    if rules is not None:
        tp["rules"] = rules
    tp["rev"] += 1


def work():
    """Copies to edit: (inputs, rules)."""
    return copy.deepcopy(tp["inputs"]), copy.deepcopy(tp["rules"])


def units():
    return T.plural(M.unit(tp["inputs"]))


def drop_rules(rules, inputs):
    keys = {T.route_key(r["from"], r["to"]) for r in inputs["routes"]}
    return [r for r in rules if r["decision"] in keys]


@st.cache_resource
def city_index():
    return {c.label: c for c in geo.cities()}


# ---------- callbacks (run before the page, so the page always shows the new state)

def load_template():
    key = S.tp_template
    commit(T.template(key), [], note=f"template: {T.TEMPLATES[key]}")
    tp.update(solved=False, pos={}, guess={}, scored=False, revealed=False, selected=None,
              delta=(f"template: {T.TEMPLATES[key]}", None))   # no cost difference across templates


def set_unit():
    inputs, _ = work()
    inputs["unit"] = S.tp_unit.strip() or "unit"
    commit(inputs, note="unit")


def set_rate(key):
    inputs, _ = work()
    old = inputs["cost_per_km"]
    if abs(float(S[key]) - old) < 1e-9:
        return
    inputs["cost_per_km"] = float(S[key])
    commit(T.reprice(inputs), note=f"cost per km {money(old, cents=True)} → {money(inputs['cost_per_km'], cents=True)}")


def add_place():
    choice, role, amount = S.tp_city, S.tp_role, S.tp_amount
    if not choice:
        return
    city = city_index().get(choice) or geo.lookup(choice)   # a typed name that is a known city counts too
    name = city.name if city else choice.strip()
    inputs, rules = work()
    if T.find_place(inputs, name):
        S.tp_msg = f"{name} is already on the map."
        return
    inputs["places"].append(T.place(name, role, amount, city=city))
    commit(inputs, note=f"+ {name}")
    S.tp_msg = f"Added {name}." + ("" if city else " It is not in the city list: type its route costs by hand.")
    S.tp_city = None


def connect_all():
    inputs, _ = work()
    n = T.connect_all(inputs)
    commit(inputs, note=f"+ {n} routes")


def solve_now():
    tp["solved"] = True


def edit_places(key):
    ed, (inputs, rules) = S[key], work()
    names = [p["name"] for p in inputs["places"]]
    for i, ch in ed["edited_rows"].items():
        p = inputs["places"][int(i)]
        new = (ch.get("Place") or "").strip()
        if new and new != p["name"]:
            old = p["name"]
            p["name"] = new
            for r in inputs["routes"]:
                r["from"] = new if r["from"] == old else r["from"]
                r["to"] = new if r["to"] == old else r["to"]
            for rule in rules:
                a, b = rule["decision"].split(" → ")
                rule["decision"] = T.route_key(new if a == old else a, new if b == old else b)
            tp["pos"][new] = tp["pos"].pop(old, None)
        if ch.get("Role") in T.ROLES:
            p["role"] = ch["Role"]
        if "Amount" in ch:
            p["amount"] = float(ch["Amount"] or 0)
    for row in ed["added_rows"]:
        name = (row.get("Place") or "").strip()
        if name and not T.find_place(inputs, name):
            inputs["places"].append(T.place(name, row.get("Role") or "customer", row.get("Amount") or 0))
    for i in sorted(ed["deleted_rows"], reverse=True):
        T.remove_place(inputs, names[i])
    commit(inputs, drop_rules(rules, inputs), note="places table")


def edit_routes(key):
    ed, (inputs, rules) = S[key], work()
    old = list(inputs["routes"])
    for i, ch in ed["edited_rows"].items():
        r = old[int(i)]
        if "Cost" in ch and ch["Cost"] is not None:
            r["cost"], r["manual"] = float(ch["Cost"]), True
        if "Capacity" in ch:
            r["capacity"] = None if ch["Capacity"] is None or (isinstance(ch["Capacity"], float) and math.isnan(ch["Capacity"])) \
                else float(ch["Capacity"])
    for i in sorted(ed["deleted_rows"], reverse=True):
        inputs["routes"].remove(old[i])
    for row in ed["added_rows"]:
        if row.get("From") and row.get("To"):
            T.add_route(inputs, row["From"], row["To"], cost=row.get("Cost"), capacity=row.get("Capacity"))
    commit(inputs, drop_rules(rules, inputs), note="routes table")


def read_paste():
    inputs, msg = T.from_paste(tp["inputs"], S.tp_paste)
    S.tp_msg = msg
    if inputs is not tp["inputs"]:
        commit(inputs, drop_rules(tp["rules"], inputs), note="pasted table")
        tp["pos"] = {}


def set_amount(name, key):
    inputs, _ = work()
    p = T.find_place(inputs, name)
    before = p["amount"]
    if abs(float(S[key]) - before) < 1e-9:
        return
    p["amount"] = float(S[key])
    commit(inputs, note=f"{name} {num(before)} → {num(p['amount'])}")


def set_route_cost(route, key):
    inputs, _ = work()
    r = next(r for r in inputs["routes"] if T.route_key(r["from"], r["to"]) == route)
    before = r["cost"]
    if abs(float(S[key]) - before) < 0.005:
        return
    r["cost"], r["manual"] = float(S[key]), True
    commit(inputs, note=f"{route} {money(before, cents=True)} → {money(r['cost'], cents=True)}")


def add_rule(route, op, value):
    _, rules = work()
    rules = [r for r in rules if r["decision"] != route] + [{"decision": route, "op": op, "value": float(value or 0)}]
    commit(rules=rules, note=rule_words(rules[-1], units()))


def remove_rule(i):
    _, rules = work()
    gone = rules.pop(i)
    commit(rules=rules, note="− " + rule_words(gone, units()))


def apply_fix(i):
    fix = solve().fixes[i]
    inputs, rules = engine.apply_fix(M, tp["inputs"], tp["rules"], fix)
    commit(inputs, rules, note="fix: " + fix.words)


def save_scenario():
    name = (S.tp_scn_name or "").strip() or f"Scenario {len(tp['scenarios']) + 1}"
    tp["scenarios"] = [s for s in tp["scenarios"] if s["name"] != name]
    tp["scenarios"].append(scenarios.snapshot(name, M, tp["inputs"], tp["rules"], solve()))
    S.tp_scn_name = ""


def load_scenario():
    s = next(s for s in tp["scenarios"] if s["name"] == S.tp_scn_pick)
    commit(copy.deepcopy(s["inputs"]), copy.deepcopy(s["rules"]), note=f"loaded {s['name']}")
    tp["solved"] = True


def import_scenarios():
    f = S.tp_scn_file
    if f is not None:
        loaded = [s for s in scenarios.loads(f.getvalue().decode("utf-8")) if s.get("model") == M.key]
        names = {s["name"] for s in loaded}
        tp["scenarios"] = [s for s in tp["scenarios"] if s["name"] not in names] + loaded


# ---------- the picture: network canvas + map

def default_pos(inputs):
    """Classic network drawing: suppliers left, hubs middle, customers right."""
    col = {"supplier": 20, "hub": 250, "customer": 480}
    seen = {r: 0 for r in T.ROLES}
    pos = {}
    for p in inputs["places"]:
        pos[p["name"]] = (col[p["role"]], 20 + seen[p["role"]] * 95)
        seen[p["role"]] += 1
    return pos


def flow_state(inputs, result, show_flows):
    pos = default_pos(inputs) | {k: v for k, v in tp["pos"].items() if v}
    plan = result.plan if (show_flows and result.ok) else {}
    biggest = max(plan.values(), default=0) or 1
    nodes = []
    for p in inputs["places"]:
        amount = "" if p["role"] == "hub" and not p["amount"] else f"  \n{num(p['amount'])}"
        nodes.append(StreamlitFlowNode(
            p["name"], pos[p["name"]], {"content": f"**{p['name']}**{amount}"},
            node_type={"supplier": "input", "customer": "output", "hub": "default"}[p["role"]],
            source_position="right", target_position="left", connectable=True, draggable=True,
            style={"background": ROLE_FILL[p["role"]], "fontSize": "15px", "width": "130px", "padding": "6px"}))
    edges = []
    for r in inputs["routes"]:
        k = T.route_key(r["from"], r["to"])
        flow = plan.get(k, 0.0)
        used = flow > TOL
        label = f"{num(flow)} × {money(r['cost'], cents=True)}" if used else money(r["cost"], cents=True)
        if r.get("capacity") is not None:
            label += f" (max {num(r['capacity'])})"
        edges.append(StreamlitFlowEdge(
            k, r["from"], r["to"], edge_type="default", animated=used, deletable=True, focusable=True,
            label=label if (used or not plan) else "", label_show_bg=True,
            label_style={"fontSize": "14px", "fontWeight": 600 if used else 400},
            label_bg_style={"fill": "#ffffff", "fillOpacity": 0.85},
            marker_end={"type": "arrowclosed"},
            style={"stroke": "#1f6feb" if used else "#b0b0b0", "strokeDasharray": "" if used or not plan else "4 4",
                   "strokeWidth": 1.5 + 5 * flow / biggest if used else 1.2}))
    return StreamlitFlowState(nodes, edges)


def canvas(inputs, result, show_flows):
    sig = json.dumps([inputs["places"], inputs["routes"], result.plan if show_flows else {}], sort_keys=True, default=str)
    if S.get("tp_flow_sig") != sig:
        S.tp_flow = flow_state(inputs, result, show_flows)
        S.tp_flow_sig = sig
    sent = S.tp_flow
    got = streamlit_flow("tp_canvas", sent, height=430, fit_view=False, allow_new_edges=True,
                         get_edge_on_click=True, enable_edge_menu=True, show_minimap=False,
                         hide_watermark=True, min_zoom=0.2, allow_zoom=False)
    if got.timestamp <= sent.timestamp:   # nothing new from the canvas (or an old value)
        return
    for n in got.nodes:
        tp["pos"][n.id] = (n.position["x"], n.position["y"])
    if got.selected_id and got.selected_id in {e.id for e in sent.edges}:
        tp["selected"] = got.selected_id
    drawn = {(e.source, e.target) for e in got.edges}
    have = {(r["from"], r["to"]) for r in inputs["routes"]}
    if drawn != have:
        new, rules = work()
        for a, b in drawn - have:
            T.add_route(new, a, b)
        new["routes"] = [r for r in new["routes"] if (r["from"], r["to"]) in drawn]
        added, removed = len(drawn - have), len(have - drawn)
        commit(new, drop_rules(rules, new), note=f"canvas: +{added} / −{removed} routes")
        st.rerun()


def zoom_for(lats, lons):
    span = max(max(lats) - min(lats), (max(lons) - min(lons)) * math.cos(math.radians(sum(lats) / len(lats))), 0.5)
    return max(2.0, min(10.0, math.log2(360 / span) - 1.1))


def map_view(inputs, result, show_flows):
    located = {p["name"]: p for p in inputs["places"] if p["lat"] is not None}
    if not located:
        st.info("Places you add from the city list appear on the map.")
        return
    plan = result.plan if (show_flows and result.ok) else {}
    biggest = max(plan.values(), default=0) or 1
    pts = [{"name": n, "lon": p["lon"], "lat": p["lat"], "color": ROLE_COLOR[p["role"]],
            "tip": f"{n}: {p['role']} {num(p['amount'])}", "r": 9000 + 14000 * math.sqrt(max(p["amount"], 0) / 500)}
           for n, p in located.items()]
    lines = []
    for r in inputs["routes"]:
        a, b = located.get(r["from"]), located.get(r["to"])
        if not (a and b):
            continue
        flow = plan.get(T.route_key(r["from"], r["to"]), 0.0)
        if plan and flow <= TOL:
            continue
        lines.append({"from": [a["lon"], a["lat"]], "to": [b["lon"], b["lat"]],
                      "w": 2 + 10 * flow / biggest if flow else 1.5,
                      "color": [31, 111, 235, 220] if flow else [150, 150, 150, 140],
                      "tip": f"{T.route_key(r['from'], r['to'])}: {num(flow)} × {money(r['cost'], cents=True)}"
                      if flow else f"{T.route_key(r['from'], r['to'])}: {money(r['cost'], cents=True)}"})
    lats, lons = [p["lat"] for p in pts], [p["lon"] for p in pts]
    deck = pdk.Deck(
        layers=[pdk.Layer("LineLayer", lines, get_source_position="from", get_target_position="to",
                          get_width="w", get_color="color", pickable=True,
                          width_units=pdk.types.String("pixels")),
                pdk.Layer("ScatterplotLayer", pts, get_position=["lon", "lat"], get_fill_color="color",
                          get_radius="r", radius_min_pixels=6, radius_max_pixels=22, pickable=True,
                          stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=1.5),
                pdk.Layer("TextLayer", pts, get_position=["lon", "lat"], get_text="name", get_size=15,
                          get_pixel_offset=[0, -22], get_color=[30, 30, 30], font_weight=600,
                          character_set=pdk.types.String("auto"))],
        initial_view_state=pdk.ViewState(latitude=(max(lats) + min(lats)) / 2, longitude=(max(lons) + min(lons)) / 2,
                                         zoom=zoom_for(lats, lons)),
        views=[pdk.View(type="MapView", controller={"scrollZoom": False})],   # page scroll stays page scroll
        map_style=pdk.map_styles.CARTO_LIGHT, tooltip={"text": "{tip}"})
    st.pydeck_chart(deck, height=430)


# ---------- header

inputs, rules, rev = tp["inputs"], tp["rules"], tp["rev"]
st.title("Where should I ship from?")
st.caption("Transportation and transshipment (min-cost flow LP) · solved with IBM CPLEX · "
           "places from the GeoNames city list (CC BY 4.0), road km ≈ straight line × 1.25")

c1, c2, c3, c4 = st.columns([2.2, 1, 1.2, 1.1], vertical_alignment="bottom")
c1.selectbox("Start from", list(T.TEMPLATES), format_func=T.TEMPLATES.get, key="tp_template",
             index=None, placeholder="Load an example …", on_change=load_template)
c2.text_input("Unit", value=inputs["unit"], key="tp_unit", on_change=set_unit)
c3.number_input(f"Cost per {inputs['unit']} and km (€)", value=float(inputs["cost_per_km"]), min_value=0.0,
                step=0.01, format="%.3f", key=f"tp_rate_{rev}", on_change=set_rate, args=(f"tp_rate_{rev}",))
show_math = c4.toggle("Show the math", key="tp_math")

result = solve()
solved = tp["solved"]

# ---------- picture: canvas + map

left, right = st.columns([1.15, 1])
with left:
    canvas(inputs, result, solved)
    st.caption("Drag places to tidy up; zoom with + / −. **Draw a route:** drag from a place's right dot to another place. "
               "**Delete a route:** right-click it. Click a route to pick it for a rule or a slider.")
with right:
    map_view(inputs, result, solved)
    st.caption(":blue[●] supplier · :red[●] customer · :gray[●] hub · line width = amount shipped")

# ---------- the answer

if not solved:
    st.button("Solve with CPLEX", type="primary", icon=":material/play_arrow:", on_click=solve_now)
    st.caption("Build or change the network first. After the first solve, every change re-solves at once.")
elif result.status == "invalid":
    st.warning("**The model is not complete yet.**  \n" + "  \n".join(f"• {p}" for p in result.problems))
elif not result.ok:
    st.error(f"**{result.message}**")
    if result.fixes:
        st.markdown("**Cheapest fixes** (each one works on its own; apply one to see the new plan):")
        for fix in words.ordered_fixes(result)[:6]:
            i = result.fixes.index(fix)
            a, b = st.columns([5, 1], vertical_alignment="center")
            a.markdown(words.fix_line(result, fix))
            b.button("Apply", key=f"fix_{rev}_{i}", on_click=apply_fix, args=(i,))
else:
    shipped = sum(l.activity for l in result.limits if l.kind == "demand")
    note, before = tp["delta"] or ("", None)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total transport cost", money(result.objective),
              delta=None if before is None or abs(result.objective - before) < 0.5 else money(result.objective - before),
              delta_color="inverse", help=f"vs before your last change ({note})" if note else None)
    m2.metric(f"{units().capitalize()} delivered", num(shipped))
    m3.metric("Routes used", f"{sum(v > TOL for v in result.plan.values())} of {len(result.plan)}")
    m4.metric("Average cost", money(result.objective / shipped, cents=True) if shipped else "—",
              help=f"per {inputs['unit']} delivered")
    if note and before is not None:
        st.caption(f"Last change: {note}")
    st.markdown("**For your manager** (copy with the icon on the right):")
    st.code(M.summary(inputs, result), language=None, wrap_lines=True)
if solved and result.warnings:
    st.info("  \n".join(result.warnings), icon=":material/info:")

# ---------- show the math: words ↔ formulation, row by row

if show_math:
    with st.container(border=True):
        plain = M.plain(inputs, rules)
        b = engine.build(M, inputs, rules)
        st.markdown(f"**You decide:** {plain['decide']}  \n**You want:** {plain['want']}  \n"
                    f"**You are limited by:** {plain['limited']}")
        g1, g2 = st.columns(2)
        g1.markdown("**The model in general**")
        g1.latex(M.general_latex)
        g2.markdown("**With your numbers**")
        if result.status != "invalid":
            objective, lims, domain = latex.formulation(b, per_line=3)
            g2.latex(objective)
            for text, tex in lims:
                w1, w2 = st.columns([1, 2.2], vertical_alignment="center")
                w1.markdown(text)
                w2.latex(tex)
            st.latex(domain)
        st.caption("Whole-number supplies and orders give a whole-number plan: the transportation matrix "
                   "is totally unimodular. Shadow prices are the u and v of the hand method.")

# ---------- tabs

t_build, t_live, t_limits, t_rules, t_guess, t_scn = st.tabs(
    [":material/construction: Build", ":material/tune: Live sliders", ":material/search: What limits you?",
     ":material/lock: Rules", ":material/target: Beat the solver", ":material/compare: Scenarios"],
    key="tp_tab", on_change="rerun")   # keeps the open tab when the answer above changes shape

with t_build:
    a, b = st.columns([1, 2.2])
    with a:
        st.markdown("**Add a place**")
        st.selectbox("City", list(city_index()), key="tp_city", index=None, accept_new_options=True,
                     placeholder="Type a city …", help="From the bundled city list. A name that is not a city "
                                                       "still works, without a spot on the map.")
        st.segmented_control("Role", list(T.ROLES), format_func=lambda r: ROLE_LABEL[r].split(" (")[0],
                             key="tp_role", default="customer")
        st.number_input("Supply / order / hub limit", min_value=0.0, value=100.0, step=10.0, key="tp_amount",
                        help="Suppliers: how much they can ship. Customers: how much they need. "
                             "Hubs: how much they can handle (0 = no limit).")
        st.button("Add place", icon=":material/add_location:", on_click=add_place, width="stretch")
        st.button("Connect every supplier to every customer", icon=":material/hub:", on_click=connect_all,
                  width="stretch", help="Also suppliers → hubs → customers. You can delete routes "
                                                 "on the canvas afterwards.")
        if S.get("tp_msg"):
            st.caption(S.tp_msg)
    with b:
        st.markdown("**Places**")
        places_df = pd.DataFrame([{"Place": p["name"], "Role": p["role"], "Amount": p["amount"],
                                   "On map": "✓" if p["lat"] is not None else "—"} for p in inputs["places"]],
                                 columns=["Place", "Role", "Amount", "On map"])
        st.data_editor(places_df, key=f"tp_places_{rev}", num_rows="dynamic", width="stretch",
                       on_change=edit_places, args=(f"tp_places_{rev}",), hide_index=True,
                       column_config={"Role": st.column_config.SelectboxColumn(options=list(T.ROLES), required=True),
                                      "Amount": st.column_config.NumberColumn(min_value=0, help="supply / order / hub limit"),
                                      "On map": st.column_config.TextColumn(disabled=True, width="small")})
        st.markdown("**Routes**")
        names = [p["name"] for p in inputs["places"]]
        routes_df = pd.DataFrame([{"From": r["from"], "To": r["to"], "Road km": r["km"], "Cost": r["cost"],
                                   "Capacity": r.get("capacity")} for r in inputs["routes"]],
                                 columns=["From", "To", "Road km", "Cost", "Capacity"])
        st.data_editor(routes_df, key=f"tp_routes_{rev}", num_rows="dynamic", width="stretch",
                       on_change=edit_routes, args=(f"tp_routes_{rev}",), hide_index=True,
                       column_config={"From": st.column_config.SelectboxColumn(options=names),
                                      "To": st.column_config.SelectboxColumn(options=names),
                                      "Road km": st.column_config.NumberColumn(disabled=True, format="%.0f"),
                                      "Cost": st.column_config.NumberColumn(min_value=0, format="€%.2f",
                                                                            help=f"per {inputs['unit']}; typed costs stay fixed"),
                                      "Capacity": st.column_config.NumberColumn(min_value=0, help="blank = no limit")})
        with st.expander("Paste a table from Excel or CSV"):
            st.markdown("Three shapes work: a **cost table** (customers across the top, suppliers down the side, "
                        "optional *Supply* column and *Demand* row), a **places list** (name, role, amount) or a "
                        "**routes list** (from, to, cost, capacity). German number format is fine.")
            st.text_area("Paste here", key="tp_paste", height=140,
                         placeholder="\tBerlin\tMunich\tSupply\nHamburg\t16\t38\t400\nLeipzig\t9\t21\t300\nDemand\t250\t280")
            st.button("Read the table", on_click=read_paste)

with t_live:
    if not solved:
        st.info("Solve first; then every slider re-solves at once.")
    else:
        st.markdown("Move a slider: CPLEX re-solves and the canvas, the map and the cost update at once.")
        # fresh keys after every change: a kept key would replay a stale browser value later
        k = f"tp_rate_sl_{rev}"
        st.slider(f"Cost per {inputs['unit']} and km (€)", 0.0, max(0.2, inputs["cost_per_km"] * 2),
                  float(inputs["cost_per_km"]), 0.001, key=k, on_change=set_rate, args=(k,), format="€%.3f")
        cols = st.columns(2)
        for i, p in enumerate(inputs["places"]):
            what = {"supplier": "supply", "customer": "order", "hub": "handling limit"}[p["role"]]
            top = float(max(100, math.ceil(p["amount"] * 2 / 50) * 50))
            k = f"tp_sl_{i}_{rev}"
            cols[i % 2].slider(f"{p['name']}: {what}", 0.0, top, float(p["amount"]), 1.0, key=k, format="%.0f",
                               on_change=set_amount, args=(p["name"], k))
        keys = [T.route_key(r["from"], r["to"]) for r in inputs["routes"]]
        if keys:
            pick = st.selectbox("Route cost", keys, index=keys.index(tp["selected"]) if tp["selected"] in keys else 0,
                                key=f"tp_route_pick_{rev}")
            r = inputs["routes"][keys.index(pick)]
            k = f"tp_rc_{rev}"
            st.slider(f"{pick}: cost per {inputs['unit']} (€)", 0.0, float(max(10, math.ceil(r["cost"] * 2))),
                      float(r["cost"]), 0.01, key=k, format="€%.2f", on_change=set_route_cost, args=(pick, k))

with t_limits:
    if not (solved and result.ok):
        st.info("Solve a model that works to see what limits it.")
    else:
        st.markdown("#### What limits you?")
        st.caption("Shadow prices (CPLEX duals): what one more unit of each limit is worth, and how far that holds.")
        for line in words.limits(result):
            st.markdown("• " + line)
        spare = words.spare(result)
        if spare:
            st.markdown("**Not a limit (room left):** " + "; ".join(spare) + ".")
        unused = words.unused(result)
        if unused:
            with st.expander(f"Routes not used ({len(unused)}) and how much cheaper they would have to be"):
                for line in unused:
                    st.markdown("• " + line)
        ranges = words.cost_ranges(result)
        if ranges:
            with st.expander("Routes used: the cost window in which the plan stays the same"):
                st.dataframe(pd.DataFrame(ranges, columns=["Route", "Amount", "Cost", "Plan holds from", "up to"]),
                             hide_index=True, width="stretch")

with t_rules:
    st.markdown("#### Price of a rule")
    st.caption("Lock or ban a route; CPLEX re-solves and says what the rule costs you.")
    keys = [T.route_key(r["from"], r["to"]) for r in inputs["routes"]]
    if keys:
        a, b, c, d = st.columns([2.2, 1.2, 1, 0.9], vertical_alignment="bottom")
        route = a.selectbox("Route", keys, index=keys.index(tp["selected"]) if tp["selected"] in keys else 0,
                            key=f"tp_rule_route_{rev}")
        op = b.selectbox("Rule", OPS, key=f"tp_rule_op_{rev}")
        current = result.plan.get(route, 0.0) if result.ok else 0.0
        value = c.number_input(units(), min_value=0.0, value=float(round(current)), step=10.0,
                               key=f"tp_rule_val_{rev}", disabled=op == "ban")
        d.button("Add rule", on_click=add_rule, args=(route, op, value), type="primary")
    for i, rule in enumerate(rules):
        a, b = st.columns([6, 1], vertical_alignment="center")
        a.markdown(rule_words(rule, units()))
        b.button("Remove", key=f"tp_rule_rm_{rev}_{i}", on_click=remove_rule, args=(i,))
    if rules and solved:
        if result.ok:
            for line in words.rule_prices(result):
                st.markdown(line)
        elif result.status == "infeasible":
            st.warning("With these rules no plan works; see the fixes above.")

with t_guess:
    st.markdown("#### Beat the solver")
    st.caption(f"Guess first: type how many {units()} go on each route, score your plan, then reveal the optimum. "
               "Works as a class poll: everyone guesses before the reveal.")
    guess_df = pd.DataFrame([{"Route": T.route_key(r["from"], r["to"]), "Cost": r["cost"],
                              "Your plan": tp["guess"].get(T.route_key(r["from"], r["to"]), 0.0)}
                             for r in inputs["routes"]], columns=["Route", "Cost", "Your plan"])
    with st.form("tp_guess_form", border=False):
        edited = st.data_editor(guess_df, key=f"tp_guess_{rev}", hide_index=True, width="stretch",
                                column_config={"Route": st.column_config.TextColumn(disabled=True),
                                               "Cost": st.column_config.NumberColumn(disabled=True, format="€%.2f"),
                                               "Your plan": st.column_config.NumberColumn(min_value=0, step=10)})
        a, b = st.columns(2)
        score = a.form_submit_button("Score my plan", icon=":material/scoreboard:")
        reveal = b.form_submit_button("Reveal the optimum", icon=":material/visibility:")
    if score or reveal:
        tp["guess"] = {r["Route"]: 0.0 if pd.isna(r["Your plan"]) else float(r["Your plan"])
                       for r in edited.to_dict("records")}
        tp["scored"] = True
        if reveal and not tp["revealed"]:
            tp.update(revealed=True, solved=True)
            st.rerun()
    if tp["scored"]:
        ev = engine.evaluate(M, inputs, rules, tp["guess"], result if tp["revealed"] else None)
        if ev.violations:
            st.error(f"**Your plan costs {money(ev.objective)} but breaks {len(ev.violations)} limit(s):**  \n"
                     + "  \n".join(f"• {w}: {how} {num(n)}" for w, n, how in ev.violations))
        else:
            st.success(f"**Your plan works and costs {money(ev.objective)}.**")
        if tp["revealed"] and result.ok:
            if ev.gap is not None:
                st.markdown(f"**The optimum costs {money(result.objective)}: you are {money(ev.gap)} above it"
                            f"{f' ({ev.gap / result.objective:.1%})' if result.objective else ''}.**"
                            if ev.gap > 0.5 else "**You found the optimum. Well done!**")
                if ev.parts:
                    st.markdown("Where the gap comes from (sums to the gap):")
                    for text, amount in ev.parts:
                        st.markdown(f"• {text} → **{money(amount)}**")
            else:
                st.markdown(f"**The optimum costs {money(result.objective)}** and keeps every limit.")

with t_scn:
    st.markdown("#### Scenarios side by side")
    a, b = st.columns([3, 1], vertical_alignment="bottom")
    a.text_input("Name this scenario", key="tp_scn_name", placeholder="e.g. Today / Close Leipzig / +100 at Hamburg")
    b.button("Save scenario", icon=":material/bookmark_add:", on_click=save_scenario, type="primary",
             disabled=not solved)
    if tp["scenarios"]:
        headers, rows = scenarios.compare(M, tp["scenarios"])
        st.table(pd.DataFrame(rows, columns=headers).set_index(""))
        a, b, c = st.columns([2, 1, 1.4], vertical_alignment="bottom")
        a.selectbox("Scenario", [s["name"] for s in tp["scenarios"]], key="tp_scn_pick")
        b.button("Load into the builder", on_click=load_scenario)
        c.download_button("Download all (JSON)", scenarios.dumps(tp["scenarios"]), file_name="scenarios.json",
                          mime="application/json", icon=":material/download:")
    st.file_uploader("Load scenarios from a file", type="json", key="tp_scn_file", on_change=import_scenarios)
