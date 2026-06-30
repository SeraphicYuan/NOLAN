"""Art flow tenant — `byo-everything` ingest (assemble, don't generate).

The art ingest is light: script + voiceover (already word-timestamped) + images already exist
in the project, so it reads the project's segments + the authored art-spec and writes the render
job. No TTS, no Whisper. The heavy generate-from-source path is the *explainer* tenant's ingest.
Logic lives in `flows/ingest.py`; this tenant just names it as the art flow's INGEST.
"""
from __future__ import annotations

from pathlib import Path


def INGEST(spec_path: Path, job_path: Path) -> None:
    """(spec_path, job_path) -> writes job_path (in-process; assemble byo-everything)."""
    from .ingest import ingest_art
    ingest_art(spec_path, job_path)
