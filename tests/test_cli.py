"""The CLI runs all four models on the plant with CPLEX and prints readable sections."""

import cplex

from plantlab.optimize.__main__ import main


def test_cli_runs_all_models(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    for title in ["Production mix", "Line balancing", "Workforce", "Parts transportation"]:
        assert title in out
    assert out.count("optimal") >= 4
    assert "€" in out and "Bottlenecks" in out


def test_cplex_is_the_engine():
    assert cplex.__version__.startswith("22.")


def test_lab_cli_simulates_and_runs_the_loop(capsys):
    from plantlab.__main__ import main as lab

    assert lab(["fit"]) == 0
    assert lab(["simulate", "--reps", "2"]) == 0
    assert lab(["loop", "--reps", "2"]) == 0
    out = capsys.readouterr().out
    assert "KS" in out and "95% CI" in out and "<- bottleneck" in out
    for name in ["Base plan", "Rework-aware plan", "2nd off-road cell", "Double buffers"]:
        assert name in out
