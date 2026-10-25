# Index

| Path | What's in it |
|---|---|
| `README.md` | The project for readers: question, what it does, how to run |
| `CLAUDE.md` | Rules for working in this repo |
| `pyproject.toml` | Package and dependencies (docplex, cplex, pyyaml, simpy, scipy; pytest for dev) |
| `src/plantlab/plant.yaml` | The fictional plant: products, stations, line tasks, workforce, suppliers, simulation settings |
| `src/plantlab/plant.py` | Loads `plant.yaml`, shared numbers (minutes per week, shifts) |
| `src/plantlab/__main__.py` | CLI: `python -m plantlab plan / fit / simulate / loop` |
| `src/plantlab/optimize/` | The four docplex models + `report.py` (text tables) + CLI (`python -m plantlab.optimize`) |
| `src/plantlab/simulate/` | `fitting.py` (distributions + KS test), `model.py` (SimPy line), `experiment.py` (replications, CIs, bottleneck) |
| `src/plantlab/loop.py` | OR plan → simulation → paper-vs-reality gap table; the what-if scenarios |
| `tests/` | pytest: hand-solved small cases per model, M/M/1 check, flow conservation, reproducibility, loop, CLI |
| `decisions/log.md` | Every decision with its reasoning (append-only) |
| `sessions/` | One summary per work session: done, decisions, next |

Coming in phase 3: `app/` (Streamlit), `src/plantlab/ai/` (optional assistant), `docs/` (memo, demo GIF).
