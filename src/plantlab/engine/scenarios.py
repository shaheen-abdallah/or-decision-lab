"""Named scenarios side by side ('Today / Close Berlin / +1 truck'), saved as a JSON file."""

import json

from plantlab.engine.core import TOL, num, rule_words
from plantlab.engine.words import money


def snapshot(name, mt, inputs, rules, result):
    """Everything needed to compare and to reload a scenario, as plain JSON-able data."""
    return {
        "name": name, "model": mt.key, "inputs": inputs, "rules": list(rules),
        "status": result.status, "objective": result.objective, "shortfall": result.shortfall,
        "plan": result.plan if result.ok else {},
        "bottlenecks": [(l.label, l.dual) for l in sorted(result.limits, key=lambda l: -abs(l.dual))
                        if l.binding and abs(l.dual) > TOL],
    }


def compare(mt, scenarios, money_sign="€"):
    """-> (headers, rows): one column per scenario, the first one is the reference."""
    if not scenarios:
        return [], []
    first = scenarios[0]
    sign = 1 if mt.sense == "min" else -1
    headers = [""] + [s["name"] for s in scenarios]
    goal = "Total cost" if mt.sense == "min" else "Total profit"

    def value(s):
        if s["status"] == "optimal":
            return money(s["objective"], money_sign)
        return f"no plan ({num(s['shortfall'])} short)" if s["status"] == "infeasible" else s["status"]

    def versus(s):
        if s is first or s["status"] != "optimal" or first["status"] != "optimal":
            return "—"
        d = s["objective"] - first["objective"]
        return "same" if abs(d) < 0.5 else ("+" if d > 0 else "") + money(d, money_sign)

    def changes(s):
        if s is first:
            return "reference"
        lines = mt.diff(first["inputs"], s["inputs"])
        lines += [f"+ {rule_words(r)}" for r in s["rules"] if r not in first["rules"]]
        lines += [f"− {rule_words(r)}" for r in first["rules"] if r not in s["rules"]]
        return "; ".join(lines) or "nothing"

    def plan_changes(s):
        if s is first:
            return "—"
        keys = list(dict.fromkeys([*first["plan"], *s["plan"]]))
        moved = [(k, first["plan"].get(k, 0.0), s["plan"].get(k, 0.0)) for k in keys]
        moved = [m for m in moved if abs(m[1] - m[2]) > TOL]
        moved.sort(key=lambda m: -abs(m[1] - m[2]))
        text = "; ".join(f"{k} {num(a)} → {num(b)}" for k, a, b in moved[:5])
        return (text + (f" (+{len(moved) - 5} more)" if len(moved) > 5 else "")) or "same plan"

    def bottlenecks(s):
        return ", ".join(f"{label} ({money(abs(d), money_sign, cents=True)})" for label, d in s["bottlenecks"][:3]) or "none"

    rows = [[goal] + [value(s) for s in scenarios],
            ["vs " + first["name"]] + [versus(s) for s in scenarios],
            ["What changed"] + [changes(s) for s in scenarios],
            ["Plan changes"] + [plan_changes(s) for s in scenarios],
            ["Bottlenecks (value of one more)"] + [bottlenecks(s) for s in scenarios]]
    return headers, rows


def dumps(scenarios):
    return json.dumps({"version": 1, "scenarios": scenarios}, indent=1, ensure_ascii=False)


def loads(text):
    data = json.loads(text)
    return data["scenarios"] if isinstance(data, dict) else data
