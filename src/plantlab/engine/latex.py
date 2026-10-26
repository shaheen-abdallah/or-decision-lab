"""'Show the math': the exact formulation, generated from a built model (Builder)."""

from plantlab.engine.core import num

SENSE = {"<=": r"\le", ">=": r"\ge", "==": "="}


def _coef(c, first):
    sign = "-" if c < 0 else ("" if first else "+")
    c = abs(c)
    value = "" if abs(c - 1) < 1e-9 else num(c).replace(",", "{,}") + r"\,"
    return f"{sign} {value}".strip() if first else f"{sign} {value}"


def expression(terms, symbols, per_line=4):
    """{key: coef} -> '39.2\\,x_{HAM,BER} + ...', broken into lines of `per_line` terms."""
    parts = [f"{_coef(c, i == 0)}{symbols[k]}" for i, (k, c) in enumerate(terms.items())]
    if not parts:
        return "0"
    lines = [" ".join(parts[i:i + per_line]) for i in range(0, len(parts), per_line)]
    return r" \\ & \quad ".join(lines)


def formulation(b, per_line=4):
    """-> objective line and one (words, LaTeX) pair per limit, all with the user's numbers."""
    symbols = {k: d.symbol for k, d in b.decisions.items()}
    obj = expression(b.objective_terms, symbols, per_line)
    objective = r"\begin{aligned} \%s\; & %s \end{aligned}" % ("min" if b.sense == "min" else "max", obj)
    limits = []
    for spec in b.limits.values():
        lhs = expression(spec.terms, symbols, per_line)
        rhs = num(spec.rhs).replace(",", "{,}")
        limits.append((spec.words, r"\begin{aligned} & %s \;%s\; %s \end{aligned}" % (lhs, SENSE[spec.sense], rhs)))
    domain = r"\text{every } %s \ge 0" % ("decision" if not symbols else "x")
    return objective, limits, domain
