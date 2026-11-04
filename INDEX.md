# Index

| Path | What's in it |
|---|---|
| `README.md` | The project for readers: the nine decisions, how to run, where things are |
| `CLAUDE.md` | Rules for working in this repo |
| `pyproject.toml` | Package `orlab` and dependencies (ortools, pyyaml, simpy, scipy; extras: `app` streamlit + pandas + altair, `dev` pytest) |
| `requirements.txt` | What Streamlit Community Cloud installs (Python 3.12) |
| `.streamlit/config.toml` | Light theme, larger text (projector-ready) |
| `redesign/` | Audit and design of the OR-Tools-style redesign (04.11.2026); `_handoff.md` in the root has the status |
| `src/orlab/core.py` | `Problem` (card, module lookup, math + code from the module) and `Solution` (status, objective, headline, bullets, tables) |
| `src/orlab/registry.py` | The catalogue: nine problems grouped by OR-Tools family, with solver, why-this-solver, sense and unit |
| `src/orlab/problems/` | One file per decision: `product_mix` (GLOP), `min_cost_flow` (SimpleMinCostFlow), `assignment` (LinearSumAssignment), `line_balancing` (SCIP), `knapsack` (KnapsackSolver), `shift_scheduling` and `job_shop` (CP-SAT), `vehicle_routing` (routing solver), `simulation` (SimPy); each has EXAMPLE, solve, explain, maths in the docstring |
| `src/orlab/plant.yaml`, `src/orlab/plant.py` | The fictional plant (products, stations, line tasks, suppliers, simulation settings) and its loader |
| `src/orlab/simulate/` | The v1 simulation moved over: `fitting.py` (distributions + KS test), `model.py` (SimPy line), `experiment.py` (replications, CIs, bottleneck), `report.py` (text helpers) |
| `app/Home.py` | The app entry (`streamlit run app/Home.py`): navigation by family, sidebar |
| `app/guide.py` | One layout for every problem page: question → data → answer → what if → how it's modelled |
| `app/pages/` | `home.py` (catalogue) and one thin page per problem (chart + what-if sliders) |
| `docs/home.png`, `docs/page.png` | Screenshots for the README |
| `docs/memo.md` | v1 recommendations memo from the scenario results (historic) |
| `tests/` | pytest, 27 tests: hand-solved cases per problem (`test_orlab_<key>.py`), registry smoke test, simulation checks (M/M/1, flow conservation, fitting, reproducibility) |
| `decisions/log.md` | Every decision with its reasoning (append-only) |
| `sessions/` | One summary per work session: done, decisions, next |

The v1 package `src/plantlab` (docplex/CPLEX models, engine, AI assistant) and its 51 tests were deleted on 04.11.2026; git tag `pre-redesign-plantlab` marks the last commit that has them.
