"""What a user can do to the tables without breaking a page (bugs found in the 07.11.2026 browser test)."""

import copy

from orlab.registry import PROBLEMS, problem


def test_cleared_cell_gives_a_message_not_a_crash():
    """Clearing the first number in every table of every page must give status 'error' with the cell named,
    never a traceback. Example: product mix, products row 1 'margin' cleared -> "products row 1, column 'margin'"."""
    for p in (p for p in PROBLEMS if p.live):
        for table, rows in p.example.items():
            if not (isinstance(rows, list) and rows and isinstance(rows[0], dict)):
                continue
            col = next((c for c, v in rows[0].items() if isinstance(v, (int, float))), None)
            if col is None:
                continue
            data = copy.deepcopy(p.example)
            data[table][0][col] = None
            data["ms"] = 100                       # routing: short search is enough here
            sol = p.solve(data)                    # must not raise
            p.explain(data)                        # must not raise
            if not sol.ok:
                assert sol.headline and sol.bullets


def test_cleared_cell_is_named():
    data = copy.deepcopy(problem("product_mix").example)
    data["products"][0]["margin"] = None
    sol = problem("product_mix").solve(data)
    assert sol.status == "error" and "products row 1, column 'margin'" in sol.bullets[0]


def test_shift_day_needs_more_people_than_the_team():
    """Example team = 7 operators. Friday late + 3 extra = 5, early = 3 -> 8 people on Friday > 7,
    and one shift a day each, so no roster exists. The message must name Friday, not the rest rule."""
    p = problem("shift_scheduling")
    data = copy.deepcopy(p.example)
    data["demand"][1]["Fri"] += 3
    sol = p.solve(data)
    assert not sol.ok and sol.headline.startswith("Fri needs 8 operators")


def test_assignment_objective_is_minutes_not_euros():
    """The assignment objective is rework minutes: 52 must read '52 min rework', not '€52'."""
    assert problem("assignment").fmt(52) == "52 min rework"


def test_pages_folder_is_not_called_pages():
    """A folder named app/pages makes Streamlit show its raw file list in the sidebar before
    st.navigation runs; the pages live in app/views and every registry page has its file."""
    from pathlib import Path
    app = Path(__file__).parents[1] / "app"
    assert not (app / "pages").exists()
    for p in (p for p in PROBLEMS if p.live):
        assert (app / "views" / f"{p.key}.py").exists()


def test_product_mix_bottleneck_sentence_grammar():
    """Example: Paint shop and SUV off-road calibration are both full -> '... SUV off-road calibration also runs full.'"""
    sol = problem("product_mix").solve(problem("product_mix").example)
    assert any("SUV off-road calibration also runs full." in b for b in sol.bullets)


def test_knapsack_left_out_list_uses_semicolons():
    """'Predictive maintenance, body shop' has a comma in its name, so the left-out list is joined with '; '."""
    sol = problem("knapsack").solve(problem("knapsack").example)
    assert any("Predictive maintenance, body shop; " in b for b in sol.bullets)
