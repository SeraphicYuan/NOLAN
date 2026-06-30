"""Art flow tenant — `byo-everything` ingest (assemble, don't generate).

The art ingest is light by design: the script + voiceover (already word-timestamped in
NOLAN's TTS page) + images already exist, so this just reads the project's segments + the
authored art-spec (focuses/regions/labels/images) and writes the render job. No TTS, no
Whisper. The heavy `extract_figure + TTS + Whisper + gen_spec` path is the *explainer*
tenant's ingest (added when that flow is promoted).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WVL = Path(__file__).resolve().parents[3] / "web-video-lab"


def INGEST(spec_path: Path, job_path: Path) -> None:
    """(spec_path, job_path) -> writes job_path. Wraps web-video-lab/art_ingest.py."""
    rc = subprocess.run([sys.executable, str(WVL / "art_ingest.py"),
                         str(spec_path), str(job_path)]).returncode
    if rc != 0:
        raise RuntimeError(f"art ingest failed for {spec_path.name}")
