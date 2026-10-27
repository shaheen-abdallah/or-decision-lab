"""Product mix (LP) on the bike-workshop template, solved by hand with the graphical method.

    max  120 c + 200 g                     c = city bikes, g = cargo bikes
    s.t. 2 c + 4 g <= 200   welding hours
         2 c + 2 g <= 140   assembly hours
         1 c + 3 g <= 150   paint-shop hours
               g <= 40      cargo bikes the market takes

Corners: (0,0) 0 · (70,0) 8,400 · (40,30) 10,800 · (20,40) 10,400 · (0,40) 8,000 -> optimum (40, 30).
Duals at (40,30), welding and assembly binding: 120 = 2w + 2a, 200 = 4w + 2a -> w = 40, a = 20.
Welding's 40 holds while the corner stays on the assembly line c + g = 70 with 0 <= g <= 40:
g = (b - 140) / 2 -> b in [140, 220].
"""

import pytest

from plantlab import engine
from plantlab.engine import latex, scenarios, words
from plantlab.models import mix as X

M = X.MODEL


def bikes():
    return X.template("2 products")


def test_optimum_duals_and_ranges():
    r = engine.solve(M, bikes())
    assert r.ok and r.objective == pytest.approx(10800)
    assert r.plan == pytest.approx({"City bike": 40, "Cargo bike": 30})
    dual = {l.key: l.dual for l in r.limits}
    assert dual["resource:Welding"] == pytest.approx(40) and dual["resource:Assembly"] == pytest.approx(20)
    assert dual["resource:Paint shop"] == pytest.approx(0)
    weld = r.limit("resource:Welding")
    assert (weld.rhs_low, weld.rhs_high) == pytest.approx((140, 220))
    assert r.limit("resource:Paint shop").slack == pytest.approx(20)
    assert words.limits(r)[0].startswith("**Welding: at most 200 hours.** One more hour of Welding adds €40.00 of profit")
    text = M.summary(bikes(), r)
    assert text.startswith("The best mix earns €10,800: 40 City bike, 30 Cargo bike.")
    assert "Welding (one more hour is worth €40.00)" in text


def test_graphical_method_corners():
    r = engine.solve(M, bikes())
    g = X.graph(bikes(), result=r)
    got = {(round(x, 6), round(y, 6)): round(z, 6) for (x, y), z in g["corners"]}
    assert got == {(0, 0): 0, (70, 0): 8400, (40, 30): 10800, (20, 40): 10400, (0, 40): 8000}
    assert g["best"] == pytest.approx((40, 30)) and g["bounded"]
    # the region as vertical slices: at c = 20 it runs from g = 0 up to the welding line (g = 40)
    assert (20.0, 0.0, 40.0) in [tuple(round(v, 6) for v in s) for s in g["band"]]
    weld = next(l for l in g["lines"] if l["key"] == "resource:Welding")
    assert X.segment(weld, g["box"]) == pytest.approx([(0, 50), (100, 0)])
    assert X.graph(X.template("3 products")) is None


def test_price_of_a_rule_and_beat_the_solver():
    # "at least 40 cargo bikes": corner (20, 40) = 10,400 -> the rule costs 400; along the welding
    # line each extra cargo bike costs 2 city bikes: 200 - 2 x 120 = -40 profit
    rules = [{"decision": "Cargo bike", "op": "at least", "value": 40}]
    r = engine.solve(M, bikes(), rules)
    assert r.objective == pytest.approx(10400)
    assert r.rule_prices[0].alone == pytest.approx(400)
    assert r.rule_prices[0].marginal == pytest.approx(-40)
    assert words.rule_prices(r)[0] == "**Your rules cost you €400 in all.**"
    # a guess of (50, 20) earns 10,000 and leaves 20 welding hours idle, each worth 40 -> gap 800
    best = engine.solve(M, bikes())
    ev = engine.evaluate(M, bikes(), [], {"City bike": 50, "Cargo bike": 20}, best)
    assert ev.feasible and ev.objective == pytest.approx(10000) and ev.gap == pytest.approx(800)
    assert [round(a) for _, a in ev.parts] == [800] and "Welding left unused" in ev.parts[0][0]
    over = engine.evaluate(M, bikes(), [], {"City bike": 70, "Cargo bike": 10})
    assert over.violations == [("Assembly: at most 140 hours", pytest.approx(20), "over by")]


def test_infeasible_minimum_gives_fixes():
    # 80 city bikes promised need 160 assembly hours, only 140 there:
    # promise 10 fewer (70 x 120 = 8,400) or +20 assembly hours (80 x 120 = 9,600)
    inp = bikes()
    inp["products"][0]["min"] = 80
    r = engine.solve(M, inp)
    assert r.status == "infeasible" and r.shortfall == pytest.approx(10)
    found = {f.changes[0][0]: (f.changes[0][1], f.objective) for f in r.fixes}
    assert found["min:City bike"] == pytest.approx((10, 8400))
    assert found["resource:Assembly"] == pytest.approx((20, 9600))
    assert r.fixes[0].words == "promise 10 fewer City bikes"
    fixed, _ = engine.apply_fix(M, inp, [], r.fixes[0])
    assert engine.solve(M, fixed).objective == pytest.approx(8400)


def test_validation_paste_latex_scenarios():
    endless = X.empty()
    endless["products"] = [X.product("Free lunch", 5)]
    assert "Free lunch uses no resource and has no maximum" in engine.solve(M, endless).message
    text = "\tCity bike\tCargo bike\tAvailable\nWelding\t2\t4\t200\nAssembly\t2\t2\t140\nProfit\t120\t200\nMax\t\t40"
    pasted, msg = X.from_paste(X.empty("bike"), text)
    assert msg == "2 products × 2 resources read."
    assert pasted["products"][1] == X.product("Cargo bike", 200, None, 40)
    assert engine.solve(M, pasted).objective == pytest.approx(10800)   # paint was not binding
    objective, lims, _ = latex.formulation(engine.build(M, bikes()))
    assert r"\max" in objective and r"x_{\text{CIT}}" in objective and r"x_{\text{CAR}}" in objective
    assert lims[0] == ("Welding: at most 200 hours", r"\begin{aligned} & 2\,x_{\text{CIT}} + 4\,x_{\text{CAR}} \;\le\; 200 \end{aligned}")
    more = bikes()
    more["resources"][1]["available"] = 160
    snaps = [scenarios.snapshot(n, M, i, [], engine.solve(M, i)) for n, i in (("Today", bikes()), ("+20 h", more))]
    _, rows = scenarios.compare(M, snaps)
    assert rows[0] == ["Total profit", "€10,800", "€11,200"]   # +20 assembly hours x €20
    assert rows[2][2] == "Assembly 140 → 160 hours"
