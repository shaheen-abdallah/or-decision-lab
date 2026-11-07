"""What every problem page works with: a `Problem` card and a `Solution`.

The shape follows the OR-Tools guides: every `solve()` declares the solver, creates the
variables, adds the constraints, sets the objective, solves, and reads the solution back.
"""

import importlib
import inspect
import re
import time
from dataclasses import dataclass, field


@dataclass
class Solution:
    status: str                       # "optimal", "feasible", "infeasible", "unbounded", "error"
    objective: float | None
    headline: str                     # the answer in one sentence
    bullets: list = field(default_factory=list)      # two or three plain-words findings
    tables: dict = field(default_factory=dict)       # name -> list of row dicts
    solver: str = ""
    seconds: float = 0.0
    extra: dict = field(default_factory=dict)        # anything a page needs for its chart

    ok = property(lambda self: self.status in ("optimal", "feasible"))


@dataclass(frozen=True)
class Problem:
    key: str
    question: str          # the business question on the card and the page
    family: str            # OR-Tools guide section: Linear optimization, Network flows, ...
    model: str             # OR name: Product mix (LP)
    solver: str            # GLOP, SimpleMinCostFlow, SCIP, CP-SAT, Routing solver
    why_solver: str        # one sentence: why this solver fits
    icon: str = ":material/help:"
    live: bool = False
    sense: str = "min"     # "min" or "max": tells the what-if panel whether a lower objective is good
    unit: str = "€"        # how the objective is shown: "€", or a word like "stations"

    def fmt(self, value):
        """The objective as the page shows it."""
        if self.unit == "€":
            return eur(value)
        return f"{num(value, 0 if float(value).is_integer() else 1)} {self.unit}"

    def delta_text(self, delta):
        """The what-if change for st.metric. Streamlit reads the arrow and colour from a leading ASCII '-',
        so a typographic minus would show a better (lower) plan as a red up-arrow."""
        return f"{'+' if delta >= 0 else '-'}{self.fmt(abs(delta))}"

    @property
    def module(self):
        return importlib.import_module(f"orlab.problems.{self.key}")

    @property
    def example(self):
        return self.module.EXAMPLE

    def solve(self, data):
        t = time.perf_counter()
        try:
            sol = self.module.solve(data)
        except (TypeError, ValueError, KeyError):
            sol = Solution("error", None, "Some input is missing or not a number.",
                           [blank_cells(data, self.example) or "Check the tables, or press *Reset to the example*."])
        sol.seconds = time.perf_counter() - t
        sol.solver = sol.solver or self.solver
        return sol

    def explain(self, data):
        try:
            return self.module.explain(data)
        except (TypeError, ValueError, KeyError):
            return {"decide": "–", "goal": "–", "limits": ["Fill in the empty cells to see the model in words."]}

    @property
    def math(self):
        """The module docstring; display formulas ($$) get the blank lines Markdown needs."""
        doc = inspect.getdoc(self.module)
        return re.sub(r"\n(\$\$[^\n]*\$\$)\n", r"\n\n\1\n\n", doc)

    @property
    def code(self):
        return inspect.getsource(self.module)


def blank_cells(data, example=None):
    """Plain-words list of the empty cells a user left in the tables (a cleared cell arrives as None).
    Cells that are empty on purpose in the example (a route not approved) are not listed."""
    def allowed(table, i, col):
        rows = (example or {}).get(table)
        return isinstance(rows, list) and i < len(rows) and col in rows[i] and rows[i][col] is None
    found = [f"{table} row {i + 1}, column '{col}'"
             for table, rows in data.items() if isinstance(rows, list)
             for i, row in enumerate(rows) if isinstance(row, dict)
             for col, v in row.items() if v is None and not allowed(table, i, col)]
    if not found:
        return ""
    more = f" and {len(found) - 3} more" if len(found) > 3 else ""
    return "Empty cell: " + "; ".join(found[:3]) + more + ". Fill it in or reset to the example."


def eur(x, decimals=0):
    return f"€{x:,.{decimals}f}"


def num(x, decimals=0):
    return f"{x:,.{decimals}f}"
