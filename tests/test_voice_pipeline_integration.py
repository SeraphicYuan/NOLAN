"""P1 end-to-end: synthesize_voiceover wires A1 (normalize) + A2 (gate) + A3
(trim/measure/loudnorm) around a FAKE TTS provider (no GPU / omnivoice env)."""

import asyncio
import json
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from nolan import voice_pipeline


def _write(path, samples, fr=24000):
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr)
        w.writeframes(pcm.tobytes())


def _tone(seconds, amp=0.3, fr=24000):
    t = np.arange(int(seconds * fr)) / fr
    return np.sin(2 * np.pi * 220 * t) * amp


class _FakeProvider:
    """Writes a padded tone per item (silent for ids in `silent`)."""
    def __init__(self, silent=()):
        self.items = None
        self.silent = set(silent)

    def synthesize_batch(self, items, out_dir, num_step=None):
        from pathlib import Path
        self.items = items
        out = {}
        for it in items:
            p = Path(out_dir) / f"{it['id']}.wav"
            if it["id"] in self.silent:
                sig = np.zeros(int(2.0 * 24000))
            else:
                pad = np.zeros(int(0.3 * 24000))
                sig = np.concatenate([pad, _tone(2.0), pad])   # 2.6 s, 0.3 s pad each side
            _write(p, sig)
            out[it["id"]] = p
        return out


def _cfg():
    return SimpleNamespace(
        tts=SimpleNamespace(enabled=True,
                            omnivoice=SimpleNamespace(free_comfyui_vram=False)),
        comfyui=SimpleNamespace(host="127.0.0.1", port=8188))


def _project(tmp_path):
    (tmp_path / "script.md").write_text(
        "# Video Script\n**Total Duration:** 0:30\n---\n"
        "## Cold open\nIn 1888, the price rose 90% to $4.2B in profit here.\n\n"
        "## The turn\nA short but clear second beat that runs on for a while here.\n",
        encoding="utf-8")
    return tmp_path


def test_full_pipeline_pass(tmp_path, monkeypatch):
    fake = _FakeProvider()
    monkeypatch.setattr("nolan.tts.create_tts_provider", lambda cfg: fake)
    base = _project(tmp_path)

    res = asyncio.run(voice_pipeline.synthesize_voiceover(
        config=_cfg(), script_project="p", project_dir=base, mode="full"))

    # A1: the synthesis text was normalized (raw script.md untouched)
    txt0 = fake.items[0]["text"]
    assert "eighteen eighty eight" in txt0 and "ninety percent" in txt0
    assert "four point two billion dollars" in txt0
    assert "1888" not in txt0

    # outputs + gate
    assert res["gate"]["ok"] is True
    mp3 = base / "assets" / "voiceover" / "voiceover.mp3"
    assert mp3.exists() and mp3.stat().st_size > 0

    # A3: measure sidecar written; durations trimmed below the padded 2.6 s
    measure = json.loads((base / "assets" / "voiceover" / "voiceover.measure.json")
                         .read_text(encoding="utf-8"))
    assert measure["ok"] is True and len(measure["sections"]) == 2
    for s in measure["sections"]:
        assert s["present"] and 1.9 < s["duration_s"] < 2.4   # ~2.0 s speech + pad


def test_full_pipeline_gate_fails_loud_on_silent_section(tmp_path, monkeypatch):
    fake = _FakeProvider(silent=("sec_0001",))
    monkeypatch.setattr("nolan.tts.create_tts_provider", lambda cfg: fake)
    base = _project(tmp_path)

    with pytest.raises(RuntimeError, match="quality gate"):
        asyncio.run(voice_pipeline.synthesize_voiceover(
            config=_cfg(), script_project="p", project_dir=base, mode="full"))

    # the sidecar is still written (inspectable) and records the failure
    measure = json.loads((base / "assets" / "voiceover" / "voiceover.measure.json")
                         .read_text(encoding="utf-8"))
    assert measure["ok"] is False and measure["errors"] >= 1
    assert any(c["id"] == "silent" for c in measure["checks"])


def test_audio_filter_chain():
    assert voice_pipeline._audio_filter(1.0, False) is None
    assert voice_pipeline._audio_filter(1.0, True) == "loudnorm=I=-16:TP=-2:LRA=11"
    f = voice_pipeline._audio_filter(1.1, True)
    assert f.startswith("atempo=1.100") and "loudnorm" in f
