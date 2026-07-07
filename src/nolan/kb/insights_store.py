"""SQLite insight index + FTS5 keyword search.

The insight `.md` notes are canonical; this table is a derived, rebuildable index
(shares ``kb.db`` with the sources catalog) that powers fast listing, faceted
filtering, and BM25 keyword search. Rows are (re)built from the structured
sidecars — see :mod:`nolan.kb.sidecar`.

FTS5 is a standalone (contentless) table carrying an UNINDEXED ``id`` so we can
join matches back to full rows; we maintain it explicitly on upsert/delete
(delete-then-insert), which is simpler and more robust than external-content
triggers over a TEXT-primary-key table.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS insights (
    id            TEXT PRIMARY KEY,   -- insight note stem
    source_id     TEXT NOT NULL,
    seq           INTEGER,
    path          TEXT,               -- vault-relative .md path
    title         TEXT,
    category      TEXT,
    technique     TEXT,
    core_idea     TEXT,
    how_to_apply  TEXT,
    why_it_works  TEXT,
    when_to_use   TEXT,
    when_not      TEXT,
    example       TEXT,
    tools_or_assets TEXT,
    difficulty    TEXT,
    nolan_hook    TEXT,
    tags          TEXT,               -- json array
    -- denormalized from the source (display + filtering + quality ranking):
    source_title  TEXT,
    source_url    TEXT,
    source_type   TEXT,
    argument_quality TEXT,
    freshness     TEXT
);
CREATE INDEX IF NOT EXISTS idx_insights_source ON insights(source_id);
CREATE INDEX IF NOT EXISTS idx_insights_category ON insights(category);
CREATE INDEX IF NOT EXISTS idx_insights_hook ON insights(nolan_hook);
CREATE INDEX IF NOT EXISTS idx_insights_difficulty ON insights(difficulty);

CREATE VIRTUAL TABLE IF NOT EXISTS insights_fts USING fts5(
    id UNINDEXED, title, technique, core_idea, how_to_apply, when_to_use, example, tags
);
"""

# columns of the insights table, in order (for INSERT)
_COLS = [
    "id", "source_id", "seq", "path", "title", "category", "technique",
    "core_idea", "how_to_apply", "why_it_works", "when_to_use", "when_not",
    "example", "tools_or_assets", "difficulty", "nolan_hook", "tags",
    "source_title", "source_url", "source_type", "argument_quality", "freshness",
]

FACET_FIELDS = ("category", "nolan_hook", "difficulty", "freshness", "source_type")


@dataclass
class InsightRow:
    id: str
    source_id: str = ""
    seq: int = 0
    path: str = ""
    title: str = ""
    category: str = ""
    technique: str = ""
    core_idea: str = ""
    how_to_apply: str = ""
    why_it_works: str = ""
    when_to_use: str = ""
    when_not: str = ""
    example: str = ""
    tools_or_assets: str = ""
    difficulty: str = ""
    nolan_hook: str = ""
    tags: List[str] = field(default_factory=list)
    source_title: str = ""
    source_url: str = ""
    source_type: str = ""
    argument_quality: str = ""
    freshness: str = ""


def _tokens(query: str) -> List[str]:
    """Alphanumeric tokens only — keeps user input away from FTS5 syntax."""
    return [t for t in re.findall(r"[0-9a-zA-Z]+", query or "") if len(t) > 1]


def _match_expr(query: str) -> Optional[str]:
    """Build a safe FTS5 MATCH expression: prefix-match every token, AND-ed."""
    toks = _tokens(query)
    if not toks:
        return None
    return " ".join(f'"{t}"*' for t in toks)


class InsightsStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or paths.DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ---------------------------------------------------------------- writes
    def _row_values(self, rec_source: dict, ins: dict) -> list:
        tags = ins.get("tags") or []
        d = {
            "id": ins["id"], "source_id": rec_source["source_id"],
            "seq": ins.get("seq", 0), "path": ins.get("path", ""),
            "title": ins.get("title", ""), "category": ins.get("category", ""),
            "technique": ins.get("technique", ""), "core_idea": ins.get("core_idea", ""),
            "how_to_apply": ins.get("how_to_apply", ""), "why_it_works": ins.get("why_it_works", ""),
            "when_to_use": ins.get("when_to_use", ""), "when_not": ins.get("when_not", ""),
            "example": ins.get("example", ""), "tools_or_assets": ins.get("tools_or_assets", ""),
            "difficulty": ins.get("difficulty", ""), "nolan_hook": ins.get("nolan_hook", ""),
            "tags": json.dumps(tags, ensure_ascii=False),
            "source_title": rec_source.get("title", ""), "source_url": rec_source.get("url", ""),
            "source_type": rec_source.get("source_type", ""),
            "argument_quality": rec_source.get("argument_quality", ""),
            "freshness": rec_source.get("freshness", ""),
        }
        return [d[c] for c in _COLS]

    def delete_source(self, source_id: str) -> None:
        ids = [r[0] for r in self._conn.execute(
            "SELECT id FROM insights WHERE source_id=?", (source_id,)).fetchall()]
        self._conn.execute("DELETE FROM insights WHERE source_id=?", (source_id,))
        for iid in ids:
            self._conn.execute("DELETE FROM insights_fts WHERE id=?", (iid,))
        self._conn.commit()

    def index_record(self, record: dict, replace: bool = True) -> int:
        """Insert every insight in a distillation sidecar record. Returns count."""
        if replace:
            self.delete_source(record["source_id"])
        n = 0
        placeholders = ",".join("?" for _ in _COLS)
        for ins in record.get("insights", []):
            vals = self._row_values(record, ins)
            self._conn.execute(
                f"INSERT OR REPLACE INTO insights ({','.join(_COLS)}) VALUES ({placeholders})", vals)
            self._conn.execute("DELETE FROM insights_fts WHERE id=?", (ins["id"],))
            self._conn.execute(
                "INSERT INTO insights_fts (id,title,technique,core_idea,how_to_apply,when_to_use,example,tags) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (ins["id"], ins.get("title", ""), ins.get("technique", ""),
                 ins.get("core_idea", ""), ins.get("how_to_apply", ""),
                 ins.get("when_to_use", ""), ins.get("example", ""),
                 " ".join(ins.get("tags") or [])))
            n += 1
        self._conn.commit()
        return n

    def clear(self) -> None:
        self._conn.execute("DELETE FROM insights")
        self._conn.execute("DELETE FROM insights_fts")
        self._conn.commit()

    # ---------------------------------------------------------------- reads
    def _to_row(self, r) -> InsightRow:
        d = dict(r)
        d.pop("rank", None)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except (ValueError, TypeError):
            d["tags"] = []
        return InsightRow(**{k: d[k] for k in InsightRow.__dataclass_fields__ if k in d})

    def _where(self, filters: Optional[dict]):
        clauses, args = [], []
        for fld in FACET_FIELDS:
            val = (filters or {}).get(fld)
            if val:
                clauses.append(f"{fld}=?")
                args.append(val)
        return (" AND ".join(clauses), args)

    def get(self, insight_id: str) -> Optional[InsightRow]:
        r = self._conn.execute("SELECT * FROM insights WHERE id=?", (insight_id,)).fetchone()
        return self._to_row(r) if r else None

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM insights").fetchone()[0]

    def list(self, filters: Optional[dict] = None, limit: int = 100) -> List[InsightRow]:
        where, args = self._where(filters)
        q = "SELECT * FROM insights"
        if where:
            q += " WHERE " + where
        q += " ORDER BY source_id, seq LIMIT ?"
        args.append(limit)
        return [self._to_row(r) for r in self._conn.execute(q, args).fetchall()]

    def keyword_search(self, query: str, filters: Optional[dict] = None,
                       limit: int = 30) -> List[tuple]:
        """Return [(InsightRow, bm25_rank)] best-first (lower rank = better)."""
        expr = _match_expr(query)
        if not expr:
            return []
        where, args = self._where(filters)
        sql = ("SELECT i.*, f.rank AS rank FROM insights i "
               "JOIN (SELECT id, bm25(insights_fts) AS rank FROM insights_fts "
               "      WHERE insights_fts MATCH ?) f ON i.id = f.id")
        params = [expr]
        if where:
            sql += " WHERE " + where
            params += args
        sql += " ORDER BY f.rank LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [(self._to_row(r), r["rank"]) for r in rows]

    def facets(self, filters: Optional[dict] = None) -> Dict[str, Dict[str, int]]:
        """Counts per facet value (respecting the other active filters is omitted
        for simplicity — global counts per field)."""
        out: Dict[str, Dict[str, int]] = {}
        for fld in FACET_FIELDS:
            rows = self._conn.execute(
                f"SELECT {fld} AS v, COUNT(*) AS n FROM insights "
                f"WHERE {fld} != '' GROUP BY {fld} ORDER BY n DESC").fetchall()
            out[fld] = {r["v"]: r["n"] for r in rows}
        return out

    def close(self) -> None:
        self._conn.close()
