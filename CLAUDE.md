# CLAUDE.md: how to work in this repo

Read this first, then `INDEX.md` and the newest file in `sessions/`.

## Who does what
- **Claude** builds the project (Abdallah's call, 25.10.2026). v1 (car plant: OR core, simulation, app) is done. **v2 (26.10.2026): OR models for decision makers** in four phases: 1 engine + home + transport (done) · 2 product mix, shortest route, max flow, public link · 3 more models + AI · 4 CO₂, robustness, block builder. The plan lives outside the repo (Personal tools hub, `09 Car plant decision lab/Plan v2 (26.10.2026).md`).
- **Abdallah** reviews and must be able to explain every model in an interview: keep the code in his course style (docplex `Model`, `*_var_dict` / `*_var_matrix`, `m.sum`, `add_constraints`), the math in each module's docstring, and summaries in plain English.

## Conventions
- v2 model types live in `src/plantlab/models/<type>.py` and plug into `src/plantlab/engine/` through the `Builder` (decisions, objective, limits with their words); cards in `models/registry.py`. Inputs are plain JSON-able dicts so scenarios save as files.
- v1 (car plant): one module per model in `src/plantlab/optimize/`: `solve(...)` takes plain dicts (testable on tiny cases), `solve_plant(plant, plan)` reads `plant.yaml`. Each returns a result dataclass with `.summary` and `.report()`.
- Every model gets a test on a case small enough to solve by hand; write the hand calculation in the test's docstring.
- Keep every model under the CPLEX Community Edition limit (1,000 variables / 1,000 constraints).
- `decisions/log.md` is **append-only**: `- [YYYY-MM-DD] DECISION … | REASONING … | CONTEXT …`
- `sessions/YYYY-MM-DD.md` per work session: **Done**, **Decisions**, **Next**.

## Commits and GitHub
Commit at the end of a session in plain English with the status in brackets, e.g. `phase 1: OR core (tested)`. Push to GitHub (public) only after Abdallah's OK (planned for phase 3).

## Confidentiality
This repo will be public. All data is invented. Never copy his course material (simulation case files and data, textbook examples, past papers) or name former employers' clients, projects or colleagues.

## Environment
`.venv` in the repo (gitignored), made with `uv venv --python 3.12` (system Python 3.9 is too old for the CPLEX wheels). Run `.venv/bin/python -m plantlab plan|fit|simulate|loop`, `.venv/bin/streamlit run app/Home.py` and `.venv/bin/pytest`. The assistant (`ai/`) is optional: the app and the tests never need an API key.
