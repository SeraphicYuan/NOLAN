"""NOLAN knowledge base — a video-craft KB backed by an Obsidian vault.

Markdown-first: the vault .md files (E:\\Nolan_KB\\Nolan_KB) are canonical;
SQLite + Chroma are derived indices rebuilt from the files. Both a human (in
Obsidian) and the agent (via the retrieval API) read the same notes.

Pipeline: ingest (url/youtube/file/text -> raw/*.md) -> distill (LLM -> parsed
insight notes) -> index (BGE + keyword) -> link (related notes + MOCs).
"""
from __future__ import annotations

from . import paths  # noqa: F401
from .catalog import KBCatalog, Source  # noqa: F401
from .ingest import ingest, IngestResult  # noqa: F401

__all__ = ["paths", "KBCatalog", "Source", "ingest", "IngestResult"]
