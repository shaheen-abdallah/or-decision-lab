# Handoff: OR Decision Lab redesign (04.11.2026)

## Done (branch `claude/or-tools-redesign-84eb4b`, worktree `.claude/worktrees/or-tools-redesign-84eb4b`, nothing pushed)
- Audit + design: `redesign/00-audit.md`, `redesign/01-design.md`. His choices (04.11): car plant as the single story, OR-Tools only, all 8 problems + simulation.
- `src/orlab/`: `core.py` (Problem, Solution), `registry.py` (9 cards, 3 live), `problems/product_mix.py` (GLOP, duals), `min_cost_flow.py` (SimpleMinCostFlow), `assignment.py` (LinearSumAssignment). Each module: EXAMPLE, solve(data), explain(data), maths in the docstring.
- `app/guide.py` renders every page: question → data (editable tables) → answer (headline, bullets, chart, tables) → what if (sliders) → how it's modelled (words / math / code / solver). `app/pages/<key>.py` are ~40 lines each.
- Tests: `tests/test_orlab_*.py`, 12 green. The old 51 `plantlab` tests still run; 2 fail for environment reasons only (no `anthropic` extra; `pytest.approx` on a list of tuples in `test_engine_mix.py`).

## Next (phase 2b, then 3, 4)
1. Pages 4–5: `line_balancing` (SCIP MIP, data from `src/orlab/plant.yaml` line_balancing; v1 code in `src/plantlab/optimize/line_balancing.py` shows the formulation), `knapsack` (KnapsackSolver; invent 8 improvement projects with cost and €/week gain). Flip `live=True` in the registry, add `app/pages/<key>.py`, one test each.
2. Phase 3: `shift_scheduling` and `job_shop` (CP-SAT; job shop gets an Altair Gantt), `vehicle_routing` (routing solver, depot + 8 dealers on a grid), `simulation` page (move `src/plantlab/simulate/` + `plant.py` into `orlab`, then delete `src/plantlab`, its tests, docplex/cplex from pyproject; show him the deletion list first).
3. README rewrite (OR-Tools story, screenshot), `docs/demo.gif` redo, INDEX.md cleanup (rows for `plantlab` go when it goes).
4. Phase 4: his OK to push + Streamlit Cloud deploy (`requirements.txt` is ready: `-e .`, streamlit, pandas, altair); CV line "live online".

## How to run
    .venv/bin/pytest -q tests/test_orlab_*.py
    .venv/bin/streamlit run app/Home.py          # or the launch config `car-plant-lab` (port 8511)
The worktree has its own `.venv` (uv, Python 3.12, `-e .[app,dev]` + ortools). Streamlit does not hot-reload `app/guide.py` or `src/`: restart the server after editing them.

## Open questions for him
- Merge this branch into `main` now, or after phase 3? (Nothing is pushed either way.)
- OK to delete `src/plantlab` once the simulation has moved (phase 3)?
