"""How much of each product should I make? Product mix (LP), with the graphical method for 2 products.

    x[p] = units of product p to make

    max   sum_p profit[p] * x[p]
    s.t.  sum_p use[r][p] * x[p] <= available[r]     every resource r (machine hours, material, ...)
          x[p] >= min[p]                             optional commitments (orders already promised)
          x[p] <= max[p]                             optional market limits (what can be sold)
          x >= 0

A resource's shadow price is what one more hour of it adds to the profit; a product's reduced cost
is how much more profitable it would have to be to enter the mix.
With 2 products the model is a picture: every limit is a line a1*x1 + a2*x2 = b, the feasible
region is the polygon they cut out, and the optimum sits on a corner (`graph`).
"""

import math
import re

from plantlab.engine.core import TOL, ModelType, num
from plantlab.engine.paste import german, number, read_table
from plantlab.engine.words import money


def plural(unit, n=2):
    return unit if n == 1 or unit.endswith("s") else unit + "s"


def symbols(names):
    """x_{\\text{CIT}}: a short, unique code per product for the formulation."""
    out, used = {}, set()
    for i, n in enumerate(names):
        code = re.sub(r"[^A-Za-z0-9]", "", n).upper()[:3] or f"P{i + 1}"
        while code in used:
            code = code[:2] + str(i + 1)
        used.add(code)
        out[n] = r"x_{\text{%s}}" % code
    return out


# ---------- building inputs

def product(name, profit, low=None, high=None):
    return {"name": name, "profit": float(profit), "min": low, "max": high}


def resource(name, available, unit="hours", use=None):
    """use: {product name: amount of this resource per unit of product}."""
    return {"name": name, "available": float(available), "unit": unit, "use": dict(use or {})}


def empty(unit="unit"):
    return {"unit": unit, "products": [], "resources": []}


def template(key):
    """Editable starting points (invented numbers, written fresh)."""
    t = empty("bike")
    if key == "blank":
        return empty()
    t["products"] = [product("City bike", 120), product("Cargo bike", 200, high=40)]
    t["resources"] = [resource("Welding", 200, "hours", {"City bike": 2, "Cargo bike": 4}),
                      resource("Assembly", 140, "hours", {"City bike": 2, "Cargo bike": 2}),
                      resource("Paint shop", 150, "hours", {"City bike": 1, "Cargo bike": 3})]
    if key == "3 products":
        t["products"].append(product("Kids bike", 70, low=10))
        for r, u in zip(t["resources"], (1, 1.5, 0.5)):
            r["use"]["Kids bike"] = u
        t["resources"].append(resource("Frames in stock", 90, "frames",
                                       {"City bike": 1, "Cargo bike": 1, "Kids bike": 1}))
    return t


TEMPLATES = {"2 products": "Bike workshop: 2 products (graphical method)",
             "3 products": "Bike workshop: 3 products + frames in stock",
             "blank": "Start empty"}


def find(items, name):
    return next((i for i in items if i["name"] == name), None)


def rename_product(inputs, old, new):
    find(inputs["products"], old)["name"] = new
    for r in inputs["resources"]:
        if old in r["use"]:
            r["use"][new] = r["use"].pop(old)
    return inputs


def remove_product(inputs, name):
    inputs["products"] = [p for p in inputs["products"] if p["name"] != name]
    for r in inputs["resources"]:
        r["use"].pop(name, None)
    return inputs


# ---------- paste from Excel / CSV

def from_paste(inputs, text):
    """A technology table: products across the top, one resource per row, an 'Available' column,
    and a 'Profit' row (optional 'Min' / 'Max' rows) -> (new inputs, message)."""
    rows = read_table(text)
    if len(rows) < 2:
        return inputs, "Paste at least two rows."
    dc = german(rows)
    header = rows[0]
    avail = next((i for i, h in enumerate(header) if i and re.match(r"(avail|capacity|limit|verfüg|kapazit)", h, re.I)), None)
    unit_col = next((i for i, h in enumerate(header) if i and re.match(r"(unit|einheit)", h, re.I)), None)
    names = [h for i, h in enumerate(header[1:], 1) if h and i not in (avail, unit_col)]
    special = {}
    body = []
    for r in rows[1:]:
        m = re.match(r"(profit|margin|gewinn|deckungs|min|max)", r[0], re.I) if r and r[0] else None
        if m:
            special[m.group(1).lower()[:3]] = r
        elif r and r[0]:
            body.append(r)
    if not names or avail is None or "pro" not in special and "mar" not in special and "gew" not in special \
            and "dec" not in special:
        return inputs, ("Could not read that table: put products across the top, resources down the side, "
                        "an 'Available' column and a 'Profit' row.")
    profit_row = special.get("pro") or special.get("mar") or special.get("gew") or special.get("dec")
    out = empty(inputs.get("unit", "unit"))
    col = {h: i for i, h in enumerate(header)}
    for n in names:
        cell = lambda row: number(row[col[n]], dc) if row and col[n] < len(row) else None
        out["products"].append(product(n, cell(profit_row) or 0, cell(special.get("min")), cell(special.get("max"))))
    for r in body:
        use = {n: number(r[col[n]], dc) or 0.0 for n in names if col[n] < len(r)}
        unit = r[unit_col] if unit_col is not None and unit_col < len(r) and r[unit_col] else "hours"
        out["resources"].append(resource(r[0], number(r[avail], dc) or 0, unit, use))
    return out, f"{len(names)} products × {len(body)} resources read."


# ---------- the model type

class Mix(ModelType):
    key = "mix"
    sense = "max"

    def unit(self, inputs):
        return inputs.get("unit") or "unit"

    def validate(self, inputs):
        errors, warnings = [], []
        products, resources = inputs["products"], inputs["resources"]
        names = [p["name"] for p in products]
        if not products:
            errors.append("Add at least one product.")
        if any(not str(n).strip() for n in names):
            errors.append("Every product needs a name.")
        for label, items in (("products", products), ("resources", resources)):
            seen = [i["name"] for i in items]
            dupes = sorted({n for n in seen if seen.count(n) > 1})
            if dupes:
                errors.append(f"Two {label} have the same name: {', '.join(dupes)}.")
        for p in products:
            if p.get("profit") is None:
                errors.append(f"{p['name']} needs a profit per unit.")
            low, high = p.get("min"), p.get("max")
            if low is not None and low < 0 or high is not None and high < 0:
                errors.append(f"{p['name']}: a minimum or maximum can't be negative.")
            elif low is not None and high is not None and low > high:
                errors.append(f"{p['name']}: the minimum ({num(low)}) is above the maximum ({num(high)}).")
        for r in resources:
            if r.get("available") is None or r["available"] < 0:
                errors.append(f"{r['name']} needs an amount available of 0 or more.")
            if any(v is not None and v < 0 for v in r["use"].values()):
                errors.append(f"{r['name']}: a product can't use a negative amount.")
        if len(products) > 500:
            errors.append("More than 500 products is too big for the free CPLEX edition.")
        if errors:
            return errors, warnings
        for p in products:
            free = all(not (r["use"].get(p["name"]) or 0) for r in resources)
            if free and p["profit"] > 0 and p.get("max") is None:
                errors.append(f"{p['name']} uses no resource and has no maximum: you could make endless "
                              "amounts. Give it a resource use or a market limit.")
            elif p["profit"] <= 0:
                warnings.append(f"{p['name']} earns nothing per unit, so it only gets made if a minimum forces it.")
        for r in resources:
            if not any(r["use"].get(p["name"]) for p in products):
                warnings.append(f"No product uses {r['name']}.")
        return errors, warnings

    def build(self, b, inputs):
        unit, products, resources = self.unit(inputs), inputs["products"], inputs["resources"]
        units = plural(unit)
        names = [p["name"] for p in products]
        profit = {p["name"]: p["profit"] for p in products}
        m = b.m

        x = m.continuous_var_dict(names, name="x")
        sym = symbols(names)
        for n in names:
            b.decision(n, x[n], label=n, unit=units, symbol=sym[n])

        b.maximize(m.sum(profit[n] * x[n] for n in names), "total profit")

        for r in resources:
            ru = r.get("unit") or "units"
            b.limit(f"resource:{r['name']}", m.sum((r["use"].get(n) or 0) * x[n] for n in names), "<=",
                    r["available"], kind="resource", label=r["name"], unit=ru,
                    words=f"{r['name']}: at most {num(r['available'])} {ru}",
                    more=f"One more {ru.rstrip('s')} of {r['name']}", fix=f"+{{n}} {ru} of {r['name']}")
        for p in products:
            n = p["name"]
            if p.get("min") is not None and p["min"] > 0:
                b.limit(f"min:{n}", x[n], ">=", p["min"], kind="min", label=f"{n} minimum", unit=units,
                        words=f"At least {num(p['min'])} {plural(n.lower())} (already promised)",
                        more=f"One more {n} promised", fix=f"promise {{n}} fewer {plural(n)}")
            if p.get("max") is not None:
                b.limit(f"max:{n}", x[n], "<=", p["max"], kind="max", label=f"{n} market", unit=units,
                        words=f"At most {num(p['max'])} {plural(n.lower())} can be sold",
                        more=f"One more {n} the market takes", fix=f"find buyers for {{n}} more {plural(n)}")

    def shortfall_words(self, inputs, amount):
        return (f"No mix meets every limit: promised amounts, market limits or your rules ask for more than "
                f"fits ({num(amount)} short in all).")

    def apply_fix(self, inputs, key, amount):
        kind, name = key.split(":", 1)
        if kind == "resource":
            find(inputs["resources"], name)["available"] += amount
        elif kind == "min":
            p = find(inputs["products"], name)
            p["min"] = max(0.0, p["min"] - amount)
        elif kind == "max":
            find(inputs["products"], name)["max"] += amount
        return inputs

    # ---------- talking about it

    def plain(self, inputs, rules=()):
        units = plural(self.unit(inputs))
        n_min = sum(1 for p in inputs["products"] if p.get("min"))
        n_max = sum(1 for p in inputs["products"] if p.get("max") is not None)
        limited = [f"{len(inputs['resources'])} resources ("
                   + ", ".join(f"{r['name']} {num(r['available'])} {r['unit']}" for r in inputs["resources"]) + ")"]
        if n_min:
            limited.append(f"{n_min} promised minimum{'s' if n_min > 1 else ''}")
        if n_max:
            limited.append(f"{n_max} market limit{'s' if n_max > 1 else ''}")
        if rules:
            limited.append(f"{len(rules)} rule{'s' if len(rules) > 1 else ''} of yours")
        return {"decide": f"How many {units} of each of the {len(inputs['products'])} products to make.",
                "want": "The highest total profit (profit per unit × units made).",
                "limited": ", ".join(limited) + "."}

    def summary(self, inputs, result):
        if result.status == "invalid":
            return "The model is not complete yet: " + " ".join(result.problems)
        if not result.ok:
            text = result.message
            if result.fixes:
                text += " Cheapest fixes: " + "; or ".join(f.words for f in result.fixes[:3]) + "."
            return text
        made = [(k, v) for k, v in result.plan.items() if v > TOL]
        parts = [f"The best mix earns {money(result.objective)}: "
                 + (", ".join(f"{num(round(v, 2))} {k}" for k, v in made) if made else "make nothing") + "."]
        tight = [l for l in sorted(result.limits, key=lambda l: -abs(l.dual))
                 if l.binding and abs(l.dual) > TOL and l.kind in ("resource", "max")]
        if tight:
            parts.append("The bottlenecks are " + " and ".join(
                f"{l.label} (one more {l.unit.rstrip('s')} is worth {money(l.dual, cents=True)})" for l in tight[:2]) + ".")
        spare = [l for l in result.limits if l.kind == "resource" and l.slack > TOL]
        if spare:
            parts.append("Spare: " + ", ".join(f"{num(l.slack)} {l.unit} of {l.label}" for l in spare) + ".")
        out = [d for d in result.decisions.values() if d.value < TOL and d.reduced_cost < -TOL]
        if out:
            d = out[0]
            parts.append(f"{d.label} is not worth making unless its profit rises by "
                         f"{money(-d.reduced_cost, cents=True)} per unit.")
        if result.rule_prices and result.objective_without_rules is not None:
            lost = result.objective_without_rules - result.objective
            parts.append(f"Your rules cost {money(lost)} of profit." if lost > 0.5 else "Your rules cost nothing.")
        return " ".join(parts)

    def diff(self, a, b):
        out = []
        pa, pb = {p["name"]: p for p in a["products"]}, {p["name"]: p for p in b["products"]}
        out += [f"+ {n}" for n in pb if n not in pa] + [f"− {n}" for n in pa if n not in pb]
        for n in pa:
            if n in pb:
                for f, label in (("profit", "profit"), ("min", "min"), ("max", "max")):
                    if pa[n].get(f) != pb[n].get(f):
                        show = lambda v: "none" if v is None else (money(v) if f == "profit" else num(v))
                        out.append(f"{n} {label} {show(pa[n].get(f))} → {show(pb[n].get(f))}")
        ra, rb = {r["name"]: r for r in a["resources"]}, {r["name"]: r for r in b["resources"]}
        out += [f"+ {n}" for n in rb if n not in ra] + [f"− {n}" for n in ra if n not in rb]
        for n in ra:
            if n in rb:
                if ra[n]["available"] != rb[n]["available"]:
                    out.append(f"{n} {num(ra[n]['available'])} → {num(rb[n]['available'])} {rb[n]['unit']}")
                if ra[n]["use"] != rb[n]["use"]:
                    out.append(f"{n} use per unit changed")
        return out

    general_latex = r"""\begin{aligned}
\max\; & \textstyle\sum_{p} c_p\, x_p \\
\text{s.t.}\; & \textstyle\sum_{p} a_{rp}\, x_p \le b_r && \text{every resource } r \\
& x_p \ge l_p && \text{promised minimums} \\
& x_p \le u_p && \text{market limits} \\
& x_p \ge 0
\end{aligned}"""


MODEL = Mix()


# ---------- the graphical method (2 products)

def lines(inputs, rules=()):
    """Every limit as a line a1*x1 + a2*x2 (sense) b, in the order a teacher adds them:
    resources, then minimums and market limits, then the user's rules. -> [dict]"""
    from plantlab.engine.core import build
    b = build(MODEL, inputs, rules)
    names = [p["name"] for p in inputs["products"]]
    out = []
    for key, spec in b.limits.items():
        a1, a2 = (spec.terms.get(n, 0.0) for n in names)
        if abs(a1) < TOL and abs(a2) < TOL:
            continue
        out.append({"key": key, "label": spec.label, "words": spec.words, "a": (a1, a2), "sense": spec.sense,
                    "b": spec.rhs, "kind": spec.kind})
    return out


def _holds(line, x, y, tol=1e-7):
    v = line["a"][0] * x + line["a"][1] * y
    s, rhs = line["sense"], line["b"]
    scale = tol * max(1.0, abs(rhs))
    return v <= rhs + scale if s == "<=" else v >= rhs - scale if s == ">=" else abs(v - rhs) <= scale


def corners(ls):
    """Corners of the feasible region (x1, x2 >= 0 and every line), sorted around the region."""
    axes = [{"a": (1.0, 0.0), "sense": ">=", "b": 0.0}, {"a": (0.0, 1.0), "sense": ">=", "b": 0.0}]
    allx = ls + axes
    pts = []
    for i in range(len(allx)):
        for j in range(i + 1, len(allx)):
            (a, b), (c, d) = allx[i]["a"], allx[j]["a"]
            det = a * d - b * c
            if abs(det) < 1e-12:
                continue
            e, f = allx[i]["b"], allx[j]["b"]
            x, y = (e * d - b * f) / det, (a * f - e * c) / det
            if all(_holds(l, x, y) for l in allx) and not any(abs(x - p[0]) < 1e-7 and abs(y - p[1]) < 1e-7 for p in pts):
                pts.append((x + 0.0, y + 0.0))
    if len(pts) > 2:
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        pts.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    return pts


def bounded(ls):
    """True when the feasible region is closed (finite) in both directions."""
    return any(l["sense"] in ("<=", "==") and l["a"][0] > TOL for l in ls) and \
        any(l["sense"] in ("<=", "==") and l["a"][1] > TOL for l in ls)


def region_band(pts):
    """A convex polygon as vertical slices (x, y_low, y_high), for an area chart."""
    if not pts:
        return []
    xs = sorted({round(p[0], 9) for p in pts})

    def edge_y(x):
        ys = []
        n = len(pts)
        for i in range(n):
            (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
            if min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9:
                if abs(x2 - x1) < 1e-12:
                    ys += [y1, y2]
                else:
                    ys.append(y1 + (y2 - y1) * (x - x1) / (x2 - x1))
        return min(ys), max(ys)

    return [(x, *edge_y(x)) for x in xs]


def graph(inputs, rules=(), result=None):
    """Everything the 2-product picture needs. -> dict or None (not 2 products)."""
    if len(inputs["products"]) != 2:
        return None
    ls = lines(inputs, rules)
    pts = corners(ls)
    names = [p["name"] for p in inputs["products"]]
    profit = [p["profit"] for p in inputs["products"]]
    xs = [p[0] for p in pts] + [l["b"] / l["a"][0] for l in ls if l["a"][0] > TOL and l["b"] > 0]
    ys = [p[1] for p in pts] + [l["b"] / l["a"][1] for l in ls if l["a"][1] > TOL and l["b"] > 0]
    span_x = max(xs, default=10) * 1.1 or 10
    span_y = max(ys, default=10) * 1.1 or 10
    best = None
    if result is not None and result.ok:
        best = (result.plan[names[0]], result.plan[names[1]])
    scored = [(p, profit[0] * p[0] + profit[1] * p[1]) for p in pts]
    return {"names": names, "profit": profit, "lines": ls, "corners": scored, "band": region_band(pts),
            "box": (span_x, span_y), "best": best, "bounded": bounded(ls)}


def segment(line, box):
    """Where a line a1*x + a2*y = b crosses the drawing box [0, X] x [0, Y] -> two points or []."""
    (a, b), c = line["a"], line["b"]
    X, Y = box
    pts = []
    if abs(b) > TOL:
        for x in (0.0, X):
            y = (c - a * x) / b
            if -1e-9 <= y <= Y + 1e-9:
                pts.append((x, y))
    if abs(a) > TOL:
        for y in (0.0, Y):
            x = (c - b * y) / a
            if -1e-9 <= x <= X + 1e-9:
                pts.append((x, y))
    pts = sorted(set((round(x, 9), round(y, 9)) for x, y in pts))
    return [pts[0], pts[-1]] if len(pts) >= 2 else []


def iso_profit(profit, value, box):
    """The iso-profit line c1*x + c2*y = value inside the box."""
    return segment({"a": tuple(profit), "b": value}, box)

