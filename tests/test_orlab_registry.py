"""Every live problem solves its own example quickly, explains itself and shows its maths and code."""

from orlab.registry import FAMILIES, PROBLEMS


def test_live_problems_solve_their_example():
    for p in (p for p in PROBLEMS if p.live):
        s = p.solve(p.example)
        assert s.ok and s.headline and len(s.bullets) >= 2 and s.seconds < 3
        words = p.explain(p.example)
        assert words["decide"] and words["goal"] and words["limits"]
        assert "$$" in p.math and "def solve" in p.code


def test_every_problem_sits_in_a_family():
    assert {p.family for p in PROBLEMS} <= set(FAMILIES)
    assert len({p.key for p in PROBLEMS}) == len(PROBLEMS)
