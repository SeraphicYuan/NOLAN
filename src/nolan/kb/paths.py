"""Filesystem layout for the NOLAN knowledge base.

Markdown-first: everything under VAULT is canonical Obsidian content. Binaries
(PDFs) and the derived index (SQLite + Chroma) live OUTSIDE the vault, under a
sibling ``_kb_data`` dir, so Obsidian stays clean and fast.

Override the vault root for tests via env ``NOLAN_KB_VAULT``.
"""
from __future__ import annotations

import os
from pathlib import Path

VAULT = Path(os.environ.get("NOLAN_KB_VAULT", r"E:\Nolan_KB\Nolan_KB"))

# --- in-vault (browsable + linkable in Obsidian) ---
RAW = VAULT / "raw"
PARSED = VAULT / "parsed"
INSIGHTS = PARSED / "insights"
MOCS = VAULT / "MOCs"

# --- outside the vault (not Obsidian content) ---
DATA = VAULT.parent / "_kb_data"
BINARIES = DATA / "binaries"       # PDFs / uploaded originals
DB = DATA / "kb.db"                # derived SQLite catalog + insight index
CHROMA = DATA / "chroma"           # derived vector store
SIDECARS = DATA / "insights"       # structured per-source distillation JSON (reindex source of truth)

# raw sub-folders by source medium
RAW_TYPES = ("youtube", "article", "file", "text")


def ensure_dirs() -> None:
    """Create the vault + data directory tree (idempotent)."""
    for d in (RAW, PARSED, INSIGHTS, MOCS, DATA, BINARIES, CHROMA, SIDECARS):
        d.mkdir(parents=True, exist_ok=True)
    for t in RAW_TYPES:
        (RAW / t).mkdir(parents=True, exist_ok=True)
