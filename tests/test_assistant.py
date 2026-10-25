"""The optional assistant, without the API: a fake client plays Claude's two turns."""

from types import SimpleNamespace as NS

import pytest

from plantlab import loop
from plantlab.ai import assistant
from plantlab.plant import load_plant


def test_to_scenario_checks_settings_and_ranges():
    plant = load_plant()
    s = assistant.to_scenario(plant, {"name": "2nd cell", "question": "q", "note": "",
                                      "plan_with_rework": False,
                                      "changes": [{"setting": "stations.offroad.units", "value": 2.0}]})
    assert s["changes"] == {"stations.offroad.units": 2}          # whole number, loop format
    assert isinstance(s["changes"]["stations.offroad.units"], int)
    with pytest.raises(ValueError):                               # outside 1-4 units
        assistant.to_scenario(plant, {"changes": [{"setting": "stations.paint.units", "value": 40}]})
    with pytest.raises(ValueError):                               # not a setting
        assistant.to_scenario(plant, {"changes": [{"setting": "plant.name", "value": 1}]})
    # every allowed setting must exist in plant.yaml
    for path in assistant.settings(plant):
        loop.apply_changes(plant, {path: 1})


class FakeClient:
    """First reply: a tool call. Second reply: the explanation."""

    def __init__(self, tool_input):
        self.requests = []
        replies = [NS(stop_reason="tool_use", content=[
                       NS(type="tool_use", id="t1", name="run_what_if", input=tool_input)]),
                   NS(stop_reason="end_turn", content=[NS(type="text", text="More SUVs.")])]
        self.beta = NS(messages=NS(create=lambda **kw: self.requests.append(kw) or replies.pop(0)))


def test_ask_runs_the_scenario_and_returns_the_answer():
    plant = load_plant()
    base = loop.run_scenario(plant, loop.SCENARIOS[0], reps=3)
    ran = []

    def run(plant, scenario):
        ran.append(scenario)
        return loop.run_scenario(plant, scenario, reps=3)

    client = FakeClient({"name": "2nd cell", "question": "q", "note": "", "plan_with_rework": False,
                         "changes": [{"setting": "stations.offroad.units", "value": 2}]})
    answer = assistant.ask("What if we add an off-road cell?", plant, base, run=run, client=client)
    assert answer.text == "More SUVs."
    assert ran == [answer.scenario] and answer.scenario["changes"] == {"stations.offroad.units": 2}
    tool_result = client.requests[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "t1" and not tool_result["is_error"]
    assert "vs base (paired CI)" in tool_result["content"]
    assert client.requests[0]["model"] == assistant.MODEL
