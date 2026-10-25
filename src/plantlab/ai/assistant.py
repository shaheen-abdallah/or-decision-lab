"""Optional AI assistant: a what-if in plain words -> scenario -> simulation -> explanation.

Runs only when ANTHROPIC_API_KEY is set (pip install -e ".[ai]"); the rest of the lab never
needs it. The model does not do the maths. It only translates:

    1. Translate   Claude (Sonnet) reads the question and calls the tool `run_what_if` with a
                   scenario in the same format as loop.SCENARIOS. The tool schema is strict
                   and lists every setting it may change, so it cannot invent a field.
    2. Run         Python checks the values, then runs the scenario exactly like
                   `python -m plantlab loop`: CPLEX plans the changed plant, SimPy builds the
                   plan 20 times, paired CI against the base plan.
    3. Explain     the tables go back to Claude as the tool result; it answers in plain
                   words and may only use numbers from those tables.

A question that is not a what-if (e.g. "why is paint the bottleneck?") gets a short answer
from the plant facts in the system prompt, without running anything.
"""

import json
import os
from dataclasses import dataclass, field

from plantlab import loop

MODEL = "claude-sonnet-5-5"
MAX_TOOL_CALLS = 3

# Settings the assistant may change, as dotted paths into plant.yaml (see loop.apply_changes)
# and (low, high) limits so a typo cannot ask for 400 paint shops.
STATION_SETTINGS = {"units": (1, 4), "minutes.sedan": (0, 60), "minutes.suv": (0, 60)}
SIM_STATION_SETTINGS = {"buffer": (0, 30), "cv": (0, 1), "mttr": (0, 240)}
PRODUCT_SETTINGS = {"margin_eur": (0, 20000), "demand_min": (0, 1000), "demand_max": (0, 1500)}
OTHER_SETTINGS = {"plant.availability": (0.5, 1), "simulation.buffer_size": (0, 30),
                  "simulation.rework.rate": (0, 0.5)}
WHOLE_NUMBERS = ("units", "buffer", "buffer_size", "demand_min", "demand_max")


def available():
    """True when the assistant can run (key set and the anthropic package installed)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def settings(plant):
    """Every setting the assistant may change -> (low, high)."""
    allowed = dict(OTHER_SETTINGS)
    for st in plant["stations"]:
        allowed.update({f"stations.{st['id']}.{k}": v for k, v in STATION_SETTINGS.items()})
    for s in plant["simulation"]["stations"]:
        allowed.update({f"simulation.stations.{s}.{k}": v for k, v in SIM_STATION_SETTINGS.items()})
    for p in plant["products"]:
        allowed.update({f"products.{p}.{k}": v for k, v in PRODUCT_SETTINGS.items()})
    return allowed


def what_if_tool(plant):
    return {
        "name": "run_what_if",
        "description": (
            "Run one what-if scenario on the plant: CPLEX re-plans the weekly Sedan/SUV mix on "
            "the changed plant, then the SimPy simulation builds that plan (20 replications) and "
            "compares it with the base plan. Use it for any question about changing the plant. "
            "Use an empty `changes` list with plan_with_rework true to let the plan see the "
            "SUV rework loop."),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short scenario name, max 4 words"},
                "question": {"type": "string", "description": "The question in one sentence"},
                "changes": {
                    "type": "array",
                    "description": "Settings to change; absolute new values, not differences",
                    "items": {
                        "type": "object",
                        "properties": {
                            "setting": {"type": "string", "enum": sorted(settings(plant))},
                            "value": {"type": "number"},
                        },
                        "required": ["setting", "value"],
                        "additionalProperties": False,
                    },
                },
                "plan_with_rework": {"type": "boolean",
                                     "description": "Let the LP plan with the rework loop"},
                "note": {"type": "string",
                         "description": "What the model leaves out (e.g. investment cost), or empty"},
            },
            "required": ["name", "question", "changes", "plan_with_rework", "note"],
            "additionalProperties": False,
        },
    }


def system_prompt(plant):
    stations = "\n".join(
        f"- {st['id']}: {st['name']}, {st['units']} unit(s), minutes per car "
        + ", ".join(f"{p} {m:g}" for p, m in st["minutes"].items())
        + f"; buffer in front {plant['simulation']['stations'][st['id']].get('buffer', plant['simulation']['buffer_size'])}"
        for st in plant["stations"])
    products = "\n".join(f"- {p}: {v['name']}, margin €{v['margin_eur']:,} per car, demand "
                         f"{v['demand_min']}-{v['demand_max']} cars a week"
                         for p, v in plant["products"].items())
    rw = plant["simulation"]["rework"]
    return f"""You are the assistant of the Car plant decision lab, a portfolio project that plans a \
fictional car assembly plant ({plant['plant']['name']}) with IBM CPLEX and stress-tests the plan \
with a SimPy simulation. Users are recruiters and engineers trying the app.

The plant: two shifts (07:00-23:00), {plant['plant']['days_per_week']} days, stations run \
{plant['plant']['availability']:.0%} of the time (breakdowns). Stations in flow order:
{stations}
Products:
{products}
Rework: {rw['rate']:.0%} of SUVs fail {rw['found_at']} and go to the rework bay \
({rw['bay']['minutes']} min), then are tested again. The base LP plan does not see this loop.

When the user asks what happens if something in the plant changes, call run_what_if once with \
the matching settings (absolute values: "one more off-road cell" means stations.offroad.units = 2). \
If the question cannot be expressed with the available settings, say so in one sentence instead \
of guessing. After the tool result, answer in at most 120 words of plain English for a plant \
manager: the result first (cars and margin per week vs the base plan, with the ± range), then why, \
then one caveat. Use only numbers that appear in the tool result. For questions that are not \
what-ifs, answer briefly from the facts above."""


def to_scenario(plant, tool_input):
    """Tool input -> a loop scenario dict; raises ValueError with a message Claude can fix."""
    allowed = settings(plant)
    changes = {}
    for c in tool_input.get("changes", []):
        path, value = c["setting"], c["value"]
        if path not in allowed:
            raise ValueError(f"unknown setting {path}")
        low, high = allowed[path]
        if not low <= value <= high:
            raise ValueError(f"{path} = {value} is outside the allowed range {low}-{high}")
        if path.endswith(WHOLE_NUMBERS):
            value = int(round(value))
        changes[path] = value
    return {"name": tool_input.get("name") or "What-if",
            "question": tool_input.get("question", ""),
            "changes": changes,
            "plan_with_rework": bool(tool_input.get("plan_with_rework")),
            "note": tool_input.get("note", "")}


def result_text(scenario_result, base):
    """What the tool sends back to Claude: the gap table + the comparison with the base plan."""
    r = scenario_result
    if r.sim is None:
        return f"The LP found no feasible plan: {r.mix.summary}"
    changes = r.scenario["changes"]
    return "\n\n".join([
        f"Scenario: {r.name}. Changes: {json.dumps(changes) if changes else 'none'}",
        "Paper (LP) vs reality (simulation):\n" + r.gap_table(),
        "Compared with the base plan (paired 95% CI):\n" + loop.LoopResult([base, r]).comparison(),
        "Plain-English lines from the lab:\n" + loop.explain(r),
    ])


@dataclass
class Answer:
    text: str
    scenario: dict | None = None      # the scenario Claude wrote (None if nothing ran)
    result: object = None             # loop.ScenarioResult
    calls: list = field(default_factory=list)   # raw tool inputs, for the "show JSON" view


def ask(question, plant, base, run=None, client=None):
    """Answer one question. `base` is the base plan's ScenarioResult (cached by the app);
    `run(plant, scenario)` runs a scenario (default: loop.run_scenario)."""
    import anthropic

    client = client or anthropic.Anthropic()
    run = run or loop.run_scenario
    tools = [what_if_tool(plant)]
    messages = [{"role": "user", "content": question}]
    answer = Answer("")

    for _ in range(MAX_TOOL_CALLS + 1):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=system_prompt(plant),
            tools=tools,
            messages=messages,
            output_config={"effort": "low"},          # translation + a short answer
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",                      # a declined request is retried server-side
        )
        if response.stop_reason == "refusal":
            answer.text = "The model declined this question. Try asking about the plant."
            return answer
        if response.stop_reason != "tool_use":
            answer.text = "\n".join(b.text for b in response.content if b.type == "text").strip()
            return answer

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            answer.calls.append(block.input)
            try:
                scenario = to_scenario(plant, block.input)
                answer.scenario, answer.result = scenario, run(plant, scenario)
                content, error = result_text(answer.result, base), False
            except (ValueError, KeyError) as e:
                content, error = f"Error: {e}. Fix the setting and call the tool again.", True
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": content, "is_error": error})
        messages.append({"role": "user", "content": results})

    answer.text = "Stopped after too many tool calls; try a simpler question."
    return answer
