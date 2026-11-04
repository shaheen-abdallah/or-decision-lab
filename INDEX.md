# Index

| Path | What's in it |
|---|---|
| `README.md` | The project for readers: question, what it does, how to run |
| `CLAUDE.md` | Rules for working in this repo |
| `pyproject.toml` | Package and dependencies (docplex, cplex, pyyaml, simpy, scipy; extras: `app` streamlit + pydeck + streamlit-flow-component, `ai` anthropic, `dev` pytest) |
| `.streamlit/config.toml` | Light theme, larger text (projector-ready) |
| `redesign/` | Audit and design of the OR-Tools-style redesign (04.11.2026); `_handoff.md` in the root has the status |
| `src/orlab/` | **The redesigned lab (v3):** `core.py` (Problem, Solution), `registry.py` (the catalogue by OR-Tools family), `problems/<key>.py` (EXAMPLE, solve, explain, maths in the docstring: product_mix GLOP, min_cost_flow, assignment) |
| `app/guide.py` | One layout for every problem page: question → data → answer → what if → how it's modelled |
| `src/plantlab/engine/` | v2 shared engine: `core.py` (Builder over docplex, solve → Result with duals/ranges/slack, elastic fixes, price of a rule, scoring a user's plan), `words.py` (results in plain words), `latex.py` (show the math), `scenarios.py` (compare, JSON), `paste.py` (Excel/CSV paste) |
| `src/plantlab/models/` | v2 model types: `transport.py` (min-cost flow: transportation + transshipment, templates, paste, manager summary), `network.py` (shortest route + Dijkstra steps, maximum flow + min cut), `mix.py` (product mix + graphical method: lines, corners, region), `registry.py` (home-page cards) |
| `src/plantlab/geo/` | Bundled city list `cities.csv` (GeoNames, CC BY 4.0; rebuilt by `make_cities.py`), search, road km |
| `src/plantlab/plant.yaml` | The fictional plant: products, stations, line tasks, workforce, suppliers, simulation settings |
| `src/plantlab/plant.py` | Loads `plant.yaml`, shared numbers (minutes per week, shifts) |
| `src/plantlab/__main__.py` | CLI: `python -m plantlab plan / fit / simulate / loop` |
| `src/plantlab/optimize/` | The four docplex models + `report.py` (text tables) + CLI (`python -m plantlab.optimize`) |
| `src/plantlab/simulate/` | `fitting.py` (distributions + KS test), `model.py` (SimPy line), `experiment.py` (replications, CIs, bottleneck) |
| `src/plantlab/loop.py` | OR plan → simulation → paper-vs-reality gap table; the what-if scenarios |
| `src/plantlab/ai/assistant.py` | Optional: plain-words what-if → scenario (Claude tool use, strict schema) → run → explanation; only with `ANTHROPIC_API_KEY` |
| `app/pages/` | `home.py` (catalogue) and one thin page per live problem (`product_mix.py`, `min_cost_flow.py`, `assignment.py`) |
| `app/Home.py` | The app entry (`streamlit run app/Home.py`): navigation by family, sidebar |
| `requirements.txt` | What Streamlit Community Cloud installs (Python 3.12) |
| `docs/memo.md` | One-page recommendations memo from the scenario results |
| `docs/demo.gif` | App walk-through for the README |
| `tests/` | pytest: hand-solved small cases per model, M/M/1 check, flow conservation, reproducibility, loop, CLI, assistant (fake client, no API); `test_engine_transport.py` for the v2 engine (optimum, duals, ranges, price of a rule, elastic fixes, gap decomposition, LaTeX, scenarios, paste, cities); `test_engine_mix.py`, `test_engine_network.py` for product mix, shortest route and max flow |
| `decisions/log.md` | Every decision with its reasoning (append-only) |
| `sessions/` | One summary per work session: done, decisions, next |

