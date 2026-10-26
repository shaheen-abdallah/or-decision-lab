"""The engine every model type plugs into.

    inputs (plain dict) --validate--> problems in plain words
           --build (Builder: docplex Model + what each part means)--> CPLEX
           --> Result: plan, objective, duals, rhs ranges, slack, reduced costs, cost ranges

On top of one solve:
    find_fixes    infeasible -> elastic re-solve: every limit that may stretch gets a slack
                  variable; first minimise the total stretch (the penalty), then the cost
                  -> the cheapest fixes in words ("+120 pallets of capacity at Hamburg")
    price_rules   lock / ban decisions -> re-solve with and without -> what each rule costs
    evaluate      a plan the user typed: feasible? cost? gap to the optimum and where it comes
                  from (c.x - z* = sum_j d_j x_j + sum_k y_k (A_k x - b_k), every term >= 0)

A model type (`plantlab.models.<type>`) only says how to build its model and how to talk about it.
"""

import math
from dataclasses import dataclass, field

from docplex.mp.dvar import Var
from docplex.mp.model import Model

INF = 1e20
TOL = 1e-6
RULE_OPS = {"ban": "==", "exactly": "==", "at least": ">=", "at most": "<="}


# ---------- what a model type gives the engine

class ModelType:
    key = ""
    sense = "min"
    money = "€"

    def validate(self, inputs):
        """-> (errors, warnings), both lists of plain sentences. Errors stop the solve."""
        return [], []

    def build(self, b, inputs):
        raise NotImplementedError

    def unit(self, inputs):
        return "unit"

    def shortfall_words(self, inputs, amount):
        return f"No plan meets every limit. The smallest change that makes one possible is {num(amount)}."

    def apply_fix(self, inputs, key, amount):
        """Change the inputs so limit `key` stretches by `amount` (rules are handled by the engine)."""
        return inputs


# ---------- building a model: docplex + the meaning of every part

@dataclass
class DecisionSpec:
    key: str
    label: str
    symbol: str
    unit: str
    var: object


@dataclass
class LimitSpec:
    key: str
    kind: str          # model-specific group: supply, demand, route, rule, ...
    label: str         # short noun: "Hamburg's capacity"
    words: str         # full sentence: "Hamburg ships at most 400 pallets"
    sense: str         # "<=", ">=", "=="
    rhs: float
    terms: dict        # decision key -> coefficient (lhs = sum coef * decision)
    unit: str = ""
    more: str = ""     # what +1 on the right-hand side means: "One more pallet available at Hamburg"
    fix: str = ""      # how a stretch reads, with {n}: "+{n} pallets of capacity at Hamburg"
    stretch: bool = True


class Builder:
    """Wraps a docplex Model. Model types add decisions, the objective and limits through it.

    With `stretch` (a set of limit keys) the model is elastic: those limits get slack variables.
    """

    def __init__(self, name, stretch=None):
        self.m = Model(name)
        self.stretch = stretch
        self.decisions = {}
        self.limits = {}
        self.cts = {}
        self.slack = {}
        self.objective = None
        self.objective_terms = {}
        self.objective_const = 0.0
        self.objective_words = ""
        self.sense = "min"
        self.trivially_infeasible = []
        self._key_of = {}

    def decision(self, key, var, label, symbol, unit=""):
        self.decisions[key] = DecisionSpec(key, label, symbol, unit, var)
        self._key_of[var] = key
        return var

    def _terms(self, expr):
        if isinstance(expr, (int, float)):
            return {}, float(expr)
        if isinstance(expr, Var):
            return {self._key_of[expr]: 1.0}, 0.0
        return {self._key_of[v]: float(c) for v, c in expr.iter_terms()}, float(expr.constant)

    def minimize(self, expr, words):
        self._objective("min", expr, words)

    def maximize(self, expr, words):
        self._objective("max", expr, words)

    def _objective(self, sense, expr, words):
        self.sense, self.objective, self.objective_words = sense, expr, words
        self.objective_terms, self.objective_const = self._terms(expr)
        self.m.set_objective(sense, expr)

    def limit(self, key, expr, sense, rhs, *, kind, label, words, unit="", more="", fix="", stretch=True):
        terms, const = self._terms(expr)
        rhs = float(rhs) - const
        spec = LimitSpec(key, kind, label, words, sense, rhs, terms, unit, more, fix, stretch)
        self.limits[key] = spec
        m, lhs = self.m, expr - const if const else expr
        if self.stretch is not None and stretch and key in self.stretch:
            if sense == "<=":
                s = m.continuous_var(name=f"stretch_{len(self.slack)}")
                lhs = lhs - s
            elif sense == ">=":
                s = m.continuous_var(name=f"stretch_{len(self.slack)}")
                lhs = lhs + s
            else:
                up, down = m.continuous_var_list(2, name=f"stretch_{len(self.slack)}")
                lhs, s = lhs - up + down, (up, down)
            self.slack[key] = s
        elif not terms:   # nothing to decide here: docplex would warn about a trivial constraint
            if _violation(sense, 0.0, rhs) > TOL:
                self.trivially_infeasible.append(key)
            return None
        ct = m.add_constraint(_compare(lhs, sense, rhs))
        self.cts[key] = ct
        return ct

    def rule(self, i, rule):
        d = self.decisions[rule["decision"]]
        op = rule["op"]
        value = 0.0 if op == "ban" else float(rule["value"])
        words = rule_words(rule, d.unit)
        fix = {"ban": f"allow {{n}} {d.unit} on {d.label} (lift the ban)",
               "exactly": f"change the fixed amount on {d.label} by {{n}} {d.unit}",
               "at least": f"lower the minimum on {d.label} by {{n}} {d.unit}",
               "at most": f"raise the maximum on {d.label} by {{n}} {d.unit}"}[op]
        more = f"One more {d.unit} forced on {d.label}" if op != "at most" else f"One more {d.unit} allowed on {d.label}"
        return self.limit(f"rule:{i}", d.var, RULE_OPS[op], value, kind="rule", label=f"rule {i + 1}",
                          words=words, unit=d.unit, more=more, fix=fix)


def _compare(lhs, sense, rhs):
    return lhs <= rhs if sense == "<=" else lhs >= rhs if sense == ">=" else lhs == rhs


def _violation(sense, activity, rhs):
    if sense == "<=":
        return max(0.0, activity - rhs)
    if sense == ">=":
        return max(0.0, rhs - activity)
    return abs(activity - rhs)


def rule_words(rule, unit=""):
    label, op = rule["decision"], rule["op"]
    if op == "ban":
        return f"Rule: nothing on {label}"
    return f"Rule: {op} {num(rule['value'])} {unit} on {label}".replace("  ", " ")


def build(mt, inputs, rules=(), stretch=None):
    b = Builder(mt.key, stretch)
    mt.build(b, inputs)
    for i, r in enumerate(rules):
        b.rule(i, r)
    return b


def run(b):
    """Solve the built model -> 'optimal' | 'infeasible' | 'unbounded'."""
    if b.trivially_infeasible:
        return "infeasible"
    if b.m.solve() is not None:
        return "optimal"
    status = b.m.solve_details.status
    if "unbounded" in status and "infeasible" in status:   # CPLEX could not tell: check feasibility alone
        b.m.set_objective("min", 0)
        return "unbounded" if b.m.solve() is not None else "infeasible"
    return "unbounded" if "unbounded" in status else "infeasible"


# ---------- results

@dataclass
class Decision:
    key: str
    label: str
    value: float
    cost: float              # objective coefficient
    reduced_cost: float
    cost_low: float          # objective ranging: the plan stays optimal for coefficients in [low, high]
    cost_high: float
    unit: str = ""


@dataclass
class Limit:
    key: str
    kind: str
    label: str
    words: str
    sense: str
    rhs: float
    activity: float
    dual: float              # d objective / d rhs (CPLEX convention)
    rhs_low: float           # the dual holds for rhs in [low, high]
    rhs_high: float
    more: str = ""
    unit: str = ""

    @property
    def slack(self):
        return {"<=": self.rhs - self.activity, ">=": self.activity - self.rhs}.get(self.sense, 0.0)

    @property
    def binding(self):
        return abs(self.slack) < TOL


@dataclass
class Fix:
    words: str
    kinds: list
    changes: list            # [(limit key, amount)]
    objective: float         # objective of the best plan after the fix
    plan: dict


@dataclass
class RulePrice:
    index: int
    words: str
    alone: float | None      # objective change with only this rule; None = impossible on its own
    marginal: float          # dual: what one more unit of the rule costs


@dataclass
class Result:
    status: str              # optimal | infeasible | unbounded | invalid
    sense: str = "min"
    message: str = ""
    objective: float | None = None
    decisions: dict = field(default_factory=dict)
    limits: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    shortfall: float = 0.0
    fixes: list = field(default_factory=list)
    rule_prices: list = field(default_factory=list)
    objective_without_rules: float | None = None

    @property
    def ok(self):
        return self.status == "optimal"

    @property
    def plan(self):
        return {k: d.value for k, d in self.decisions.items()}

    def limit(self, key):
        return next((l for l in self.limits if l.key == key), None)


def _extract(b):
    m = b.m
    sens = m.get_cplex().solution.sensitivity
    dkeys = list(b.decisions)
    dvars = [b.decisions[k].var for k in dkeys]
    reduced = m.reduced_costs(dvars) if dvars else []
    obj_rng = sens.objective([v.index for v in dvars]) if dvars else []
    decisions = {}
    for k, v, d, (lo, hi) in zip(dkeys, dvars, reduced, obj_rng):
        spec = b.decisions[k]
        decisions[k] = Decision(k, spec.label, _clean(v.solution_value), b.objective_terms.get(k, 0.0),
                                _clean(d), lo, hi, spec.unit)
    lkeys = [k for k in b.limits if k in b.cts]
    rhs_rng = dict(zip(lkeys, sens.rhs([b.cts[k].index for k in lkeys]))) if lkeys else {}
    limits = []
    for k, spec in b.limits.items():
        act = sum(c * decisions[d].value for d, c in spec.terms.items())
        ct = b.cts.get(k)
        dual = _clean(ct.dual_value) if ct is not None else 0.0
        lo, hi = rhs_rng.get(k, (-INF, INF))
        limits.append(Limit(k, spec.kind, spec.label, spec.words, spec.sense, spec.rhs, _clean(act), dual,
                            lo, hi, spec.more, spec.unit))
    return decisions, limits


def _clean(x):
    return 0.0 if abs(x) < 1e-9 else x


def solve(mt, inputs, rules=(), *, fixes=True, rule_prices=True):
    """Validate, build, solve. Infeasible -> fixes; rules -> their price."""
    errors, warnings = mt.validate(inputs)
    errors = errors + _rule_problems(mt, inputs, rules) if not errors else errors
    if errors:
        return Result("invalid", mt.sense, "Fix these first: " + " ".join(errors), problems=errors, warnings=warnings)
    b = build(mt, inputs, rules)
    status = run(b)
    r = Result(status, b.sense, warnings=warnings)
    if status == "unbounded":
        r.message = ("The model has no best answer: the objective can grow without end. "
                     "Some number is missing a limit (a negative cost, or a product with no capacity limit).")
        return r
    if status == "infeasible":
        r.shortfall, r.fixes = find_fixes(mt, inputs, rules)
        r.message = mt.shortfall_words(inputs, r.shortfall) if r.fixes else \
            "No plan meets every limit, and stretching the limits does not help either."
        return r
    r.objective = b.m.objective_value
    r.decisions, r.limits = _extract(b)
    if rules and rule_prices:
        r.objective_without_rules, r.rule_prices = price_rules(mt, inputs, rules, r)
    return r


def _rule_problems(mt, inputs, rules):
    if not rules:
        return []
    keys = set(build(mt, inputs).decisions)
    out = []
    for i, rule in enumerate(rules):
        if rule.get("decision") not in keys:
            out.append(f"Rule {i + 1} is about '{rule.get('decision')}', which is not in the model any more.")
        elif rule.get("op") not in RULE_OPS:
            out.append(f"Rule {i + 1}: pick ban, exactly, at least or at most.")
        elif rule["op"] != "ban" and (rule.get("value") is None or float(rule["value"]) < 0):
            out.append(f"Rule {i + 1} needs an amount of 0 or more.")
    return out


# ---------- price of a rule

def price_rules(mt, inputs, rules, with_rules):
    """-> (objective without rules, [RulePrice]). Price = change in the objective, signed so that
    a positive number always means 'this rule hurts' (more cost, or less profit)."""
    sign = 1 if mt.sense == "min" else -1
    b0 = build(mt, inputs)
    if run(b0) != "optimal":
        return None, []
    base = b0.m.objective_value
    prices = []
    for i, rule in enumerate(rules):
        b = build(mt, inputs, [rule])
        alone = sign * (b.m.objective_value - base) if run(b) == "optimal" else None
        lim = with_rules.limit(f"rule:{i}")
        prices.append(RulePrice(i, rule_words(rule, b0.decisions[rule["decision"]].unit), alone,
                                lim.dual if lim else 0.0))
    return base, prices


# ---------- infeasible -> fixes

def _elastic(mt, inputs, rules, keys):
    """Stretch only `keys`: first the smallest total stretch, then the best objective with it."""
    b = build(mt, inputs, rules, stretch=set(keys))
    slack = [v for s in b.slack.values() for v in (s if isinstance(s, tuple) else (s,))]
    if b.trivially_infeasible or not slack:
        return None
    total = b.m.sum(slack)
    b.m.minimize(total)
    if b.m.solve() is None:
        return None
    least = b.m.objective_value
    b.m.add_constraint(total <= least * (1 + 1e-9) + 1e-9)
    b.m.set_objective(b.sense, b.objective)
    if b.m.solve() is None:
        return None
    changes = []
    for k, s in b.slack.items():
        v = s[0].solution_value - s[1].solution_value if isinstance(s, tuple) else s.solution_value
        if abs(v) > TOL:
            changes.append((k, round(v, 6)))
    words = " and ".join(b.limits[k].fix.format(n=num(abs(v))) for k, v in changes)
    plan = {k: _clean(d.var.solution_value) for k, d in b.decisions.items()}
    return least, Fix(words, [b.limits[k].kind for k, _ in changes], changes, b.m.objective_value, plan)


def find_fixes(mt, inputs, rules=()):
    """-> (smallest total stretch, fixes). Fixes that work on their own come first, cheapest first;
    if no single limit can fix it, the combined smallest stretch."""
    b = build(mt, inputs, rules)
    keys = [k for k, l in b.limits.items() if l.stretch]
    combined = _elastic(mt, inputs, rules, keys)
    if combined is None:
        return 0.0, []
    least, best = combined
    singles = [f for k in keys if (f := _elastic(mt, inputs, rules, [k])) is not None]
    sign = 1 if b.sense == "min" else -1

    def rank(f):   # smallest change first; then more capacity before less demand before softer rules
        key = f.changes[0][0]
        group = 2 if key.startswith("rule:") else 0 if b.limits[key].sense == "<=" else 1
        return round(sum(abs(v) for _, v in f.changes), 3), group, sign * f.objective

    fixes = sorted((f for _, f in singles), key=rank)
    return least, fixes or [best]


def apply_fix(mt, inputs, rules, fix):
    """Inputs and rules after applying a fix (rules loosened here, the rest by the model type)."""
    import copy
    inputs, rules = copy.deepcopy(inputs), copy.deepcopy(list(rules))
    for key, amount in fix.changes:
        if key.startswith("rule:"):
            rule = rules[int(key.split(":")[1])]
            if rule["op"] == "ban":
                rule.update(op="at most", value=abs(amount))
            else:
                rule["value"] = max(0.0, float(rule["value"]) + amount * (-1 if rule["op"] == "at least" else 1))
        else:
            inputs = mt.apply_fix(inputs, key, amount)
    return inputs, rules


# ---------- beat the solver

@dataclass
class Evaluation:
    objective: float
    violations: list         # [(limit words, amount, phrase)]
    gap: float | None = None # how much worse than the optimum (>= 0); None if not comparable
    parts: list = field(default_factory=list)   # [(words, amount)] summing to the gap

    @property
    def feasible(self):
        return not self.violations


def evaluate(mt, inputs, rules, plan, optimum=None):
    """Score a user's plan {decision key: amount}; missing decisions count as 0."""
    b = build(mt, inputs, rules)
    x = {k: _amount(plan.get(k)) for k in b.decisions}
    obj = b.objective_const + sum(c * x[k] for k, c in b.objective_terms.items())
    violations = [(f"{b.decisions[k].label} can't be negative", -v, "below 0") for k, v in x.items() if v < -TOL]
    activity = {}
    for k, spec in b.limits.items():
        act = activity[k] = sum(c * x[d] for d, c in spec.terms.items())
        over = _violation(spec.sense, act, spec.rhs)
        if over > TOL:
            phrase = "short by" if spec.sense == ">=" or (spec.sense == "==" and act < spec.rhs) else "over by"
            violations.append((spec.words, over, phrase))
    ev = Evaluation(obj, violations)
    if violations or optimum is None or not optimum.ok:
        return ev
    sign = 1 if mt.sense == "min" else -1
    ev.gap = sign * (obj - optimum.objective)
    money = mt.money
    for k, d in optimum.decisions.items():
        part = sign * d.reduced_cost * x[k]
        if abs(part) > TOL:
            ev.parts.append((f"{num(x[k])} {d.unit} on {d.label}: each {'costs' if sign > 0 else 'earns'} "
                             f"{money}{abs(d.reduced_cost):,.2f} {'more' if sign > 0 else 'less'} than the best "
                             f"alternative (reduced cost)", part))
    for lim in optimum.limits:
        part = sign * lim.dual * (activity[lim.key] - lim.rhs)
        if abs(part) > TOL:
            gap = abs(activity[lim.key] - lim.rhs)
            what = "left unused" if lim.sense == "<=" else "more than needed"
            ev.parts.append((f"{num(gap)} {lim.unit} of {lim.label} {what}: each is worth "
                             f"{money}{abs(lim.dual):,.2f}", part))
    ev.parts.sort(key=lambda p: -p[1])
    return ev


def _amount(v):
    """A typed amount: blank, None or NaN (an emptied table cell) counts as 0."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(v) else v


def num(x):
    """1,234 or 12.5: amounts in words without needless decimals."""
    return f"{x:,.0f}" if abs(x - round(x)) < 1e-6 else f"{x:,.2f}".rstrip("0").rstrip(".")
