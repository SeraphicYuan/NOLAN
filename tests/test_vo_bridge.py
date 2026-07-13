"""Honesty tests for the NOLAN->HyperFrames voiceover bridge (bridge/vo_bridge.py).

Asserts the translator emits the exact `audio_meta.json` shape the faceless chain consumes
(voices[{frame,path,duration_s,words}]), 1:1 section->frame, durations matched to the wavs,
files copied — from both the mode='full' (_work/sec_*.wav) and mode='segments' layouts.
"""
import importlib.util
import json
import wave
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VO_BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge" / "vo_bridge.py"


def _load():
    spec = importlib.util.spec_from_file_location("vo_bridge", VO_BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wav(path: Path, secs: float, sr: int = 8000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * int(sr * secs))


def test_translate_from_work_layout(tmp_path):
    vo = tmp_path / "proj"
    work = vo / "assets" / "voiceover" / "_work"
    _wav(work / "sec_0000.wav", 2.0)
    _wav(work / "sec_0001.wav", 3.0)
    (vo / "assets" / "voiceover" / "voiceover.mp3").write_bytes(b"ID3fakeaudition")
    comp = tmp_path / "comp"

    vb = _load()
    res = vb.translate(comp, vo)                      # pass the PROJECT dir
    assert res["sections"] == 2 and res["frames_expected"] == 2

    meta = json.loads((comp / "audio_meta.json").read_text(encoding="utf-8"))
    assert meta["bgm"] is None and meta["sfx"] == []
    assert [v["frame"] for v in meta["voices"]] == [1, 2]          # 1:1, 1-based
    assert [v["path"] for v in meta["voices"]] == ["assets/voice/01.wav", "assets/voice/02.wav"]
    assert abs(meta["voices"][0]["duration_s"] - 2.0) < 0.05
    assert abs(meta["voices"][1]["duration_s"] - 3.0) < 0.05
    assert abs(meta["total_s"] - 5.0) < 0.05
    assert (comp / "assets" / "voice" / "01.wav").is_file()
    assert (comp / "assets" / "voice" / "02.wav").is_file()
    assert (comp / "assets" / "voice" / "voiceover.mp3").is_file()  # audition copy


def test_translate_from_segments_layout_with_words(tmp_path):
    vo = tmp_path / "proj" / "assets" / "voiceover"
    seg = vo / "segments"
    _wav(seg / "00_hook.wav", 1.5)
    _wav(seg / "01_close.wav", 2.5)
    seg.joinpath("segments.json").write_text(json.dumps([
        {"index": 0, "title": "Hook", "file": "00_hook.wav", "duration": 1.5},
        {"index": 1, "title": "Close", "file": "01_close.wav", "duration": 2.5},
    ]), encoding="utf-8")
    seg.joinpath("01_close.words.json").write_text(
        json.dumps([{"id": 0, "text": "hi", "start": 0.0, "end": 0.3}]), encoding="utf-8")
    comp = tmp_path / "comp"

    vb = _load()
    vb.translate(comp, tmp_path / "proj")            # project dir resolves to assets/voiceover
    meta = json.loads((comp / "audio_meta.json").read_text(encoding="utf-8"))
    assert [v["title"] for v in meta["voices"]] == ["Hook", "Close"]
    assert meta["voices"][1]["words"] == [{"id": 0, "text": "hi", "start": 0.0, "end": 0.3}]
    assert meta["voices"][0]["words"] == []          # no words.json for the hook -> empty


def test_translate_from_segments_dict_shape(tmp_path):
    """voice_pipeline emits segments.json as a DICT {project, voice_id, segments:[...]}, not a bare
    list. Before the unwrap fix this raised `TypeError: string indices must be integers` on the first
    `s["file"]` (iterating a dict yields its string keys) — which blocked bridging EVERY real NOLAN VO.
    """
    vo = tmp_path / "proj" / "assets" / "voiceover"
    seg = vo / "segments"
    _wav(seg / "00_hook.wav", 1.5)
    _wav(seg / "01_close.wav", 2.5)
    seg.joinpath("segments.json").write_text(json.dumps({
        "project": "demo", "voice_id": "abc123",
        "segments": [
            {"index": 0, "title": "Hook", "file": "00_hook.wav", "duration": 1.5},
            {"index": 1, "title": "Close", "file": "01_close.wav", "duration": 2.5},
        ],
    }), encoding="utf-8")
    comp = tmp_path / "comp"

    vb = _load()
    res = vb.translate(comp, tmp_path / "proj")          # must not raise on the real dict shape
    assert res["sections"] == 2 and res["frames_expected"] == 2
    meta = json.loads((comp / "audio_meta.json").read_text(encoding="utf-8"))
    assert [v["frame"] for v in meta["voices"]] == [1, 2]
    assert [v["title"] for v in meta["voices"]] == ["Hook", "Close"]
    assert abs(meta["total_s"] - 4.0) < 0.05


def test_resolve_vo_dir_accepts_project_or_voiceover_dir(tmp_path):
    vb = _load()
    (tmp_path / "assets" / "voiceover" / "_work").mkdir(parents=True)
    assert vb._resolve_vo_dir(tmp_path).name == "voiceover"                      # project dir
    assert vb._resolve_vo_dir(tmp_path / "assets" / "voiceover").name == "voiceover"  # vo dir


def test_missing_voiceover_raises(tmp_path):
    vb = _load()
    with pytest.raises(FileNotFoundError):
        vb.translate(tmp_path / "comp", tmp_path / "empty")
