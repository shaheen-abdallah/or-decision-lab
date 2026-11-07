"""Describe your problem: the AI's answer is faked, so these tests need no key and no network.

Each fake reply is what the model would send back: one tool call whose arguments are JSON.
We check that the right page is chosen, that good tables pass the page's format and that
bad answers become a friendly message instead of a crash.
"""

import json

from orlab import describe
from orlab.registry import PROBLEMS, problem


def reply(tool, args):
    """The shape of an OpenAI-compatible chat answer with one tool call."""
    raw = args if isinstance(args, str) else json.dumps(args)
    return {"choices": [{"message": {"tool_calls": [{"function": {"name": tool, "arguments": raw}}]}}]}


def fake(tool, args):
    """A stand-in for the HTTP call; it also checks the request we would have sent."""
    def post(body, key):
        assert key == "test-key" and body["model"] == describe.MODEL
        assert len(body["tools"]) == len(PROBLEMS) + 1
        return reply(tool, args)
    return post


WAREHOUSES = ("Two warehouses, Hamburg ships up to 300 boxes a week and Munich 250. Shops in Berlin "
              "and Cologne need 200 and 250. Freight per box: Hamburg-Berlin 3, Hamburg-Cologne 5, "
              "Munich-Berlin 6, Munich-Cologne 4. Cheapest plan?")
SHIFTS = "I run a small café with four staff; I need 2 people early and 1 late, Monday to Wednesday."
JOBS = "Three technicians, three machines to repair; each person takes a different time on each machine."


def test_shipping_from_warehouses_goes_to_min_cost_flow():
    """Hand check: supply 550 >= demand 450, so the tables are consistent; the plant columns
    (Berlin, Cologne) match the plant rows, so the format check passes."""
    data = {"part": "box",
            "suppliers": [{"supplier": "Hamburg", "capacity": 300, "Berlin": 3, "Cologne": 5},
                          {"supplier": "Munich", "capacity": 250, "Berlin": 6, "Cologne": 4}],
            "plants": [{"plant": "Berlin", "demand": 200}, {"plant": "Cologne", "demand": 250}]}
    s = describe.ask(WAREHOUSES, "test-key", post=fake("fill_min_cost_flow",
                                                       {"why": "Ship from sources to sinks.", "sure": True, "data": data}))
    assert (s.status, s.key, s.data) == ("fit", "min_cost_flow", data)
    # After Confirm the page solves it: Hamburg→Berlin 200 × €3, Munich→Cologne 250 × €4 = €1,600.
    assert problem("min_cost_flow").solve(s.data).objective == 1600


def test_staffing_shifts_goes_to_shift_scheduling():
    """Hand check: 3 days x (2 + 1) = 9 operator-shifts; four people with at most 3 shifts give 12 >= 9."""
    ops = [{"operator": n, "min shifts": 2, "max shifts": 3, "max late": 2, "days off wanted": ""}
           for n in ["Ana", "Ben", "Cem", "Dana"]]
    data = {"operators": ops, "demand": [{"shift": "early", "Mon": 2, "Tue": 2, "Wed": 2},
                                         {"shift": "late", "Mon": 1, "Tue": 1, "Wed": 1}]}
    s = describe.ask(SHIFTS, "test-key", post=fake("fill_shift_scheduling", {"why": "Shifts.", "sure": True, "data": data}))
    assert (s.status, s.key) == ("fit", "shift_scheduling") and s.data == data
    assert "9 operator-shifts" in problem("shift_scheduling").explain(s.data)["limits"][0]


def test_assigning_people_to_jobs_goes_to_assignment_and_keeps_unsure():
    """Hand check: 3 people, 3 machines, one missing pairing (None) is allowed."""
    data = {"operators": [{"operator": "Ali", "Lathe": 30, "Press": 50, "Mill": None},
                          {"operator": "Bea", "Lathe": 40, "Press": 20, "Mill": 35},
                          {"operator": "Cai", "Lathe": 25, "Press": 45, "Mill": 30}]}
    s = describe.ask(JOBS, "test-key", post=fake("fill_assignment", {"why": "One job each.", "sure": False, "data": data}))
    assert (s.status, s.key, s.data) == ("unsure", "assignment", data)
    # Best: Ali-Lathe 30 + Bea-Press 20 + Cai-Mill 30 = 80.
    assert problem("assignment").solve(s.data).objective == 80


def test_tables_that_break_the_format_fall_back_to_the_example():
    """Station columns must be the product names: 'Car' is not a product, so the check fails."""
    data = {"products": [{"product": "Bike", "margin": 50, "min": 0, "max": 100}],
            "stations": [{"station": "Welding", "hours": 40, "Car": 5}]}
    s = describe.read_reply(reply("fill_product_mix", {"why": "Mix.", "sure": True, "data": data}))
    assert s.key == "product_mix" and s.data is None and s.note and s.problems
    assert describe.check("product_mix", {"products": "x"})            # wrong shape, no crash


def test_every_page_example_passes_its_own_format():
    for p in PROBLEMS:
        assert describe.check(p.key, p.example) == [], p.key
        assert describe.schema(p)["required"] == list(describe.FORMAT[p.key])


def test_no_fit_names_the_closest_page():
    s = describe.read_reply(reply("no_fit", {"why": "This is a forecasting question.", "closest": "simulation"}))
    assert (s.status, s.key) == ("none", "simulation")


def test_bad_answers_become_a_friendly_message():
    for bad in [reply("fill_knapsack", "{not json"), reply("fill_nonsense", {}), {"choices": []}, None,
                {"choices": [{"message": {"content": "I think it is a knapsack."}}]}]:
        s = describe.read_reply(bad)
        assert s.status == "error" and "could not be read" in s.note

    def offline(body, key):
        raise OSError("no network")
    assert describe.ask(WAREHOUSES, "k", post=offline).status == "error"
    assert describe.ask("hi", "k", post=offline).note.startswith("Describe")


def test_no_key_means_the_feature_stays_hidden(monkeypatch):
    monkeypatch.delenv(describe.KEY_NAME, raising=False)
    assert describe.api_key() is None and describe.api_key({}) is None

    class NoSecretsFile:
        def get(self, name):
            raise FileNotFoundError
    assert describe.api_key(NoSecretsFile()) is None
    assert describe.api_key({describe.KEY_NAME: "from-secrets"}) == "from-secrets"
    monkeypatch.setenv(describe.KEY_NAME, "from-env")
    assert describe.api_key() == "from-env"


def test_the_app_without_key_and_with_a_confirmed_suggestion(monkeypatch):
    """The real app, headless: no key -> the card only explains; a (faked) suggestion -> Confirm
    opens the assignment page with the user's tables and only then solves (30 + 20 + 30 = 80)."""
    import os
    from streamlit.testing.v1 import AppTest
    home = os.path.join(os.path.dirname(__file__), "..", "app", "Home.py")

    monkeypatch.delenv(describe.KEY_NAME, raising=False)
    at = AppTest.from_file(home).run(timeout=60)
    assert not at.exception and not at.text_area
    assert any("API key" in c.value for c in at.caption)

    monkeypatch.setenv(describe.KEY_NAME, "test-key")
    data = {"operators": [{"operator": "Ali", "Lathe": 30, "Press": 50, "Mill": None},
                          {"operator": "Bea", "Lathe": 40, "Press": 20, "Mill": 35},
                          {"operator": "Cai", "Lathe": 25, "Press": 45, "Mill": 30}]}
    monkeypatch.setattr(describe.ask, "__defaults__",
                        (fake("fill_assignment", {"why": "One job each.", "sure": True, "data": data}),))
    at = AppTest.from_file(home).run(timeout=60)
    at.text_area[0].input(JOBS).run()
    next(b for b in at.button if b.label == "Suggest a model").click().run(timeout=60)
    assert any("You decide" in m.value for m in at.markdown)
    next(b for b in at.button if b.label.startswith("Confirm")).click().run(timeout=60)
    assert not at.exception
    assert at.title[0].value == problem("assignment").question
    assert "Ali → Lathe" in at.success[0].value
