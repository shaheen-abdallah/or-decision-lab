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

    @property
    def module(self):
        return importlib.import_module(f"orlab.problems.{self.key}")

    @property
    def example(self):
        return self.module.EXAMPLE

    def solve(self, data):
        t = time.perf_counter()
        sol = self.module.solve(data)
        sol.seconds = time.perf_counter() - t
        sol.solver = sol.solver or self.solver
        return sol

    def explain(self, data):
        return self.module.explain(data)

    @property
    def math(self):
        """The module docstring; display formulas ($$) get the blank lines Markdown needs."""
        doc = inspect.getdoc(self.module)
        return re.sub(r"\n(\$\$[^\n]*\$\$)\n", r"\n\n\1\n\n", doc)

    @property
    def code(self):
        return inspect.getsource(self.module)


def eur(x, decimals=0):
    return f"€{x:,.{decimals}f}"


def num(x, decimals=0):
    return f"{x:,.{decimals}f}"
