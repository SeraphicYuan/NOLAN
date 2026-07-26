"""Tier-2 blocks obey the same timing contract as the rest of the composer.

They did not, for as long as they lived in `compose_extension.py`: every gate written for "the
composer" read compose.py only, so `gauge` front-loaded (`t = start + 0.4 + i*0.25`, fixed 1.1s draw
— on diamond-v2's 17.5s beat the ring finished at 1.5s and the frame held frozen for 16), `isotype`
hand-rolled its own window, five blocks scheduled with `[None] * n` (deaf to every anchor), and
`_layout_cell` ken-burnsed for a literal `duration:6` regardless of the beat.

check_reveal_sync.py catches a NEW hardcoded stagger. These are the properties it does not check:
that a draw/growth duration scales with its beat, and that a block reads the cues it claims to.
"""
import re
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
SRC = (BRIDGE / "compose.py").read_text(encoding="utf-8")
sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402

TIER2 = ["spotlight", "data_table", "trajectory", "stream", "bar_race", "split_view", "slope",
         "isotype", "dumbbell", "small_multiples", "histogram", "gauge", "process", "layout"]


def _body(fn: str) -> str:
    i = SRC.find(f"def {fn}(")
    assert i >= 0, f"{fn} not found in compose.py"
    j = SRC.find("\ndef ", i + 1)
    return SRC[i:j if j > 0 else len(SRC)]


def test_every_tier2_block_is_registered_in_the_one_composer():
    """The merge's standing guarantee: there is no second module to drift into."""
    assert not (BRIDGE / "compose_extension.py").exists(), "the Tier-2 split is back"
    for t in TIER2:
        assert t in compose.BLOCKS, f"{t} fell out of BLOCKS"


def test_no_tier2_block_schedules_with_a_dead_cue_list():
    """`_reveal_times(n, start, dur, [None] * n)` spreads but can never honour an anchor — and the
    block still counted as a cue consumer, so author.py accepted an `at` that did nothing."""
    offenders = [t for t in TIER2 if re.search(r"_reveal_times\([^)]*\[None\]\s*\*", _body(t))]
    assert not offenders, f"these schedule with a dead cue list: {offenders}"


def test_the_gauge_sweep_tracks_its_beat():
    """The incident, pinned: a 17.5s beat must not finish its arc in 1.1s, and the value must land on
    the anchored cue rather than 0.4s after the scene opens."""
    sc = {"id": "g", "start": 10.0, "dur": 17.5,
          "data": {"items": [{"value": 10, "label": "x", "_cue": 22.68}], "max": 100}}
    _frag, tl = compose.gauge("g", sc)
    arc = next(l for l in tl if "-arc0" in l)
    at = float(re.search(r",([\d.]+)\);$", arc).group(1))
    dur = float(re.search(r"duration:([\d.]+)", arc).group(1))
    assert abs(at - 22.68) < 0.01, f"the anchored cue was ignored: fired at {at}"
    assert dur > 1.5, f"the sweep still finishes in {dur}s of a 17.5s hold"


def test_a_media_cell_ken_burns_for_its_whole_cell_not_a_literal_six_seconds():
    """`duration:6` on a 20s beat = 6s of move then 14s frozen; on a 3s beat, a move cut mid-stride."""
    assert "duration:6,ease" not in SRC.replace(" ", ""), "the literal ken-burns duration is back"
    frag, tl = compose._layout_cell("L", 0, {"kind": "media", "src": "assets/x.jpg"},
                                    (0, 0, 960, 540), 4.0, end=24.0)
    kb = next(l for l in tl if "-img" in l)
    assert float(re.search(r"duration:([\d.]+)", kb).group(1)) >= 19.0, kb


def test_tier2_ink_reads_the_theme_token():
    """These blocks hardcoded near-white / near-black ink. Any theme whose --text is neither (ink-blue,
    sepia, high-contrast) lost its identity on exactly these blocks — and `test_block_token_fidelity`
    could not see it, because that gate reads compose.py and they lived somewhere else."""
    bad = []
    for t in TIER2:
        for m in re.finditer(r'ink = "(#[0-9a-fA-F]{6})"', _body(t)):
            bad.append(f"{t}: {m.group(1)}")
    assert not bad, f"Tier-2 ink must be var(--text, <fallback>): {bad}"


def test_tier2_growth_tweens_scale_with_the_beat():
    """A bar that grows in a fixed 0.4s on a 15s hold is the static-slide bug in miniature."""
    for block in ("histogram", "dumbbell", "gauge", "isotype"):
        body = _body(block)
        assert "_reveal_dur(" in body or "end - t0" in body or "nxt - t0" in body, \
            f"{block} sizes its reveal animation with a literal"
