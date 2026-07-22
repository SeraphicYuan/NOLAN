"""Audio measurement + silence-trim for the voice organ (A3 of the voice program).

Pure stdlib+numpy (no soundfile/ffmpeg) so it is unit-testable without the GPU or
the omnivoice env. Reads PCM wavs (OmniVoice emits mono 24 kHz 16-bit), reports
loudness/peak/clip/duration, and trims leading/trailing silence by SLICING the
original PCM frames (format preserved) — trimming BEFORE durations are read keeps
the "narration owns duration" beat clock honest.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Optional, Tuple

import numpy as np


def _read_mono_float(path) -> Tuple[np.ndarray, int, "wave._wave_params", bytes]:
    """Return (mono float32 in [-1,1], framerate, params, raw_bytes)."""
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        raw = w.readframes(params.nframes)
    sw = params.sampwidth
    if sw == 2:
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    elif sw == 4:
        arr = np.frombuffer(raw, dtype="<i4").astype(np.float64) / 2147483648.0
    elif sw == 1:                                   # 8-bit PCM is unsigned
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported sample width: {sw} bytes")
    if params.nchannels > 1:
        arr = arr.reshape(-1, params.nchannels).mean(axis=1)
    return arr, params.framerate, params, raw


def _dbfs(x: float) -> float:
    return -120.0 if x <= 1e-9 else round(20.0 * math.log10(x), 1)


def wav_stats(path) -> dict:
    """Loudness/peak/clip/duration for one wav. Never raises on a bad/empty file."""
    try:
        mono, fr, params, _ = _read_mono_float(path)
    except Exception:
        return {"rms_dbfs": -120.0, "peak_dbfs": -120.0, "clip_frac": 0.0,
                "duration_s": 0.0, "sample_rate": 0, "ok_read": False}
    n = len(mono)
    dur = round(n / float(fr), 3) if fr else 0.0
    if n == 0:
        return {"rms_dbfs": -120.0, "peak_dbfs": -120.0, "clip_frac": 0.0,
                "duration_s": dur, "sample_rate": fr, "ok_read": True}
    rms = float(np.sqrt(np.mean(mono ** 2)))
    peak = float(np.max(np.abs(mono)))
    clip_frac = float(np.mean(np.abs(mono) >= 0.999))
    return {"rms_dbfs": _dbfs(rms), "peak_dbfs": _dbfs(peak),
            "clip_frac": round(clip_frac, 5), "duration_s": dur,
            "sample_rate": fr, "ok_read": True}


def trim_silence(path, *, threshold_dbfs: float = -45.0, keep_ms: int = 60,
                 min_keep_s: float = 0.2, dst: Optional[Path] = None) -> float:
    """Trim leading/trailing silence below ``threshold_dbfs``, keeping ``keep_ms`` of
    padding. Slices original PCM frames (format preserved). Never trims below
    ``min_keep_s`` and never touches all-silence audio (the gate flags that instead).
    Returns the resulting duration in seconds.
    """
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        raw = w.readframes(params.nframes)
    n, fr = params.nframes, params.framerate
    if n == 0 or fr == 0:
        return 0.0
    mono, _, _, _ = _read_mono_float(path)
    thr = 10.0 ** (threshold_dbfs / 20.0)
    above = np.where(np.abs(mono) >= thr)[0]
    if len(above) == 0:
        return round(n / fr, 3)                     # all silence — leave for the gate
    keep = int(keep_ms / 1000.0 * fr)
    start = max(0, int(above[0]) - keep)
    end = min(n, int(above[-1]) + 1 + keep)
    if (end - start) / float(fr) < min_keep_s:
        return round(n / fr, 3)                      # too aggressive — keep original
    bpf = params.nchannels * params.sampwidth       # bytes per frame
    trimmed = raw[start * bpf:end * bpf]
    out = Path(dst) if dst else Path(path)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(fr)
        w.writeframes(trimmed)
    return round((end - start) / float(fr), 3)
