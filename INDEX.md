# Index

| Path | What's in it |
|---|---|
| `README.md` | The project for readers: question, what it does, how to run |
| `CLAUDE.md` | Rules for working in this repo |
| `pyproject.toml` | Package and dependencies (docplex, cplex, pyyaml, simpy, scipy; extras: `app` streamlit + pydeck + streamlit-flow-component, `ai` anthropic, `dev` pytest) |
| `.streamlit/config.toml` | Light theme, larger text (projector-ready) |
| `src/plantlab/engine/` | v2 shared engine: `core.py` (Builder over docplex, solve → Result with duals/ranges/slack, elastic fixes, price of a rule, scoring a user's plan), `words.py` (results in plain words), `latex.py` (show the math), `scenarios.py` (compare, JSON), `paste.py` (Excel/CSV paste) |
| `src/plantlab/models/` | v2 model types: `transport.py` (min-cost flow: transportation + transshipment, templates, paste, manager summary), `registry.py` (home-page cards) |
| `src/plantlab/geo/` | Bundled city list `cities.csv` (GeoNames, CC BY 4.0; rebuilt by `make_cities.py`), search, road km |
| `src/plantlab/plant.yaml` | The fictional plant: products, stations, line tasks, workforce, suppliers, simulation settings |
| `src/plantlab/plant.py` | Loads `plant.yaml`, shared numbers (minutes per week, shifts) |
| `src/plantlab/__main__.py` | CLI: `python -m plantlab plan / fit / simulate / loop` |
| `src/plantlab/optimize/` | The four docplex models + `report.py` (text tables) + CLI (`python -m plantlab.optimize`) |
| `src/plantlab/simulate/` | `fitting.py` (distributions + KS test), `model.py` (SimPy line), `experiment.py` (replications, CIs, bottleneck) |
| `src/plantlab/loop.py` | OR plan → simulation → paper-vs-reality gap table; the what-if scenarios |
| `src/plantlab/ai/assistant.py` | Optional: plain-words what-if → scenario (Claude tool use, strict schema) → run → explanation; only with `ANTHROPIC_API_KEY` |
| `app/Home.py` | The app entry (`streamlit run app/Home.py`): navigation, sidebar |
| `app/pages/home.py` | Home: question-first cards, "describe your problem" placeholder, car plant links |
| `app/pages/transport.py` | Where should I ship from? Canvas + map, answer, math, tabs: build · live sliders · what limits you · rules · beat the solver · scenarios |
| `app/car_plant.py` | Worked example (v1 app): Plan (OR) · Simulate · What-if · Ask |
| `docs/memo.md` | One-page recommendations memo from the scenario results |
| `docs/demo.gif` | App walk-through for the README |
| `tests/` | pytest: hand-solved small cases per model, M/M/1 check, flow conservation, reproducibility, loop, CLI, assistant (fake client, no API); `test_engine_transport.py` for the v2 engine (optimum, duals, ranges, price of a rule, elastic fixes, gap decomposition, LaTeX, scenarios, paste, cities) |
| `decisions/log.md` | Every decision with its reasoning (append-only) |
| `sessions/` | One summary per work session: done, decisions, next |

