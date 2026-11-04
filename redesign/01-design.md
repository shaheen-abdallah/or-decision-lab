# Design: OR Decision Lab, redesigned after Google OR-Tools (04.11.2026)

## The idea in two lines
One fictional car plant, one decision per page, each page built like an OR-Tools guide: **the question → the data → how it's modelled (variables, constraints, objective, solver) → the solution → what if**. Google OR-Tools is the engine; a hiring manager reads the question and the answer, an interviewer opens "How it's modelled" and sees the code.

## What is borrowed from OR-Tools, and what is not
Borrowed:
- **The catalogue by solver family** (OR-Tools' guide sections): Linear optimization · Integer optimization · Assignment · Scheduling · Routing · Network flows. Every problem page says which solver solved it (GLOP, SCIP, CP-SAT, routing solver, graph solvers) and why that solver fits.
- **The seven-step guide structure** (declare the solver → variables → constraints → objective → solve → display) becomes the fixed layout of every page and the fixed shape of every `solve()` function, so all pages read the same.
- **Small, explicit examples**: each problem is sized so the data fits on one screen and the answer can be checked by hand (that is also the test).
- **Code is part of the page**: a "Code" tab shows the real Python that solved it, like OR-Tools' "complete program" at the end of every guide.
Not borrowed: OR-Tools' generic textbook cases (Stigler diet, N-queens). Every example is the same plant, so the pages tell one story. Not borrowed either: the no-code builder ambition of v2 (drag-and-drop, maps, Excel paste); it hid the models.

## Structure (pages = problems)
Home: "One car plant, eight decisions" with the catalogue grid grouped by solver family, each card = business question + model name + solver.

| # | Family (solver) | Page question | Model | Data from the plant |
|---|---|---|---|---|
| 1 | Linear optimization (GLOP) | How many Sedans and SUVs this week? | Product mix LP, duals as "what an extra hour is worth", 2-product graph | stations' hours, margins, demand caps |
| 2 | Network flows (SimpleMinCostFlow) | Which supplier ships seats to which plant? | Transportation / min-cost flow | 3 suppliers, 3 plants, €/seat-set |
| 3 | Assignment (LinearSumAssignment) | Which operator on which station? | Assignment | skill scores operator × station |
| 4 | Integer optimization (SCIP) | How few stations for the trim line? | Line balancing (SALBP-1) MIP | tasks, times, precedence, takt |
| 5 | Integer optimization (SCIP / CP-SAT) | Which improvement projects fit the budget? | Knapsack | projects, cost, €/week gain |
| 6 | Scheduling (CP-SAT) | Who works which shift? | Shift scheduling with coverage and rest rules | shifts, demand, operators |
| 7 | Scheduling (CP-SAT) | In what order through the paint shop? | Job shop (makespan) | 4 car batches × 3 stations |
| 8 | Routing (routing solver) | Which route delivers parts to the dealers? | VRP with capacity | depot + 8 dealers, km matrix |
| 9 | Simulation (SimPy, kept from v1) | Does the plan survive reality? | Discrete-event line simulation | plant.yaml |

The car plant page from v1 (Plan / Simulate / What-if / Ask) is retired; its models become pages 1, 2, 4, 6 and 9.

## One page, fixed layout
1. **Question** (one sentence) and the plant context (two sentences).
2. **Data**: editable tables (`st.data_editor`) with "Reset to the example".
3. **Answer**: headline metric + a table and one chart; two or three plain-words bullets ("Paint is the bottleneck: one more hour is worth €15,300").
4. **What if**: one to three sliders that re-solve instantly (OR-Tools solves these in milliseconds).
5. **How it's modelled** (tabs): *Words* (variables, constraints, objective as sentences) · *Math* (LaTeX from the docstring) · *Code* (the module's `solve()` source) · *Solver* (which one, why, time).

## Stack
Python 3.12, `ortools` 9.x (GLOP, SCIP, CP-SAT, routing, graph), Streamlit, pandas, Altair, SimPy, pytest. Dropped: docplex/cplex, streamlit-flow-component, pydeck, GeoNames, anthropic. Package renamed `plantlab` → `orlab` (`src/orlab/problems/<name>.py`: `EXAMPLE`, `solve(data) -> Solution`, math in the docstring; `src/orlab/plant.yaml` the story; `app/pages/<name>.py` thin, rendered by `app/guide.py`). The old code stays in git history; the v1 simulation moves over as is.

## Tests
One test per problem on the example data with the hand calculation in the docstring (optimum, one dual or one binding constraint, one what-if). Plus: every registered problem solves its example in < 2 s; every page imports. Target ~25 focused tests replacing 51.

## Phases
- **2a (this session):** `orlab` package, `Solution` + registry + page renderer, home, pages 1 (product mix) and 2 (min-cost flow), tests, browser walkthrough, commits.
- **2b:** pages 3, 4, 5 (assignment, line balancing, knapsack); README rewrite.
- **3:** pages 6, 7, 8 (CP-SAT shift scheduling, job shop with a Gantt chart, VRP with a route map drawn on a plan grid); simulation page moved; home polish.
- **4:** deploy on Streamlit Cloud (his sign-in), demo GIF, CV line "live online"; optional later: "describe your problem" AI, German switch.

## Recommendation and the choices only he can make
Recommendation: the table above, car plant as the single story, OR-Tools only, name stays "OR Decision Lab".
Asked him (one round): example domain (car plant vs something else), engine (OR-Tools only vs keep CPLEX alongside), scope (8 problems vs 5).
