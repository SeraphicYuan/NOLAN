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
