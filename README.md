# OR Decision Lab

**Status:** v2 in progress. The lab becomes **OR models for decision makers**: build a model without code, IBM CPLEX solves it and explains the answer in plain words. Phases 1–2 of 4 done (27.10.2026): the shared engine and four models: *Where should I ship from?* (transportation + transshipment), *What's the cheapest way from A to B?* (shortest route), *How much can my network carry at most?* (maximum flow) and *How much of each product should I make?* (product mix). The car plant below (v1, done 25.10.2026) stays as the worked example. Recommendations from v1: [docs/memo.md](docs/memo.md).

## v2: OR models for decision makers (no code)
A home page asks business questions ("Where should I ship from?", "How much of each product should I make?", ...); each opens a visual builder on an editable example. Live now: **transport** (min-cost flow LP), **shortest route** and **maximum flow** (LPs on the same network canvas and map), **product mix** (LP with the graphical method). Coming next: minimum spanning tree, production planning, assignment, staffing, and an AI that suggests the model from a description.

| Question | Model | What you see besides the optimum |
|---|---|---|
| Where should I ship from? | Transportation / transshipment (min-cost flow LP) | Flows on canvas + map, shadow prices of supplies and orders |
| What's the cheapest way from A to B? | Shortest route (LP) | The route on canvas + map; **Dijkstra step by step** (teach mode) with the same answer as the LP; how much longer a road may get before the route changes; the closest alternatives |
| How much can my network carry at most? | Maximum flow (LP) | Flow / capacity on every road; the **minimum cut** highlighted in red as the bottleneck (max-flow = min-cut) |
| How much of each product should I make? | Product mix (LP) | With 2 products the **graphical method**: feasible region, limit lines (solid = binding), corners with their profit, iso-profit line, best corner; teach mode adds one limit at a time; sliders move the lines live |

Every model has the same tools around it (below for transport): live sliders, "What limits you?", price of a rule, fixes when infeasible, beat the solver, scenarios, manager summary and "Show the math".

On the transport page you:
- **build the network** from city names (bundled GeoNames list, no live geocoding), drag places on a canvas, draw routes by dragging, or paste a table from Excel/CSV; costs come from road km × cost per km and stay editable per route;
- **solve** with CPLEX and see the flows on the canvas and as routes on a map;
- move **live sliders** (supplies, orders, cost per km, one route's cost) and watch cost and flows change;
- read **"What limits you?"**: shadow prices and their ranges in words ("One more pallet at Stuttgart saves €15.00, for the next 80");
- **lock or ban a route** and get the **price of the rule** ("costs €1,257 on its own");
- make it **infeasible** and get the **cheapest fixes** from an elastic re-solve ("+250 pallets at Stuttgart → €15,281"), each one a click to apply;
- **beat the solver**: type a gut-feeling plan, score it, reveal the optimum and where the gap comes from (reduced costs and unused capacity, summing exactly to the gap);
- save **scenarios** and compare them side by side (cost, what changed, plan changes, bottlenecks), download/upload as JSON;
- copy a **manager summary** and flip **"Show the math"**: the general model and the exact LP with your numbers, next to each limit in words.

Every model type plugs into one engine (`src/plantlab/engine/`): validate in plain words → docplex model → CPLEX → plan, duals, ranges, slack; elastic fixes, price of a rule, plan scoring, scenarios and LaTeX come free for the next models.

**Question:** How should a mixed-model car assembly plant (Sedan + SUV) plan its week: what to build, how to lay out the line, whom to staff on which shift, and where to buy parts from? And does that plan survive real-world variability?

![Demo: plan, simulate, what-if](docs/demo.gif)

## What it does
Four optimisation models plan one fictional plant (`src/plantlab/plant.yaml`, ten stations, two shifts, 07:00–23:00). Each prints its result and a plain-English summary.

| Model | Type | Answers |
|---|---|---|
| Production mix | LP | Best weekly Sedan/SUV mix; bottlenecks; what one extra hour at each station is worth (shadow prices + ranging) |
| Line balancing | IP (SALBP-1) | Fewest stations for the wiring + trim line at the plan's takt, then the smoothest balance |
| Workforce | IP | Permanent, temporary and cross-trained (floater) operators per station and shift at minimum cost |
| Parts transportation | LP | Cheapest seat-set flows from three suppliers to three plants; value of extra supplier capacity |

The weekly plan from the production mix feeds the other three (takt time, staffing need, seat demand).

Example (current data): build 300 Sedans + 540 SUVs a week (€2.53 M margin). Paint and SUV off-road calibration are the bottlenecks; one more paint hour is worth €15,333 a week for the next 7.4 h, far above the €900/h overtime cost.

## Paper vs reality (simulation)
A SimPy model builds the plan on the same line with what the LP leaves out: random station times (fitted to time studies with scipy.stats and a KS test), breakdowns, small buffers that block, and SUVs that fail the off-road test and come back for rework. Twenty replications give 95% confidence intervals; scenarios share random numbers per station, so each is compared with the base plan by a paired interval.

| Scenario | Plan (LP) | Simulated cars/week | Simulated margin vs base | Bottleneck |
|---|---|---|---|---|
| Base plan | 840 | 769 ± 11 (−8.4%) | €2.31 M (paper: €2.53 M) | Off-road calibration |
| Rework-aware plan | 847 | 788 ± 11 | +€20k ± 16k | Paint shop |
| 2nd off-road cell | 827 | 773 ± 10 | +€81k ± 28k (LP said +€35k) | Paint shop |
| Double buffers | 840 | 794 ± 11 | +€73k ± 14k, but WIP 34 → 56 cars | Off-road calibration |

The LP loads paint and the test cell to 100%. Rework makes the test cell need about 106%, and a station planned at 100% loses output to every disturbance. A car spends 3.6 h in the plant for 1.3 h of work.

## The app
`streamlit run app/Home.py` opens the home page, the transport builder and the car plant example (four pages):
- **Plan (OR):** the four CPLEX models with charts: station loads and shadow prices, the balanced line against the takt, staffing per shift, supplier flows.
- **Simulate:** the plan on the simulated line: KPIs with confidence intervals, paper vs reality, load on paper vs active and blocked time per station, the fitted distributions.
- **What-if:** the three built-in scenarios, plus your own (paint units, off-road cells, buffers, rework rate, availability). CPLEX re-plans, SimPy re-simulates, in about two seconds.
- **Ask** (optional, only with `ANTHROPIC_API_KEY`): type a what-if in plain words. Claude (Sonnet) writes the scenario through a strict tool schema, the lab runs it, and Claude explains the result using only the lab's numbers. The model never does the maths.

## How to run
Needs Python 3.10–3.14 (uses the free IBM CPLEX Community Edition, limited to 1,000 variables and constraints; the models stay below that).
```bash
uv venv --python 3.12
uv pip install -e ".[dev,app]"            # add ai for the optional assistant: ".[dev,app,ai]"
.venv/bin/streamlit run app/Home.py
.venv/bin/python -m plantlab plan         # the four CPLEX models
.venv/bin/python -m plantlab fit          # input analysis: fitted distributions + KS test
.venv/bin/python -m plantlab simulate     # KPIs with 95% CIs, bottleneck
.venv/bin/python -m plantlab loop         # paper vs reality: base plan + 3 what-ifs (~10 s)
.venv/bin/pytest                          # tests: hand-checked cases, M/M/1, flow conservation, assistant
```
For the Ask page: `export ANTHROPIC_API_KEY=...` before `streamlit run`.

## Deploy (Streamlit Community Cloud)
`requirements.txt` installs the package and the app. On share.streamlit.io: New app → this repo, branch `main`, main file `app/Home.py`, Python 3.12. No secrets needed (the Ask page stays hidden without `ANTHROPIC_API_KEY`). The free tier sleeps when idle: open the link once a few minutes before a class or a demo.

## Data
All plant and transport numbers are invented for this project. Station names follow a generic car assembly flow; no real plant, company or course case is used. City names and coordinates: [GeoNames](https://www.geonames.org) (CC BY 4.0), filtered by `src/plantlab/geo/make_cities.py`.

## Repo map
See [INDEX.md](INDEX.md). Decisions in `decisions/log.md`, one summary per work session in `sessions/`.

## Author
Abdallah Shaheen, Industrial Engineering student (German Jordanian University; exchange semester at RPTU Kaiserslautern).
