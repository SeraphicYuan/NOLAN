"""Tests for the global block planner — the deterministic core that satisfies the whole-video contract."""
from nolan.hyperframes.block_plan import plan_blocks, _max_run


def test_breaks_runs_and_relieves_concentration():
    # 12 beats all PREFER 'statement', but each offers alternatives → the planner must diversify
    beats = [{"id": f"b{i}", "candidates": ["statement", "stat", "comparison", "diagram"], "groundable": i % 2 == 0}
             for i in range(12)]
    m = plan_blocks(beats, max_run=3, max_share=0.5, coverage=(0.45, 0.95))["metrics"]
    assert m["max_run"] <= 3                                 # no run of the same block > 3
    assert m["max_share"] <= 0.5 + 1e-9                      # no block owns > half the video
    assert m["distinct_blocks"] >= 2                         # reached past 'statement'


def test_coverage_floor_warns_when_too_few_groundable():
    beats = [{"id": f"b{i}", "candidates": ["statement", "stat"], "groundable": i == 0} for i in range(10)]
    r = plan_blocks(beats, coverage=(0.45, 0.95))
    assert r["metrics"]["coverage"] < 0.45
    assert any("coverage" in w for w in r["warnings"])       # loud: can't hit the floor


def test_coverage_pulled_into_band_when_groundable():
    beats = [{"id": f"b{i}", "candidates": ["stat", "statement"], "groundable": True} for i in range(10)]
    m = plan_blocks(beats, coverage=(0.45, 0.95))["metrics"]
    assert 0.45 <= m["coverage"] <= 0.95                     # all-groundable (1.0) pulled down under the ceiling


def test_no_alternative_is_reported_not_silently_broken():
    beats = [{"id": f"b{i}", "candidates": ["statement"], "groundable": True} for i in range(6)]  # no alts
    r = plan_blocks(beats, max_run=3)
    assert any("run" in w for w in r["warnings"])            # honest: can't break the run without alternatives


def test_max_run_helper():
    assert _max_run(["a", "a", "b", "a"]) == 2
    assert _max_run(["a", "a", "a"]) == 3
    assert _max_run([]) == 0
