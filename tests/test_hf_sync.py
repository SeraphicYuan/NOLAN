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
