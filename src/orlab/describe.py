"""Describe your problem: an AI maps a manager's words onto one of the nine known models.

The rule (plan, 26.10.2026): never a free-text "any model". The language model may only *choose*
one of the nine pages and *fill its tables*; the app then shows that model in plain words
(the page's own `explain()`, not the AI's words), the user edits and confirms, and only then
does the solver run. A manager cannot spot a wrong model, so nothing is solved before Confirm.

How one description is handled:

1. `ask(text, key)` sends the words to OpenRouter (an OpenAI-compatible chat API) with one
   *tool* per page. Each tool's parameters are that page's input format as a JSON schema
   (`schema(problem)`), plus a `no_fit` tool for problems none of the nine covers.
2. `read_reply(reply)` takes the tool call the model made and turns it into a `Suggestion`.
3. `check(key, data)` validates the filled tables against the page's input format
   (the same columns, numbers where numbers belong, names that match across tables) and
   test-reads them with the page's `explain()`. If the tables fail, the page is still
   suggested but opens with its own example data, and the user is told so.

Without a key (`api_key()` finds none) the feature stays hidden; the app and the tests never
need a key or a network connection.
"""

import copy
import json
import numbers
import os
import urllib.request
from dataclasses import dataclass, field

from orlab.registry import PROBLEMS, problem

MODEL = "openai/gpt-4o-mini"      # cheap and good at tool calls; about €0.001 per description
URL = "https://openrouter.ai/api/v1/chat/completions"
KEY_NAME = "OPENROUTER_API_KEY"
MAX_ROWS = 30                     # keeps every page fast to solve and easy to read

# For each page: table -> (fixed columns with their type, type of the extra columns or None).
# Extra columns are the names the user chooses: stations, plants, days.
FORMAT = {
    "product_mix": {
        "products": ({"product": "text", "margin": "number", "min": "number", "max": "number"}, None),
        "stations": ({"station": "text", "hours": "number"}, "number"),       # one column per product
    },
    "min_cost_flow": {
        "part": "text",
        "suppliers": ({"supplier": "text", "capacity": "number"}, "number or empty"),  # one per plant
        "plants": ({"plant": "text", "demand": "number"}, None),
    },
    "assignment": {
        "operators": ({"operator": "text"}, "number or empty"),              # one column per station
    },
    "line_balancing": {
        "tasks": ({"id": "text", "task": "text", "seconds": "number", "after": "text"}, None),
        "line": ({"cycle time (s)": "number"}, None),
    },
    "knapsack": {
        "projects": ({"project": "text", "cost k€": "number", "gain €/week": "number"}, None),
        "budget": ({"budget k€": "number"}, None),
    },
    "shift_scheduling": {
        "operators": ({"operator": "text", "min shifts": "number", "max shifts": "number",
                       "max late": "number", "days off wanted": "text"}, None),
        "demand": ({"shift": "text"}, "number"),                             # one column per day
    },
    "job_shop": {
        "batches": ({"batch": "text"}, "number"),                            # one column per station
    },
    "vehicle_routing": {
        "stops": ({"stop": "text", "x": "number", "y": "number", "pallets": "number"}, None),
        "fleet": ({"vans": "number", "pallets per van": "number"}, None),
    },
    "simulation": {
        "plan": ({"product": "text", "cars per week": "number"}, None),
        "settings": ({"replications": "number", "buffer size": "number",
                      "off-road calibration units": "number"}, None),
    },
}

# What the model must know beyond the column names: the rules each page's solve() relies on.
RULES = {
    "product_mix": "Each station row has one minutes-per-unit column named exactly like each product.",
    "min_cost_flow": "Each supplier row has one cost column (€ per unit) named exactly like each plant; "
                     "empty = route not allowed. 'part' names the unit shipped.",
    "assignment": "Each operator row has one cost column per job/station (lower is better); "
                  "empty = not allowed. At least as many operators as jobs.",
    "line_balancing": "'after' lists the ids of tasks that must come first, comma-separated, or empty.",
    "knapsack": "One budget row. Costs in thousand €, gains in € per week.",
    "shift_scheduling": "Exactly two demand rows with shift 'early' and 'late'; day columns like Mon, Tue. "
                        "'days off wanted' uses the same day names, comma-separated.",
    "job_shop": "One column per machine/station in the order every batch visits them; minutes; 0 = skips it.",
    "vehicle_routing": "The first stop is the depot with 0 pallets; x and y are km on a map.",
    "simulation": "Only for this app's car plant: products 'sedan' and 'suv'. Rarely the right fit "
                  "for an outside problem.",
}

TYPES = {"text": {"type": "string"}, "number": {"type": "number"},
         "number or empty": {"type": ["number", "null"]}}


@dataclass
class Suggestion:
    status: str                    # "fit", "unsure", "none" (fits no page) or "error"
    key: str | None = None         # the page suggested (the closest one when status is "none")
    why: str = ""                  # the AI's reason, in plain words
    data: dict | None = None       # the page's tables, checked; None = use the page's example
    note: str = ""                 # what went wrong, for the user
    problems: list = field(default_factory=list)   # the checks the AI's tables failed


# ---------- the key ----------

def api_key(secrets=None):
    """The OpenRouter key from the environment or from Streamlit secrets; None if there is none."""
    key = os.environ.get(KEY_NAME)
    if not key and secrets is not None:
        try:
            key = secrets.get(KEY_NAME)
        except Exception:          # no secrets.toml: Streamlit raises instead of returning None
            key = None
    return key or None


# ---------- the schemas the model must answer in ----------

def schema(p):
    """One page's input format as a JSON schema, built from FORMAT."""
    props = {}
    for table, spec in FORMAT[p.key].items():
        if spec == "text":
            props[table] = {"type": "string"}
            continue
        fixed, extra = spec
        row = {"type": "object", "properties": {c: TYPES[t] for c, t in fixed.items()},
               "required": list(fixed), "additionalProperties": TYPES[extra] if extra else False}
        props[table] = {"type": "array", "items": row, "minItems": 1, "maxItems": MAX_ROWS}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def tools():
    """One tool per page (choose it and fill its tables) and one for 'none of these fits'."""
    out = []
    for p in PROBLEMS:
        out.append({"type": "function", "function": {
            "name": f"fill_{p.key}",
            "description": f"{p.question} ({p.model}). {RULES[p.key]}",
            "parameters": {"type": "object", "properties": {
                "why": {"type": "string", "description": "One or two plain sentences: why this model fits."},
                "sure": {"type": "boolean", "description": "False if another page could fit as well."},
                "data": schema(p)}, "required": ["why", "sure", "data"], "additionalProperties": False}}})
    out.append({"type": "function", "function": {
        "name": "no_fit",
        "description": "None of the models fits the problem.",
        "parameters": {"type": "object", "properties": {
            "why": {"type": "string", "description": "Plain words: what the problem needs that no page offers."},
            "closest": {"type": "string", "enum": [p.key for p in PROBLEMS]}},
            "required": ["why", "closest"], "additionalProperties": False}}})
    return out


SYSTEM = ("You help a manager who is not an OR expert. Read their problem and call exactly one tool: "
          "the model that fits, with its tables filled from their words. Use their names and numbers; "
          "where a number is missing, invent a plausible one and say so in 'why'. Keep tables small "
          "(at most 12 rows). If no model fits, call no_fit and name the closest. Plain English, no jargon.")


def request(text):
    """The chat request for one description."""
    return {"model": MODEL, "temperature": 0, "tool_choice": "required", "tools": tools(),
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text.strip()}]}


# ---------- asking ----------

def _post(body, key, timeout=60):
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "X-Title": "OR Decision Lab"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ask(text, key, post=_post):
    """Send a description, return a Suggestion. `post` is swapped for a fake in the tests."""
    if not text or len(text.strip()) < 15:
        return Suggestion("error", note="Describe the problem in a sentence or two first.")
    try:
        reply = post(request(text), key)
    except Exception as e:      # network, wrong key, no credit: never crash the page
        return Suggestion("error", note=f"The AI service did not answer ({type(e).__name__}). "
                                        "Try again, or pick a page yourself.")
    return read_reply(reply)


def read_reply(reply):
    """Turn the model's tool call into a Suggestion; any malformed answer becomes a friendly error."""
    bad = Suggestion("error", note="The AI's answer could not be read. Try again, or pick a page yourself.")
    try:
        call = reply["choices"][0]["message"]["tool_calls"][0]["function"]
        name, args = call["name"], json.loads(call["arguments"])
    except (KeyError, IndexError, TypeError, ValueError):
        return bad
    if not isinstance(args, dict):
        return bad
    keys = [p.key for p in PROBLEMS]
    if name == "no_fit":
        closest = args.get("closest") if args.get("closest") in keys else None
        return Suggestion("none", closest, str(args.get("why", "")))
    key = name.removeprefix("fill_")
    if key not in keys:
        return bad
    why, problems = str(args.get("why", "")), check(key, args.get("data"))
    status = "fit" if args.get("sure", True) is not False else "unsure"
    if problems:
        return Suggestion(status, key, why, None, problems=problems,
                          note="The AI could not fill this page's tables cleanly, so the page opens "
                               "with its own example data: edit it there.")
    return Suggestion(status, key, why, clean(key, args["data"]))


# ---------- checking the tables ----------

def _is(value, kind):
    if kind == "text":
        return isinstance(value, str)
    if kind == "number or empty" and value is None:
        return True
    return isinstance(value, numbers.Real) and not isinstance(value, bool) and value == value  # not NaN


def check(key, data):
    """Everything wrong with `data` as input for page `key`; an empty list means it is usable."""
    if not isinstance(data, dict):
        return ["no tables"]
    out = []
    for table, spec in FORMAT[key].items():
        if spec == "text":
            if not isinstance(data.get(table), str):
                out.append(f"'{table}' must be text")
            continue
        fixed, extra = spec
        rows = data.get(table)
        if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
            out.append(f"'{table}' must be a non-empty table")
            continue
        if len(rows) > MAX_ROWS:
            out.append(f"'{table}' has more than {MAX_ROWS} rows")
        cols = [c for c in rows[0] if c not in fixed]
        if cols and not extra:
            out.append(f"'{table}' has unknown columns: {', '.join(cols)}")
        if extra and not cols:
            out.append(f"'{table}' needs at least one {table[:-1]} column")
        for i, r in enumerate(rows, 1):
            for c, t in fixed.items():
                if not _is(r.get(c), t):
                    out.append(f"'{table}' row {i}: '{c}' must be {t}")
            if [c for c in r if c not in fixed] != cols:
                out.append(f"'{table}' row {i} has different columns from row 1")
            elif extra and not all(_is(r[c], extra) for c in cols):
                out.append(f"'{table}' row {i}: the extra columns must be {extra}")
    if out:
        return out[:6]
    out = _links(key, data)
    if not out:
        try:
            words = problem(key).explain(data)
            assert words["decide"] and words["goal"]
        except Exception as e:
            out.append(f"the page could not read the tables ({type(e).__name__})")
    return out


def _extra(data, table, key):
    """The user-named columns of a table (stations, plants, days)."""
    return [c for c in data[table][0] if c not in FORMAT[key][table][0]]


def _links(key, data):
    """The rules that tie one table to another (column names that must match row names)."""
    out = []
    if key == "product_mix":
        if set(_extra(data, "stations", key)) != {p["product"] for p in data["products"]}:
            out.append("the station columns must be the product names")
    elif key == "min_cost_flow":
        if set(_extra(data, "suppliers", key)) != {p["plant"] for p in data["plants"]}:
            out.append("the supplier cost columns must be the plant names")
    elif key == "assignment":
        if len(data["operators"]) < len(_extra(data, "operators", key)):
            out.append("there must be at least as many operators as jobs")
    elif key == "line_balancing":
        ids = {t["id"] for t in data["tasks"]}
        after = {a.strip() for t in data["tasks"] for a in t["after"].split(",") if a.strip()}
        if not after <= ids:
            out.append("'after' names a task id that does not exist")
    elif key == "shift_scheduling":
        if sorted(r["shift"] for r in data["demand"]) != ["early", "late"]:
            out.append("demand needs exactly one 'early' and one 'late' row")
    elif key == "vehicle_routing":
        if len(data["stops"]) < 2:
            out.append("routing needs a depot and at least one stop")
    elif key == "simulation":
        if not {r["product"] for r in data["plan"]} <= {"sedan", "suv"}:
            out.append("the simulation only knows the products 'sedan' and 'suv'")
    return out


def clean(key, data):
    """Only the tables the page knows, in its order (a copy, safe to edit)."""
    return {t: copy.deepcopy(data[t]) for t in FORMAT[key]}
