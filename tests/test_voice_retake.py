"""P2: per-section retake (B2) + take versioning (B3), synthesis via a fake provider."""

import asyncio
import json
import wave
from types import SimpleNamespace

import numpy as np

from nolan import voice_pipeline


def _write(p, samples, fr=24000):
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr); w.writeframes(pcm.tobytes())


def _tone(seconds, amp=0.3, fr=24000):
    t = np.arange(int(seconds * fr)) / fr
    return np.sin(2 * np.pi * 220 * t) * amp


class _Fake:
    def __init__(self, mode="tone"):
        self.mode = mode

    def synthesize_batch(self, items, out_dir, num_step=None):
        from pathlib import Path
        out = {}
        for it in items:
            p = Path(out_dir) / f"{it['id']}.wav"
            sig = (np.zeros(int(2 * 24000)) if self.mode == "silent"
                   else np.concatenate([np.zeros(7200), _tone(2.0), np.zeros(7200)]))
            _write(p, sig)
            out[it["id"]] = p
        return out


def _cfg():
    return SimpleNamespace(
        tts=SimpleNamespace(enabled=True, omnivoice=SimpleNamespace(free_comfyui_vram=False)),
        comfyui=SimpleNamespace(host="127.0.0.1", port=8188))


def _project(tmp_path):
    (tmp_path / "script.md").write_text(
        "# Video Script\n---\n"
        "## Cold open\nFor a century one company quietly controlled the whole supply.\n\n"
        "## The turn\nThen the whole illusion started to crack apart in public.\n",
        encoding="utf-8")
    return tmp_path


# ---------- B3: archive / prune / restore ----------

def test_archive_prune_restore(tmp_path):
    vo = tmp_path / "assets" / "voiceover"
    (vo / "_work").mkdir(parents=True)
    (vo / "voiceover.mp3").write_bytes(b"MP3-v1")
    (vo / "voiceover.measure.json").write_text(json.dumps({"total_s": 10.0}), encoding="utf-8")
    _write(vo / "_work" / "sec_0000.wav", _tone(1.0))

    # pre-seed two OLD take dirs so the prune has something to drop
    for name in ("20200101-000001", "20200101-000002"):
        d = vo / "_takes" / "full" / name
        d.mkdir(parents=True)
        (d / "voiceover.mp3").write_bytes(b"old")

    t1 = voice_pipeline.archive_current_take(vo, keep=2)
    assert t1 and (vo / "_takes" / "full" / t1 / "voiceover.mp3").read_bytes() == b"MP3-v1"
    assert (vo / "_takes" / "full" / t1 / "_work" / "sec_0000.wav").exists()   # anchors archived
    # pruned to the 2 newest (the new take + the later-named old one)
    remaining = {p.name for p in (vo / "_takes" / "full").glob("*/")}
    assert t1 in remaining and "20200101-000001" not in remaining and len(remaining) == 2
    assert voice_pipeline.list_takes(vo)[0]["id"] == t1        # newest first

    # restore brings v1 back after the current mp3 changes
    (vo / "voiceover.mp3").write_bytes(b"MP3-v2")
    assert voice_pipeline.restore_take(vo, t1) is True
    assert (vo / "voiceover.mp3").read_bytes() == b"MP3-v1"

    # nothing to archive when there is no current mp3
    (vo / "voiceover.mp3").unlink()
    assert voice_pipeline.archive_current_take(vo) is None


# ---------- B2: retake ----------

def _synth_initial(base, monkeypatch, mode="tone"):
    monkeypatch.setattr("nolan.tts.create_tts_provider", lambda c: _Fake(mode))
    asyncio.run(voice_pipeline.synthesize_voiceover(
        config=_cfg(), script_project="p", project_dir=base, mode="full"))


def test_retake_accepts_good_take(tmp_path, monkeypatch):
    base = _project(tmp_path)
    _synth_initial(base, monkeypatch)
    vo = base / "assets" / "voiceover"

    r = asyncio.run(voice_pipeline.retake_section(
        config=_cfg(), script_project="p", project_dir=base, index=0))
    assert r["ok"] and r["accepted"]
    assert list((vo / "_takes" / "sec_00").glob("*.wav"))                 # B3 snapshot made
    assert len(list((vo / "_work").glob("sec_*.wav"))) == 2               # count invariant held
    assert (vo / "voiceover.mp3").exists()                               # re-concatenated
    assert r["captions_invalidated"] is False                            # (no captions existed)


def test_retake_rejects_bad_take_keeps_old_audio(tmp_path, monkeypatch):
    base = _project(tmp_path)
    _synth_initial(base, monkeypatch)
    vo = base / "assets" / "voiceover"
    good = (vo / "_work" / "sec_0000.wav").read_bytes()

    monkeypatch.setattr("nolan.tts.create_tts_provider", lambda c: _Fake("silent"))
    r = asyncio.run(voice_pipeline.retake_section(
        config=_cfg(), script_project="p", project_dir=base, index=0))
    assert r["ok"] is False and r["accepted"] is False
    assert (vo / "_work" / "sec_0000.wav").read_bytes() == good           # old take preserved


def test_retake_invalidates_stale_captions(tmp_path, monkeypatch):
    base = _project(tmp_path)
    _synth_initial(base, monkeypatch)
    vo = base / "assets" / "voiceover"
    (vo / "voiceover.srt").write_text("1\n00:00 --> 00:01\nstale\n", encoding="utf-8")

    r = asyncio.run(voice_pipeline.retake_section(
        config=_cfg(), script_project="p", project_dir=base, index=1))
    assert r["accepted"] and r["captions_invalidated"] is True
    assert not (vo / "voiceover.srt").exists()                            # stale captions removed


def test_cli_measure_and_takes(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from nolan.cli import main
    monkeypatch.chdir(tmp_path)
    vo = tmp_path / "projects" / "p" / "assets" / "voiceover"
    vo.mkdir(parents=True)
    (vo / "voiceover.measure.json").write_text(json.dumps({
        "ok": True, "errors": 0, "warnings": 0, "total_s": 12.3,
        "sections": [{"index": 0, "present": True, "duration_s": 6.1, "expected_s": 6.0,
                      "delta_s": 0.1, "rms_dbfs": -18.0, "words": 15}], "checks": []}),
        encoding="utf-8")
    r = CliRunner().invoke(main, ["voiceover", "measure", "p"])
    assert r.exit_code == 0 and "gate ok=True" in r.output and "sec  0" in r.output
    r2 = CliRunner().invoke(main, ["voiceover", "takes", "p"])
    assert r2.exit_code == 0 and "no archived takes" in r2.output
