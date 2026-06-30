"""Explainer flow tenant — paper / article -> video. Two ingest modes (registry.json):

- **byo-script** — `INGEST`: assemble an authored chapter spec (steps + anchors +
  word-timestamps) into the render job. Logic in flows/ingest.py::ingest_explainer.
- **generate-from-source** — `PREPARE` (figure_catalog / extract_figure / synthesize_segments /
  word_timestamps in flows/source.py) turns a source paper into the spec's input assets; the
  agent authors the spec between (the skill part); then `INGEST` assembles. The deterministic
  asset-prep is promoted here; the spec-authoring stays a skill handoff.
"""
from __future__ import annotations

from pathlib import Path

from . import source

# generate-from-source asset-prep surface (deterministic half; agent authors the spec between)
PREPARE = {
    "figure_catalog": source.figure_catalog,        # paper -> figures to choose from
    "extract_figure": source.extract_figure,        # lift one figure -> trimmed png
    "synthesize_segments": source.synthesize_segments,  # script -> narration wavs (OmniVoice)
    "word_timestamps": source.word_timestamps,      # wavs -> wordsCache (Whisper)
}


def INGEST(spec_path: Path, job_path: Path) -> None:
    """(spec_path, job_path) -> writes job_path (in-process; anchors -> frames)."""
    from .ingest import ingest_explainer
    ingest_explainer(spec_path, job_path)
