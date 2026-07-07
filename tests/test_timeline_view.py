"""Timeline view (P2) — the scene plan derived onto a time axis.

Derived only (no storage); sections span the sec_*.wav durations (narration
owns duration); motion badges distinguish AUTHORED (motion_spec/layout/motif/
recipe/clip) from DERIVED (the same still-treatment pre-pass premium runs);
sfx cues become markers at absolute time; the VO envelope is normalized 0..1.
"""

import json
import math
import struct
import wave
from pathlib import Path

import pytest

from nolan.timeline_view import build_timeline


def _write_wav(path: Path, seconds: float, freq: float = 220.0,
               amp: float = 0.5, sr: int = 16000):
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(seconds * sr)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = b"".join(
            struct.pack("<h", int(amp * 32000 * math.sin(2 * math.pi * freq
                                                         * i / sr)))
            for i in range(n))
        w.writeframes(frames)


def _proj(tmp_path, scenes_by_section, wav_secs=(4.0, 3.0)):
    plan = {"sections": scenes_by_section, "meta": {}}
    (tmp_path / "scene_plan.json").write_text(json.dumps(plan),
                                              encoding="utf-8")
    for i, s in enumerate(wav_secs):
        _write_wav(tmp_path / "assets" / "voiceover" / "_work"
                   / f"sec_{i:04d}.wav", s)
    return tmp_path


def test_sections_span_wav_durations(tmp_path):
    tl = build_timeline(_proj(tmp_path, {"a": [], "b": []}))
    assert tl["duration"] == pytest.approx(7.0, abs=0.01)
    assert tl["sections"][0]["start"] == 0.0
    assert tl["sections"][0]["end"] == pytest.approx(4.0, abs=0.01)
    assert tl["sections"][1]["start"] == pytest.approx(4.0, abs=0.01)
    assert tl["sections"][0]["name"] == "a"
    assert tl["has_narration"] is True


def test_motion_badges_authored_vs_derived(tmp_path):
    scenes = {"a": [
        {"id": "s1", "start_seconds": 0.0, "end_seconds": 2.0,
         "matched_asset": "assets/art/x.jpg",
         "narration_excerpt": "this is the man himself"},
        {"id": "s2", "start_seconds": 2.0, "end_seconds": 4.0,
         "motion_spec": {"effect": "stat-over", "content": {}}},
        {"id": "s3", "start_seconds": 4.0, "end_seconds": 6.0,
         "matched_clip": {"video_path": "lib/v.mp4", "clip_start": 1.0}},
    ]}
    tl = build_timeline(_proj(tmp_path, scenes))
    by = {u["scene_id"]: u for u in tl["units"]}
    # a plain still gets the SAME pre-pass premium runs -> derived badge
    assert by["s1"]["motion"]["source"] == "derived"
    assert by["s1"]["motion"]["badge"].startswith("kenburns")
    assert by["s2"]["motion"] == {"badge": "stat-over", "source": "authored"}
    assert by["s3"]["motion"] == {"badge": "clip", "source": "authored"}
    assert by["s3"]["kind"] == "clip"
    assert by["s1"]["media"] == "x.jpg"


def test_sfx_markers_at_absolute_time(tmp_path):
    scenes = {"a": [
        {"id": "s1", "start_seconds": 10.0, "end_seconds": 14.0,
         "matched_asset": "assets/art/x.jpg",
         "sfx": {"query": "fire crackling", "at": 1.5, "volume": 0.22}},
    ]}
    tl = build_timeline(_proj(tmp_path, scenes))
    assert tl["sfx"] == [{"t": 11.5, "scene_id": "s1",
                          "label": "fire crackling", "volume": 0.22}]


def test_vo_envelope_normalized(tmp_path):
    tl = build_timeline(_proj(tmp_path, {"a": []}, wav_secs=(2.0,)))
    peaks = tl["vo"]["peaks"]
    assert len(peaks) == pytest.approx(2.0 * tl["vo"]["rate"], abs=1)
    assert max(peaks) == 1.0 and min(peaks) >= 0.0


def test_derived_badges_never_written_to_plan(tmp_path):
    p = _proj(tmp_path, {"a": [
        {"id": "s1", "start_seconds": 0.0, "end_seconds": 2.0,
         "matched_asset": "assets/art/x.jpg"}]})
    build_timeline(p)
    plan = json.loads((p / "scene_plan.json").read_text(encoding="utf-8"))
    assert "_still_treatment" not in json.dumps(plan)


def test_no_plan_is_loud(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_timeline(tmp_path)
