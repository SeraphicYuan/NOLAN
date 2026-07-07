"""Still-treatment variety (aeneid feedback: every image = same abrupt push).

Pins: narrative-semantic selection (pan for journeys, out for reveals, in
for naming), the hard no-two-consecutive rule, the drift close, the
in-memory pre-pass scoping (specs/layouts/pins excluded), and the mode
reaching camera_tour_props → ArtworkStage.
"""

from nolan.still_motion import (
    assign_still_treatments, camera_tour_props, select_still_treatment,
)


def test_narrative_semantics():
    assert select_still_treatment(
        {"narration_excerpt": "he rose from Mantua through powerful patrons"}
    ) == "kenburns-pan"
    assert select_still_treatment(
        {"narration_excerpt": "a hymn to Rome, to destiny — the entire empire"}
    ) == "kenburns-out"
    assert select_still_treatment(
        {"narration_excerpt": "his schoolmates nicknamed him Parthenias"}
    ) == "kenburns-in"


def test_no_two_consecutive():
    first = select_still_treatment({"narration_excerpt": "this manuscript"})
    second = select_still_treatment({"narration_excerpt": "this manuscript"},
                                    prev=first)
    assert first == "kenburns-in" and second != first


def test_prepass_assigns_variety_and_drift_close():
    plan = {"sections": {"a": [
        {"id": "s1", "matched_asset": "a.jpg", "energy": 0.3,
         "narration_excerpt": "this poem, the manuscript itself"},
        {"id": "s2", "matched_asset": "b.jpg", "energy": 0.3,
         "narration_excerpt": "these pages, this man"},
        {"id": "s3", "layout_spec": {"template": "quote"},
         "narration_excerpt": "arma virumque"},
        {"id": "s4", "generated_asset": "c.png", "energy": 0.2,
         "narration_excerpt": "and the story simply stops"},
    ]}}
    n = assign_still_treatments(plan)
    assert n == 3
    a = plan["sections"]["a"]
    assert a[0]["_still_treatment"] == "kenburns-in"
    assert a[1]["_still_treatment"] != a[0]["_still_treatment"]  # no repeat
    assert "_still_treatment" not in a[2]                        # layout owns it
    assert a[3]["_still_treatment"] == "drift"                   # quiet close


def test_mode_reaches_camera_props():
    s = {"id": "s1", "energy": 0.3, "motion_speed": "slow",
         "_still_treatment": "kenburns-out"}
    props = camera_tour_props(s, 0)
    assert props["mode"] == "kenburns-out"
    assert camera_tour_props({"id": "s2"}, 0)["mode"] == "kenburns-in"


def test_premium_prepass_wired():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "src/nolan/premium_render.py"
           ).read_text(encoding="utf-8")
    assert "assign_still_treatments" in src
