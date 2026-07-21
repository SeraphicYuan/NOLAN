"""Tests for nolan.hyperframes.sync — phrase timing + operative-cue re-derivation (P0.1 item 4)."""
import json
from pathlib import Path

from nolan.hyperframes import sync


def test_phrase_time_finds_spoken_start():
    from nolan.whisper import WordTimestamp
    words = [WordTimestamp("the", 0.0, 0.3), WordTimestamp("grid", 1.0, 1.4),
             WordTimestamp("never", 2.0, 2.4), WordTimestamp("built", 2.6, 3.0)]
    assert abs(sync._phrase_time("never built", words) - 2.0) < 0.01
    assert sync._phrase_time("never built", words, after=2.5) is None   # only occurrence is before `after`
    assert sync._phrase_time("does not occur", words) is None


def _comp(tmp: Path, words, scenes, frame_dur=6.0):
    (tmp / "compositions" / "frames").mkdir(parents=True)
    (tmp / "compositions" / "frames" / "01-a.spec.json").write_text(
        json.dumps({"frames": [{"id": "01-a", "dur": frame_dur, "scenes": scenes}]}), encoding="utf-8")
    (tmp / "audio_meta.json").write_text(json.dumps(
        {"voices": [{"frame": 1, "path": "assets/voice/01.wav", "duration_s": frame_dur, "words": words}]}),
        encoding="utf-8")
    return tmp


def test_place_scenes_resolves_operative_cue_from_spoken_word(tmp_path):
    words = [{"word": w, "start": s, "end": s + 0.3} for w, s in
             [("the", 0.0), ("grid", 1.0), ("was", 1.5), ("never", 2.0), ("built", 2.6),
              ("for", 3.2), ("this", 3.5)]]
    scenes = [{"id": "s1", "type": "statement", "start": 0, "dur": 6,
               "data": {"lines": ["The grid was", "never built for this"], "operative": "never built", "cue": 1.0}}]
    comp = _comp(tmp_path, words, scenes)
    sync.place_scenes(comp)
    d = json.loads((comp / "compositions" / "frames" / "01-a.spec.json").read_text(encoding="utf-8"))
    cue = d["frames"][0]["scenes"][0]["data"]["cue"]
    assert abs(cue - 2.0) < 0.05                       # 'never' spoken at 2.0s, scene starts 0 → cue 2.0 (not the typed 1.0)


# --- Layer 2: per-DATA-element narration anchors ("show it as you say it") -------------------------

def test_phrase_time_number_aware_spelled_out_matches_digits():
    """Whisper writes numbers as DIGITS; a spelled-out anchor must still land on them (subtlety #1)."""
    from nolan.whisper import WordTimestamp
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in
             enumerate("the model trained on 900 million tokens".split())]
    assert abs(sync._phrase_time("nine hundred million tokens", words) - 4.0) < 0.01   # '900' spoken @4.0
    # both forms canonicalize equal
    assert sync._collapse_nums(sync._norm("sixty percent")) == sync._collapse_nums(sync._norm("60%"))


def test_retime_reveals_pins_anchored_elements_and_leaves_rest():
    """A data element with `at` gets an ABSOLUTE `_cue` at its spoken time; unanchored stays None so
    the composer spreads it. Field-name-agnostic across data blocks."""
    from nolan.whisper import WordTimestamp
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in
             enumerate("the model trained on 900 million tokens last year".split())]
    sc = {"type": "chart", "start": 0.0, "dur": 10.0, "data": {"series": [
        {"label": "A", "value": 10, "at": "trained on"},     # 'trained' spoken @2.0
        {"label": "B", "value": 20, "at": "900 million"},    # '900' spoken @4.0 (digit form)
        {"label": "C", "value": 30}]}}                        # unanchored
    n = sync._retime_reveals(sc, sc["data"], words)
    ser = sc["data"]["series"]
    assert n == 2
    assert abs(ser[0]["_cue"] - 2.0) < 0.01
    assert abs(ser[1]["_cue"] - 4.0) < 0.01
    assert "_cue" not in ser[2] or ser[2]["_cue"] is None


def test_retime_reveals_idempotent_unpins_removed_anchor():
    """Re-running after an anchor is removed clears the stale `_cue` (un-pins the element)."""
    from nolan.whisper import WordTimestamp
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate("alpha beta gamma".split())]
    sc = {"type": "stat", "start": 0.0, "dur": 6.0, "data": {"items": [{"label": "X", "at": "beta"}]}}
    sync._retime_reveals(sc, sc["data"], words)
    assert abs(sc["data"]["items"][0]["_cue"] - 1.0) < 0.01
    del sc["data"]["items"][0]["at"]                          # author removed the anchor
    sync._retime_reveals(sc, sc["data"], words)
    assert "_cue" not in sc["data"]["items"][0]               # stale placement cleared


# --- Phase 4: structural block-selection critic (advisory) ----------------------------------------

def test_selection_critic_flags_tree_in_connection_board_but_not_a_web():
    chain = [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]
    web = [{"from": "a", "to": "b"}, {"from": "c", "to": "b"}, {"from": "b", "to": "a"}]  # 2 parents + cycle
    assert sync._selection_advice({"type": "connection_board", "data": {"links": chain}})
    assert sync._selection_advice({"type": "connection_board", "data": {"links": web}}) is None


def test_selection_critic_flags_nonoverlapping_spans_and_singleton_chart():
    seq = [{"label": "A", "start": 0, "end": 10}, {"label": "B", "start": 10, "end": 20}]
    ovl = [{"label": "A", "start": 0, "end": 12}, {"label": "B", "start": 8, "end": 20}]
    assert sync._selection_advice({"type": "spans", "data": {"spans": seq}})           # a sequence → timeline
    assert sync._selection_advice({"type": "spans", "data": {"spans": ovl}}) is None    # real overlap → fine
    assert sync._selection_advice({"type": "chart", "data": {"series": [{"label": "x", "value": 5}]}})
    assert sync._selection_advice({"type": "chart",
                                   "data": {"series": [{"label": a} for a in "abc"]}}) is None


def test_selection_critic_flags_sparse_data_on_long_hold_unless_grounded_or_anchored():
    """The acid-test lesson: a few elements on a long window read STATIC even when perfectly spread —
    editorial, not motion. Flag it, unless the author grounded it (Layer 3) or anchored it (Layer 2)."""
    two_long = {"type": "chart", "dur": 21.0, "data": {"series": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]}}
    assert sync._selection_advice(two_long)                                    # sparse + long + bare → flag
    assert sync._selection_advice({**two_long, "dur": 6.0}) is None            # short hold → fine
    grounded = {"type": "chart", "dur": 21.0, "data": {"series": [{"label": "A"}, {"label": "B"}],
                                                        "ground": {"kind": "image", "src": "x"}}}
    assert sync._selection_advice(grounded) is None                           # Layer 3 fills the hold
    anchored = {"type": "chart", "dur": 21.0, "data": {"series": [{"label": "A", "at": "first"},
                                                                  {"label": "B", "at": "later"}]}}
    assert sync._selection_advice(anchored) is None                           # Layer 2 syncs the reveals
    dense = {"type": "chart", "dur": 20.0, "data": {"series": [{"label": c} for c in "abcdef"]}}
    assert sync._selection_advice(dense) is None                              # enough elements to fill


# --- #2: number-aware scene placement + gap interpolation (no all-or-nothing proportional dump) ------

def test_resolve_scene_starts_number_aware_and_interpolated():
    from nolan.whisper import WordTimestamp
    words = [WordTimestamp(w, float(i * 1.5), float(i * 1.5) + 0.5) for i, w in enumerate(
        "the model spent 900 million then paused before the final act arrived".split())]
    scenes = [{"id": "s1", "data": {}},                                   # opens the frame
              {"id": "s2", "data": {"anchor": "nine hundred million"}},    # number-aware → '900 million'
              {"id": "s3", "data": {"anchor": "unspeakable phrase xyz"}},  # unresolved → interpolated
              {"id": "s4", "data": {"anchor": "final act"}}]              # exact match near the end
    starts, resolved = sync._resolve_scene_starts(scenes, words, frame_dur=18.0, aligner_raw=[None] * 4)
    assert "s2" in resolved and "s4" in resolved and "s3" not in resolved
    assert abs(starts[1] - 4.5) < 0.01                                    # '900' spoken @4.5
    assert starts[0] < starts[1] < starts[2] < starts[3]                  # monotonic; s3 interpolated in the gap
    assert starts[1] < starts[2] < starts[3]


def test_placement_prefers_early_content_over_late_anchor():
    """The 'santa cruz' drift: a scene anchored to a CLOSING phrase (spoken late) must still be placed when
    its TOPIC first surfaces, so the previous scene doesn't overrun the whole segment."""
    from nolan.whisper import WordTimestamp
    # "... power grid ... then the arizona campus drinks gallons ... santa cruz"  — arizona@~4, santa cruz@~9
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(
        "the power grid then the arizona campus drinks gallons a city santa cruz".split())]
    scenes = [{"id": "s1", "type": "statement", "data": {"kicker": "POWER GRID"}},
              {"id": "s2", "type": "scale", "anchor": "santa cruz",                  # anchor = late closing phrase
               "data": {"kicker": "ONE ARIZONA CAMPUS", "title": "drinks gallons"}}]  # content: arizona/campus/gallons
    starts, resolved = sync._resolve_scene_starts(scenes, words, frame_dur=14.0, aligner_raw=[None, None])
    # s2 placed at its CONTENT (arizona ~5), not the late 'santa cruz' anchor (~11)
    assert starts[1] < 8.0, f"s2 placed at the late anchor, not its content: {starts[1]}"


def test_visual_lag_flags_misordered_scenes():
    """Two scenes whose narration order is reversed vs their spec order → a mis-order flag (placement can't
    fix without reordering)."""
    from nolan.whisper import WordTimestamp
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(
        "intro water stress areas then arizona desert campus gallons later".split())]
    # spec order: arizona scene FIRST, water scene SECOND — but VO says water (1-3) before arizona (5-8)
    scenes = [{"id": "s1", "type": "scale", "start": 5.0, "data": {"kicker": "ARIZONA DESERT CAMPUS"}},
              {"id": "s2", "type": "stat", "start": 8.0, "data": {"kicker": "WATER STRESS AREAS"}}]
    flags = sync._visual_lag_flags(scenes, words)
    assert any(f["kind"] == "misorder" and f["scene"] == "s2" for f in flags)


def test_placement_isolates_a_bad_anchor_outlier_no_cascade():
    """Containment: a scene with a bad LATE anchor (and no matching content) is an OUTLIER — it is isolated
    to its own window, NOT allowed to drag every later scene late (the old sequential-floor cascade)."""
    from nolan.whisper import WordTimestamp
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(
        "intro alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima decoy".split())]
    scenes = [{"id": "s1", "data": {"kicker": "ALPHA"}},                         # alpha @1
              {"id": "s2", "anchor": "decoy", "data": {"kicker": "ZEBRA XYLOPHONE"}},  # only signal = decoy @13
              {"id": "s3", "data": {"kicker": "CHARLIE"}},                       # charlie @3
              {"id": "s4", "data": {"kicker": "HOTEL"}}]                         # hotel @8
    starts, resolved = sync._resolve_scene_starts(scenes, words, frame_dur=18.0, aligner_raw=[None] * 4)
    assert "s2" not in resolved and "s3" in resolved and "s4" in resolved       # s2 is the isolated outlier
    assert starts[2] < 6 and starts[3] < 11                                     # s3/s4 stay on their content — no cascade
