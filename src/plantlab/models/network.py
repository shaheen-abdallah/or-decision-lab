"""Network models on one canvas: shortest route and maximum flow (both LPs), plus the hand methods.

Shortest route: what's the cheapest (shortest, fastest) way from A to B?

    x[i,j] = 1 if the route uses road i -> j (the LP gives 0/1 by itself: the matrix is totally unimodular)

    min   sum_(i,j) length[i,j] * x[i,j]
    s.t.  out(A) - in(A) = 1                 leave the start once
          in(B) - out(B) = 1                 arrive at the end once
          in(k) - out(k) = 0                 every other place: what comes in goes out
          x >= 0

    The hand method is Dijkstra (`dijkstra` keeps every step for teach mode). A road's cost range
    says how long it may get before the route changes; an unused road's reduced cost says how much
    shorter it would have to be to join the route.

Maximum flow: how much can my network carry at most from A to B?

    x[i,j] = flow on road i -> j,  v = total flow from A to B

    max   v
    s.t.  out(A) - in(A) = v,  in(B) - out(B) = v,  in(k) - out(k) = 0 elsewhere
          x[i,j] <= capacity[i,j]
          x >= 0

    Max-flow = min-cut: the roads that are full and lead from the places the network can still
    reach (from A, through roads with room left) to the rest form the bottleneck (`min_cut`); their
    capacities add up to the maximum flow. Only more room on a cut road raises it.

Two-way roads (`two_way`) count as one road in each direction, each with the full length and capacity.
"""

import copy
import heapq
import re
import unicodedata

from plantlab import geo
from plantlab.engine.core import TOL, ModelType, num
from plantlab.engine.paste import german, number, read_table


def route_key(a, b):
    return f"{a} → {b}"


def codes(names):
    """Short LaTeX-friendly codes: Hamburg -> HAM, a second HAM -> HA2."""
    out, used = {}, set()
    for n in names:
        base = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
        base = re.sub(r"[^A-Za-z0-9]", "", base).upper()[:3] or "P"
        code, i = base, 1
        while code in used:
            i += 1
            code = base[:2] + str(i)
        used.add(code)
        out[n] = code
    return out


# ---------- building inputs

def place(name, city=None):
    c = city if isinstance(city, geo.City) else geo.lookup(city or name)
    return {"name": name, "lat": c.lat if c else None, "lon": c.lon if c else None}


def find_place(inputs, name):
    return next((p for p in inputs["places"] if p["name"] == name), None)


def empty(kind="shortest"):
    if kind == "maxflow":
        return {"unit": "truck", "per": "day", "two_way": False, "places": [], "routes": [], "start": None, "end": None}
    return {"measure": "km", "two_way": True, "places": [], "routes": [], "start": None, "end": None}


def add_route(inputs, a, b, length=None, capacity=None):
    """Add a road a - b if missing; its length is the road km unless given."""
    if a == b or any({r["from"], r["to"]} == {a, b} if inputs["two_way"] else (r["from"], r["to"]) == (a, b)
                     for r in inputs["routes"]):
        return False
    pa, pb = find_place(inputs, a), find_place(inputs, b)
    km = None
    if pa and pb and pa["lat"] is not None and pb["lat"] is not None:
        km = round(geo.road_km(pa, pb), 0)
    inputs["routes"].append({"from": a, "to": b, "km": km,
                             "length": float(length) if length is not None else (km if km is not None else 1.0),
                             "capacity": None if capacity is None else float(capacity)})
    return True


def arcs(inputs):
    """Directed arcs [(key, from, to, route)]; a two-way road gives one each way."""
    out = []
    for r in inputs["routes"]:
        out.append((route_key(r["from"], r["to"]), r["from"], r["to"], r))
        if inputs.get("two_way"):
            out.append((route_key(r["to"], r["from"]), r["to"], r["from"], r))
    return out


def find_route(inputs, key):
    """The road behind an arc key (either direction on a two-way road)."""
    a, b = key.split(" → ")
    return next((r for r in inputs["routes"] if (r["from"], r["to"]) == (a, b)
                 or inputs.get("two_way") and (r["from"], r["to"]) == (b, a)), None)


def remove_place(inputs, name):
    inputs["places"] = [p for p in inputs["places"] if p["name"] != name]
    inputs["routes"] = [r for r in inputs["routes"] if name not in (r["from"], r["to"])]
    for end in ("start", "end"):
        if inputs.get(end) == name:
            inputs[end] = None
    return inputs


def rename_place(inputs, old, new):
    find_place(inputs, old)["name"] = new
    for r in inputs["routes"]:
        r["from"] = new if r["from"] == old else r["from"]
        r["to"] = new if r["to"] == old else r["to"]
    for end in ("start", "end"):
        if inputs.get(end) == old:
            inputs[end] = new
    return inputs


GERMANY = ["Hamburg", "Bremen", "Hannover", "Berlin", "Dortmund", "Kassel", "Leipzig", "Frankfurt",
           "Nuremberg", "Stuttgart", "Munich"]
ROADS = [("Hamburg", "Bremen"), ("Hamburg", "Hannover"), ("Hamburg", "Berlin"), ("Bremen", "Hannover"),
         ("Bremen", "Dortmund"), ("Hannover", "Dortmund"), ("Hannover", "Kassel"), ("Hannover", "Leipzig"),
         ("Berlin", "Leipzig"), ("Dortmund", "Kassel"), ("Dortmund", "Frankfurt"), ("Kassel", "Frankfurt"),
         ("Kassel", "Leipzig"), ("Leipzig", "Nuremberg"), ("Kassel", "Nuremberg"), ("Frankfurt", "Nuremberg"),
         ("Frankfurt", "Stuttgart"), ("Nuremberg", "Munich"), ("Stuttgart", "Munich"), ("Nuremberg", "Stuttgart")]
# trucks a day each road can take for the shipper (invented)
CAPACITY = {("Hamburg", "Bremen"): 30, ("Hamburg", "Hannover"): 60, ("Hamburg", "Berlin"): 40,
            ("Bremen", "Dortmund"): 35, ("Hannover", "Dortmund"): 20, ("Hannover", "Kassel"): 45,
            ("Berlin", "Leipzig"): 40, ("Hannover", "Leipzig"): 15, ("Dortmund", "Frankfurt"): 50,
            ("Kassel", "Frankfurt"): 30, ("Kassel", "Nuremberg"): 20, ("Leipzig", "Nuremberg"): 45,
            ("Frankfurt", "Stuttgart"): 40, ("Frankfurt", "Nuremberg"): 25, ("Nuremberg", "Munich"): 70,
            ("Stuttgart", "Munich"): 50}


def template(kind, key):
    """Editable starting points (invented numbers, real city distances)."""
    t = empty(kind)
    if key == "blank":
        return t
    if key == "small":   # small enough to solve by hand on the board
        t["places"] = [place(n) | {"lat": None, "lon": None} for n in "SABCDT"]
        if kind == "shortest":
            for a, b, l in [("S", "A", 4), ("S", "B", 2), ("B", "A", 1), ("A", "C", 5), ("B", "C", 8),
                            ("B", "D", 10), ("C", "D", 2), ("C", "T", 6), ("D", "T", 2)]:
                add_route(t, a, b, length=l)
        else:
            for a, b, c in [("S", "A", 10), ("S", "B", 8), ("A", "B", 5), ("A", "C", 6), ("B", "D", 9),
                            ("D", "C", 4), ("C", "T", 8), ("D", "T", 7)]:
                add_route(t, a, b, capacity=c)
        t["start"], t["end"] = "S", "T"
        return t
    t["places"] = [place(n, city="Frankfurt am Main" if n == "Frankfurt" else None) for n in GERMANY]
    if kind == "shortest":
        for a, b in ROADS:
            add_route(t, a, b)
    else:
        for (a, b), c in CAPACITY.items():
            add_route(t, a, b, capacity=c)
    t["start"], t["end"] = "Hamburg", "Munich"
    return t


TEMPLATES = {"shortest": {"germany": "Hamburg → Munich on German motorways", "small": "Six places, by hand (S → T)",
                          "blank": "Start empty"},
             "maxflow": {"germany": "Trucks a day from the port of Hamburg to Munich", "small": "Six places, by hand (S → T)",
                         "blank": "Start empty"}}


# ---------- paste from Excel / CSV

def from_paste(inputs, text, kind):
    """A list of roads: from, to, length (shortest route) or capacity (max flow). Unknown places are added."""
    rows = read_table(text)
    dc = german(rows)
    out = copy.deepcopy(inputs)
    n = 0
    for r in rows:
        if len(r) < 3 or not r[0] or not r[1] or number(r[2], dc) is None:
            continue
        for name in r[:2]:
            if not find_place(out, name):
                out["places"].append(place(name))
        out["routes"] = [x for x in out["routes"] if not (x["from"] == r[0] and x["to"] == r[1])]
        value = number(r[2], dc)
        add_route(out, r[0], r[1], length=value if kind == "shortest" else None,
                  capacity=value if kind == "maxflow" else None)
        n += 1
    if not n:
        return inputs, "Could not read that: one road per row, as from, to, " + \
            ("length." if kind == "shortest" else "capacity.")
    return out, f"{n} roads read."


# ---------- shared checks

def _check(inputs, kind):
    errors = []
    names = [p["name"] for p in inputs["places"]]
    if any(not str(n).strip() for n in names):
        errors.append("Every place needs a name.")
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        errors.append(f"Two places have the same name: {', '.join(dupes)}.")
    s, t = inputs.get("start"), inputs.get("end")
    if not s or not t:
        errors.append("Pick where the trip starts and where it ends.")
    elif s == t:
        errors.append("The start and the end are the same place.")
    elif s not in names or t not in names:
        errors.append("The start or the end is not one of your places.")
    seen = set()
    for r in inputs["routes"]:
        k = route_key(r["from"], r["to"])
        if r["from"] not in names or r["to"] not in names:
            errors.append(f"Road {k}: '{r['to'] if r['from'] in names else r['from']}' is not one of your places.")
        if r["from"] == r["to"]:
            errors.append(f"Road {k} goes nowhere.")
        if k in seen:
            errors.append(f"Road {k} is there twice.")
        seen.add(k)
        if kind == "shortest" and (r.get("length") is None or r["length"] < 0):
            errors.append(f"Road {k} needs a length of 0 or more.")
        if kind == "maxflow" and r.get("capacity") is not None and r["capacity"] < 0:
            errors.append(f"Road {k}: a capacity can't be negative.")
    if len(arcs(inputs)) > 900:
        errors.append("More than 900 roads is too big for the free CPLEX edition.")
    if not errors and inputs["end"] not in reachable(inputs, inputs["start"]):
        errors.append(f"No road leads from {inputs['start']} to {inputs['end']}. Draw one on the canvas.")
    return errors


def reachable(inputs, start, room=None):
    """Places reachable from `start`; with `room` (arc key -> spare amount) only through arcs with room."""
    nxt = {}
    for k, a, b, _ in arcs(inputs):
        if room is None or room.get(k, 0) > TOL:
            nxt.setdefault(a, []).append(b)
    seen, todo = {start}, [start]
    while todo:
        for b in nxt.get(todo.pop(), []):
            if b not in seen:
                seen.add(b)
                todo.append(b)
    return seen


def _balances(b, inputs, x, v=None):
    """Flow balance at every place. Shortest route (v None): the start sends one trip, the end
    receives it. Max flow: the start sends v, the end receives v. Everyone else passes on all of it."""
    m = b.m
    names = [p["name"] for p in inputs["places"]]
    out = {n: [] for n in names}
    into = {n: [] for n in names}
    for k, a, c, _ in arcs(inputs):
        out[a].append(k)
        into[c].append(k)
    s, t = inputs["start"], inputs["end"]
    for n in names:
        net = m.sum(x[k] for k in into[n]) - m.sum(x[k] for k in out[n])
        if n == s:
            b.limit(f"start:{n}", -net if v is None else -net - v, "==", 1 if v is None else 0, kind="start",
                    label=f"start at {n}", stretch=False,
                    words=f"The trip leaves {n} once" if v is None else f"Everything sent leaves {n}")
        elif n == t:
            b.limit(f"end:{n}", net if v is None else net - v, "==", 1 if v is None else 0, kind="end",
                    label=f"end at {n}", stretch=False,
                    words=f"The trip arrives at {n} once" if v is None else f"Everything sent arrives at {n}")
        elif into[n] or out[n]:
            b.limit(f"pass:{n}", net, "==", 0, kind="pass", label=f"{n} passes on",
                    words=f"What reaches {n} goes on", stretch=False)


# ---------- shortest route

class ShortestRoute(ModelType):
    key = "shortest"
    sense = "min"
    money = ""

    def unit(self, inputs):
        return inputs.get("measure") or "km"

    def validate(self, inputs):
        errors = _check(inputs, "shortest")
        warnings = []
        if not errors and not inputs.get("two_way"):
            warnings.append("Roads are one-way: each goes only in the direction it was drawn.")
        return errors, warnings

    def build(self, b, inputs):
        m, unit = b.m, self.unit(inputs)
        a = arcs(inputs)
        code = codes([p["name"] for p in inputs["places"]])
        x = m.continuous_var_dict([k for k, *_ in a], name="x")
        for k, i, j, _ in a:
            b.decision(k, x[k], label=k, unit="trips", symbol=r"x_{\text{%s,%s}}" % (code[i], code[j]))
        b.minimize(m.sum(r["length"] * x[k] for k, _, _, r in a), f"total {unit}")
        _balances(b, inputs, x)

    def shortfall_words(self, inputs, amount):
        return f"No route from {inputs['start']} to {inputs['end']} keeps every rule."

    # ---------- talking about it

    def plain(self, inputs, rules=()):
        unit = self.unit(inputs)
        n = len(inputs["routes"])
        way = "two-way" if inputs.get("two_way") else "one-way"
        limited = [f"{n} {way} roads", f"the trip starts at {inputs['start']} and ends at {inputs['end']}",
                   "every place passes on what it receives"]
        if rules:
            limited.append(f"{len(rules)} rule{'s' if len(rules) > 1 else ''} of yours")
        return {"decide": "Which roads the trip uses (1 = used, 0 = not).",
                "want": f"The fewest {unit} from start to end (sum of the roads used).",
                "limited": ", ".join(limited) + "."}

    def summary(self, inputs, result):
        if result.status == "invalid":
            return "The model is not complete yet: " + " ".join(result.problems)
        if not result.ok:
            text = result.message
            if result.fixes:
                text += " To make it work: " + "; or ".join(f.words for f in result.fixes[:3]) + "."
            return text
        unit = self.unit(inputs)
        stops = path(inputs, result.plan)
        parts = [f"The best route from {inputs['start']} to {inputs['end']} is {' → '.join(stops)}: "
                 f"{num(round(result.objective, 2))} {unit} over {len(stops) - 1} roads."]
        tight = slack_roads(result)
        if tight:
            k, room = tight
            parts.append(f"It stays the best until a road on it gets {num(round(room, 2))} {unit} longer "
                         f"({k} is the most sensitive).")
        close = sorted((d for d in result.decisions.values() if d.value < TOL and d.reduced_cost > TOL),
                       key=lambda d: d.reduced_cost)
        if close:
            d = close[0]
            parts.append(f"The nearest alternative uses {d.label}, which would have to be "
                         f"{num(round(d.reduced_cost, 2))} {unit} shorter to win.")
        if result.rule_prices and result.objective_without_rules is not None:
            extra = result.objective - result.objective_without_rules
            parts.append(f"Your rules add {num(round(extra, 2))} {unit}." if extra > TOL else "Your rules add nothing.")
        return " ".join(parts)

    def diff(self, a, b):
        return _diff(a, b, "length", self.unit(b))

    general_latex = r"""\begin{aligned}
\min\; & \textstyle\sum_{(i,j)} \ell_{ij}\, x_{ij} \\
\text{s.t.}\; & \textstyle\sum_{j} x_{sj} - \sum_{k} x_{ks} = 1 && \text{leave the start } s \\
& \textstyle\sum_{k} x_{kt} - \sum_{j} x_{tj} = 1 && \text{arrive at the end } t \\
& \textstyle\sum_{k} x_{ki} - \sum_{j} x_{ij} = 0 && \text{every other place } i \\
& x_{ij} \ge 0
\end{aligned}"""


def path(inputs, plan):
    """The places on the route, in order (follows the arcs with flow 1 from the start)."""
    nxt = {}
    for k, a, b, _ in arcs(inputs):
        if plan.get(k, 0) > 0.5:
            nxt[a] = b
    stops, here = [inputs["start"]], inputs["start"]
    while here in nxt and here != inputs["end"] and len(stops) <= len(inputs["places"]):
        here = nxt[here]
        stops.append(here)
    return stops


def slack_roads(result):
    """(road, how much longer it may get) for the road on the route closest to changing the route."""
    used = [(d.label, d.cost_high - d.cost) for d in result.decisions.values() if d.value > 0.5]
    used = [u for u in used if u[1] < 1e19]
    return min(used, key=lambda u: u[1]) if used else None


def dijkstra(inputs):
    """Dijkstra from the start, step by step, for teach mode.
    -> [{"settle": place, "dist": {place: d}, "prev": {place: place}, "updated": [places]}]
    The first step settles the start at 0; each step settles the closest open place and relaxes its roads."""
    nxt = {}
    for k, a, b, r in arcs(inputs):
        nxt.setdefault(a, []).append((b, r["length"]))
    s = inputs["start"]
    dist, prev, done, steps = {s: 0.0}, {}, set(), []
    heap = [(0.0, s)]
    while heap:
        d, here = heapq.heappop(heap)
        if here in done:
            continue
        done.add(here)
        updated = []
        for there, length in sorted(nxt.get(here, [])):
            if there not in done and d + length < dist.get(there, float("inf")) - 1e-12:
                dist[there], prev[there] = d + length, here
                heapq.heappush(heap, (dist[there], there))
                updated.append(there)
        steps.append({"settle": here, "dist": dict(dist), "prev": dict(prev), "updated": updated,
                      "done": sorted(done)})
        if here == inputs["end"]:
            break
    return steps


def dijkstra_path(steps, end):
    prev = steps[-1]["prev"] if steps else {}
    if not steps or end not in steps[-1]["dist"]:
        return []
    stops = [end]
    while stops[-1] in prev:
        stops.append(prev[stops[-1]])
    return stops[::-1]


# ---------- maximum flow

class MaxFlow(ModelType):
    key = "maxflow"
    sense = "max"
    money = ""

    def unit(self, inputs):
        return f"{inputs.get('unit') or 'unit'}s/{inputs.get('per') or 'day'}".replace("ss/", "s/")

    def validate(self, inputs):
        errors = _check(inputs, "maxflow")
        warnings = []
        if not errors:
            open_ = [route_key(r["from"], r["to"]) for r in inputs["routes"] if r.get("capacity") is None]
            if open_:
                warnings.append(f"{len(open_)} road(s) have no capacity, so they carry any amount: "
                                + ", ".join(open_[:4]) + ("…" if len(open_) > 4 else "") + ".")
        return errors, warnings

    def build(self, b, inputs):
        m, unit = b.m, self.unit(inputs)
        a = arcs(inputs)
        code = codes([p["name"] for p in inputs["places"]])
        x = m.continuous_var_dict([k for k, *_ in a], name="x")
        for k, i, j, _ in a:
            b.decision(k, x[k], label=k, unit=unit, symbol=r"x_{\text{%s,%s}}" % (code[i], code[j]))
        v = m.continuous_var(name="v")
        b.decision("total", v, label=f"total flow {inputs['start']} → {inputs['end']}", unit=unit, symbol="v")
        b.maximize(v, f"total flow ({unit})")
        _balances(b, inputs, x, v)
        for k, i, j, r in a:
            if r.get("capacity") is not None:
                b.limit(f"cap:{k}", x[k], "<=", r["capacity"], kind="capacity", label=f"room on {k}", unit=unit,
                        words=f"{k} carries at most {num(r['capacity'])} {unit}",
                        more=f"One more {unit.split('/')[0].rstrip('s')} of room on {k}",
                        fix=f"+{{n}} {unit} of room on {k}")

    def shortfall_words(self, inputs, amount):
        return f"Your rules ask for more than the roads can carry ({num(amount)} {self.unit(inputs)} too many)."

    def apply_fix(self, inputs, key, amount):
        if key.startswith("cap:"):
            r = find_route(inputs, key[4:])
            r["capacity"] = (r["capacity"] or 0.0) + amount
        return inputs

    def plain(self, inputs, rules=()):
        unit = self.unit(inputs)
        caps = sum(r.get("capacity") is not None for r in inputs["routes"])
        limited = [f"{caps} road capacities", f"everything starts at {inputs['start']} and ends at {inputs['end']}",
                   "every place passes on what it receives"]
        if rules:
            limited.append(f"{len(rules)} rule{'s' if len(rules) > 1 else ''} of yours")
        return {"decide": f"How many {unit} go on each of the {len(arcs(inputs))} roads.",
                "want": f"The most {unit} from {inputs['start']} to {inputs['end']}.",
                "limited": ", ".join(limited) + "."}

    def summary(self, inputs, result):
        if result.status == "invalid":
            return "The model is not complete yet: " + " ".join(result.problems)
        if result.status == "unbounded":
            return "The network can carry any amount: some route from start to end has no capacity limit."
        if not result.ok:
            text = result.message
            if result.fixes:
                text += " Cheapest fixes: " + "; or ".join(f.words for f in result.fixes[:3]) + "."
            return text
        unit = self.unit(inputs)
        _, cut, cap = min_cut(inputs, result.plan)
        parts = [f"The network carries at most {num(round(result.objective, 2))} {unit} from "
                 f"{inputs['start']} to {inputs['end']}."]
        if cut:
            parts.append(f"The bottleneck (minimum cut) is {' and '.join(cut)}: together they carry {num(round(cap, 2))}, "
                         "and everything sent must cross them. More room elsewhere adds nothing; only these roads "
                         "can raise the maximum.")
        if result.rule_prices and result.objective_without_rules is not None:
            lost = result.objective_without_rules - result.objective
            parts.append(f"Your rules cost {num(round(lost, 2))} {unit}." if lost > TOL else "Your rules cost nothing.")
        return " ".join(parts)

    def diff(self, a, b):
        return _diff(a, b, "capacity", self.unit(b))

    general_latex = r"""\begin{aligned}
\max\; & v \\
\text{s.t.}\; & \textstyle\sum_{j} x_{sj} - \sum_{k} x_{ks} = v && \text{everything starts at } s \\
& \textstyle\sum_{k} x_{kt} - \sum_{j} x_{tj} = v && \text{and arrives at } t \\
& \textstyle\sum_{k} x_{ki} - \sum_{j} x_{ij} = 0 && \text{every other place } i \\
& 0 \le x_{ij} \le u_{ij} && \text{every road}
\end{aligned}"""


def min_cut(inputs, plan):
    """-> (places reachable from the start through roads with room, cut roads, their capacity).
    With a maximum flow, the end is not reachable and the cut roads are all full."""
    room = {}
    for k, a, b, r in arcs(inputs):
        cap = float("inf") if r.get("capacity") is None else r["capacity"]
        f = plan.get(k, 0.0)
        room[k] = room.get(k, 0.0) + cap - f
        back = route_key(b, a)
        room[back] = room.get(back, 0.0) + f     # flow can be sent back (undone)
    reach = reachable_residual(inputs, room)
    cut, cap = [], 0.0
    for k, a, b, r in arcs(inputs):
        if a in reach and b not in reach:
            cut.append(k)
            cap += float("inf") if r.get("capacity") is None else r["capacity"]
    return reach, cut, cap


def reachable_residual(inputs, room):
    nxt = {}
    for k, a, b, _ in arcs(inputs):
        if room.get(k, 0) > TOL:
            nxt.setdefault(a, []).append(b)
        if room.get(route_key(b, a), 0) > TOL:
            nxt.setdefault(b, []).append(a)
    s = inputs["start"]
    seen, todo = {s}, [s]
    while todo:
        for b in nxt.get(todo.pop(), []):
            if b not in seen:
                seen.add(b)
                todo.append(b)
    return seen


def _diff(a, b, field, unit):
    out = []
    na, nb = {p["name"] for p in a["places"]}, {p["name"] for p in b["places"]}
    out += [f"+ {n}" for n in nb - na] + [f"− {n}" for n in na - nb]
    for end in ("start", "end"):
        if a.get(end) != b.get(end):
            out.append(f"{end} {a.get(end)} → {b.get(end)}")
    ra = {route_key(r["from"], r["to"]): r for r in a["routes"]}
    rb = {route_key(r["from"], r["to"]): r for r in b["routes"]}
    out += [f"+ road {k}" for k in rb if k not in ra] + [f"− road {k}" for k in ra if k not in rb]
    show = lambda v: "no limit" if v is None else num(v)
    for k in ra:
        if k in rb and ra[k].get(field) != rb[k].get(field):
            out.append(f"{k} {show(ra[k].get(field))} → {show(rb[k].get(field))} {unit}")
    return out


SHORTEST = ShortestRoute()
MAXFLOW = MaxFlow()
MODELS = {"shortest": SHORTEST, "maxflow": MAXFLOW}
