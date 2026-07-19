"""SQLite catalog of crawled SFX candidates — a reusable local index.

One row per external sound (keyed by provider + ext_id, e.g. freesound/60013):
its metadata + preview link + whether it's been curated into our bank
(`in_library`, `library_kind`, `library_file`, `rating`). The crawl upserts
into this (idempotent, refreshing download counts); curation flips `in_library`.

Its future value: query the LOCAL catalog for the right SFX instead of hitting
the website every time. Full-text search over name/description/tags via FTS5
(falls back to LIKE if the sqlite build lacks FTS5). Mirrors imagelib/catalog.py.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[3]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sounds (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    provider      TEXT NOT NULL DEFAULT 'freesound',
    ext_id        TEXT NOT NULL,
    name          TEXT,
    description   TEXT,
    tags          TEXT,
    license       TEXT,
    type          TEXT,
    duration      REAL,
    filesize      INTEGER,
    num_downloads INTEGER,
    username      TEXT,
    page_url      TEXT,
    preview_url   TEXT,
    in_library    INTEGER NOT NULL DEFAULT 0,
    library_kind  TEXT,
    library_file  TEXT,
    rating        INTEGER,
    lead_silence_s REAL,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    UNIQUE(provider, ext_id)
);
CREATE INDEX IF NOT EXISTS idx_sounds_downloads ON sounds(num_downloads DESC);
CREATE INDEX IF NOT EXISTS idx_sounds_inlib     ON sounds(in_library);
CREATE INDEX IF NOT EXISTS idx_sounds_license   ON sounds(license);
"""


def default_db_path() -> Path:
    return _REPO / "projects" / "_library" / "sfx" / "catalog.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SoundCatalog:
    """SQLite store for crawled SFX candidates + curation status."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            # migrate DBs created before lead_silence_s existed
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(sounds)")}
            if "lead_silence_s" not in cols:
                self._conn.execute("ALTER TABLE sounds ADD COLUMN lead_silence_s REAL")
            self._fts = self._init_fts()
            self._conn.commit()

    def _init_fts(self) -> bool:
        """Create the FTS5 mirror; return False if this sqlite lacks FTS5."""
        try:
            self._conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS sounds_fts USING fts5("
                "ext_id UNINDEXED, provider UNINDEXED, name, description, tags)")
            return True
        except sqlite3.OperationalError:
            return False

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ writes
    def upsert_many(self, records: List[Dict[str, Any]], provider: str = "freesound") -> int:
        """Insert/refresh candidate rows (idempotent by provider+ext_id).

        Refreshes volatile metadata (downloads, name, …) + `last_seen`; PRESERVES
        curation state (`in_library`, `library_kind`, `library_file`, `rating`)
        and `first_seen`.
        """
        n = 0
        with self._lock:
            for r in records:
                tags = r.get("tags")
                tags = ", ".join(tags) if isinstance(tags, list) else (tags or "")
                now = _now()
                self._conn.execute(
                    """INSERT INTO sounds
                       (provider, ext_id, name, description, tags, license, type,
                        duration, filesize, num_downloads, username, page_url,
                        preview_url, first_seen, last_seen)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(provider, ext_id) DO UPDATE SET
                         name=excluded.name, description=excluded.description,
                         tags=excluded.tags, license=excluded.license,
                         type=excluded.type, duration=excluded.duration,
                         filesize=excluded.filesize,
                         num_downloads=excluded.num_downloads,
                         username=excluded.username, page_url=excluded.page_url,
                         preview_url=excluded.preview_url, last_seen=excluded.last_seen""",
                    (provider, str(r.get("id")), r.get("name"), r.get("description"),
                     tags, r.get("license"), r.get("type"), r.get("duration"),
                     r.get("filesize"), r.get("num_downloads"), r.get("username"),
                     r.get("page_url"), r.get("preview_hq_mp3"), now, now))
                if self._fts:
                    self._conn.execute(
                        "DELETE FROM sounds_fts WHERE ext_id=? AND provider=?",
                        (str(r.get("id")), provider))
                    self._conn.execute(
                        "INSERT INTO sounds_fts (ext_id, provider, name, description, tags)"
                        " VALUES (?,?,?,?,?)",
                        (str(r.get("id")), provider, r.get("name") or "",
                         r.get("description") or "", tags))
                n += 1
            self._conn.commit()
        return n

    def mark_in_library(self, ext_id: str, kind: str, library_file: str,
                        rating: int, provider: str = "freesound",
                        lead_silence_s: Optional[float] = None) -> None:
        """Flag a catalogued sound as curated into our bank."""
        with self._lock:
            self._conn.execute(
                """UPDATE sounds SET in_library=1, library_kind=?, library_file=?,
                   rating=?, lead_silence_s=COALESCE(?, lead_silence_s)
                   WHERE provider=? AND ext_id=?""",
                (kind, library_file, int(rating), lead_silence_s, provider, str(ext_id)))
            self._conn.commit()

    def unmark(self, ext_id: str, provider: str = "freesound") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sounds SET in_library=0, library_kind=NULL, library_file=NULL,"
                " rating=NULL WHERE provider=? AND ext_id=?", (provider, str(ext_id)))
            self._conn.commit()

    # ------------------------------------------------------------------ reads
    def get(self, ext_id: str, provider: str = "freesound") -> Optional[Dict[str, Any]]:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM sounds WHERE provider=? AND ext_id=?",
                (provider, str(ext_id))).fetchone()
        return dict(r) if r else None

    def search(self, query: str = "", *, limit: int = 25,
               in_library: Optional[bool] = None,
               license_contains: Optional[str] = None) -> List[Dict[str, Any]]:
        """Text search over name/description/tags (FTS5 if available, else LIKE).

        Empty query → browse by downloads. Results ordered by download count.
        """
        params: list = []
        where = ["1=1"]
        if in_library is not None:
            where.append("s.in_library=?"); params.append(1 if in_library else 0)
        if license_contains:
            where.append("s.license LIKE ?"); params.append(f"%{license_contains}%")

        if query and self._fts:
            sql = ("SELECT s.* FROM sounds_fts f JOIN sounds s"
                   " ON s.ext_id=f.ext_id AND s.provider=f.provider"
                   " WHERE sounds_fts MATCH ? AND " + " AND ".join(where))
            params = [query] + params
        elif query:
            like = f"%{query}%"
            where.append("(s.name LIKE ? OR s.description LIKE ? OR s.tags LIKE ?)")
            params += [like, like, like]
            sql = "SELECT s.* FROM sounds s WHERE " + " AND ".join(where)
        else:
            sql = "SELECT s.* FROM sounds s WHERE " + " AND ".join(where)
        sql += " ORDER BY s.num_downloads DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            try:
                rows = self._conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                # a malformed FTS query (special chars) — quote it and retry
                if query and self._fts:
                    params[0] = '"' + query.replace('"', '') + '"'
                    rows = self._conn.execute(sql, params).fetchall()
                else:
                    raise
        return [dict(r) for r in rows]

    def stats(self) -> Dict[str, int]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) c FROM sounds").fetchone()["c"]
            inlib = self._conn.execute(
                "SELECT COUNT(*) c FROM sounds WHERE in_library=1").fetchone()["c"]
        return {"total": total, "in_library": inlib}

    def top(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.search("", limit=limit)
