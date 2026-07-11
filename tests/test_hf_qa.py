"""Tests for nolan.hf_qa — freeze guard + audio integrity (pure logic, probe injected)."""
import json
from pathlib import Path

from nolan.hf_qa import MediaInfo, video_uses, check_freeze, check_render, qa


def _write_spec(tmp: Path, scenes):
    fdir = tmp / "compositions" / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "01-a.spec.json").write_text(
        json.dumps({"frames": [{"id": "01-a", "dur": 30, "scenes": scenes}]}), encoding="utf-8")


def test_video_uses_finds_grounds_and_comparison_sides(tmp_path):
    _write_spec(tmp_path, [
        {"id": "s1", "dur": 10, "type": "statement",
         "data": {"ground": {"kind": "video", "src": "assets/videos/a.mp4"}}},
        {"id": "s2", "dur": 8, "type": "comparison",
         "data": {"left": {"type": "video", "src": "assets/videos/b.mp4"}, "right": {"type": "text"}}},
        {"id": "s3", "dur": 12, "type": "statement", "data": {"ground": {"kind": "image", "src": "assets/x.jpg"}}},
    ])
    uses = video_uses(tmp_path)
    assert len(uses) == 2                                          # image ground is not a video use
    assert {u.src for u in uses} == {"assets/videos/a.mp4", "assets/videos/b.mp4"}
    assert {u.window for u in uses} == {10.0, 8.0}
    assert {u.kind for u in uses} == {"ground", "comparison"}


def test_check_freeze_flags_short_clips(tmp_path):
    _write_spec(tmp_path, [
        {"id": "s1", "dur": 10, "type": "statement", "data": {"ground": {"kind": "video", "src": "assets/videos/a.mp4"}}},
        {"id": "s2", "dur": 8, "type": "comparison", "data": {"left": {"type": "video", "src": "assets/videos/b.mp4"}}},
    ])
    for rel in ("assets/videos/a.mp4", "assets/videos/b.mp4"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    durs = {"a.mp4": 12.0, "b.mp4": 5.0}                           # b (5s) is shorter than its 8s window
    rows = {r["scene"]: r for r in check_freeze(tmp_path, probe_fn=lambda p: MediaInfo(duration=durs[Path(p).name]))}
    assert rows["s1"]["ok"] is True
    assert rows["s2"]["ok"] is False and "freezes" not in rows["s2"]  # (flag captured in report text, ok=False here)
    assert rows["s2"]["clip_dur"] == 5.0 and rows["s2"]["window"] == 8.0


def test_check_render_audio_integrity():
    ok = check_render(Path("x.mp4"), expected_total=100.0,
                      probe_fn=lambda p: MediaInfo(duration=100.0, has_audio=True, audio_duration=100.0))
    assert ok["ok"] is True
    silent = check_render(Path("x.mp4"), probe_fn=lambda p: MediaInfo(duration=100.0, has_audio=False))
    assert silent["ok"] is False
    truncated = check_render(Path("x.mp4"), probe_fn=lambda p: MediaInfo(duration=100.0, has_audio=True, audio_duration=88.0))
    assert truncated["ok"] is False and truncated["audio_matches_video"] is False


def test_qa_passes_when_no_video_and_no_render(tmp_path):
    _write_spec(tmp_path, [{"id": "s1", "dur": 10, "type": "statement", "data": {"lines": ["hi"]}}])
    rep = qa(tmp_path, probe_fn=lambda p: MediaInfo())
    assert rep["overall_pass"] is True and rep["freeze"] == [] and rep["render"] is None
