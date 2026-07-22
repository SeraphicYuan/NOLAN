"""SQLite catalog for the picture library — provenance, dedup, licensing.

One row per stored image: where it came from, its license, dimensions, tags, and
curation status. Dedup is by content hash (sha256 of the file bytes).
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash  TEXT UNIQUE NOT NULL,
    path          TEXT NOT NULL,
    url           TEXT,
    source        TEXT,
    source_url    TEXT,
    license       TEXT,
    title         TEXT,
    description   TEXT,
    width         INTEGER,
    height        INTEGER,
    bytes         INTEGER,
    tags          TEXT,
    query         TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    added_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assets_status  ON assets(status);
CREATE INDEX IF NOT EXISTS idx_assets_source  ON assets(source);
"""


@dataclass
class Asset:
    content_hash: str
    path: str
    url: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    license: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    bytes: Optional[int] = None
    tags: Optional[str] = None
    query: Optional[str] = None
    status: str = "active"
    added_at: Optional[str] = None
    id: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


class AssetCatalog:
    """SQLite store for picture-library assets."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + a lock: the library is used from worker-thread
        # pools (e.g. match-broll). All access is serialized through self._lock.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            # Migrate older DBs created before the description column existed.
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(assets)")}
            if "description" not in cols:
                self._conn.execute("ALTER TABLE assets ADD COLUMN description TEXT")
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ writes
    def add(self, asset: Asset) -> Asset:
        """Insert an asset; if its content_hash already exists, return that row."""
        existing = self.get_by_hash(asset.content_hash)
        if existing:
            return existing
        asset.added_at = asset.added_at or datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO assets
                   (content_hash, path, url, source, source_url, license, title,
                    description, width, height, bytes, tags, query, status, added_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (asset.content_hash, asset.path, asset.url, asset.source,
                 asset.source_url, asset.license, asset.title, asset.description,
                 asset.width, asset.height, asset.bytes, asset.tags, asset.query,
                 asset.status, asset.added_at),
            )
            self._conn.commit()
        asset.id = cur.lastrowid
        return asset

    def set_status(self, asset_id: int, status: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE assets SET status=? WHERE id=?", (status, asset_id))
            self._conn.commit()

    def delete(self, asset_id: int) -> None:
        """Hard-remove a row — frees its content-hash so re-adding the SAME bytes creates a fresh asset.
        A re-ingest/refresh needs this: set_status('deleted') keeps the row, and get_by_hash still finds it,
        so identical re-captured bytes would silently dedup back to the stale (deleted) asset."""
        with self._lock:
            self._conn.execute("DELETE FROM assets WHERE id=?", (asset_id,))
            self._conn.commit()

    def set_description(self, asset_id: int, description: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE assets SET description=? WHERE id=?",
                               (description, asset_id))
            self._conn.commit()

    # ------------------------------------------------------------------ reads
    def _row(self, row: sqlite3.Row) -> Asset:
        return Asset(**{k: row[k] for k in row.keys()})

    def get(self, asset_id: int) -> Optional[Asset]:
        with self._lock:
            r = self._conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
        return self._row(r) if r else None

    def get_by_hash(self, content_hash: str) -> Optional[Asset]:
        with self._lock:
            r = self._conn.execute("SELECT * FROM assets WHERE content_hash=?",
                                   (content_hash,)).fetchone()
        return self._row(r) if r else None

    def get_many(self, ids: List[int]) -> dict:
        """Return {id: Asset} for the given ids (order not guaranteed)."""
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM assets WHERE id IN ({marks})", ids).fetchall()
        return {r["id"]: self._row(r) for r in rows}

    def list(self, *, status: Optional[str] = "active", source: Optional[str] = None,
             license_contains: Optional[str] = None, limit: Optional[int] = None
             ) -> List[Asset]:
        sql = "SELECT * FROM assets WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status=?"; params.append(status)
        if source:
            sql += " AND source=?"; params.append(source)
        if license_contains:
            sql += " AND license LIKE ?"; params.append(f"%{license_contains}%")
        sql += " ORDER BY id DESC"
        if limit:
            sql += " LIMIT ?"; params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row(r) for r in rows]

    def count(self, status: Optional[str] = None) -> int:
        with self._lock:
            if status:
                r = self._conn.execute("SELECT COUNT(*) c FROM assets WHERE status=?", (status,))
            else:
                r = self._conn.execute("SELECT COUNT(*) c FROM assets")
            return r.fetchone()["c"]
