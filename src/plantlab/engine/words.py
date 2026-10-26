"""Results in plain words: what limits you, what is unused, what rules cost, how to fix it."""

from plantlab.engine.core import INF, TOL, num


def money(value, money="€", cents=False):
    sign = "-" if value < -0.005 else ""
    return f"{sign}{money}{abs(value):,.2f}" if cents else f"{sign}{money}{abs(value):,.0f}"


def _effect(dual, sense, money_sign):
    """What +1 on a limit's right-hand side does to the objective, in words."""
    amount = money(abs(dual), money_sign, cents=True)
    if sense == "min":
        return f"saves {amount}" if dual < 0 else f"adds {amount} to the cost"
    return f"adds {amount} of profit" if dual > 0 else f"costs {amount} of profit"


def _range(lim):
    """How far the shadow price holds when the limit grows."""
    if lim.rhs_high >= INF / 10:
        return "for every extra one"
    return f"for the next {num(lim.rhs_high - lim.rhs)} {lim.unit}".rstrip()


def limits(result, money_sign="€"):
    """'What limits you?': binding limits with a shadow price, most valuable first."""
    out = []
    tight = [l for l in result.limits if l.binding and abs(l.dual) > TOL]
    for l in sorted(tight, key=lambda l: -abs(l.dual)):
        out.append(f"**{l.words}.** {l.more} {_effect(l.dual, result.sense, money_sign)}, {_range(l)}.")
    return out


def spare(result):
    """Limits with room left: not a bottleneck."""
    return [f"{l.label}: {num(l.slack)} {l.unit} spare" for l in result.limits
            if l.sense == "<=" and l.slack > TOL]


def unused(result, money_sign="€"):
    """Decisions left at zero and how much better they would have to get."""
    out = []
    for d in result.decisions.values():
        if d.value < TOL and abs(d.reduced_cost) > TOL:
            better = "cheaper" if result.sense == "min" else "more profitable"
            out.append(f"{d.label} is not used: it would have to be "
                       f"{money(abs(d.reduced_cost), money_sign, cents=True)} {better} per unit to pay off.")
    return out


def cost_ranges(result, money_sign="€"):
    """Used decisions: the cost window in which the plan stays the same."""
    out = []
    for d in result.decisions.values():
        if d.value > TOL:
            lo = "any lower cost" if d.cost_low <= -INF / 10 else money(d.cost_low, money_sign, cents=True)
            hi = "any higher cost" if d.cost_high >= INF / 10 else money(d.cost_high, money_sign, cents=True)
            out.append((d.label, num(d.value), money(d.cost, money_sign, cents=True), lo, hi))
    return out


def rule_prices(result, money_sign="€"):
    """What the user's rules cost, together and one by one."""
    if not result.rule_prices or result.objective_without_rules is None:
        return []
    sign = 1 if result.sense == "min" else -1
    total = sign * (result.objective - result.objective_without_rules)
    if abs(total) <= TOL:
        out = ["**Your rules change nothing: the best plan already follows them.**"]
    else:
        out = [f"**Your rules {'cost' if total > 0 else 'save'} you {money(abs(total), money_sign)} in all.**"]
    for p in result.rule_prices:
        if p.alone is None:
            alone = "impossible on its own"
        elif abs(p.alone) <= TOL:
            alone = "free on its own (the best plan does this anyway)"
        else:
            alone = f"costs {money(p.alone, money_sign)} on its own"
        marg = f"; each extra unit {_effect(p.marginal, result.sense, money_sign)}" if abs(p.marginal) > TOL else ""
        out.append(f"{p.words}: {alone}{marg}.")
    return out


def ordered_fixes(result):
    """Fixes for display: the best of each kind first (more supply, fewer deliveries, softer rules)."""
    seen, first, rest = set(), [], []
    for f in result.fixes:
        kind = tuple(f.kinds)
        (rest if kind in seen else first).append(f)
        seen.add(kind)
    return first + rest


def fix_line(result, fix, money_sign="€"):
    word = "costs" if result.sense == "min" else "earns"
    return f"{fix.words[0].upper() + fix.words[1:]} → the best plan then {word} {money(fix.objective, money_sign)}"


def fixes(result, money_sign="€", top=4):
    """The cheapest fixes in words, at most `top`."""
    return [fix_line(result, f, money_sign) for f in ordered_fixes(result)[:top]]
