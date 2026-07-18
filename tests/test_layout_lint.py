"""Deterministic layout linter (nolan.hyperframes.layout_lint) — the composition gate v2.

Docs claim, tests enforce: the linter's spec (machine-readable safe-areas + per-archetype zones) must
exist in the registry, and each check must fire on a crafted violation and stay silent on clean/exempt
geometry. Real shipped comps are the precision backstop (0 false positives)."""
import json
from pathlib import Path

import pytest

from nolan import composition as comp
from nolan.hyperframes import layout_lint as L

REPO = Path(__file__).resolve().parents[1]


def kinds(vios):
    return sorted((v.kind, v.severity) for v in vios)


def errs(vios):
    return [v for v in vios if v.severity == "error"]


# ── the spec the linter checks against must exist (docs claim, tests enforce) ──
def test_registry_carries_the_machine_readable_spec():
    sa = comp.grid()["safe_areas"]
    assert isinstance(sa["caption_keep_out_y"], (int, float)) and 0.5 < sa["caption_keep_out_y"] < 1
    assert isinstance(sa["title_safe_inset"], (int, float)) and 0 < sa["title_safe_inset"] < 0.2
    for aid in comp.ids():
        z = comp.get(aid).get("zone")
        assert z and "x" in z and "y" in z, f"{aid} has no machine zone"
        assert z["x"][0] <= z["x"][1] and z["y"][0] <= z["y"][1]


# ── each check fires on a crafted violation ────────────────────────────────────
def test_overlap_between_boxed_content():
    v = L.lint_raw_scene([
        '<div style="position:absolute;left:20cqw;top:30cqh;width:40cqw;height:30cqh">A</div>',
        '<div style="position:absolute;left:30cqw;top:35cqh;width:40cqw;height:30cqh">B</div>'],
        "centered-hero")
    assert any(x.kind == "overlap" for x in v)


def test_stacked_kinetic_words_flagged_as_overlap():
    # the real bespoke bug: two words at ~the same anchor, neither clearing
    v = L.lint_raw_scene([
        '<div style="position:absolute;left:40cqw;top:45cqh">word one</div>',
        '<div style="position:absolute;left:41cqw;top:46cqh">word two</div>'],
        "centered-hero")
    assert any(x.kind == "overlap" for x in v)


def test_caption_collision_gated_on_captions_flag():
    low = ['<div style="position:absolute;left:8cqw;bottom:8cqh;width:30cqw;height:12cqh">low text</div>']
    on = L.lint_raw_scene(low, "editorial-column", captions_on=True)
    off = L.lint_raw_scene(low, "editorial-column", captions_on=False)
    assert any(x.kind == "caption_collision" and x.severity == "error" for x in on)
    assert not any(x.kind == "caption_collision" for x in off)


def test_out_of_bounds_flagged():
    v = L.lint_raw_scene(
        ['<div style="position:absolute;left:-4cqw;top:40cqh;width:30cqw;height:12cqh">off</div>'],
        "centered-hero")
    assert any(x.kind == "out_of_bounds" and x.severity == "error" for x in v)


def test_clean_centered_hero_is_silent():
    v = L.lint_raw_scene([
        '<div style="position:absolute;left:30cqw;top:38cqh;width:40cqw;height:20cqh">7</div>',
        '<div style="position:absolute;left:40cqw;top:22cqh">By the numbers</div>'],
        "centered-hero")
    assert not v, kinds(v)


# ── exemptions keep precision high ─────────────────────────────────────────────
def test_allow_overflow_suppresses_edge_and_caption():
    v = L.lint_raw_scene(
        ['<div data-layout-allow-overflow style="position:absolute;left:8cqw;bottom:6cqh;'
         'width:30cqw;height:12cqh">deliberately low</div>'])
    assert not any(x.kind in ("caption_collision", "out_of_bounds") for x in v)


def test_lower_third_furniture_exempt_from_caption_not_bounds():
    # a lower-third dips low by design (own scrim) → NOT a caption error; but off-canvas is still an error
    low = ['<div class="ltwrap" style="position:absolute;left:6cqw;bottom:8cqh;width:30cqw;height:10cqh">'
           '<div class="lt-name">Name</div></div>']
    assert not any(x.kind == "caption_collision" for x in L.lint_raw_scene(low))
    off = ['<div class="ltwrap" style="position:absolute;left:-6cqw;top:40cqh;width:30cqw;height:10cqh">'
           '<div class="lt-name">Name</div></div>']
    assert any(x.kind == "out_of_bounds" for x in L.lint_raw_scene(off))


def test_svg_and_chart_internals_are_skipped():
    art = ['<svg style="position:absolute;inset:0"><text x="10" y="1050" '
           'style="position:absolute;top:99cqh">axis label</text></svg>']
    assert not L.lint_raw_scene(art)
    chart = ['<div class="chart" style="position:absolute;inset:8cqw">'
             '<div class="ch-xlab" style="position:absolute;bottom:2cqh">2024</div></div>']
    assert not any(x.kind == "caption_collision" for x in L.lint_raw_scene(chart))


def test_large_flex_zone_is_skipped_not_flagged():
    # a split-screen half: a big wrapper spanning near-full height whose text is flex-centred inside.
    zone = ['<div style="position:absolute;left:2cqw;top:4cqh;width:46cqw;height:92cqh">'
            '<div class="scene">Left panel body text</div></div>']
    assert not L.lint_raw_scene(zone), "a flex zone must be skipped, not edge-flagged"


# ── frame-level: composed clips make overlap a HARD error ──────────────────────
def test_composed_frame_overlap_is_hard_error():
    frame = ('<div id="root" data-composition-id="f" data-width="1920" data-height="1080">'
             '<section class="clip" data-start="0" data-duration="5" data-track-index="2">'
             '<div style="position:absolute;left:20cqw;top:30cqh;width:40cqw;height:30cqh">A</div>'
             '<div style="position:absolute;left:30cqw;top:34cqh;width:40cqw;height:30cqh">B</div>'
             '</section></div>')
    v = L.lint_frame_html(frame, frame="f")
    assert any(x.kind == "overlap" and x.severity == "error" for x in v)


def test_non_overlapping_time_windows_do_not_collide():
    # two boxes at the same place but in DIFFERENT clip windows are never on screen together
    frame = ('<div id="root" data-composition-id="f">'
             '<section class="clip" data-start="0" data-duration="5" data-track-index="2">'
             '<div style="position:absolute;left:20cqw;top:30cqh;width:40cqw;height:30cqh">A</div></section>'
             '<section class="clip" data-start="5" data-duration="5" data-track-index="2">'
             '<div style="position:absolute;left:20cqw;top:30cqh;width:40cqw;height:30cqh">B</div></section>'
             '</div>')
    assert not any(x.kind == "overlap" for x in L.lint_frame_html(frame, frame="f"))


# ── precision backstop: real shipped comps stay clean ──────────────────────────
def test_real_shipped_comps_have_no_layout_errors():
    base = REPO / "render-service" / "_lab_hyperframes" / "videos"
    if not base.exists():
        pytest.skip("no lab comps on disk")
    # a couple of known-good shipped comps (author-demo is a deliberate collision FIXTURE — excluded)
    good = ["aeneid-essay", "ai-datacenter-debate-v4"]
    checked = 0
    for name in good:
        c = base / name
        if not (c / "compositions" / "frames").exists():
            continue
        rep = L.lint_composition(c, captions_on=True)
        assert rep["errors"] == 0, f"{name}: {rep['errors']} false-positive errors: {rep['frames']}"
        checked += 1
    if not checked:
        pytest.skip("known-good comps absent")
