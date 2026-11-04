# Audit of the current app (04.11.2026)

Run: tests 49/51 green (the 2 failures are environmental: no `anthropic` extra installed, and newer pytest rejects `approx` on a list of tuples). App runs; home, mix, transport, network pages load.

1. **Works:** the engine idea (one Builder, duals/ranges/slack, elastic fixes, price of a rule, scoring a plan) is solid and hand-tested; the maths is correct and well documented in docstrings.
2. **Works:** v1 car plant (4 models + SimPy simulation + paper-vs-reality table) is a complete, honest story a hiring manager understands.
3. **Weak:** the app tries to be a no-code builder (drag-and-drop canvas, map, paste from Excel, six tabs per page). A visitor sees widgets, not a model; the "two minutes to understand" test fails.
4. **Weak:** no single thread. Home shows cards with generic templates (bikes, German motorways); the car plant sits apart as "worked example". Two apps in one.
5. **Weak:** CPLEX dependency: 1,000-variable limit, 100 MB wheel, slow cold start on Streamlit Cloud, and the solver is not what German employers' job ads name (they name OR-Tools, Gurobi, Python).
6. **Weak:** 6,500 lines for 4 model pages; `transport.py` (631 lines) and `network_page.py` (615) duplicate `lab.py`. Hard to extend, hard for him to explain in an interview.
7. **Weak:** the car plant pages and the v2 pages have different looks, state handling and vocabulary.
8. **Keep:** `plant.yaml` and the plant story, the SimPy simulation, the test style (hand-solved tiny cases in docstrings), plain-words summaries, "show the math".
9. **Keep as ideas, rebuild smaller:** live what-if sliders and "what limits you" (duals in words) for the LP pages.
10. **Drop:** streamlit-flow canvas, pydeck map, GeoNames list, paste-from-Excel, beat the solver, price of a rule, elastic fixes, scenario files, the AI assistant (keep off the critical path; can return in a later phase).
