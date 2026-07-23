"""Transcript visual-tier: adaptive snapshot-density planner + structured-entity caption fusion.
Pure-function tests — no network, no ffmpeg (the storyboard/keyframe/caption I/O is exercised live)."""
from nolan import transcript_frames as tf


def _gaps(times, duration):
    """Consecutive gaps including the head (0→first) and tail (last→duration)."""
    edges = [0.0] + list(times) + ([duration] if duration else [])
    return [round(b - a, 3) for a, b in zip(edges, edges[1:])]


def test_static_video_even_grid():
    """No scene changes → an even ~max_gap grid from the fill; every gap within [min, max]."""
    times = tf.plan_snapshot_times([], duration=120.0, min_gap=30, max_gap=50)
    assert times, "a static video must still get snapshots"
    for g in _gaps(times, 120.0):
        assert g <= 50 + 0.5, f"gap {g} exceeds max_gap"
    # interior spacing never below the floor
    for a, b in zip(times, times[1:]):
        assert b - a >= 30 - 0.01, f"interior gap {b-a} below min_gap"


def test_changes_are_anchored_and_thinned():
    """Rapid cuts collapse to >=min_gap apart; a surviving cut lands just AFTER the change (lag)."""
    changes = [10, 12, 14, 40, 42, 44]
    times = tf.plan_snapshot_times(changes, duration=120.0, min_gap=30, max_gap=50, lag=1.0)
    for a, b in zip(times, times[1:]):
        assert b - a >= 30 - 0.01
    # the 40s cluster survives as one anchor at ~41 (change + lag)
    assert any(abs(t - 41.0) < 0.2 for t in times), times


def test_large_gap_filled_min_gap_wins():
    """A gap wider than max_gap is filled — but never split below min_gap (the 55s tension case)."""
    # 90s gap → one interior point at ~45 (both sub-gaps 45 <= max, >= min)
    filled = tf._fill_gap(0.0, 90.0, 30, 50)
    assert len(filled) == 1 and abs(filled[0] - 45.0) < 0.01
    # 55s gap → min_gap wins → NO interior point (27.5 would violate the floor)
    assert tf._fill_gap(0.0, 55.0, 30, 50) == []
    # 120s gap → two points at 40, 80
    f2 = tf._fill_gap(0.0, 120.0, 30, 50)
    assert len(f2) == 2 and abs(f2[0] - 40) < 0.01 and abs(f2[1] - 80) < 0.01


def test_short_video_still_gets_opening():
    """A short no-change clip still captures the opening shot (t=0 seed), never returns empty."""
    assert tf.plan_snapshot_times([], duration=40.0, min_gap=30, max_gap=50)


def test_caption_fuses_structured_entities():
    """The searchable caption folds people/location/objects/context in — so a named entity is retrievable
    even when the summary sentence omits it (mirrors vector_search._build_segment_text)."""
    import json
    reply = json.dumps({
        "frame_description": "A man speaks on a stage.",
        "combined_summary": "The founder announces a new rocket at a keynote.",
        "inferred_context": {
            "people": ["Elon Musk"],
            "location": "Starbase, Texas",
            "objects": ["Starship rocket", "podium"],
            "story_context": "product unveiling",
            "confidence": "high",
        },
    })
    cap = tf._extract_caption(reply)
    assert "The founder announces" in cap
    assert "People: Elon Musk" in cap
    assert "Location: Starbase, Texas" in cap
    assert "Objects: Starship rocket, podium" in cap
    assert "Context: product unveiling" in cap


def test_caption_plain_text_fallback():
    """Non-JSON reply degrades to the raw text, not a crash."""
    assert tf._extract_caption("just a plain sentence") == "just a plain sentence"
    assert tf._extract_caption("") == ""


def test_analysis_extracts_asset_type_and_derives_content_kind():
    """gemma's rich 11-value asset_type is parsed, and the coarse content_kind is DERIVED from it."""
    import json
    a = tf._extract_analysis(json.dumps({
        "frame_description": "a harbour at dawn", "asset_type": "Live-Footage",
        "inferred_context": {"location": "harbour"}}))
    assert a["asset_type"] == "live-footage" and a["content_kind"] == "broll"   # normalized + rolled up
    assert a["location"] == "harbour"
    # a talking head + a chart roll up correctly
    assert tf._extract_analysis(json.dumps({"asset_type": "talking-head"}))["content_kind"] == "talking_head"
    assert tf._extract_analysis(json.dumps({"asset_type": "chart-graphic"}))["content_kind"] == "graphics"


def test_split_caption_roundtrips_fusion():
    """split_caption reverses the fused ' | Label: value' format for the structured detail column."""
    fused = ("The founder announces a rocket. | People: Elon Musk, Gwynne Shotwell | "
             "Location: Starbase | Objects: Starship, podium | Context: unveiling")
    s = tf.split_caption(fused)
    assert s["summary"] == "The founder announces a rocket."
    assert s["people"] == ["Elon Musk", "Gwynne Shotwell"]
    assert s["location"] == "Starbase"
    assert s["objects"] == ["Starship", "podium"]
    assert s["story"] == "unveiling"
    # summary-only caption
    assert tf.split_caption("just a scene")["summary"] == "just a scene"


def test_asset_type_to_content_kind_rollup():
    """The video library's fine asset_type rolls up to the shared coarse content_kind."""
    from nolan.visual_facts import content_kind_of
    assert content_kind_of("talking-head") == "talking_head"
    assert content_kind_of("live-footage") == "broll"
    assert content_kind_of("archival-footage") == "broll"
    assert content_kind_of("chart-graphic") == "graphics"
    assert content_kind_of("text-card") == "graphics"
    assert content_kind_of("other") == ""
    assert content_kind_of("") == ""


def test_plan_shots_one_per_shot_plus_gapfill():
    """Cuts -> one frame per shot (into the shot), + a gap-fill frame for a shot longer than `gap`."""
    from nolan import transcript_frames as tf
    shots = tf.plan_shots([10, 20, 35], 120.0, gap=50.0)
    # 4 shots: [0-10],[10-20],[20-35],[35-120]; the last (85s) also gets a gap-fill
    times = [t for t, s, e in shots]
    assert (0.8, 0.0, 10.0) in shots and (10.8, 10.0, 20.0) in shots
    assert any(abs(t - 85.0) < 0.1 for t in times), shots            # gap-fill inside the 85s shot
    # every frame carries its shot bounds
    assert all(s <= t <= e for t, s, e in shots)


def test_densify_broll_rule():
    """A broll shot samples every 5s up to 25s (or shot end); short broll + non-broll get nothing."""
    from nolan import transcript_frames as tf
    # long broll shot [40,80], base at 41 -> extras 46,51,56,61 (<= 41+25)
    ex = tf.densify_broll([(41.0, 40.0, 80.0, "broll")])
    assert ex == [46.0, 51.0, 56.0, 61.0], ex
    # capped by the next cut: broll shot only [40,52] -> just 46, 51
    assert tf.densify_broll([(41.0, 40.0, 52.0, "broll")]) == [46.0, 51.0]
    # short broll shot -> none; talking_head -> none
    assert tf.densify_broll([(1.0, 0.0, 4.0, "broll")]) == []
    assert tf.densify_broll([(41.0, 40.0, 80.0, "talking_head")]) == []


def test_stills_split_from_broll():
    """Stills (photo/painting/illustration) are their OWN content_kind, not b-roll; footage stays b-roll."""
    from nolan.visual_facts import content_kind_of, CONTENT_KINDS
    assert "stills" in CONTENT_KINDS
    assert content_kind_of("photo") == "stills" and content_kind_of("illustration") == "stills"
    assert content_kind_of("live-footage") == "broll" and content_kind_of("archival-footage") == "broll"


def test_caption_fuses_shot_field():
    """The `shot` framing/mood field is folded into the searchable caption (recovers appearance search)."""
    import json
    from nolan import transcript_frames as tf
    a = tf._extract_analysis(json.dumps({
        "frame_description": "an oil tanker", "asset_type": "live-footage",
        "shot": "top-down aerial, daylight"}))
    assert a["shot"] == "top-down aerial, daylight"
    assert "Shot: top-down aerial, daylight" in a["caption"]
