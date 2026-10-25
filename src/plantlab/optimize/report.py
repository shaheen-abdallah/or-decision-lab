"""Small text helpers so every model prints the same way."""


def eur(value):
    return f"€{value:,.0f}"


def pct(value):
    return f"{value:.0%}"


def table(headers, rows):
    """Plain-text table: first column left-aligned, the rest right-aligned."""
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(str(h)), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def line(cells):
        first = cells[0].ljust(widths[0])
        rest = (c.rjust(w) for c, w in zip(cells[1:], widths[1:]))
        return "  ".join([first, *rest])

    out = [line([str(h) for h in headers]), "  ".join("-" * w for w in widths)]
    out += [line(r) for r in rows]
    return "\n".join(out)
