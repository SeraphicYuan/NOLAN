"""Same-track time overlap is caught at AUTHOR time, not minutes later at render.

A centred `spotlight` emitted BOTH halves of its label on one track over identical windows, which is
illegal (`timeline_track_too_dense`) — so NO centred spotlight had ever assembled, and the block shipped
broken because the earliest thing that says so is the external `hyperframes` CLI at render/validate
time, behind sync + recompose + sound + captions. A composer bug is cheapest in the composer's own gate.

STATUS: the pure detector below is correct and tested, but it is NOT wired as a gate. Wiring it blocked
legitimate multi-scene frames, because adjacent scenes DELIBERATELY overlap on a shared track — the
composer gives each scene a ~0.6s tail (0-5.60, 5.00-10.60, 10.00-14.00 for scenes at 0/5/10) and the
transitions injector 0/1-ping-pongs the lanes afterwards. A raw same-track overlap is therefore normal
in composed HTML at this stage. The spotlight defect was narrower: two elements of ONE scene on one
track over an IDENTICAL window. Scoping to same-scene, identical-window pairs is the real fix and needs
characterising against the injector first.

(The postmortem attributes this check to assemble-index.mjs; the hf-author copy of that script has no
track guards at all — it is a different generation. The rule is real, the enforcement point was not.)
"""
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"


def _author():
    sys.path.insert(0, str(BRIDGE))
    try:
        import author
        return author
    finally:
        sys.path.pop(0)


def _clip(start, dur, track):
    return (f'<div class="clip" data-start="{start}" data-duration="{dur}" '
            f'data-track-index="{track}"></div>')


def test_overlapping_clips_on_one_track_are_found():
    bad = _author().track_overlaps(_clip(0, 5, 2) + _clip(1, 3, 2))
    assert bad and bad[0][0] == 2


def test_adjacent_clips_are_not_an_overlap():
    """Back-to-back is the NORMAL case — a false positive here would block every sequential frame."""
    assert _author().track_overlaps(_clip(0, 2, 2) + _clip(2, 2, 2) + _clip(4, 1, 2)) == []


def test_same_window_on_different_tracks_is_fine():
    """The spotlight FIX: two halves over one window, split across lanes. Must stay legal."""
    assert _author().track_overlaps(_clip(0, 5, 2) + _clip(0, 5, 1)) == []


def test_attribute_order_does_not_matter():
    html = (f'<div data-track-index="4" data-start="0" data-duration="5"></div>'
            f'<div data-track-index="4" data-start="1" data-duration="2"></div>')
    assert _author().track_overlaps(html)


def test_float_boundaries_do_not_false_fire():
    """Composed times are floats; 2.0000001 abutting 2.0 must not read as an overlap."""
    assert _author().track_overlaps(_clip(0, 2, 3) + _clip(2.0000001, 1, 3)) == []


def test_adjacent_scene_tails_are_why_this_is_not_a_gate():
    """The composer's own output: scenes at 0/5/10 emit 0-5.60, 5.00-10.60, 10.00-14.00 on a shared
    track. Gating on that blocks every normal multi-scene frame — this test records WHY, so nobody
    wires the detector up again without scoping it to same-scene identical windows first."""
    a = _author()
    html = _clip(0, 5.6, 1) + _clip(5.0, 5.6, 1) + _clip(10.0, 4.0, 1)
    assert a.track_overlaps(html), "the detector still SEES them — it is the gating that was wrong"
    src = (BRIDGE / "author.py").read_text(encoding="utf-8")
    build = src[src.index('for fr in spec["frames"]:'):]
    assert "track_overlaps(html)" not in build, "do not gate on raw same-track overlap"
