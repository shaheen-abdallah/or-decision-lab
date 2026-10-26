"""Paste from Excel or CSV: text -> rows of cells, numbers in English or German format."""

import re


def read_table(text):
    """Tab (Excel), semicolon (German CSV) or comma separated text -> list of rows of stripped cells."""
    lines = [l for l in text.strip("\n").splitlines() if l.strip()]
    if not lines:
        return []
    sep = "\t" if any("\t" in l for l in lines) else ";" if any(";" in l for l in lines) else ","
    return [[c.strip().strip('"') for c in l.split(sep)] for l in lines]


def german(rows):
    """True when the numbers use a decimal comma (12,5 or 1.234,5)."""
    cells = [c for r in rows for c in r]
    return any(re.fullmatch(r"-?[\d.]*\d,\d+", c) and not re.fullmatch(r"-?\d{1,3}(,\d{3})+", c) for c in cells)


def number(cell, decimal_comma=False):
    """'1,234.5' / '1.234,5' / '€ 12' / '' -> float or None."""
    s = re.sub(r"[€$%\s]", "", str(cell))
    if s in ("", "-", "—"):
        return None
    if decimal_comma:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None
