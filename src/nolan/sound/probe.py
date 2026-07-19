"""Audio silence/onset probing — so a curated SFX places precisely.

Some source sounds carry LEADING SILENCE (dead air before the actual sound).
Dropped at a cue time as-is, the sound then fires late. `analyze_silence`
measures the leading (and trailing) silence + the onset; the ingest path trims
leading silence by default so every curated one-shot starts at t≈0, and records
what it found. `nolan sfx doctor` re-scans the bank to flag any file whose sound
still doesn't start at zero.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, Optional


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _duration_from_log(log: str) -> Optional[float]:
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", log)
    if not m:
        return None
    h, mm, ss = m.groups()
    return int(h) * 3600 + int(mm) * 60 + float(ss)


def analyze_silence(path, noise_db: float = -45.0, min_sil: float = 0.05) -> Dict[str, float]:
    """Measure leading/trailing silence + onset for an audio file.

    Uses ffmpeg ``silencedetect`` (a silence run = level below ``noise_db`` for
    at least ``min_sil`` s). Returns seconds:
      duration · lead_silence_s (onset) · trail_silence_s · is_silent (bool).
    Leading silence = a silence run that begins at ~0; its end is the onset.
    """
    ff = _ffmpeg()
    r = subprocess.run(
        [ff, "-i", str(path), "-af",
         f"silencedetect=noise={noise_db}dB:d={min_sil}", "-f", "null", "-"],
        capture_output=True, text=True)
    log = r.stderr or ""
    dur = _duration_from_log(log) or 0.0
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", log)]

    lead = 0.0
    if starts and starts[0] <= min_sil + 0.02 and ends:
        lead = ends[0]                       # first run starts at ~0 → onset
    trail = 0.0
    if starts:
        if len(ends) < len(starts):          # last run has no end → runs to EOF
            trail = max(0.0, dur - starts[-1])
        elif ends and dur and abs(ends[-1] - dur) < 0.05:
            trail = max(0.0, dur - starts[-1])
    is_silent = bool(dur) and lead >= dur - 0.03
    return {"duration": round(dur, 3), "lead_silence_s": round(lead, 3),
            "trail_silence_s": round(trail, 3), "is_silent": is_silent}


def normalize_cmd(src: str, dest: str, *, trim_lead: bool = True,
                  noise_db: float = -45.0, sample_rate: int = 48000,
                  channels: int = 2) -> list:
    """ffmpeg argv: 48 kHz stereo, optionally stripping leading silence.

    ``silenceremove`` with ``start_periods=1`` removes only the leading silent
    run — so a one-shot begins at t=0. Beds/risers whose quiet lead-in is
    intentional pass ``trim_lead=False``.
    """
    af = []
    if trim_lead:
        af.append(f"silenceremove=start_periods=1:start_threshold={noise_db}dB:start_silence=0")
    cmd = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    if af:
        cmd += ["-af", ",".join(af)]
    cmd += ["-ar", str(sample_rate), "-ac", str(channels), str(dest)]
    return cmd
