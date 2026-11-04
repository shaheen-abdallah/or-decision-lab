# Handoff: OR Decision Lab redesign (04.11.2026, end of phase 3)

## Done (branch `claude/or-tools-redesign-p2-4e5e73`, worktree `.claude/worktrees/or-tools-redesign-p2-4e5e73`, nothing pushed)
- All nine pages live and browser-checked: product mix (GLOP), min-cost flow, assignment, line balancing (SCIP, two-stage: fewest stations then smoothest), knapsack (KnapsackSolver, shows the greedy gap), shift scheduling and job shop (CP-SAT, Gantt), vehicle routing (routing solver, map), simulation (SimPy, moved from v1 into `src/orlab/simulate/`).
- `Problem` got `sense` ("min"/"max") and `unit` so the what-if panel formats and colours each objective correctly.
- `src/plantlab` (42 files) and its 11 test files deleted; tag `pre-redesign-plantlab` (commit 338e0ec) holds the last version with them. docplex/cplex/anthropic gone from `pyproject.toml`. Old `docs/demo.gif` removed; `docs/home.png` and `docs/page.png` are the README screenshots (800 px, from the browser pane).
- 27 tests green (`.venv/bin/pytest`), each with the hand calculation in its docstring. README and INDEX rewritten.

## Next (phase 4, needs his OK)
1. Merge this branch into `main` (the branch `claude/or-tools-redesign-84eb4b` is the same work up to 566ecc3; this one continues it) and push to GitHub.
2. Streamlit Community Cloud deploy (his sign-in at share.streamlit.io; `requirements.txt` is ready), then the CV line "live online".
3. Better screenshots at full resolution or a short GIF (`docs/`), home polish if he wants.
4. Optional later: "describe your problem" AI, German switch.

## How to run
    .venv/bin/pytest -q
    .venv/bin/streamlit run app/Home.py          # or the launch config `car-plant-lab` (port 8512)
The worktree has its own `.venv` (uv, Python 3.12, `-e .[app,dev]` + ortools). Streamlit does not hot-reload `app/guide.py` or `src/`: restart the server after editing them.

## Gotchas
- The routing solver runs guided local search for 0.8 s per solve (`data["ms"]` overrides it; tests use 200 ms); its answer is "very good, not proven optimal" and the page says so.
- The simulation page runs 10 replications (about 1 s); the registry smoke test allows 3 s per example.
- Rows with `0` minutes in the job shop skip that station; empty costs in assignment / min-cost flow mean "not allowed".
