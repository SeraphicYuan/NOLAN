"""A2 + A3: voiceover quality gate + audio measurement/trim (synthesis-free)."""

import wave

import numpy as np

from nolan.voice_audio import wav_stats, trim_silence
from nolan.voice_gate import gate_voiceover


def _write(path, samples, fr=24000):
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fr)
        w.writeframes(pcm.tobytes())


def _tone(seconds, amp=0.3, freq=220, fr=24000):
    t = np.arange(int(seconds * fr)) / fr
    return np.sin(2 * np.pi * freq * t) * amp


# ---------- A3: measurement ----------

def test_wav_stats_tone(tmp_path):
    p = tmp_path / "tone.wav"
    _write(p, _tone(1.0, amp=0.3))
    st = wav_stats(p)
    assert abs(st["duration_s"] - 1.0) < 0.01
    assert st["sample_rate"] == 24000
    assert -15 < st["rms_dbfs"] < -11      # 0.3 sine ≈ -13.5 dBFS
    assert st["clip_frac"] == 0.0


def test_wav_stats_silence(tmp_path):
    p = tmp_path / "sil.wav"
    _write(p, np.zeros(24000))
    st = wav_stats(p)
    assert st["rms_dbfs"] <= -119 and abs(st["duration_s"] - 1.0) < 0.01


def test_wav_stats_clipped(tmp_path):
    p = tmp_path / "clip.wav"
    _write(p, _tone(1.0, amp=5.0))          # overdriven → clamped to ±1
    st = wav_stats(p)
    assert st["clip_frac"] > 0.01


# ---------- A3: trim ----------

def test_trim_silence_removes_pad(tmp_path):
    p = tmp_path / "padded.wav"
    sig = np.concatenate([np.zeros(int(0.3 * 24000)), _tone(0.5), np.zeros(int(0.3 * 24000))])
    _write(p, sig)                          # 1.1 s total
    new_dur = trim_silence(p, keep_ms=60)
    assert 0.5 < new_dur < 0.75             # ≈ 0.5 speech + 2×60 ms pad
    assert abs(wav_stats(p)["duration_s"] - new_dur) < 0.01


def test_trim_silence_keeps_all_silence(tmp_path):
    p = tmp_path / "allsil.wav"
    _write(p, np.zeros(int(0.8 * 24000)))
    assert abs(trim_silence(p) - 0.8) < 0.01   # untouched — the gate will flag it


# ---------- A2: gate ----------

def _sections(*word_counts):
    return [{"title": f"s{i}", "body": " ".join(["word"] * n)} for i, n in enumerate(word_counts)]


def test_gate_pass(tmp_path):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    _write(a, _tone(1.0)); _write(b, _tone(1.2))
    rep = gate_voiceover(_sections(3, 3), [a, b])
    assert rep.ok and not [c for c in rep.checks if c.level == "error"]
    assert len(rep.sections) == 2 and rep.sections[0]["present"]


def test_gate_missing_section(tmp_path):
    a = tmp_path / "a.wav"
    _write(a, _tone(1.0))
    rep = gate_voiceover(_sections(3, 3), [a, None])
    assert not rep.ok
    ids = {c.id for c in rep.checks}
    assert "count" in ids and "present" in ids


def test_gate_silent_section(tmp_path):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    _write(a, _tone(1.0)); _write(b, np.zeros(24000))
    rep = gate_voiceover(_sections(3, 3), [a, b])
    assert not rep.ok and any(c.id == "silent" for c in rep.checks)


def test_gate_too_short(tmp_path):
    a = tmp_path / "a.wav"
    _write(a, _tone(0.5))                    # 0.5 s for a ~20-word (8 s) section
    rep = gate_voiceover(_sections(20), [a])
    assert not rep.ok and any(c.id == "too_short" for c in rep.checks)


def test_gate_clipped_is_warn_not_fail(tmp_path):
    a = tmp_path / "a.wav"
    _write(a, _tone(1.0, amp=5.0))
    rep = gate_voiceover(_sections(3), [a])
    assert rep.ok                            # clipping warns, does not fail the gate
    assert any(c.id == "clipped" and c.level == "warn" for c in rep.checks)
