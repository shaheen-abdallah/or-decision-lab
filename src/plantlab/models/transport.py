"""Where should I ship from? Transportation + transshipment as a min-cost flow (LP).

    x[i,j] = units on route i -> j (only routes the user drew)

    min   sum_(i,j) cost[i,j] * x[i,j]
    s.t.  out(i) - in(i) <= supply[i]        every supplier ships at most what it has
          in(j) - out(j) >= demand[j]        every customer gets at least what it ordered
          in(h) - out(h) == 0                a hub passes on everything it receives
          in(h) <= handling[h]               optional hub capacity
          x[i,j] <= capacity[i,j]            optional route capacity
          x >= 0

Costs come from road km x cost per unit-km (editable per route). With whole-number supplies and
demands the best plan is in whole units (the constraint matrix is totally unimodular).
Duals: a full supplier's dual is what one more unit there saves; a customer's dual is what one
more unit ordered there costs (the u_i + v_j of the hand method).
"""

import copy
import re
import unicodedata

from plantlab import geo
from plantlab.engine.core import ModelType, num
from plantlab.engine.paste import german, number, read_table
from plantlab.engine.words import money

ROLES = ("supplier", "customer", "hub")
ROLE_WORDS = {"supplier": ["supplier", "source", "plant", "warehouse", "factory", "lieferant", "werk", "lager"],
              "customer": ["customer", "store", "shop", "sink", "destination", "kunde", "markt", "filiale"],
              "hub": ["hub", "cross-dock", "crossdock", "dc", "depot", "umschlag"]}


def route_key(a, b):
    return f"{a} → {b}"


def plural(unit, n=2):
    return unit if n == 1 or unit.endswith("s") else unit + "s"


def codes(places):
    """Short LaTeX-friendly codes: Hamburg -> HAM, Hannover -> HAN, a second HAM -> HA2."""
    out, used = {}, set()
    for p in places:
        base = unicodedata.normalize("NFKD", p["name"]).encode("ascii", "ignore").decode()
        base = re.sub(r"[^A-Za-z0-9]", "", base).upper()[:3] or "P"
        code, n = base, 1
        while code in used:
            n += 1
            code = base[:2] + str(n)
        used.add(code)
        out[p["name"]] = code
    return out


# ---------- building inputs

def place(name, role, amount=0.0, city=None):
    """A place; its coordinates come from the bundled city list when the name (or `city`) is known."""
    c = city if isinstance(city, geo.City) else geo.lookup(city or name)
    return {"name": name, "role": role, "amount": float(amount or 0),
            "lat": c.lat if c else None, "lon": c.lon if c else None}


def find_place(inputs, name):
    return next((p for p in inputs["places"] if p["name"] == name), None)


def route_cost(inputs, km):
    return round(km * inputs["cost_per_km"], 2)


def add_route(inputs, a, b, cost=None, capacity=None):
    """Add a -> b if missing; cost from road distance unless given (then it is kept as typed)."""
    if a == b or any(r["from"] == a and r["to"] == b for r in inputs["routes"]):
        return False
    pa, pb = find_place(inputs, a), find_place(inputs, b)
    km = None
    if pa and pb and pa["lat"] is not None and pb["lat"] is not None:
        km = round(geo.road_km(pa, pb, inputs.get("road_factor", geo.ROAD_FACTOR)), 1)
    manual = cost is not None or km is None
    inputs["routes"].append({"from": a, "to": b, "km": km,
                             "cost": float(cost) if cost is not None else (route_cost(inputs, km) if km else 0.0),
                             "capacity": capacity, "manual": manual})
    return True


def connect_all(inputs):
    """Draw the usual routes: suppliers -> hubs -> customers, and suppliers -> customers."""
    by = {r: [p["name"] for p in inputs["places"] if p["role"] == r] for r in ROLES}
    added = 0
    for s in by["supplier"]:
        for t in by["hub"] + by["customer"]:
            added += add_route(inputs, s, t)
    for h in by["hub"]:
        for t in by["customer"]:
            added += add_route(inputs, h, t)
    return added


def reprice(inputs):
    """After a change of cost per km: every route not typed by hand gets km x rate again."""
    for r in inputs["routes"]:
        if not r.get("manual") and r.get("km"):
            r["cost"] = route_cost(inputs, r["km"])
    return inputs


def remove_place(inputs, name):
    inputs["places"] = [p for p in inputs["places"] if p["name"] != name]
    inputs["routes"] = [r for r in inputs["routes"] if name not in (r["from"], r["to"])]
    return inputs


def empty(unit="pallet", cost_per_km=0.05):
    return {"unit": unit, "cost_per_km": cost_per_km, "road_factor": geo.ROAD_FACTOR, "places": [], "routes": []}


def template(key):
    """Editable starting points (invented numbers, real city distances)."""
    t = empty()
    if key == "blank":
        return t
    if key == "transshipment":
        t["cost_per_km"] = 0.04
        t["places"] = [place("Bremen", "supplier", 450), place("Nuremberg", "supplier", 400),
                       place("Kassel", "hub", 600),
                       place("Dortmund", "customer", 220), place("Leipzig", "customer", 200),
                       place("Hannover", "customer", 180), place("Stuttgart", "customer", 230)]
        connect_all(t)
        for r in t["routes"]:   # part loads straight to a store cost about twice as much per km
            if r["from"] != "Kassel" and r["to"] != "Kassel":
                r["cost"], r["manual"] = round(r["km"] * 0.08, 2), True
        return t
    t["places"] = [place("Hamburg", "supplier", 400), place("Leipzig", "supplier", 300),
                   place("Stuttgart", "supplier", 350),
                   place("Berlin", "customer", 250), place("Köln", "customer", 300),
                   place("Munich", "customer", 280), place("Frankfurt", "customer", 200, city="Frankfurt am Main")]
    connect_all(t)
    return t


TEMPLATES = {"3x4": "3 warehouses → 4 stores (Germany)",
             "transshipment": "Through a cross-dock (transshipment)",
             "blank": "Start empty"}


# ---------- paste from Excel / CSV

def _role(text):
    t = text.strip().casefold()
    return next((r for r, words in ROLE_WORDS.items() if any(t.startswith(w) for w in words)), None)


def from_paste(inputs, text):
    """Three shapes -> (new inputs, message):
    a cost table (suppliers down, customers across, optional Supply column and Demand row),
    a places list (name, role, amount) or a routes list (from, to, cost[, capacity])."""
    rows = read_table(text)
    if len(rows) < 2 and not (rows and len(rows[0]) >= 3):
        return inputs, "Paste at least two rows."
    dc = german(rows)
    out = copy.deepcopy(inputs)
    width = max(len(r) for r in rows)
    roles = [_role(r[1]) for r in rows if len(r) >= 3]
    if width >= 3 and sum(r is not None for r in roles) >= max(1, len(roles) - 1):
        n = 0
        for r in rows:
            role = _role(r[1]) if len(r) >= 3 else None
            if role and r[0]:
                old = find_place(out, r[0])
                amount = number(r[2], dc) or 0.0
                if old:
                    old.update(role=role, amount=amount)
                else:
                    out["places"].append(place(r[0], role, amount))
                n += 1
        return out, f"{n} places read."
    names = {p["name"] for p in out["places"]}
    if width >= 3 and all(r[0] in names and r[1] in names for r in rows[-2:]):
        n = 0
        for r in rows:
            if r[0] in names and r[1] in names and number(r[2], dc) is not None:
                cap = number(r[3], dc) if len(r) > 3 else None
                out["routes"] = [x for x in out["routes"] if not (x["from"] == r[0] and x["to"] == r[1])]
                add_route(out, r[0], r[1], cost=number(r[2], dc), capacity=cap)
                n += 1
        return out, f"{n} routes read."
    # cost table (classic transportation tableau)
    header = rows[0]
    supply_col = next((i for i, h in enumerate(header) if i and re.match(r"(supply|capacity|available|angebot|kapazit)", h, re.I)), None)
    customers = [h for i, h in enumerate(header[1:], 1) if h and i != supply_col]
    body = rows[1:]
    demand_row = next((r for r in body if re.match(r"(demand|order|need|bedarf|nachfrage)", r[0], re.I)), None)
    suppliers = [r for r in body if r is not demand_row and r[0]]
    if not customers or not suppliers:
        return inputs, "Could not read that table: put customers across the top and suppliers down the side."
    out = empty(inputs["unit"], inputs["cost_per_km"])
    for r in suppliers:
        out["places"].append(place(r[0], "supplier", number(r[supply_col], dc) if supply_col and supply_col < len(r) else 0))
    for i, c in enumerate(header):
        if c in customers:
            d = number(demand_row[i], dc) if demand_row and i < len(demand_row) else 0
            out["places"].append(place(c, "customer", d or 0))
    for r in suppliers:
        for i, c in enumerate(header):
            if c in customers and i < len(r) and number(r[i], dc) is not None:
                add_route(out, r[0], c, cost=number(r[i], dc))
    return out, f"{len(suppliers)} suppliers × {len(customers)} customers read."


# ---------- the model type

class Transport(ModelType):
    key = "transport"
    sense = "min"

    def unit(self, inputs):
        return inputs.get("unit") or "unit"

    def validate(self, inputs):
        errors, warnings = [], []
        places, routes = inputs["places"], inputs["routes"]
        units = plural(self.unit(inputs))
        names = [p["name"] for p in places]
        if any(not str(n).strip() for n in names):
            errors.append("Every place needs a name.")
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            errors.append(f"Two places have the same name: {', '.join(dupes)}.")
        roles = {p["role"] for p in places}
        if "supplier" not in roles or "customer" not in roles:
            errors.append("Add at least one supplier and one customer.")
        for p in places:
            if p["role"] not in ROLES:
                errors.append(f"{p['name']}: pick supplier, customer or hub.")
            elif p["role"] != "hub" and (p.get("amount") is None or p["amount"] < 0):
                what = "a supply" if p["role"] == "supplier" else "an order"
                errors.append(f"{p['name']} needs {what} of 0 or more.")
        seen = set()
        for r in routes:
            k = route_key(r["from"], r["to"])
            if r["from"] not in names or r["to"] not in names:
                missing = r["to"] if r["from"] in names else r["from"]
                errors.append(f"Route {k}: '{missing}' is not one of your places.")
            if r["from"] == r["to"]:
                errors.append(f"Route {k} goes nowhere.")
            if k in seen:
                errors.append(f"Route {k} is there twice.")
            seen.add(k)
            if r.get("cost") is None or r["cost"] < 0:
                errors.append(f"Route {k} needs a cost of 0 or more.")
            if r.get("capacity") is not None and r["capacity"] < 0:
                errors.append(f"Route {k}: a capacity can't be negative.")
        if len(routes) > 900:
            errors.append("More than 900 routes is too big for the free CPLEX edition.")
        if errors:
            return errors, warnings
        into = {n: [r for r in routes if r["to"] == n] for n in names}
        out = {n: [r for r in routes if r["from"] == n] for n in names}
        for p in places:
            n = p["name"]
            if p["role"] == "customer" and p["amount"] > 0 and not into[n]:
                warnings.append(f"{n} has no route in, so nothing can reach it.")
            if p["role"] == "supplier" and p["amount"] > 0 and not out[n]:
                warnings.append(f"{n} has no route out.")
            if p["role"] == "hub" and not (into[n] and out[n]):
                warnings.append(f"Hub {n} needs routes in and out to be useful.")
        supply = sum(p["amount"] for p in places if p["role"] == "supplier")
        demand = sum(p["amount"] for p in places if p["role"] == "customer")
        if supply < demand:
            warnings.append(f"Suppliers have {num(supply)} {units}, customers need {num(demand)}: "
                            "not every order can be met.")
        return errors, warnings

    def build(self, b, inputs):
        unit, places, routes = self.unit(inputs), inputs["places"], inputs["routes"]
        units = plural(unit)
        arcs = [route_key(r["from"], r["to"]) for r in routes]
        cost = {k: r["cost"] for k, r in zip(arcs, routes)}
        code = codes(places)
        m = b.m

        x = m.continuous_var_dict(arcs, name="x")
        for k, r in zip(arcs, routes):
            b.decision(k, x[k], label=k, unit=units,
                       symbol=r"x_{\text{%s,%s}}" % (code[r["from"]], code[r["to"]]))

        b.minimize(m.sum(cost[k] * x[k] for k in arcs), "total transport cost")

        out = {p["name"]: [k for k, r in zip(arcs, routes) if r["from"] == p["name"]] for p in places}
        into = {p["name"]: [k for k, r in zip(arcs, routes) if r["to"] == p["name"]] for p in places}
        for p in places:
            n, amount = p["name"], p["amount"] or 0.0
            net_in = m.sum(x[k] for k in into[n]) - m.sum(x[k] for k in out[n])
            if p["role"] == "supplier":
                b.limit(f"supply:{n}", -net_in, "<=", amount, kind="supply", label=f"{n}'s supply", unit=units,
                        words=f"{n} ships at most {num(amount)} {units}",
                        more=f"One more {unit} available at {n}", fix=f"+{{n}} {units} of supply at {n}")
            elif p["role"] == "customer":
                b.limit(f"demand:{n}", net_in, ">=", amount, kind="demand", label=f"{n}'s order", unit=units,
                        words=f"{n} gets at least {num(amount)} {units}",
                        more=f"One more {unit} ordered by {n}", fix=f"deliver {{n}} fewer {units} to {n}")
            else:
                b.limit(f"balance:{n}", net_in, "==", 0, kind="balance", label=f"{n}'s balance", unit=units,
                        words=f"{n} passes on everything it receives",
                        more=f"One more {unit} left at {n}", stretch=False)
                if amount > 0:
                    b.limit(f"hub:{n}", m.sum(x[k] for k in into[n]), "<=", amount, kind="hub",
                            label=f"{n}'s handling capacity", unit=units,
                            words=f"{n} handles at most {num(amount)} {units}",
                            more=f"One more {unit} of handling at {n}", fix=f"+{{n}} {units} of handling at {n}")
        for k, r in zip(arcs, routes):
            if r.get("capacity") is not None:
                b.limit(f"route:{k}", x[k], "<=", r["capacity"], kind="route", label=f"room on {k}", unit=units,
                        words=f"{k} carries at most {num(r['capacity'])} {units}",
                        more=f"One more {unit} of room on {k}", fix=f"+{{n}} {units} of room on {k}")

    def shortfall_words(self, inputs, amount):
        units = plural(self.unit(inputs))
        supply = sum(p["amount"] for p in inputs["places"] if p["role"] == "supplier")
        demand = sum(p["amount"] for p in inputs["places"] if p["role"] == "customer")
        if supply < demand - 1e-6:
            return (f"You're {num(amount)} {units} short: suppliers can ship {num(supply)}, "
                    f"customers need {num(demand)}.")
        return (f"No plan meets every limit: {num(amount)} {units} can't get through "
                "(missing routes, full routes or your rules block them).")

    def apply_fix(self, inputs, key, amount):
        kind, name = key.split(":", 1)
        if kind in ("supply", "hub"):
            find_place(inputs, name)["amount"] += amount
        elif kind == "demand":
            p = find_place(inputs, name)
            p["amount"] = max(0.0, p["amount"] - amount)
        elif kind == "route":
            r = next(r for r in inputs["routes"] if route_key(r["from"], r["to"]) == name)
            r["capacity"] = (r["capacity"] or 0.0) + amount
        return inputs

    # ---------- talking about it

    def plain(self, inputs, rules=()):
        """The model in plain words: You decide / You want / You are limited by."""
        units = plural(self.unit(inputs))
        n = {r: [p for p in inputs["places"] if p["role"] == r] for r in ROLES}
        caps = sum(r.get("capacity") is not None for r in inputs["routes"])
        limited = [f"{len(n['supplier'])} supplier capacities ({num(sum(p['amount'] for p in n['supplier']))} {units} in all)",
                   f"{len(n['customer'])} customer orders ({num(sum(p['amount'] for p in n['customer']))} in all)"]
        if n["hub"]:
            limited.append(f"{len(n['hub'])} hub(s) that pass everything on")
        if caps:
            limited.append(f"{caps} route capacit{'y' if caps == 1 else 'ies'}")
        if rules:
            limited.append(f"{len(rules)} rule{'s' if len(rules) > 1 else ''} of yours")
        return {"decide": f"How many {units} go on each of the {len(inputs['routes'])} routes.",
                "want": f"The lowest total transport cost (cost per {self.unit(inputs)} on a route × {units} on it).",
                "limited": ", ".join(limited) + "."}

    def summary(self, inputs, result):
        """Copy-ready paragraph for a manager."""
        from plantlab.engine import words
        units = plural(self.unit(inputs))
        if result.status == "invalid":
            return "The model is not complete yet: " + " ".join(result.problems)
        if not result.ok:
            text = result.message
            if result.fixes:
                text += " Cheapest fixes: " + "; or ".join(f.words for f in result.fixes[:3]) + "."
            return text
        flows = [(k, v) for k, v in result.plan.items() if v > 1e-6]
        moved = sum(l.activity for l in result.limits if l.kind == "demand")
        parts = [f"The cheapest plan moves {num(moved)} {units} for {money(result.objective)} in transport cost, "
                 f"using {len(flows)} of {len(result.plan)} routes: "
                 + ", ".join(f"{k} {num(v)}" for k, v in sorted(flows, key=lambda f: -f[1])) + "."]
        tight = [l for l in sorted(result.limits, key=lambda l: -abs(l.dual)) if l.binding and abs(l.dual) > 1e-6]
        full = [l for l in tight if l.kind in ("supply", "hub", "route")]
        if full:
            l = full[0]
            parts.append(f"The bottleneck is {l.label}: one more {self.unit(inputs)} there would save "
                         f"{money(-l.dual, cents=True)}.")
        orders = [l for l in tight if l.kind == "demand"]
        if orders:
            l = orders[0]
            parts.append(f"The most expensive order to serve is {l.label.replace(chr(39) + 's order', '')} "
                         f"({money(l.dual, cents=True)} for each extra {self.unit(inputs)}).")
        spare = [l for l in result.limits if l.kind == "supply" and l.slack > 1e-6]
        if spare:
            parts.append("Spare supply: " + ", ".join(f"{l.label.replace(chr(39) + 's supply', '')} "
                                                      f"{num(l.slack)}" for l in spare) + ".")
        if result.rule_prices and result.objective_without_rules is not None:
            extra = result.objective - result.objective_without_rules
            parts.append(f"Your {len(result.rule_prices)} rule(s) add {money(extra)} to the cost."
                         if extra > 0.5 else "Your rules cost nothing extra.")
        return " ".join(parts)

    def diff(self, a, b):
        """What changed from scenario a to scenario b, in short phrases."""
        out = []
        if a.get("cost_per_km") != b.get("cost_per_km"):
            out.append(f"cost per km {money(a['cost_per_km'], cents=True)} → {money(b['cost_per_km'], cents=True)}")
        pa = {p["name"]: p for p in a["places"]}
        pb = {p["name"]: p for p in b["places"]}
        out += [f"+ {n} ({pb[n]['role']} {num(pb[n]['amount'])})" for n in pb if n not in pa]
        out += [f"− {n}" for n in pa if n not in pb]
        for n in pa:
            if n in pb and (pa[n]["amount"] != pb[n]["amount"] or pa[n]["role"] != pb[n]["role"]):
                out.append(f"{n} {num(pa[n]['amount'])} → {num(pb[n]['amount'])}"
                           + (f" ({pb[n]['role']})" if pa[n]["role"] != pb[n]["role"] else ""))
        ra = {route_key(r["from"], r["to"]): r for r in a["routes"]}
        rb = {route_key(r["from"], r["to"]): r for r in b["routes"]}
        out += [f"+ route {k}" for k in rb if k not in ra]
        out += [f"− route {k}" for k in ra if k not in rb]
        for k in ra:
            if k in rb:
                if abs(ra[k]["cost"] - rb[k]["cost"]) > 1e-9 and a.get("cost_per_km") == b.get("cost_per_km"):
                    out.append(f"{k} {money(ra[k]['cost'], cents=True)} → {money(rb[k]['cost'], cents=True)}")
                if ra[k].get("capacity") != rb[k].get("capacity"):
                    cap = lambda c: "no limit" if c is None else num(c)
                    out.append(f"{k} capacity {cap(ra[k].get('capacity'))} → {cap(rb[k].get('capacity'))}")
        return out

    general_latex = r"""\begin{aligned}
\min\; & \textstyle\sum_{(i,j)} c_{ij}\, x_{ij} \\
\text{s.t.}\; & \textstyle\sum_{j} x_{ij} - \sum_{k} x_{ki} \le s_i && \text{every supplier } i \\
& \textstyle\sum_{k} x_{kj} - \sum_{l} x_{jl} \ge d_j && \text{every customer } j \\
& \textstyle\sum_{k} x_{kh} - \sum_{l} x_{hl} = 0 && \text{every hub } h \\
& x_{ij} \le u_{ij} && \text{routes with a capacity} \\
& x_{ij} \ge 0
\end{aligned}"""


MODEL = Transport()
