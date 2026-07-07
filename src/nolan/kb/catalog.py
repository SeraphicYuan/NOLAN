"""SQLite catalog for KB sources — a derived index over the vault.

The markdown files are canonical; this catalog caches source metadata for fast
listing, dedup, and status tracking. Dedup is by content hash so re-ingesting
the same URL/video is idempotent. Modelled on nolan.imagelib.catalog.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id           TEXT PRIMARY KEY,   -- content hash (idempotent ingest)
    source_type  TEXT NOT NULL,      -- youtube | article | file | text
    title        TEXT,
    url          TEXT,
    author       TEXT,               -- channel / author
    published    TEXT,
    ingested_at  REAL,
    raw_path     TEXT,               -- POSIX path relative to VAULT
    char_count   INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'raw', -- raw | distilled
    meta         TEXT                -- json blob
);
CREATE INDEX IF NOT EXISTS idx_sources_url ON sources(url);
CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
"""


@dataclass
class Source:
    id: str
    source_type: str
    title: str = ""
    url: str = ""
    author: str = ""
    published: str = ""
    ingested_at: float = 0.0
    raw_path: str = ""
    char_count: int = 0
    status: str = "raw"
    meta: dict = field(default_factory=dict)


class KBCatalog:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or paths.DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- reads ---
    def _row(self, row) -> Source:
        d = dict(row)
        d["meta"] = json.loads(d.get("meta") or "{}")
        return Source(**d)

    def get(self, source_id: str) -> Optional[Source]:
        r = self._conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        return self._row(r) if r else None

    def get_by_url(self, url: str) -> Optional[Source]:
        if not url:
            return None
        r = self._conn.execute("SELECT * FROM sources WHERE url=? LIMIT 1", (url,)).fetchone()
        return self._row(r) if r else None

    def list(self, status: Optional[str] = None, source_type: Optional[str] = None,
             limit: int = 500) -> List[Source]:
        q, args = "SELECT * FROM sources", []
        where = []
        if status:
            where.append("status=?"); args.append(status)
        if source_type:
            where.append("source_type=?"); args.append(source_type)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY ingested_at DESC LIMIT ?"; args.append(limit)
        return [self._row(r) for r in self._conn.execute(q, args).fetchall()]

    def count(self, status: Optional[str] = None) -> int:
        if status:
            return self._conn.execute("SELECT COUNT(*) FROM sources WHERE status=?", (status,)).fetchone()[0]
        return self._conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]

    # --- writes ---
    def upsert(self, s: Source) -> None:
        self._conn.execute(
            """INSERT INTO sources (id, source_type, title, url, author, published,
                   ingested_at, raw_path, char_count, status, meta)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   title=excluded.title, url=excluded.url, author=excluded.author,
                   published=excluded.published, raw_path=excluded.raw_path,
                   char_count=excluded.char_count, status=excluded.status, meta=excluded.meta""",
            (s.id, s.source_type, s.title, s.url, s.author, s.published,
             s.ingested_at or time.time(), s.raw_path, s.char_count, s.status,
             json.dumps(s.meta or {}, ensure_ascii=False)),
        )
        self._conn.commit()

    def set_status(self, source_id: str, status: str) -> None:
        self._conn.execute("UPDATE sources SET status=? WHERE id=?", (status, source_id))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
