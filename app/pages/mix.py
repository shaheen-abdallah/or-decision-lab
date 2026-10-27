"""How much of each product should I make? The product-mix builder (LP, graphical method for 2 products).

Picture on top (2 products: feasible region, limit lines, corners, iso-profit line, optimal corner;
more products: the mix as bars), the answer in words next to it, then tabs: build · live sliders ·
what limits you · rules · beat the solver · scenarios. Teach mode adds the model one line at a time.
"""

import math

import altair as alt
import pandas as pd
import streamlit as st

from lab import Lab, metric_delta
from plantlab import engine
from plantlab.engine import words
from plantlab.engine.core import TOL, num
from plantlab.engine.words import money
from plantlab.models import mix as X

M = X.MODEL
S = st.session_state
LINE_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#8c564b", "#e377c2", "#17becf", "#bcbd22"]

lab = Lab("mx", M, lambda: X.template("2 products"), lambda v: money(v))


def units():
    return X.plural(M.unit(lab.inputs))


# ---------- callbacks

def load_template():
    key = S.mx_template
    lab.reset(X.template(key), f"template: {X.TEMPLATES[key]}")


def set_unit():
    inputs, _ = lab.work()
    inputs["unit"] = S.mx_unit.strip() or "unit"
    lab.commit(inputs, note="unit")


def set_available(name, key):
    inputs, _ = lab.work()
    r = X.find(inputs["resources"], name)
    before = r["available"]
    if abs(float(S[key]) - before) < 1e-9:
        return
    r["available"] = float(S[key])
    lab.commit(inputs, note=f"{name} {num(before)} → {num(r['available'])} {r['unit']}")


def set_profit(name, key):
    inputs, _ = lab.work()
    p = X.find(inputs["products"], name)
    before = p["profit"]
    if abs(float(S[key]) - before) < 0.005:
        return
    p["profit"] = float(S[key])
    lab.commit(inputs, note=f"{name} profit {money(before)} → {money(p['profit'])}")


def read_paste():
    inputs, msg = X.from_paste(lab.inputs, S.mx_paste)
    S.mx_msg = msg
    if inputs is not lab.inputs:
        lab.commit(inputs, [], note="pasted table")


def blank(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def apply_tables(products_df, resources_df):
    """Rebuild the inputs from the two edited tables (renames follow the row)."""
    inputs, rules = lab.work()
    old_names = [p["name"] for p in inputs["products"]]
    products = []
    for i, row in enumerate(products_df.to_dict("records")):
        name = (row.get("Product") or "").strip() if isinstance(row.get("Product"), str) else ""
        if not name:
            continue
        products.append({"name": name, "old": old_names[i] if i < len(old_names) else None,
                         "profit": 0.0 if blank(row.get("Profit per unit")) else float(row["Profit per unit"]),
                         "min": None if blank(row.get("Min")) else float(row["Min"]),
                         "max": None if blank(row.get("Max")) else float(row["Max"])})
    resources = []
    for row in resources_df.to_dict("records"):
        name = (row.get("Resource") or "").strip() if isinstance(row.get("Resource"), str) else ""
        if not name:
            continue
        use = {p["name"]: 0.0 if p["old"] is None or blank(row.get(p["old"])) else float(row[p["old"]])
               for p in products}
        resources.append(X.resource(name, 0.0 if blank(row.get("Available")) else float(row["Available"]),
                                    (row.get("Unit") or "hours") if isinstance(row.get("Unit"), str) else "hours", use))
    renamed = {p["old"]: p["name"] for p in products if p["old"]}
    inputs["products"] = [X.product(p["name"], p["profit"], p["min"], p["max"]) for p in products]
    inputs["resources"] = resources
    for r in rules:
        r["decision"] = renamed.get(r["decision"], r["decision"])
    lab.commit(inputs, keep_rules(rules, inputs), note="tables")


def keep_rules(rules, inputs):
    names = {p["name"] for p in inputs["products"]}
    return [r for r in rules if r["decision"] in names]


# ---------- the picture

def box_lines(box):
    return [{"key": "box:x", "a": (1.0, 0.0), "sense": "<=", "b": box[0]},
            {"key": "box:y", "a": (0.0, 1.0), "sense": "<=", "b": box[1]}]


def chart(g, shown, result, guess=None, show_iso=True, show_best=True):
    """The graphical method: region of the first `shown` limits, their lines, corners, iso-profit, optimum."""
    names, box = g["names"], g["box"]
    ls = g["lines"][:shown]
    region = X.region_band(X.corners(ls + box_lines(box)))
    layers = []
    if region:
        band = pd.DataFrame(region, columns=["x", "lo", "hi"])
        layers.append(alt.Chart(band).mark_area(opacity=0.22, color="#4c8bf5", interpolate="linear").encode(
            x=alt.X("x:Q", title=f"{names[0]} ({units()})", scale=alt.Scale(domain=[0, box[0]], nice=False)),
            y=alt.Y("lo:Q", title=f"{names[1]} ({units()})", scale=alt.Scale(domain=[0, box[1]], nice=False)),
            y2="hi:Q"))
    rows = []
    for i, l in enumerate(ls):
        seg = X.segment(l, box)
        lim = result.limit(l["key"]) if result.ok else None
        tight = bool(lim and lim.binding)
        for x, y in seg:
            rows.append({"x": x, "y": y, "limit": l["words"], "binding": "binding" if tight else "room left"})
    if rows:
        df = pd.DataFrame(rows)
        order = list(dict.fromkeys(df["limit"]))
        layers.append(alt.Chart(df).mark_line(strokeWidth=3).encode(
            x="x:Q", y="y:Q",
            color=alt.Color("limit:N", sort=order, scale=alt.Scale(domain=order, range=LINE_COLORS[:len(order)]),
                            legend=alt.Legend(title=None, orient="bottom", columns=1, labelFontSize=15, labelLimit=420)),
            strokeDash=alt.StrokeDash("binding:N", scale=alt.Scale(domain=["binding", "room left"],
                                                                   range=[[1, 0], [6, 4]]), legend=None),
            detail="limit:N", tooltip=["limit:N", "binding:N"]))
    if shown >= len(g["lines"]):
        pts = pd.DataFrame([{"x": x, "y": y, "profit": z, "label": f"({num(round(x, 2))}, {num(round(y, 2))}) → {money(z)}"}
                            for (x, y), z in g["corners"]])
        if len(pts):
            layers.append(alt.Chart(pts).mark_circle(size=90, color="#333").encode(
                x="x:Q", y="y:Q", tooltip=[alt.Tooltip("label:N", title="corner")]))
    best = g["best"] if show_best else None
    profit = g["profit"]
    if show_iso:
        level = (profit[0] * best[0] + profit[1] * best[1]) if best else 0.5 * max((z for _, z in g["corners"]), default=0)
        seg = X.iso_profit(profit, level, box) if level > 0 else []
        if seg:
            iso = pd.DataFrame([{"x": x, "y": y, "what": f"iso-profit line: {money(level)}"} for x, y in seg])
            layers.append(alt.Chart(iso).mark_line(strokeDash=[2, 3], color="#555", strokeWidth=2).encode(
                x="x:Q", y="y:Q", tooltip=["what:N"]))
    if best:
        pt = pd.DataFrame([{"x": best[0], "y": best[1], "label": f"best: {num(round(best[0], 2))} and "
                                                                  f"{num(round(best[1], 2))} → {money(result.objective)}"}])
        layers.append(alt.Chart(pt).mark_point(shape="diamond", size=420, filled=True, color="#e8710a").encode(
            x="x:Q", y="y:Q", tooltip=["label:N"]))
        layers.append(alt.Chart(pt).mark_text(dx=12, dy=-14, align="left", fontSize=16, fontWeight="bold").encode(
            x="x:Q", y="y:Q", text=alt.value(f"best {money(result.objective)}")))
    if guess is not None:
        gp = pd.DataFrame([{"x": guess[0], "y": guess[1], "label": "your plan"}])
        layers.append(alt.Chart(gp).mark_point(shape="cross", size=380, filled=True, color="#7b2cbf").encode(
            x="x:Q", y="y:Q", tooltip=["label:N"]))
        layers.append(alt.Chart(gp).mark_text(dx=12, dy=14, align="left", fontSize=15, color="#7b2cbf").encode(
            x="x:Q", y="y:Q", text="label:N"))
    if not layers:
        layers.append(alt.Chart(pd.DataFrame({"x": [0], "y": [0]})).mark_point(opacity=0).encode(
            x=alt.X("x:Q", title=f"{names[0]} ({units()})", scale=alt.Scale(domain=[0, box[0]])),
            y=alt.Y("y:Q", title=f"{names[1]} ({units()})", scale=alt.Scale(domain=[0, box[1]]))))
    return alt.layer(*layers).properties(height=470).configure_axis(labelFontSize=14, titleFontSize=16)


def bars(result):
    df = pd.DataFrame([{"Product": k, "Amount": v} for k, v in result.plan.items()])
    return alt.Chart(df).mark_bar(color="#4c8bf5").encode(
        x=alt.X("Amount:Q", title=units()), y=alt.Y("Product:N", sort="-x", title=None),
        tooltip=["Product", alt.Tooltip("Amount:Q", format=",.2f")]).properties(height=60 + 48 * len(df)) \
        .configure_axis(labelFontSize=15, titleFontSize=16)


# ---------- header

inputs, rules, rev = lab.inputs, lab.rules, lab.rev
st.title("How much of each product should I make?")
st.caption("Product mix (linear program) · solved with IBM CPLEX · with 2 products you see the graphical method")

two = len(inputs["products"]) == 2
c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1], vertical_alignment="bottom")
c1.selectbox("Start from", list(X.TEMPLATES), format_func=X.TEMPLATES.get, key="mx_template",
             index=None, placeholder="Load an example …", on_change=load_template)
c2.text_input("Unit", value=inputs["unit"], key="mx_unit", on_change=set_unit)
teach = c3.toggle("Teach mode", key="mx_teach", disabled=not two,
                  help="Build the model one piece at a time on the graph (2 products).")
show_math = c4.toggle("Show the math", key="mx_math")


result = lab.solve()
solved = lab.s["solved"]
g = X.graph(inputs, rules, result) if two else None

# teach mode: decisions -> objective -> each limit -> solve
steps = None
if teach and g:
    steps = ["Decisions", "Goal"] + [f"+ {l['label']}" for l in g["lines"]] + ["Best corner"]
    if S.get("mx_step") not in steps:
        S.mx_step = steps[0]
    st.select_slider("Step", steps, key="mx_step", label_visibility="collapsed")
step = steps.index(S.mx_step) if steps else None

# ---------- picture + answer

left, right = st.columns([1.3, 1])
with left:
    if g and result.status != "invalid":
        if steps:
            shown = max(0, step - 1) if step < len(steps) - 1 else len(g["lines"])
            show_best = step == len(steps) - 1 and result.ok
            st.altair_chart(chart(g, shown, result, show_iso=step >= 1, show_best=show_best), width="stretch")
            texts = {0: f"**You decide** how many {X.plural(g['names'][0].lower())} (across) and "
                        f"{X.plural(g['names'][1].lower())} (up) to make. Every point is a plan.",
                     1: f"**You want** the most profit: {money(g['profit'][0])} × across + {money(g['profit'][1])} × up. "
                        "The dotted line joins plans with the same profit; moving it outwards earns more."}
            if step in texts:
                st.markdown(texts[step])
            elif step < len(steps) - 1:
                l = g["lines"][step - 2]
                st.markdown(f"**You are limited by:** {l['words']}. Plans on the wrong side of the line are out; "
                            "the shaded area is what's still possible.")
            else:
                st.markdown("**The best plan sits on a corner:** push the profit line out until it last touches "
                            "the shaded area.")
        else:
            guess = None
            if lab.s["scored"]:
                guess = tuple(lab.s["guess"].get(n, 0.0) for n in g["names"])
            st.altair_chart(chart(g, len(g["lines"]), result, guess, show_best=solved and result.ok), width="stretch")
            st.caption("Shaded = every plan that fits. Solid line = a limit you hit (binding); dashed = room left. "
                       "Dots = corners (hover for their profit). The orange diamond is the best plan.")
            if not g["bounded"]:
                st.caption("The shaded area is cut at the edge of the picture: it goes on further.")
    elif solved and result.ok:
        st.altair_chart(bars(result), width="stretch")
        st.caption("With more than 2 products the picture would need more than 2 axes: here is the mix itself.")
    else:
        st.info("Add products and resources below. With exactly 2 products you see the graphical method.")

with right:
    if not solved:
        st.button("Solve with CPLEX", type="primary", icon=":material/play_arrow:", on_click=lab.solve_now)
        st.caption("Change the example first if you like. After the first solve, every change re-solves at once.")
        plain = M.plain(inputs, rules) if not result.status == "invalid" else None
        if plain:
            st.markdown(f"**You decide:** {plain['decide']}  \n**You want:** {plain['want']}  \n"
                        f"**You are limited by:** {plain['limited']}")
    elif lab.answer_problems(result):
        d, note = lab.delta(result)
        m1, m2 = st.columns(2)
        m1.metric("Total profit", money(result.objective), delta=metric_delta(d, money),
                  help=f"vs before your last change ({note})" if note else None)
        m2.metric(f"{units().capitalize()} made", num(round(sum(result.plan.values()), 2)))
        made = st.columns(min(3, len(result.plan)) or 1)
        for i, (k, v) in enumerate(result.plan.items()):
            made[i % len(made)].metric(k, num(round(v, 2)))
        if note and d is not None:
            st.caption(f"Last change: {note}")
        lab.summary(result)
    if solved and result.warnings:
        st.info("  \n".join(result.warnings), icon=":material/info:")

if show_math:
    reveal = None if not steps else max(0, step - 1) if step < len(steps) - 1 else None
    lab.math(result, "A limit's shadow price (dual) is what one more unit of it adds to the profit; "
                     "it holds within its range (see 'What limits you?').", reveal=reveal)

# ---------- tabs

t_build, t_live, t_limits, t_rules, t_guess, t_scn = lab.tabs(
    [":material/construction: Build", ":material/tune: Live sliders", ":material/search: What limits you?",
     ":material/lock: Rules", ":material/target: Beat the solver", ":material/compare: Scenarios"])

with t_build:
    names = [p["name"] for p in inputs["products"]]
    with st.form("mx_tables", border=False):
        st.markdown("**Products**: what each earns per unit; optional promised minimum and market maximum")
        pdf = pd.DataFrame([{"Product": p["name"], "Profit per unit": p["profit"], "Min": p.get("min"),
                             "Max": p.get("max")} for p in inputs["products"]],
                           columns=["Product", "Profit per unit", "Min", "Max"])
        pe = st.data_editor(pdf, key=lab.w("products"), num_rows="dynamic", hide_index=True, width="stretch",
                            column_config={"Profit per unit": st.column_config.NumberColumn(format="€%.2f"),
                                           "Min": st.column_config.NumberColumn(min_value=0, help="blank = none"),
                                           "Max": st.column_config.NumberColumn(min_value=0, help="blank = no limit")})
        st.markdown("**Resources**: how much each product uses per unit, and how much you have")
        rdf = pd.DataFrame([{"Resource": r["name"], "Unit": r["unit"], **{n: r["use"].get(n, 0.0) for n in names},
                             "Available": r["available"]} for r in inputs["resources"]],
                           columns=["Resource", "Unit", *names, "Available"])
        re_ = st.data_editor(rdf, key=lab.w("resources"), num_rows="dynamic", hide_index=True, width="stretch",
                             column_config={n: st.column_config.NumberColumn(min_value=0, help=f"per {n}")
                                            for n in names} | {"Available": st.column_config.NumberColumn(min_value=0)})
        st.caption("A new product gets its resource column after you apply. Delete a row with the bin on its left.")
        if st.form_submit_button("Apply changes", type="primary", icon=":material/check:"):
            apply_tables(pe, re_)
            st.rerun()
    with st.expander("Paste a table from Excel or CSV"):
        st.markdown("Products across the top, one resource per row, an **Available** column and a **Profit** row "
                    "(optional **Min** and **Max** rows). German number format is fine.")
        st.text_area("Paste here", key="mx_paste", height=140,
                     placeholder="\tCity bike\tCargo bike\tAvailable\nWelding\t2\t4\t200\nAssembly\t2\t2\t140\n"
                                 "Profit\t120\t200")
        st.button("Read the table", on_click=read_paste)
        if S.get("mx_msg"):
            st.caption(S.mx_msg)

with t_live:
    if not solved:
        st.info("Solve first; then every slider re-solves at once.")
    else:
        st.markdown("Move a slider: CPLEX re-solves, the limit line moves on the graph and the best corner follows.")
        a, b = st.columns(2)
        with a:
            st.markdown("**How much you have**")
            for i, r in enumerate(inputs["resources"]):
                k = lab.w(f"av_{i}")
                top = float(max(10, math.ceil(r["available"] * 2 / 10) * 10))
                st.slider(f"{r['name']} ({r['unit']})", 0.0, top, float(r["available"]), 1.0, key=k, format="%.0f",
                          on_change=set_available, args=(r["name"], k))
        with b:
            st.markdown("**Profit per unit**")
            for i, p in enumerate(inputs["products"]):
                k = lab.w(f"pr_{i}")
                top = float(max(10, math.ceil(abs(p["profit"]) * 2 / 10) * 10))
                st.slider(p["name"], 0.0, top, float(max(0.0, p["profit"])), 1.0, key=k, format="€%.0f",
                          on_change=set_profit, args=(p["name"], k))

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
        for line in words.unused(result):
            st.markdown("• " + line)
        ranges = [(d.label, num(round(d.value, 2)), money(d.cost, cents=True),
                   "any lower" if d.cost_low <= -1e19 else money(d.cost_low, cents=True),
                   "any higher" if d.cost_high >= 1e19 else money(d.cost_high, cents=True))
                  for d in result.decisions.values() if d.value > TOL]
        if ranges:
            st.markdown("**The mix stays the same while each profit stays in its window:**")
            st.dataframe(pd.DataFrame(ranges, columns=["Product", "Amount", "Profit per unit", "Mix holds from", "up to"]),
                         hide_index=True, width="stretch")
            if g:
                st.caption("On the graph: inside the window the profit line tilts but still touches the same corner.")

with t_rules:
    lab.rules_tab(result, [p["name"] for p in inputs["products"]], units(), step=5.0, what="product")

with t_guess:
    st.markdown("#### Beat the solver")
    st.caption(f"Guess first: how many {units()} of each product? Score it (it shows on the graph), then reveal "
               "the optimum. Works as a class poll: everyone guesses before the reveal.")
    gdf = pd.DataFrame([{"Product": p["name"], "Profit per unit": p["profit"],
                         "Your plan": lab.s["guess"].get(p["name"], 0.0)} for p in inputs["products"]],
                       columns=["Product", "Profit per unit", "Your plan"])
    with st.form("mx_guess_form", border=False):
        edited = st.data_editor(gdf, key=lab.w("guess"), hide_index=True, width="stretch",
                                column_config={"Product": st.column_config.TextColumn(disabled=True),
                                               "Profit per unit": st.column_config.NumberColumn(disabled=True, format="€%.2f"),
                                               "Your plan": st.column_config.NumberColumn(min_value=0, step=1)})
        score, reveal = lab.reveal_buttons()
    lab.after_guess(score, reveal, {r["Product"]: 0.0 if pd.isna(r["Your plan"]) else float(r["Your plan"])
                                    for r in edited.to_dict("records")})
    if lab.s["scored"]:
        ev = engine.evaluate(M, inputs, rules, lab.s["guess"], result if lab.s["revealed"] else None)
        lab.guess_feedback(ev, result)

with t_scn:
    lab.scenarios_tab("e.g. Today / +20 assembly hours / new product")
