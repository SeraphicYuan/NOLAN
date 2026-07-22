"""Document source registry — the paper analogue of data/registry.py.

A comp keeps ingested documents under `<comp>/documents/`: an `index.json` of metadata + one dir per
document (`<id>/layout.json` + `pages/*.png`). `load_document` is PROVENANCE-GATED: a document with no
provenance is a fabrication risk (the same principle as the A-P1 number gate — a REAL region must trace to a
REAL source), so loading one raises. `region_bbox` resolves a region/word id → its normalized bbox, the hook
region targeting (B-P2) builds on.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


def _documents_dir(comp) -> Path:
    """`<comp>/documents/`. `comp` may be a comp dir Path or a videos/<slug> id resolved against the lab."""
    p = Path(comp)
    if p.is_dir() and (p / "documents").exists():
        return p / "documents"
    if p.is_dir():
        return p / "documents"
    # a bare id → resolve against the compose-first lab videos dir (parents: document→nolan→src→REPO)
    lab = Path(__file__).resolve().parents[3] / "render-service" / "_lab_hyperframes" / "videos"
    return lab / str(comp) / "documents"


@dataclass
class Document:
    id: str
    dir: Path
    meta: Dict = field(default_factory=dict)

    @property
    def pages(self) -> List[Dict]:
        return self.meta.get("pages", [])

    @property
    def provenance(self) -> str:
        return self.meta.get("provenance", "")

    def page(self, n: int) -> Optional[Dict]:
        return next((p for p in self.pages if p.get("page") == n), None)

    def image_path(self, n: int) -> Optional[Path]:
        p = self.page(n)
        return (self.dir / p["image"]) if p and p.get("image") else None


def load_document(comp, doc_id: str) -> Optional[Document]:
    """Load an ingested document by id (provenance-gated: raises on an un-sourced document). None if it was
    never ingested (caller decides — a document reference with no ingest is not a silent pass)."""
    ddir = _documents_dir(comp) / doc_id
    lm = ddir / "layout.json"
    if not lm.exists():
        return None
    meta = json.loads(lm.read_text(encoding="utf-8"))
    if not meta.get("provenance"):
        raise ValueError(f"document {doc_id!r} has no provenance — an un-sourced document is a fabrication "
                         f"risk (re-ingest it so it traces to a real PDF).")
    return Document(doc_id, ddir, meta)


def list_documents(comp) -> List[Dict]:
    idx = _documents_dir(comp) / "index.json"
    if not idx.exists():
        return []
    try:
        return json.loads(idx.read_text(encoding="utf-8")).get("documents", [])
    except (json.JSONDecodeError, OSError):
        return []


def region_bbox(doc: Document, page: int, region_id: str) -> Optional[List[float]]:
    """The NORMALIZED bbox of a region OR word id on a page — the hook region targeting (B-P2) resolves for
    pan/zoom/highlight. None if the id isn't on that page."""
    p = doc.page(page)
    if not p:
        return None
    for r in p.get("regions", []) + p.get("words", []):
        if r.get("id") == region_id:
            return r.get("bbox")
    return None
