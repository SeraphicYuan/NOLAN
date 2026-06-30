"""Explainer flow tenant — paper / article -> video.

Byo-script ingest: assemble a generated chapter spec (steps + anchors + word-timestamps) into
the render job. The full generate-from-source mode (extract_figure + OmniVoice TTS + Whisper
word-align, which wrap NOLAN's own modules) feeds the same spec and is added as that ingest
matures. Logic lives in flows/ingest.py::ingest_explainer; this tenant just names it.
"""
from __future__ import annotations

from pathlib import Path


def INGEST(spec_path: Path, job_path: Path) -> None:
    """(spec_path, job_path) -> writes job_path (in-process; anchors -> frames)."""
    from .ingest import ingest_explainer
    ingest_explainer(spec_path, job_path)
