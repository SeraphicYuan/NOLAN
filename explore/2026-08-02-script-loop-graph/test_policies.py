"""The chosen policy, pinned.

A threshold with no test is a threshold that drifts — and these three were chosen from a table of
eight candidates, so the reasoning behind them is exactly the kind that evaporates. Each test
names the recorded round it was decided against.

    D:\\env\\nolan\\python.exe -X utf8 -m pytest explore/2026-08-02-script-loop-graph/ -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from policies import (CONTINUE, MIN_GAIN, STOP, WEIGHTED_FLOOR,  # noqa: E402
                      severity_floor)
from state import LoopState, RoundState                          # noqa: E402


def _round(n, high=0, med=0, low=0, approved=None, reviewed=None):
    return RoundState(n=n, draft_path=f"draft-{n:02d}.md", draft_words=2000,
                      findings_by_severity={"high": high, "med": med, "low": low},
                      approved=approved, reviewed=reviewed)


def _loop(*rounds, mode="auto"):
    return LoopState(slug="t", mode=mode, rounds=list(rounds))


def test_a_high_severity_finding_is_never_shippable():
    """attention-is-all-you-need and aidebate-braid both promoted with one open. Of everything
    the judge asserts, this is what it is most likely to be right about."""
    # clean by every other measure — one high still blocks
    st = _loop(_round(1, high=1, med=0, low=0))
    assert severity_floor(st).action == CONTINUE
    assert "high" in severity_floor(st).why


def test_the_floor_is_set_so_it_almost_never_fires():
    """DELIBERATE. The lowest round-1 weighted score in the recorded corpus is 17 (homer-auto),
    so a floor of 15 fires on none of them. A floor tight enough to fire would be fitted to six
    unlabelled points. If someone raises this to 20, this test tells them what they are changing.
    """
    assert WEIGHTED_FLOOR == 15
    # homer-auto's real round 1: 0h/4m/5l = 4*3 + 5*1 = 17
    homer_auto_r1 = _round(1, high=0, med=4, low=5)
    assert homer_auto_r1.weighted() == 17
    assert severity_floor(_loop(homer_auto_r1)).action == CONTINUE, (
        "floor 15 must NOT stop a 17 — that is the whole point of choosing 15 over 20")
    # a genuinely clean draft still gets the early-out
    assert severity_floor(_loop(_round(1, high=0, med=2, low=4))).action == STOP


def test_a_round_that_does_not_pay_for_itself_ends_the_loop():
    """the-diamond-illusion round 3: weighted 18 -> 18 while the draft grew 204 words. Total
    findings fell 10 -> 8, so a count-based rule reads this as convergence."""
    r2 = _round(2, high=0, med=4, low=6)     # weighted 18
    r3 = _round(3, high=0, med=5, low=3)     # weighted 18 — three low cleared, one med ADDED
    assert r2.weighted() == r3.weighted() == 18
    assert r3.total < r2.total, "count falls even though weight does not — the trap"
    d = severity_floor(_loop(r2, r3))
    assert d.action == STOP and "not >" in d.why


def test_the_gain_bar_must_be_beaten_not_tied():
    """`> 3`, as chosen — a round that moves severity by exactly 3 has not earned another."""
    r1 = _round(1, high=0, med=8, low=8)     # weighted 32
    tie = _round(2, high=0, med=7, low=8)    # weighted 29 — gain of exactly 3
    assert r1.weighted() - tie.weighted() == MIN_GAIN
    assert severity_floor(_loop(r1, tie)).action == STOP
    beats = _round(2, high=0, med=6, low=8)  # weighted 26 — gain 6
    assert severity_floor(_loop(r1, beats)).action == CONTINUE


def test_a_run_can_still_be_saved_by_a_big_early_gain():
    """Diamond round 2: 33 -> 18 is a gain of 15 and must NOT terminate the loop — the rule ends
    rounds that stall, not rounds that work."""
    r1 = _round(1, high=1, med=5, low=9)     # weighted 33
    r2 = _round(2, high=0, med=4, low=6)     # weighted 18, gain 15
    assert r1.weighted() - r2.weighted() == 15
    assert severity_floor(_loop(r1, r2)).action == CONTINUE


def test_state_never_carries_the_draft():
    """References and control data only. A 2,500-word draft in the state bloats every checkpoint
    and tempts a node into editing prose it should be asking a writer to edit."""
    import dataclasses
    fields = {f.name for f in dataclasses.fields(RoundState)}
    assert "draft_path" in fields
    for banned in ("draft_text", "text", "body", "narration", "content"):
        assert banned not in fields, f"RoundState must not carry {banned}"
