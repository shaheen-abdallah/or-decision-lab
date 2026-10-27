"""Shortest route and maximum flow on the 'six places' templates, solved by hand.

Shortest route (two-way roads): S-A 4, S-B 2, B-A 1, A-C 5, B-C 8, B-D 10, C-D 2, C-T 6, D-T 2.
Dijkstra from S: S 0 | B 2 | A 3 (via B) | C 8 (via A) | D 10 (via C; via B would be 12) | T 12 (via D).
Best route S → B → A → C → D → T = 12. Without B → A: S → A → C → D → T = 13.

Maximum flow (one-way): S-A 10, S-B 8, A-B 5, A-C 6, B-D 9, D-C 4, C-T 8, D-T 7.
Augmenting paths: S-A-C-T 6, S-B-D-T 7, S-A-B-D-C-T 2 -> 15. Residual reach from S: {S, A, B};
cut A → C (6) + B → D (9) = 15. C → T (8) + D → T (7) = 15 is a second minimum cut, so more room
on A → C alone adds nothing; with one more on C → T too, the maximum is 16. Without A → C: 9.
"""

import pytest

from plantlab import engine
from plantlab.engine import scenarios
from plantlab.models import network as N


def small(kind):
    return N.template(kind, "small")


def test_shortest_route_matches_dijkstra():
    inp = small("shortest")
    r = engine.solve(N.SHORTEST, inp)
    assert r.ok and r.objective == pytest.approx(12)
    assert N.path(inp, r.plan) == ["S", "B", "A", "C", "D", "T"]
    steps = N.dijkstra(inp)
    assert [s["settle"] for s in steps] == ["S", "B", "A", "C", "D", "T"]
    assert steps[-1]["dist"] == pytest.approx({"S": 0, "B": 2, "A": 3, "C": 8, "D": 10, "T": 12})
    assert steps[1]["updated"] == ["A", "C", "D"]     # from B: A 4 -> 3, C 10, D 12
    assert N.dijkstra_path(steps, "T") == ["S", "B", "A", "C", "D", "T"]
    # S -> A (4) loses to S -> B -> A (3) by 1: its reduced cost
    assert r.decisions["S → A"].reduced_cost == pytest.approx(1)
    assert N.MODELS["shortest"].summary(inp, r).startswith(
        "The best route from S to T is S → B → A → C → D → T: 12 km over 5 roads.")


def test_shortest_route_rules_and_fixes():
    inp = small("shortest")
    r = engine.solve(N.SHORTEST, inp, [{"decision": "B → A", "op": "ban"}])
    assert r.objective == pytest.approx(13) and r.rule_prices[0].alone == pytest.approx(1)
    blocked = [{"decision": "C → T", "op": "ban"}, {"decision": "D → T", "op": "ban"}]
    r = engine.solve(N.SHORTEST, inp, blocked)
    assert r.status == "infeasible" and r.message == "No route from S to T keeps every rule."
    assert {f.changes[0][0] for f in r.fixes} == {"rule:0", "rule:1"}
    fixed_inputs, fixed_rules = engine.apply_fix(N.SHORTEST, inp, blocked, r.fixes[0])
    assert engine.solve(N.SHORTEST, fixed_inputs, fixed_rules).ok
    # a plan typed by hand: the route S → A → C → T is 15, 3 above the optimum
    plan = {"S → A": 1, "A → C": 1, "C → T": 1}
    ev = engine.evaluate(N.SHORTEST, inp, [], plan, engine.solve(N.SHORTEST, inp))
    assert ev.feasible and ev.objective == pytest.approx(15) and ev.gap == pytest.approx(3)
    broken = engine.evaluate(N.SHORTEST, inp, [], {"S → A": 1, "A → C": 1})
    assert not broken.feasible


def test_shortest_route_validation():
    inp = small("shortest")
    inp["routes"] = [r for r in inp["routes"] if "T" not in (r["from"], r["to"])]
    assert engine.solve(N.SHORTEST, inp).problems == ["No road leads from S to T. Draw one on the canvas."]
    inp["end"] = "S"
    assert "The start and the end are the same place." in engine.solve(N.SHORTEST, inp).problems


def test_max_flow_and_min_cut():
    inp = small("maxflow")
    r = engine.solve(N.MAXFLOW, inp)
    assert r.ok and r.objective == pytest.approx(15)
    reach, cut, cap = N.min_cut(inp, r.plan)
    assert reach == {"S", "A", "B"} and sorted(cut) == ["A → C", "B → D"] and cap == pytest.approx(15)
    assert "minimum cut) is A → C and B → D" in N.MAXFLOW.summary(inp, r)
    ban = engine.solve(N.MAXFLOW, inp, [{"decision": "A → C", "op": "ban"}])
    assert ban.objective == pytest.approx(9) and ban.rule_prices[0].alone == pytest.approx(6)
    more = small("maxflow")
    N.find_route(more, "A → C")["capacity"] = 7     # on one cut, but the other one still holds
    assert engine.solve(N.MAXFLOW, more).objective == pytest.approx(15)
    N.find_route(more, "C → T")["capacity"] = 9
    assert engine.solve(N.MAXFLOW, more).objective == pytest.approx(16)
    more = small("maxflow")
    N.find_route(more, "S → A")["capacity"] = 20    # not on the cut: nothing
    assert engine.solve(N.MAXFLOW, more).objective == pytest.approx(15)


def test_max_flow_fixes_unbounded_and_scores():
    # at least 8 on A → C (room for 6): +2 room there (C → T takes 8) or ask for 2 less
    inp, rules = small("maxflow"), [{"decision": "A → C", "op": "at least", "value": 8}]
    r = engine.solve(N.MAXFLOW, inp, rules)
    assert r.status == "infeasible" and r.shortfall == pytest.approx(2)
    found = {f.changes[0][0]: f.changes[0][1] for f in r.fixes}
    assert found == pytest.approx({"cap:A → C": 2, "rule:0": 2})
    fixed, rules = engine.apply_fix(N.MAXFLOW, inp, rules, next(f for f in r.fixes if f.changes[0][0] == "cap:A → C"))
    assert N.find_route(fixed, "A → C")["capacity"] == pytest.approx(8)
    assert engine.solve(N.MAXFLOW, fixed, rules).ok
    open_ = small("maxflow")
    for k in ("S → A", "A → C", "C → T"):
        N.find_route(open_, k)["capacity"] = None
    assert engine.solve(N.MAXFLOW, open_).status == "unbounded"
    # beat the solver: S-A-C-T 6 + S-B-D-T 7 = 13, two short of the optimum
    plan = {"S → A": 6, "A → C": 6, "C → T": 6, "S → B": 7, "B → D": 7, "D → T": 7, "total": 13}
    ev = engine.evaluate(N.MAXFLOW, inp, [], plan, engine.solve(N.MAXFLOW, inp))
    assert ev.feasible and ev.gap == pytest.approx(2)


def test_paste_templates_and_scenarios():
    inp, msg = N.from_paste(N.empty("maxflow") | {"start": "S", "end": "T"}, "S\tA\t5\nA\tT\t3\nS\tT\t2", "maxflow")
    assert msg == "3 roads read." and engine.solve(N.MAXFLOW, inp).objective == pytest.approx(5)
    for kind in ("shortest", "maxflow"):
        g = N.template(kind, "germany")
        assert engine.solve(N.MODELS[kind], g).ok
        assert all(p["lat"] is not None for p in g["places"])
    g = N.template("shortest", "germany")
    longer = N.template("shortest", "germany")
    N.find_route(longer, "Kassel → Nuremberg")["length"] += 100
    snaps = [scenarios.snapshot(n, N.SHORTEST, i, [], engine.solve(N.SHORTEST, i)) for n, i in (("Today", g), ("Roadworks", longer))]
    _, rows = scenarios.compare(N.SHORTEST, snaps)
    assert rows[2][2].startswith("Kassel → Nuremberg") and rows[0][1] != rows[0][2]
