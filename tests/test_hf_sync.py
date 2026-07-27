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


def test_retime_lines_vo_syncs_each_text_line():
    """A text block's LINES reveal WHEN THE VO READS THEM (data._line_cues), not on a fixed stagger — the
    kinetic-typography sync for a statement showing script text."""
    from nolan.whisper import WordTimestamp
    words = [WordTimestamp(w, float(i * 0.6), float(i * 0.6) + 0.5) for i, w in enumerate(
        "the grid was never built for a world that needs both directions at once".split())]
    sc = {"type": "statement", "start": 0.0, "dur": 10.0,
          "data": {"lines": ["The grid was never built", "for a world that needs both directions"]}}
    n = sync._retime_lines(sc, sc["data"], words)
    lc = sc["data"]["_line_cues"]
    assert n == 2
    assert abs(lc[0] - 0.0) < 0.05 and abs(lc[1] - 3.0) < 0.05          # each line pinned to when it's spoken
    assert lc[0] < lc[1]                                                # monotonic


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
    scenes = [{"id": "s1", "type": "statement", "data": {"title": "POWER GRID"}},
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
    scenes = [{"id": "s1", "type": "scale", "start": 5.0, "data": {"title": "ARIZONA DESERT CAMPUS"}},
              {"id": "s2", "type": "stat", "start": 8.0, "data": {"title": "WATER STRESS AREAS"}}]
    flags = sync._visual_lag_flags(scenes, words)
    assert any(f["kind"] == "misorder" and f["scene"] == "s2" for f in flags)


def test_number_provenance_flags_fabricated_breakdown():
    """A data-viz block whose numbers are spoken NOWHERE in the narration is a fabrication risk (the sankey
    that invented a $100 breakdown). Numbers that ARE spoken pass (number-aware)."""
    from nolan.whisper import WordTimestamp
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(
        "big tech will spend 800 billion then a trillion by 2027".split())]
    fabricated = {"id": "s1", "type": "sankey", "data": {"source": {"label": "bill", "value": 100},
                  "targets": [{"label": "a", "value": 34}, {"label": "b", "value": 24}, {"label": "c", "value": 18}]}}
    grounded = {"id": "s2", "type": "chart", "data": {"series": [{"label": "26", "value": 800},
                {"label": "27", "value": 1000}, {"label": "x", "value": 2027}]}}   # 800, 2027 spoken
    ff = sync._number_provenance_flags([fabricated, grounded], words)
    assert any(f["scene"] == "s1" for f in ff)                         # 34/24/18 spoken nowhere -> flagged
    assert not any(f["scene"] == "s2" for f in ff)                     # 800 / 2027 are spoken -> fine
    # A-P1: an explicit value_source exempts the numbers (traceable, not fabricated)
    sourced = {"id": "s3", "type": "sankey", "data": {"value_source": "EPA 2024 report",
               "targets": [{"label": "a", "value": 34}, {"label": "b", "value": 24}, {"label": "c", "value": 18}]}}
    assert not any(f["scene"] == "s3" for f in sync._number_provenance_flags([sourced], words))


def test_placement_isolates_a_bad_anchor_outlier_no_cascade():
    """Containment: a scene with a bad LATE anchor (and no matching content) is an OUTLIER — it is isolated
    to its own window, NOT allowed to drag every later scene late (the old sequential-floor cascade)."""
    from nolan.whisper import WordTimestamp
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(
        "intro alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima decoy".split())]
    scenes = [{"id": "s1", "data": {"title": "ALPHA"}},                         # alpha @1
              {"id": "s2", "anchor": "decoy", "data": {"title": "ZEBRA XYLOPHONE"}},  # only signal = decoy @13
              {"id": "s3", "data": {"title": "CHARLIE"}},                       # charlie @3
              {"id": "s4", "data": {"title": "HOTEL"}}]                         # hotel @8
    starts, resolved = sync._resolve_scene_starts(scenes, words, frame_dur=18.0, aligner_raw=[None] * 4)
    assert "s2" not in resolved and "s3" in resolved and "s4" in resolved       # s2 is the isolated outlier
    assert starts[2] < 6 and starts[3] < 11                                     # s3/s4 stay on their content — no cascade


def _stream_freq(words):
    from nolan.aligner import flatten_words
    stream = sync._collapse_nums([(t, s) for (t, s, _e) in flatten_words(words)])
    freq = {}
    for tok, _s in stream:
        freq[tok] = freq.get(tok, 0) + 1
    return stream, freq


def test_content_window_finds_topic_opening_for_paraphrased_scene():
    """The 7:31 text-lag: a scene whose on-screen lines PARAPHRASE the VO, with an editorial kicker ('THE
    WHOLE THING') that echoes a LATER phrase. Exact-phrase and distinctive-word (`_content_time`) matching
    both point at the late echo; the fuzzy content-WINDOW finds where the topic OPENS (hand/bill/people early)."""
    from nolan.whisper import WordTimestamp
    vo = ("so the people cashing in hand the bill to folks who never voted "     # hand/bill/people @2-7
          "before we make them ask first that is the whole thing")              # whole/thing (kicker echo) @~20
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(vo.split())]
    stream, freq = _stream_freq(words)
    sc = {"id": "s1", "type": "statement", "data": {
        "kicker": "THE WHOLE THING",
        "lines": ["Do they hand the bill", "to people who never voted", "or make them ask first"]}}
    win = sync._content_window_time(sc, stream, freq, 0.0)
    con = sync._content_time(sc, stream, freq, 0.0, min_words=2)
    assert win is not None and win < 8.0, f"window should find the early hand/bill opening, got {win}"
    assert con is None or con > win, f"distinctive-word check should be dragged late by 'whole thing': {con}"
    # placement takes the earliest signal → the scene lands on its opening, not the late anchor/kicker
    starts, _ = sync._resolve_scene_starts(
        [{"id": "s0", "data": {"kicker": "INTRO"}}, sc], words, frame_dur=24.0, aligner_raw=[None, None])
    assert starts[1] < 8.0


def test_content_window_prefers_earliest_opening_not_a_denser_later_echo():
    """The 02-intro false mis-order: a scene's on-screen text is a NOMINALIZED paraphrase ('preference'/
    'prediction' for spoken 'prefer'/'likely'), so only generic words match — and a LATER sentence can echo
    MORE of them densely. Taking the globally-densest span mislocated the scene late and manufactured a false
    mis-order; the matcher returns the EARLIEST corroborated opening (a distinctive 'sides' at the true open)."""
    from nolan.whisper import WordTimestamp
    #        0      1      2      3     4      5..9 filler        15     16       17
    vo = ("upfront i prefer over likely but cover both sides fairly to be clear and honest "
          "then much later the honest version revisits both again")
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(vo.split())]
    stream, freq = _stream_freq(words)
    # bag = {preference, prediction, both, sides, honest, version}; 'prefer'/'likely' don't match the nominal forms
    sc = {"id": "s1", "type": "spectrum",
          "data": {"kicker": "PREFERENCE vs PREDICTION", "title": "both sides", "sub": "the honest version"}}
    win = sync._content_window_time(sc, stream, freq, 0.0)
    # 'sides' occurs once at the true opening (~8) → the early span corroborates; the later 'honest version'
    # echo is denser but must NOT win. (With globally-densest this returned the late echo → a false mis-order.)
    assert win is not None and win < 12.0, f"should return the early 'both sides' opening, got {win}"


def test_visual_lag_hard_flag_marks_an_unfixable_lag():
    """The SCENE-TIMING GATE: a ≥6s lag placement could not fix (an isolated outlier pinned late) is marked
    `hard` so the finish DAG blocks it; a mis-order is `hard` too. A well-placed scene is not flagged."""
    from nolan.whisper import WordTimestamp
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(
        "intro arizona campus drinks gallons daily then lots more filler talk goes here now".split())]
    late = {"id": "s1", "type": "scale", "start": 12.0,                          # topic @1-4, pinned @12 → lag ~9
            "data": {"kicker": "ARIZONA CAMPUS", "title": "drinks gallons"}}
    flags = sync._visual_lag_flags([late], words)
    lag = [f for f in flags if f["kind"] == "lag"]
    assert lag and lag[0]["hard"] is True and lag[0]["lag"] >= sync._HARD_LAG_S
    # a scene placed ON its topic is not flagged at all
    ok = {"id": "s1", "type": "scale", "start": 1.0, "data": {"kicker": "ARIZONA CAMPUS", "title": "drinks gallons"}}
    assert not sync._visual_lag_flags([ok], words)


def test_visual_lag_soft_when_author_anchored_the_scene_there():
    """Author intent overrides the hard gate: if a scene carries an explicit anchor that resolves AT its
    placement, a lag vs an earlier topic-mention is a judgement call (the late-anchor ◆ advisory), NOT a
    placement failure — it stays SOFT so the render isn't blocked over a deliberate choice."""
    from nolan.whisper import WordTimestamp
    # 'trick … three marks' concept @3-6; the scene's own anchor 'sells belief' @14; scene placed @12 (author-pinned)
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(
        "intro the confidence trick runs three marks then filler filler filler filler it sells belief later".split())]
    sc = {"id": "s1", "type": "diagram", "start": 12.0, "anchor": "sells belief",
          # the corroborating words live in `sub`/`title`, NOT the kicker: kicker is design copy and no
          # longer feeds narration matching (it masked a real 14s lead), so a fixture that leans on it
          # is testing a path that no longer exists.
          "data": {"kicker": "One trick", "title": "three marks", "sub": "the confidence trick"}}
    flags = sync._visual_lag_flags([sc], words)
    lag = [f for f in flags if f["kind"] == "lag"]
    assert lag, "the lag should still be REPORTED (advisory)"
    assert lag[0]["hard"] is False, "author-anchored-here lag must be soft, not a hard block"


# --- forced-alignment upgrade (reconcile free ASR against the KNOWN narration) ---------------------

def test_forced_alignment_recovers_known_words_from_garbled_asr(tmp_path, monkeypatch):
    """align_voices reconciles Whisper's free ASR against the KNOWN narration (SOURCE.md) so the stored
    word stream carries the true SCRIPT words at Whisper's timing — a mis-heard 'GRU'->'GU' still lets the
    author's anchor match. Without it, scene placement keys off a corrupt transcript (the weak-anchor class)."""
    (tmp_path / "assets" / "voice").mkdir(parents=True)
    (tmp_path / "assets" / "voice" / "01.wav").write_bytes(b"RIFF0000")          # presence only; ASR is mocked
    (tmp_path / "SOURCE.md").write_text(
        "# Script\n\n## Recurrence\n\nAn RNN, an LSTM, a GRU. And recurrence works one word at a time.\n",
        encoding="utf-8")
    (tmp_path / "audio_meta.json").write_text(json.dumps(
        {"voices": [{"frame": 1, "path": "assets/voice/01.wav", "duration_s": 6.0, "words": []}]}),
        encoding="utf-8")
    garbled = [{"word": w, "start": i * 0.4, "end": i * 0.4 + 0.35} for i, w in enumerate(
        "An RNN an LSTM a GU and recurrent such works one word at a time".split())]   # 'GU'/'recurrent such'
    from nolan.flows import source
    monkeypatch.setattr(source, "word_timestamps", lambda wavs, *a, **k: {"01": garbled})
    summ = sync.align_voices(tmp_path, force=True)
    assert summ["reconciled"] == 1
    meta = json.loads((tmp_path / "audio_meta.json").read_text(encoding="utf-8"))
    stream = " ".join(w["word"].lower() for w in meta["voices"][0]["words"])
    assert "gru" in stream and "recurrence works" in stream        # KNOWN words recovered @ Whisper timing
    assert all(w["start"] is not None for w in meta["voices"][0]["words"])


def test_known_narration_maps_source_sections_to_frames_in_order(tmp_path):
    """_known_narration sources the true narration from voices[].text first, else SOURCE.md's `## ` sections
    mapped to voices in frame order; a section/voice count mismatch returns {} (never risk a mis-map)."""
    (tmp_path / "SOURCE.md").write_text(
        "# Title\n\n**Total Duration:** 1:00\n\n## One [0:00]\n\nAlpha bravo charlie.\n\n"
        "## Two [0:30]\n\nDelta echo foxtrot.\n", encoding="utf-8")
    known = sync._known_narration(tmp_path, [{"frame": 2}, {"frame": 1}])          # order-independent
    assert "alpha bravo charlie" in known[1].lower() and "delta echo foxtrot" in known[2].lower()
    assert sync._known_narration(tmp_path, [{"frame": 1}]) == {}                   # 2 sections vs 1 voice
    explicit = sync._known_narration(tmp_path, [{"frame": 1, "text": "explicit words"},
                                                {"frame": 2, "text": "more"}])
    assert explicit[1] == "explicit words"                                         # voices[].text wins


def test_content_time_requires_corroboration_at_min_words_2():
    """A SINGLE distinctive label word must not anchor placement — it can echo a common phrase early and
    drag a correctly-anchored scene off its spoken word (the 04-move equation, placed 9s early). min_words=2
    (matching the lag lint) requires 2 clustering words, so a lone echo can't outweigh the real anchor."""
    from nolan.aligner import flatten_words
    from nolan.whisper import WordTimestamp
    wt = [WordTimestamp(w, float(i), i + 0.5) for i, w in enumerate(
        "gradient flows early then unrelated talk goes on for a while".split())]
    stream = sync._collapse_nums([(t, s) for (t, s, _e) in flatten_words(wt)])
    freq = {}
    for tok, _s in stream:
        freq[tok] = freq.get(tok, 0) + 1
    sc = {"data": {"title": "Gradient"}}                                          # ONE distinctive word
    assert sync._content_time(sc, stream, freq, 0.0, min_words=1) is not None      # lone word fires @1
    assert sync._content_time(sc, stream, freq, 0.0, min_words=2) is None          # but NOT when corroborated


def test_visual_lag_flags_symmetric_lead_detection():
    """S1 (post-mortem): the scene-timing gate is SYMMETRIC — a scene whose VISUAL leads the narration
    (text before voice) is flagged, advisory (never `hard`, so it doesn't block); a well-placed scene is
    not; an author-pinned early scene (anchor resolves near its start) is exempt."""
    from nolan.whisper import WordTimestamp
    from nolan.hyperframes.sync import _visual_lag_flags
    toks = "we open on a quiet ordinary still calm plain grey solar eclipse arrives now here".split()
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(toks)]

    # "solar eclipse" is spoken ~t=10; a scene placed at t=0 LEADS its content by ~10s
    early = {"id": "lead1", "type": "statement", "start": 0.0, "data": {"title": "SOLAR ECLIPSE"}}
    lead = [f for f in _visual_lag_flags([early], words) if f["kind"] == "lead"]
    assert lead and lead[0]["scene"] == "lead1", lead
    assert lead[0]["hard"] is False and lead[0]["lead"] >= 4.0      # symmetric but ADVISORY, never blocks

    # well-placed: start ≈ content time → no lead
    placed = {"id": "ok1", "type": "statement", "start": 10.0, "data": {"title": "SOLAR ECLIPSE"}}
    assert not [f for f in _visual_lag_flags([placed], words) if f["kind"] == "lead"]

    # author pinned it early on purpose (anchor 'quiet ordinary' resolves near start) → exempt
    pinned = {"id": "pin1", "type": "statement", "start": 2.0,
              "data": {"kicker": "SOLAR ECLIPSE", "anchor": "quiet ordinary"}}
    assert not [f for f in _visual_lag_flags([pinned], words) if f["kind"] == "lead"]


def test_retime_reveals_auto_anchors_unanchored_items_by_label():
    """S2 (post-mortem): a multi-fact item with NO explicit `at` is auto-anchored by its own label when that
    yields a confident (≥2 content-word) match — so a back-loaded block fires each item ON its word instead
    of even-spread (which leads). Verbatim label first, then content words; a 1-word label stays spread."""
    from nolan.whisper import WordTimestamp
    toks = "we open quietly then later the syndicate controlled supply and dumped surplus onto the market".split()
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(toks)]
    sc = {"type": "stat", "start": 0.0, "dur": 20.0, "data": {"items": [
        {"value": "90%", "label": "controlled supply"},                     # spoken ~t=7
        {"value": "-40%", "label": "dumped surplus onto the market"},       # spoken ~t=10 (needs verbatim, "the" kept)
        {"value": "x", "label": "GE"}]}}                                     # 1 content word → stays spread
    n = sync._retime_reveals(sc, sc["data"], words)
    its = sc["data"]["items"]
    assert n == 2, its
    assert abs(its[0]["_cue"] - 7.0) < 0.01
    assert abs(its[1]["_cue"] - 10.0) < 0.01                                # verbatim match kept the stop-word
    assert its[2].get("_cue") is None                                       # lone common word → unpinned (spread)


def test_a_number_element_anchors_on_its_NUMBER_not_its_trailing_label():
    """S2's label auto-anchor is right for a bullet and wrong for a figure.

    Measured on diamond-v2 f04s02: the VO says "only ten percent of American engagement rings had a
    diamond in them" — "ten percent" at 20.52, the item's label at 22.68 — so anchoring the gauge on
    its label drew the arc 2.16s AFTER the number it illustrates. The number is what the eye waits for.
    """
    from nolan.whisper import WordTimestamp
    toks = "only ten percent of american engagement rings had a diamond in them".split()
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(toks)]
    label_t = float(toks.index("had"))

    sc = {"type": "gauge", "start": 0.0, "dur": 20.0,
          "data": {"suffix": "%", "items": [{"value": 10, "label": "had a diamond in them"}]}}
    sync._retime_reveals(sc, sc["data"], words)
    assert abs(sc["data"]["items"][0]["_cue"] - 1.0) < 0.01, "did not land on 'ten'"
    assert sc["data"]["items"][0]["_cue"] < label_t

    # an EXPLICIT `at` is the author's call and still wins outright
    sc2 = {"type": "gauge", "start": 0.0, "dur": 20.0, "data": {"suffix": "%", "items": [
        {"value": 10, "label": "had a diamond in them", "at": "had a diamond"}]}}
    sync._retime_reveals(sc2, sc2["data"], words)
    assert abs(sc2["data"]["items"][0]["_cue"] - label_t) < 0.01

    # a BARE number far from its label must NOT drag the reveal: "10" is said at t=1, the label at t=14,
    # a 13s lead — beyond _VALUE_BARE_MAX_LEAD, and with no unit word there is nothing to disambiguate it.
    far = "10 of them a long digression about something else entirely then dumped surplus onto the market".split()
    fwords = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(far)]
    sc3 = {"type": "stat", "start": 0.0, "dur": 30.0,
           "data": {"items": [{"value": 10, "label": "dumped surplus onto the market"}]}}
    sync._retime_reveals(sc3, sc3["data"], fwords)
    assert abs(sc3["data"]["items"][0]["_cue"] - float(far.index("dumped"))) < 0.01, \
        "a stray earlier number dragged the reveal off its label"

    # …and a reveal is never pushed LATER than the label it already had
    sc4 = {"type": "stat", "start": 0.0, "dur": 30.0,
           "data": {"items": [{"value": 10, "label": "long digression"}]}}
    sync._retime_reveals(sc4, sc4["data"], fwords)
    assert sc4["data"]["items"][0]["_cue"] <= float(far.index("long"))


# --- kicker is DESIGN COPY, not narration (postmortem item 3 + the 12:23 lead) -----------------

def test_kicker_alone_does_not_drive_placement_or_corroboration():
    """`bridge/catalog.json` declares kicker "small eyebrow label (design intent, not narration)", yet it
    fed the matcher. Two costs, both live: a kicker naming a person mentioned much earlier dragged a
    scene 17s and HARD-BLOCKED it (authors rewrote design copy to appease a timing matcher), and a
    kicker echoing the narrator's lead-in corroborated at 0s, MASKING a 14s text-before-voice lead."""
    from nolan.aligner import WordTimestamp, flatten_words
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(
        "gerety wrote the line decades before the campaign finally reached the public".split())]
    stream = sync._collapse_nums([(t, s) for (t, s, _e) in flatten_words(words)])
    freq = {}
    for tok, _s in stream:
        freq[tok] = freq.get(tok, 0) + 1
    kicker_only = {"data": {"kicker": "GERETY DECADES"}}
    assert sync._content_time(kicker_only, stream, freq, 0.0) is None, "kicker must not corroborate"
    assert not sync._scene_bag(kicker_only), "kicker must not enter the matching bag"
    # ...and not through `_scene_query` either — the door taken by every scene WITHOUT an anchor, which
    # kept its own copy of the pre-registry key tuple long after `_content_time` stopped reading kicker.
    assert sync._scene_query(kicker_only) == "", "kicker alone must not become the placement query"
    both = {"data": {"kicker": "GERETY DECADES", "title": "The line that outlived her"}}
    assert sync._scene_query(both) == "The line that outlived her"
    assert sync._scene_query({"data": {"kicker": "X", "title": "T", "anchor": "wrote the line"}}) == \
        "wrote the line", "an explicit anchor still wins"


def test_visible_text_reaches_a_quote_and_nested_labels():
    """The pull_quote whose QUOTE was invisible to `_content_time` is the 12:23-vs-12:34 defect; nested
    step/item labels were invisible for every list-shaped block."""
    from nolan.block_registry import visible_text
    q = visible_text({"kicker": "A VERY ARTIFICIAL MARKET", "quote": "they are valuable because people pay"})
    assert "valuable because people pay" in q and "ARTIFICIAL" not in q
    nested = visible_text({"title": "Biting its own tail",
                           "steps": [{"label": "they are valuable"}, {"label": "so people pay"}]})
    assert "they are valuable" in nested and "so people pay" in nested


def test_visible_text_drops_paths_and_config_tokens():
    from nolan.block_registry import visible_text
    got = visible_text({"ground": {"src": "assets/a.mp4"}, "side": "left", "fit": "cover",
                        "title": "The real headline"})
    assert got == "The real headline"


# --- the QUOTATION matcher: ORDER locates what frequency cannot (the 12:23 lead itself) -----------
# Removing the kicker (above) uncovered the lead but still could not LOCATE it: a quotation is built from
# the frame's own subject words, so every one of them recurs. Both frequency matchers returned None on the
# live scene, and a gate cannot flag what it cannot locate. Order is the signal they discard.

def _quote_frame():
    """The live f09s01 shape, mechanism for mechanism.

    The narrator reaches the quote 13s in; the scene paints it at 0.0s; every word of it recurs in the
    frame, AND the next scene re-uses that exact vocabulary as its step labels — which is what pushes
    the window matcher's inverse-frequency weight below its threshold (siblings are down-weighted ×0.25
    so a scene can't be placed on its neighbour's entities). Both effects are needed to reproduce the
    blindness: frequency alone still resolves, late and by luck."""
    from nolan.aligner import WordTimestamp, flatten_words
    spoken = ("so here is where we land the historian put it into one loop "
              "they are very valuable because people want to pay money for them "
              "people want to pay money for them because they are very valuable "
              "that is the whole illusion").split()
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(spoken)]
    stream = sync._collapse_nums([(t, s) for (t, s, _e) in flatten_words(words)])
    freq = {}
    for tok, _s in stream:
        freq[tok] = freq.get(tok, 0) + 1
    # NOTE the trim: the screen reads "They are valuable", the narrator says "they are VERY valuable".
    quote = ("They are valuable because people want to pay money for them. "
             "People want to pay money for them because they are very valuable.")
    q1 = {"id": "q1", "type": "pull_quote", "start": 0.0, "dur": 14.0,
          "data": {"kicker": "A VERY ARTIFICIAL MARKET", "quote": quote, "cite": "the historian"}}
    sibling = {"id": "q2", "type": "cycle", "start": 14.0, "dur": 10.0,
               "data": {"title": "Biting its own tail", "steps": [
                   {"label": "They are valuable"}, {"label": "So people pay money"},
                   {"label": "So they are valuable"}]}}
    scenes = [q1, sibling]
    return scenes, words, stream, freq, sync._shared_bag_tokens(scenes)


def test_both_frequency_matchers_are_blind_to_a_quotation():
    """The premise. If this ever starts passing by another route, the quotation matcher is redundant —
    but until then, this is why a 14s text-before-voice lead was invisible to the gate."""
    (sc, _sib), _words, stream, freq, shared = _quote_frame()
    assert sync._content_time(sc, stream, freq, 0.0, min_words=2) is None      # needs freq==1; all recur
    assert sync._content_window_time(sc, stream, freq, 0.0, shared=shared) is None   # Σ 1/freq < 1.5


def test_prose_time_locates_the_quote_the_bag_matchers_missed():
    (sc, _sib), _words, stream, freq, shared = _quote_frame()
    assert abs(sync._prose_time(sc, stream) - 13.0) < 0.01     # 'they are very valuable…' opens at t=13
    assert abs(sync._topic_open_time(sc, stream, freq, 0.0, shared=shared) - 13.0) < 0.01


def test_the_1223_lead_is_flagged_end_to_end():
    """The user-visible defect: quote readable at 12:23, spoken at 12:34. Advisory, not hard — a lead is
    a taste call — but it must SURFACE, and for a frame's first scene (pinned to 0.0) surfacing is the
    only available fix: placement cannot move it, so the author must add a lead-in beat."""
    scenes, words, _stream, _freq, _shared = _quote_frame()
    leads = [f for f in sync._visual_lag_flags(scenes, words) if f["kind"] == "lead"]
    assert leads and leads[0]["scene"] == "q1", leads
    assert leads[0]["lead"] >= 10.0 and leads[0]["hard"] is False


def test_placement_uses_the_quotation_match_so_lint_and_placement_agree():
    """Both paths read the same signal — placement must not leave a scene where the lint flags it.
    (The live scene is its frame's FIRST, which placement pins to 0.0 by construction; here it is not,
    so the effect on placement is visible.)"""
    (q1, sib), words, _stream, _freq, _shared = _quote_frame()
    opener = {"id": "s0", "type": "statement", "start": 0.0, "data": {"lines": ["So here is where we land"]}}
    starts, resolved = sync._resolve_scene_starts([opener, q1, sib], words, 40.0, [None, None, None])
    assert abs(starts[1] - 13.0) < 0.05, starts       # placed WHEN it is said, not at the author's 0.0
    assert "q1" in resolved                           # and counted as resolved, not interpolated


def test_prose_time_requires_ORDER_not_just_the_words():
    """What separates this from the bag matchers. The same vocabulary, shuffled, is not a quotation —
    if this passed, the matcher would just be an unweighted bag with extra steps."""
    (sc, _sib), _words, stream, _freq, _shared = _quote_frame()
    toks = sc["data"]["quote"].replace(".", "").split()
    scrambled = dict(sc, data=dict(sc["data"], quote=" ".join(sorted(toks))))
    assert sync._prose_time(scrambled, stream) is None


def test_prose_time_ignores_short_strings():
    """Order carries no evidence over a label. A short 'match' against the most common words in the
    language is noise, and it would claim authority the frequency matchers correctly refuse."""
    (sc, _sib), _words, stream, _freq, _shared = _quote_frame()
    short = dict(sc, data={"title": "want to pay money for them"})     # 6 tokens < the 8-token floor
    assert sync._prose_time(short, stream) is None


def test_prose_time_does_not_match_across_two_fields():
    """`visible_strings` keeps displayed strings separate: a phrase that only exists by concatenating a
    title with a caption is on screen nowhere, so it must not corroborate anything."""
    (sc, _sib), _words, stream, _freq, _shared = _quote_frame()
    split = dict(sc, data={"title": "they are valuable because people",
                           "sub": "want to pay money for them"})
    assert sync._prose_time(split, stream) is None
    from nolan.block_registry import visible_strings
    assert visible_strings(split["data"]) == ["they are valuable because people",
                                              "want to pay money for them"]


def test_prose_time_respects_after():
    (sc, _sib), _words, stream, _freq, _shared = _quote_frame()
    assert sync._prose_time(sc, stream, after=14.0) is not None    # the second, closing half
    assert sync._prose_time(sc, stream, after=39.0) is None
