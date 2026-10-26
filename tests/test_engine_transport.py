"""Engine + transport model on cases solved by hand (u_i + v_j method, checked against CPLEX).

The 2 x 2 case (the same numbers as test_parts_transport):

            P1   P2   supply
    S1       4    6     20
    S2       5    3     40
    demand  25   25

Optimum: S1 -> P1 20, S2 -> P1 5, S2 -> P2 25 = 80 + 25 + 75 = 180, S2 keeps 10 spare.
u_S2 = 0 (spare), v_P1 = 5, v_P2 = 3 (S2's routes are used), u_S1 = 4 - 5 = -1.
"""

import pytest

from plantlab import engine
from plantlab.engine import latex, scenarios, words
from plantlab.engine.paste import number, read_table
from plantlab.models import transport as T

M = T.MODEL


def two_by_two(s1=20, s2=40, d1=25, d2=25, capacity=None):
    inp = T.empty("set")
    inp["places"] = [T.place("S1", "supplier", s1), T.place("S2", "supplier", s2),
                     T.place("P1", "customer", d1), T.place("P2", "customer", d2)]
    for a, b, c in [("S1", "P1", 4), ("S1", "P2", 6), ("S2", "P1", 5), ("S2", "P2", 3)]:
        T.add_route(inp, a, b, cost=c, capacity=(capacity or {}).get((a, b)))
    return inp


def test_optimum_duals_and_ranges():
    r = engine.solve(M, two_by_two())
    assert r.ok and r.objective == pytest.approx(180)
    assert r.plan == pytest.approx({"S1 → P1": 20, "S1 → P2": 0, "S2 → P1": 5, "S2 → P2": 25})
    dual = {l.key: l.dual for l in r.limits}
    assert dual["demand:P1"] == pytest.approx(5) and dual["demand:P2"] == pytest.approx(3)
    assert dual["supply:S1"] == pytest.approx(-1) and dual["supply:S2"] == pytest.approx(0)
    # S1's -1 holds while S1 has 10..25 sets: below 10, S2 runs out; above 25, S2 -> P1 is gone
    s1 = r.limit("supply:S1")
    assert (s1.rhs_low, s1.rhs_high) == pytest.approx((10, 25))
    # reduced cost of the unused route S1 -> P2: 6 - (u_S1 + v_P2) = 6 - (-1 + 3) = 4
    assert r.decisions["S1 → P2"].reduced_cost == pytest.approx(4)
    assert "S2's supply: 10 sets spare" in words.spare(r)
    assert any(line.startswith("**S1 ships at most 20 sets.** One more set available at S1 saves €1.00, "
                               "for the next 5 sets") for line in words.limits(r))


def test_price_of_a_rule():
    # force 5 sets on S1 -> P2: each costs 6 instead of 3 (via S2) and pushes one S1 set at P1 to S2 (+1)
    # -> 5 x (3 + 1) = 20; plan S1->P1 15, S1->P2 5, S2->P1 10, S2->P2 20 = 60 + 30 + 50 + 60 = 200
    rules = [{"decision": "S1 → P2", "op": "at least", "value": 5}]
    r = engine.solve(M, two_by_two(), rules)
    assert r.objective == pytest.approx(200)
    assert r.objective_without_rules == pytest.approx(180)
    assert r.rule_prices[0].alone == pytest.approx(20)
    assert r.rule_prices[0].marginal == pytest.approx(4)    # the reduced cost of S1 -> P2
    # banning a route the optimum does not use is free
    free = engine.solve(M, two_by_two(), [{"decision": "S1 → P2", "op": "ban"}])
    assert free.rule_prices[0].alone == pytest.approx(0)


def test_infeasible_gives_cheapest_fixes():
    # 20 sets for 50 ordered: 30 short
    # +30 at S1 (50, 10): S2->P2 10, S1->P1 25, S1->P2 15 = 30 + 100 + 90 = 220
    # +30 at S2 (10, 40): S1->P1 10, S2->P1 15, S2->P2 25 = 40 + 75 + 75 = 190
    # cutting one order cannot help on its own (each is only 25)
    r = engine.solve(M, two_by_two(s1=10, s2=10))
    assert r.status == "infeasible"
    assert r.shortfall == pytest.approx(30)
    assert "You're 30 sets short: suppliers can ship 20, customers need 50." == r.message
    found = {f.changes[0][0]: (f.changes[0][1], f.objective) for f in r.fixes}
    assert found == {"supply:S2": pytest.approx((30, 190)), "supply:S1": pytest.approx((30, 220))}
    assert r.fixes[0].words == "+30 sets of supply at S2"
    fixed, _ = engine.apply_fix(M, two_by_two(s1=10, s2=10), [], r.fixes[0])
    assert engine.solve(M, fixed).objective == pytest.approx(190)


def test_combined_fix_when_no_single_limit_helps():
    # only 20 sets and routes S1 -> P1, S2 -> P2: each order is 25 -> 5 short at each customer;
    # raising one supply or cutting one order can't fix both -> the combined smallest stretch (10)
    inp = two_by_two(s1=20, s2=20)
    inp["routes"] = [r for r in inp["routes"] if (r["from"], r["to"]) in {("S1", "P1"), ("S2", "P2")}]
    r = engine.solve(M, inp)
    assert r.shortfall == pytest.approx(10)
    assert len(r.fixes) == 1 and len(r.fixes[0].changes) == 2


def test_rule_that_breaks_feasibility_can_be_loosened():
    # S1 may ship at most 20 but the rule demands 30 on S1 -> P1
    r = engine.solve(M, two_by_two(), [{"decision": "S1 → P1", "op": "at least", "value": 30}])
    assert r.status == "infeasible"
    rule_fix = next(f for f in r.fixes if f.changes[0][0] == "rule:0")
    assert rule_fix.changes[0][1] == pytest.approx(10)
    _, rules = engine.apply_fix(M, two_by_two(), [{"decision": "S1 → P1", "op": "at least", "value": 30}], rule_fix)
    assert rules[0]["value"] == pytest.approx(20)


def test_beat_the_solver_gap_and_where_it_comes_from():
    inp = two_by_two()
    best = engine.solve(M, inp)
    # S1->P2 20, S2->P1 25, S2->P2 5 = 120 + 125 + 15 = 260: gap 80 = reduced cost 4 x 20 sets on S1 -> P2
    ev = engine.evaluate(M, inp, [], {"S1 → P2": 20, "S2 → P1": 25, "S2 → P2": 5}, best)
    assert ev.feasible and ev.objective == pytest.approx(260) and ev.gap == pytest.approx(80)
    assert [round(p[1], 6) for p in ev.parts] == [80]
    # S1->P1 10, S2->P1 15, S2->P2 25 = 190: gap 10 = 10 sets of S1 left unused x €1
    ev = engine.evaluate(M, inp, [], {"S1 → P1": 10, "S2 → P1": 15, "S2 → P2": 25}, best)
    assert ev.gap == pytest.approx(10)
    assert ev.parts[0][0].startswith("10 sets of S1's supply left unused")
    # an emptied table cell (NaN) counts as 0
    assert engine.evaluate(M, inp, [], {"S1 → P1": 20, "S1 → P2": float("nan"), "S2 → P1": 5, "S2 → P2": 25},
                           best).gap == pytest.approx(0)
    # too much from S1 and nothing for P2: two broken limits, no gap
    ev = engine.evaluate(M, inp, [], {"S1 → P1": 30}, best)
    assert not ev.feasible and ev.gap is None
    assert {(w, round(a)) for w, a, _ in ev.violations} == {("S1 ships at most 20 sets", 10),
                                                            ("P2 gets at least 25 sets", 25)}


def test_transshipment_hub_and_capacities():
    # S (100) -> C (100): direct 10, via hub H 3 + 4 = 7 -> 700
    inp = T.empty("unit")
    inp["places"] = [T.place("S", "supplier", 100), T.place("H", "hub", 0), T.place("C", "customer", 100)]
    for a, b, c in [("S", "C", 10), ("S", "H", 3), ("H", "C", 4)]:
        T.add_route(inp, a, b, cost=c)
    assert engine.solve(M, inp).objective == pytest.approx(700)
    # hub handles at most 60: 60 x 7 + 40 x 10 = 820; one more unit of handling saves 10 - 7 = 3
    inp["places"][1]["amount"] = 60
    r = engine.solve(M, inp)
    assert r.objective == pytest.approx(820)
    assert r.limit("hub:H").dual == pytest.approx(-3)
    # same bottleneck as a route capacity instead
    inp["places"][1]["amount"] = 0
    inp["routes"][1]["capacity"] = 60
    assert engine.solve(M, inp).limit("route:S → H").dual == pytest.approx(-3)


def test_plain_words_validation_and_warnings():
    inp = two_by_two()
    inp["routes"][0]["cost"] = -1
    r = engine.solve(M, inp)
    assert r.status == "invalid" and "Route S1 → P1 needs a cost of 0 or more." in r.problems
    inp = two_by_two()
    inp["routes"] = [r for r in inp["routes"] if r["to"] != "P2"]
    r = engine.solve(M, inp)
    assert "P2 has no route in, so nothing can reach it." in r.warnings
    assert r.status == "infeasible" and r.fixes[0].words == "deliver 25 fewer sets to P2"
    r = engine.solve(M, two_by_two(), [{"decision": "S9 → P1", "op": "ban"}])
    assert r.status == "invalid" and "not in the model" in r.problems[0]


def test_unbounded_model_gets_a_plain_message():
    class Free(engine.ModelType):
        key, sense = "free", "max"

        def build(self, b, inputs):
            x = b.decision("x", b.m.continuous_var(name="x"), "x", "x")
            b.maximize(x, "x")
            b.limit("floor", x, ">=", 1, kind="floor", label="floor", words="x is at least 1")

    r = engine.solve(Free(), {})
    assert r.status == "unbounded" and "without end" in r.message


def test_show_the_math_has_every_number():
    b = engine.build(M, two_by_two())
    objective, limits, _ = latex.formulation(b)
    assert r"4\,x_{\text{S1,P1}}" in objective and r"\min" in objective
    assert len(limits) == 4
    assert limits[0] == ("S1 ships at most 20 sets",
                         r"\begin{aligned} & x_{\text{S1,P1}} + x_{\text{S1,P2}} \;\le\; 20 \end{aligned}")


def test_scenarios_compare_and_round_trip():
    a = two_by_two()
    b = two_by_two(s1=0)                       # close S1
    sa = scenarios.snapshot("Today", M, a, [], engine.solve(M, a))
    sb = scenarios.snapshot("Close S1", M, b, [], engine.solve(M, b))
    headers, rows = scenarios.compare(M, [sa, sb])
    table = {r[0]: r[1:] for r in rows}
    assert headers == ["", "Today", "Close S1"]
    assert table["Total cost"] == ["€180", "no plan (10 short)"]
    assert table["What changed"][1] == "S1 20 → 0"
    assert scenarios.loads(scenarios.dumps([sa, sb]))[1]["name"] == "Close S1"


def test_paste_cost_table_from_excel_and_german_numbers():
    text = "\tBerlin\tMunich\tSupply\nHamburg\t15,5\t38\t400\nLeipzig\t9\t21,25\t300\nDemand\t250\t280\t"
    inp, msg = T.from_paste(T.empty(), text)
    assert msg == "2 suppliers × 2 customers read."
    assert [(p["name"], p["role"], p["amount"]) for p in inp["places"]] == [
        ("Hamburg", "supplier", 400), ("Leipzig", "supplier", 300), ("Berlin", "customer", 250), ("Munich", "customer", 280)]
    assert inp["places"][0]["lat"] == pytest.approx(53.55, abs=0.01)    # known city -> on the map
    assert {(r["from"], r["to"]): r["cost"] for r in inp["routes"]}[("Leipzig", "Munich")] == 21.25
    assert number("1.234,5", decimal_comma=True) == 1234.5 and number("1,234.5") == 1234.5
    assert read_table("a;b\n1;2") == [["a", "b"], ["1", "2"]]
    inp, msg = T.from_paste(inp, "Kassel\thub\t500\nBremen\tsupplier\t100")
    assert msg == "2 places read." and T.find_place(inp, "Kassel")["role"] == "hub"


def test_city_list_and_road_distance():
    from plantlab import geo
    assert geo.find("münch")[0].name == "Munich" and geo.lookup("München").name == "Munich"
    h, m = geo.lookup("Hamburg"), geo.lookup("Munich")
    assert geo.great_circle_km(h.lat, h.lon, m.lat, m.lon) == pytest.approx(612, abs=3)   # known: ~612 km
    assert geo.road_km(h, m) == pytest.approx(612 * 1.25, abs=4)
    inp = T.template("3x4")
    assert len(inp["routes"]) == 12 and all(r["km"] and r["cost"] == round(r["km"] * 0.05, 2) for r in inp["routes"])
