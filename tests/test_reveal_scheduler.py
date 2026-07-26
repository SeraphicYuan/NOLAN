"""The shared reveal scheduler (`compose._reveal_times`) — the pin/run contract.

INCIDENT (diamond-v2 `f03s01`, a `process` block): the author anchored step 1 to "you hide most of
it" (aligner `_cue` 6.84) and left steps 2-3 unanchored. The scheduler placed them at 7.34 / 7.84 —
three beats of a 14.9s scene delivered inside one second, followed by seven dead ones. Only the
all-unanchored path ever "filled the hold"; one late anchor crushed everything after it into a
`minstep` pile-up. Anchored cues are now PINS and unanchored runs spread across the gaps between them.

The properties below are what the render depends on: order, containment, and — where there is room —
a cadence that uses the beat.
"""
import itertools
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402


def test_the_incident_case_fills_the_hold():
    """f03s01 exactly: 3 steps, 14.9s, only step 1 anchored (late, at 6.84)."""
    t = compose._reveal_times(3, 0.0, 14.9, [6.84, None, None])
    assert t[0] == 6.84                                   # the anchor is honoured verbatim
    gaps = [round(t[i + 1] - t[i], 2) for i in range(2)]
    assert all(g >= 2.0 for g in gaps), f"the unanchored tail bunched again: {t}"
    assert t[-1] <= 14.4                                  # still inside the window (dur - tail)


def test_unanchored_path_is_untouched():
    """No cue anywhere → the original spread, byte for byte. This is the blast-radius guard: the
    pin logic must not perturb the ~everything case."""
    for n, dur in ((1, 6.0), (3, 12.0), (5, 9.0), (8, 20.0)):
        assert compose._reveal_times(n, 0.0, dur) == compose._reveal_times(n, 0.0, dur, [None] * n)


def test_order_and_containment_hold_under_adversarial_pins():
    """Monotonic and inside [start, start+dur-tail] for every pin pattern — including pins packed
    tighter than `minstep`, where cadence must yield to ORDER (a reveal that fires out of sequence is
    a wrong frame; one that fires early is only an ugly one)."""
    starts, dur = 3.0, 10.0
    for n in (2, 3, 4, 5):
        for pattern in itertools.product([None, "early", "mid", "late", "tight"], repeat=n):
            cues = []
            for p in pattern:
                cues.append({"early": starts + 0.1, "mid": starts + 5.0, "late": starts + 9.9,
                             "tight": starts + 4.0, None: None}[p])
            t = compose._reveal_times(n, starts, dur, cues)
            assert len(t) == n
            assert all(t[i] <= t[i + 1] + 1e-9 for i in range(n - 1)), f"out of order {pattern} -> {t}"
            assert all(starts - 0.01 <= x <= starts + dur - 0.5 + 0.01 for x in t), f"escaped {pattern} -> {t}"


def test_a_run_between_two_pins_splits_the_gap_and_never_crosses():
    """Two anchors 6s apart with two unanchored elements between → the pair divides the gap."""
    t = compose._reveal_times(4, 0.0, 20.0, [2.0, None, None, 8.0])
    assert t[0] == 2.0 and t[3] == 8.0
    assert 2.0 < t[1] < t[2] < 8.0
    assert abs((t[1] - 2.0) - (t[2] - t[1])) < 0.2       # evenly, not hugged against the first pin


def test_a_leading_run_lands_before_its_pin():
    """Unanchored elements BEFORE the first anchor must arrive before it, not after."""
    t = compose._reveal_times(3, 0.0, 12.0, [None, None, 7.0])
    assert t[0] < t[1] < 7.0 and t[2] == 7.0
