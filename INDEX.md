# Index

| Path | What's in it |
|---|---|
| `README.md` | The project for readers: question, what it does, how to run |
| `CLAUDE.md` | Rules for working in this repo |
| `pyproject.toml` | Package and dependencies (docplex, cplex, pyyaml, simpy, scipy; extras: `app` streamlit, `ai` anthropic, `dev` pytest) |
| `src/plantlab/plant.yaml` | The fictional plant: products, stations, line tasks, workforce, suppliers, simulation settings |
| `src/plantlab/plant.py` | Loads `plant.yaml`, shared numbers (minutes per week, shifts) |
| `src/plantlab/__main__.py` | CLI: `python -m plantlab plan / fit / simulate / loop` |
| `src/plantlab/optimize/` | The four docplex models + `report.py` (text tables) + CLI (`python -m plantlab.optimize`) |
| `src/plantlab/simulate/` | `fitting.py` (distributions + KS test), `model.py` (SimPy line), `experiment.py` (replications, CIs, bottleneck) |
| `src/plantlab/loop.py` | OR plan → simulation → paper-vs-reality gap table; the what-if scenarios |
| `src/plantlab/ai/assistant.py` | Optional: plain-words what-if → scenario (Claude tool use, strict schema) → run → explanation; only with `ANTHROPIC_API_KEY` |
| `app/streamlit_app.py` | The app: Plan (OR) · Simulate · What-if · Ask (`streamlit run app/streamlit_app.py`) |
| `docs/memo.md` | One-page recommendations memo from the scenario results |
| `docs/demo.gif` | App walk-through for the README |
| `tests/` | pytest: hand-solved small cases per model, M/M/1 check, flow conservation, reproducibility, loop, CLI, assistant (fake client, no API) |
| `decisions/log.md` | Every decision with its reasoning (append-only) |
| `sessions/` | One summary per work session: done, decisions, next |

