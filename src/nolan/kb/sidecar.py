"""Structured per-source distillation record — the machine-readable twin of the
human `.md` notes.

The vault `.md` files are canonical for reading/editing in Obsidian, but parsing
their prose bodies back into fields is fragile. So distillation also writes a
JSON sidecar per source at ``_kb_data/insights/<source_id>.json`` holding the full
structured distillation (TLDR, source quality, and every insight with all fields
+ its note id/path). This sidecar is the reliable **rebuild source** for the
derived index (SQLite insights table + FTS + Chroma): ``kb reindex`` reads
sidecars, never re-parses `.md` and never re-calls the LLM.

Modelled on HERMES's ``InsightsStore`` (insights.json cache next to report.md).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, List, Optional

from . import paths


def path_for(source_id: str) -> Path:
    return paths.SIDECARS / f"{source_id}.json"


def write(record: dict) -> Path:
    paths.SIDECARS.mkdir(parents=True, exist_ok=True)
    p = path_for(record["source_id"])
    p.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load(source_id: str) -> Optional[dict]:
    p = path_for(source_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def delete(source_id: str) -> None:
    p = path_for(source_id)
    if p.exists():
        p.unlink()


def iter_all() -> Iterator[dict]:
    """Yield every stored sidecar record (for a full reindex)."""
    if not paths.SIDECARS.exists():
        return
    for p in sorted(paths.SIDECARS.glob("*.json")):
        try:
            yield json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue


def list_ids() -> List[str]:
    if not paths.SIDECARS.exists():
        return []
    return [p.stem for p in paths.SIDECARS.glob("*.json")]
