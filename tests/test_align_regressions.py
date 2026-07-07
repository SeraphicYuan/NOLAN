"""Alignment regressions from the aeneid-2beat-v2 full-pipeline run.

The incident: scene_010's excerpt starts "It is…"; the partial-match path
accepted a bare 2-word prefix 46s late (conf 0.27), the forward-only cursor
starved every later scene, and the beat-anchoring "usable" gate accepted the
resulting equal-starts pileup — beat 2 rendered as a 46-second title card.
"""

from types import SimpleNamespace

from nolan.aligner import align_scenes_to_audio, find_text_in_words
from nolan.scenes import Scene, ScenePlan, anchor_scenes_to_sections


def _w(text, t0, dt=0.4):
    out, t = [], t0
    for tok in text.split():
        out.append(SimpleNamespace(word=tok, start=round(t, 2),
                                   end=round(t + dt, 2), probability=1.0))
        t += dt
    return out


def test_two_word_prefix_is_not_a_match():
    """'It is' appearing early must not claim an excerpt whose real content
    never occurs there."""
    words = _w("it is a warm day in the north of italy today", 0.0) + \
            _w("the man who turns out to be the mystery arrives", 30.0)
    m = find_text_in_words("It is the man who turns out to be the mystery",
                           words, 0)
    # either no match, or a confident one — never a 0.2-confidence prefix grab
    if m:
        assert m[2] >= 0.5


def test_bad_prefix_does_not_starve_later_scenes():
    words = (_w("in the year nineteen bc a dying poet gave one instruction", 0.0)
             + _w("it is quiet here", 10.0)
             + _w("publius vergilius maro was born in seventy bc on a farm", 20.0)
             + _w("that is the story of his hero", 40.0))
    scenes = [
        {"id": "s1", "narration_excerpt":
            "In the year 19 BC a dying poet gave one instruction"},
        {"id": "s2", "narration_excerpt":
            "It is the man who turns out to be the mystery"},   # not in audio
        {"id": "s3", "narration_excerpt":
            "Publius Vergilius Maro was born in 70 BC on a farm"},
        {"id": "s4", "narration_excerpt": "That is the story of his hero"},
    ]
    results, _ = align_scenes_to_audio(scenes, words)
    by = {r.scene_id: r for r in results}
    # s3/s4 must still land near their true spots (~20s / ~40s), not be
    # starved to the tail by s2's bogus prefix hit on "it is"
    assert 18 <= by["s3"].start_seconds <= 22
    assert 38 <= by["s4"].start_seconds <= 42


def test_anchor_rejects_equal_start_pileup():
    """Degenerate equal starts must trigger proportional redistribution."""
    plan = ScenePlan(sections={
        "a": [Scene(id="s1", narration_excerpt="ten words " * 5),
              Scene(id="s2", narration_excerpt="ten words " * 5)],
        "b": [Scene(id="s3", narration_excerpt="five words " * 3),
              Scene(id="s4", narration_excerpt="five words " * 3),
              Scene(id="s5", narration_excerpt="five words " * 3)],
    })
    # section b: whisper stacked everything on one timestamp (the incident)
    plan.sections["a"][0].start_seconds = 0.0
    plan.sections["a"][1].start_seconds = 5.0
    for s in plan.sections["b"]:
        s.start_seconds = 46.13
    anchor_scenes_to_sections(plan, [10.0, 30.0])
    b = plan.sections["b"]
    starts = [s.start_seconds for s in b]
    assert starts[0] == 10.0                      # section start owned
    assert starts[1] > starts[0] and starts[2] > starts[1]
    durs = [s.end_seconds - s.start_seconds for s in b]
    assert all(d > 5 for d in durs)               # 30s split three ways
    assert abs(b[-1].end_seconds - 40.0) < 0.01   # tiles the section exactly


def test_anchor_keeps_genuinely_increasing_starts():
    plan = ScenePlan(sections={
        "a": [Scene(id="s1", narration_excerpt="x"),
              Scene(id="s2", narration_excerpt="y")]})
    plan.sections["a"][0].start_seconds = 0.2
    plan.sections["a"][1].start_seconds = 6.4
    anchor_scenes_to_sections(plan, [12.0])
    a = plan.sections["a"]
    assert a[0].start_seconds == 0.0              # first owns the lead-in
    assert a[1].start_seconds == 6.4              # real whisper start kept
    assert abs(a[1].end_seconds - 12.0) < 0.01
