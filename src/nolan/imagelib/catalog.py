"""SQLite catalog for the picture library — provenance, dedup, licensing.

One row per image: where it came from, its license, dimensions, tags, and
curation status. Dedup is by content hash (sha256 of the file bytes).

TWO TIERS in ONE catalog (`held`), the same shape the transcript library used to add a
discovery tier to the video library (`source_kind='transcript'`, `has_footage=0` in the SAME
VideoIndex) rather than forking a second store:

  * ``held=1`` — the Picture Library proper: the bytes are on disk, `path` resolves.
  * ``held=0`` — **Visual Lib**, the not-held discovery tier: catalog metadata + a local
    THUMBNAIL only. The row says *this image exists, here, under these terms*; the bytes are
    fetched on promotion (`ImageLibrary.promote`, which flips it to held=1).

`held=0` rows are EXCLUDED from every read path by default (`list(held=1)`), so no existing
consumer — the acquisition engine's `search_library` above all — can be handed a row whose
file isn't there. Opting in is explicit (`held=0` / `held=None`).

IDENTITY IS CATALOG-DERIVED, NEVER VLM-ASSERTED. `creator`/`date_text`/`institution`/
`source_ref`/`wikidata_qid` come from the source's own catalog and carry `identity_source`
('catalog' | 'web' | 'vlm') to say so. CLIP cannot discriminate named works (all 46 Holbein
woodcuts cluster at 0.29-0.36) and a VLM naming an artwork is a hallucination that becomes a
factual error on screen (the Alamy/named-work lesson) — so a description may be generated,
an identity may not.
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

CREATE TABLE IF NOT EXISTS collections (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    slug           TEXT UNIQUE NOT NULL,
    source         TEXT NOT NULL,
    title          TEXT NOT NULL,
    description    TEXT,
    rights         TEXT,
    copyright_free INTEGER,
    era            TEXT,
    topics         TEXT,
    url            TEXT,
    item_count     INTEGER,
    added_at       TEXT NOT NULL,
    last_crawled   TEXT
);
"""

# Columns added after the first release. Applied by ALTER TABLE on open (SQLite has no
# IF NOT EXISTS for columns), so an existing catalog.db upgrades in place.
_ASSET_MIGRATIONS = {
    # THE tier flag. Default 1 so every pre-existing row keeps meaning "the bytes are here".
    "held": "INTEGER NOT NULL DEFAULT 1",
    # The source's own stable id, namespaced: 'artic:27992', 'met:436535', 'commons:File_x.jpg'.
    # A not-held row's ONLY durable handle — museum CDN urls rotate, so a discovery tier keyed on
    # the url cannot be re-fetched, re-crawled without duplicating, or told "already promoted".
    "source_ref": "TEXT",
    # Populated ONLY when a source hands it over free (Commons, several museum APIs). One nullable
    # column now = the difference between switching entity-linking on later and re-harvesting.
    "wikidata_qid": "TEXT",
    # Identity block (catalog-derived — see the module docstring).
    "creator": "TEXT",
    "date_text": "TEXT",
    "institution": "TEXT",
    "identity_source": "TEXT",
    # Where `description` came from: 'catalog' (the institution's own prose — medium, place) or a
    # model id (the T2 caption pass). Kept apart from `identity_source` because they answer
    # different questions and only one of them may ever be a model: a caption is a reading of the
    # picture, an identity is a claim about which picture it is. Also the coverage denominator —
    # counting catalog prose as "captioned" would report a 0%-captioned collection as complete.
    "description_source": "TEXT",
    # Local 512px derivative: what makes this a VISUAL library rather than a text index, what CLIP
    # embeds for a not-held row, and what survives a dead link. NULL on a record-only row — see
    # `thumb_url`.
    "thumb_path": "TEXT",
    # WHERE the thumbnail can be fetched from. Required by the phase-split crawl: a Phase-A row is
    # indexed from its catalog record alone (no bytes, ~50x cheaper), and without this column
    # Phase B could not fetch its pixels later without re-walking the whole source.
    "thumb_url": "TEXT",
    "collection_id": "INTEGER",
    # THE CATALOG TIER, unpacked. These arrived as one comma-joined prose blob in `description`
    # ("Oil on canvas, Saint-Rémy-de-Provence, oil on canvas, Painting and Sculpture of Europe"),
    # which embeds fine and filters not at all — you cannot ask for "textiles from Iran" of a
    # sentence. They are the institution's OWN words, so they are also the fields a vision model
    # must never be asked for: the museum already recorded them.
    "medium": "TEXT",
    "classification": "TEXT",
    "department": "TEXT",
    "culture": "TEXT",
    "place": "TEXT",
    # Coarse subject bucket DERIVED from the above (nolan.imagelib.taxonomy). Stored so it can be
    # filtered in SQL; derived by a pure function so the vocabulary can change without a
    # re-crawl — `nolan images rederive` recomputes it from columns already on disk.
    "image_kind": "TEXT",
    # Reserved for the labelled-region pass (subject/face/text/watermark/negative_space boxes).
    # DELIBERATELY UNPOPULATED: the executor (a focal point in compose's media_ground) does not
    # exist yet, and an authored field with no consumer is the repo's most-repeated bug. The column
    # ships now only because adding one to a populated table is the expensive part.
    "regions": "TEXT",
}

# Columns added to `collections` after its first release, same ALTER-on-open mechanism.
_COLLECTION_MIGRATIONS = {
    # THE DENOMINATOR. `item_count` says what we indexed; without what EXISTS upstream, a
    # coverage page reads "841 indexed" and looks complete when it is 1.4% of the collection —
    # the same honesty failure this tier was built to avoid, one level up. Nullable because not
    # every source can be asked how big it is, and a guessed denominator is worse than none.
    "upstream_count": "INTEGER",
    # THE RESUME CURSOR, a JSON blob whose shape is the adapter's business ({"page": 14} for a
    # paginated listing, {"offset": 3200} for an id walk). Without it every run restarts at page
    # one and leans on source_ref dedup to skip — which for the Met costs one HTTP request per
    # already-indexed object just to rediscover it is a duplicate. A job measured in hours that
    # cannot resume is a job that never finishes.
    "cursor": "TEXT",
    # When the cursor was last advanced, so a stalled crawl is visible rather than merely slow.
    "cursor_at": "TEXT",
}


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
    # --- discovery tier (see module docstring) ---
    held: int = 1
    source_ref: Optional[str] = None
    wikidata_qid: Optional[str] = None
    creator: Optional[str] = None
    date_text: Optional[str] = None
    institution: Optional[str] = None
    identity_source: Optional[str] = None
    description_source: Optional[str] = None
    thumb_path: Optional[str] = None
    thumb_url: Optional[str] = None
    collection_id: Optional[int] = None
    regions: Optional[str] = None
    # --- catalog tier, unpacked (see _ASSET_MIGRATIONS) ---
    medium: Optional[str] = None
    classification: Optional[str] = None
    department: Optional[str] = None
    culture: Optional[str] = None
    place: Optional[str] = None
    image_kind: Optional[str] = None

    @property
    def has_pixels(self) -> bool:
        """True once Phase B has fetched this row's thumbnail. A record-only row is searchable by
        IDENTITY (BGE over the catalog text) but not by LOOK (CLIP needs pixels)."""
        return bool(self.thumb_path)

    def to_dict(self) -> dict:
        return asdict(self)

    def identity_text(self) -> str:
        """The catalog-derived identity as ONE searchable string — what BGE embeds for a
        discovery row, and the retrieval channel CLIP provably cannot serve for named works."""
        parts = [self.title, self.creator, self.date_text, self.institution, self.description]
        return " | ".join(p.strip() for p in parts if (p or "").strip())


@dataclass
class Collection:
    """A harvest unit — a museum department, an archive collection, a curated set.

    First-class and searchable BEFORE any member is captioned (the transcript library's
    `sources.json` channel, for pictures): a hit on the collection answers "this collection
    probably has it". `description` is also CONTEXT for a member's later caption pass, the same
    trick that makes frame captions entity-aware by feeding them the transcript window.
    """
    slug: str
    source: str
    title: str
    description: Optional[str] = None
    rights: Optional[str] = None
    copyright_free: Optional[bool] = None
    era: Optional[str] = None
    topics: Optional[str] = None
    url: Optional[str] = None
    item_count: Optional[int] = None
    added_at: Optional[str] = None
    last_crawled: Optional[str] = None
    id: Optional[int] = None
    # --- crawl state (see _COLLECTION_MIGRATIONS) ---
    upstream_count: Optional[int] = None
    cursor: Optional[str] = None
    cursor_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def coverage(self) -> Optional[float]:
        """Indexed share of what exists upstream, or None when the denominator is unknown.

        None is a first-class answer here and must be rendered as "unknown", never as 100%: the
        whole point of carrying `upstream_count` is that a collection which is 1.4% harvested
        should be unable to look finished.
        """
        if not self.upstream_count:
            return None
        return min(1.0, (self.item_count or 0) / self.upstream_count)


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
            for col, decl in _ASSET_MIGRATIONS.items():
                if col not in cols:
                    self._conn.execute(f"ALTER TABLE assets ADD COLUMN {col} {decl}")
            ccols = {r["name"] for r in self._conn.execute("PRAGMA table_info(collections)")}
            for col, decl in _COLLECTION_MIGRATIONS.items():
                if col not in ccols:
                    self._conn.execute(f"ALTER TABLE collections ADD COLUMN {col} {decl}")
            # A source's own id is UNIQUE where present — re-crawling a collection must UPDATE the
            # row, never duplicate it. Partial index: held=1 rows carry no source_ref and are
            # unaffected (SQLite treats every NULL as distinct anyway; the WHERE is documentation
            # plus a smaller index).
            self._conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_assets_source_ref "
                               "ON assets(source_ref) WHERE source_ref IS NOT NULL")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_held ON assets(held)")
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ writes
    def add(self, asset: Asset) -> Asset:
        """Insert an asset; if its content_hash (or source_ref) already exists, return that row."""
        existing = self.get_by_hash(asset.content_hash)
        if existing:
            return existing
        if asset.source_ref:
            existing = self.get_by_ref(asset.source_ref)
            if existing:
                return existing
        asset.added_at = asset.added_at or datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO assets
                   (content_hash, path, url, source, source_url, license, title,
                    description, width, height, bytes, tags, query, status, added_at,
                    held, source_ref, wikidata_qid, creator, date_text, institution,
                    identity_source, description_source, thumb_path, thumb_url,
                    collection_id, regions,
                    medium, classification, department, culture, place, image_kind)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                           ?,?,?,?,?,?)""",
                (asset.content_hash, asset.path, asset.url, asset.source,
                 asset.source_url, asset.license, asset.title, asset.description,
                 asset.width, asset.height, asset.bytes, asset.tags, asset.query,
                 asset.status, asset.added_at,
                 int(asset.held), asset.source_ref, asset.wikidata_qid, asset.creator,
                 asset.date_text, asset.institution, asset.identity_source,
                 asset.description_source, asset.thumb_path, asset.thumb_url,
                 asset.collection_id, asset.regions,
                 asset.medium, asset.classification, asset.department, asset.culture,
                 asset.place, asset.image_kind),
            )
            self._conn.commit()
        asset.id = cur.lastrowid
        return asset

    # Columns a promotion (or a re-crawl) may rewrite. `content_hash`/`path`/`held` change when a
    # discovery row's bytes land; the identity columns refresh from the source's catalog.
    _UPDATABLE = frozenset({
        "content_hash", "path", "url", "source", "source_url", "license", "title", "description",
        "width", "height", "bytes", "tags", "query", "held", "source_ref", "wikidata_qid",
        "creator", "date_text", "institution", "identity_source", "description_source",
        "thumb_path", "thumb_url", "collection_id", "regions",
        "medium", "classification", "department", "culture", "place", "image_kind"})

    def update(self, asset_id: int, **fields) -> None:
        """Patch named columns on one row. Unknown column names raise (a typo'd field that
        silently did nothing is the same class of bug as an authored field with no consumer)."""
        bad = set(fields) - self._UPDATABLE
        if bad:
            raise ValueError(f"not updatable columns: {sorted(bad)}")
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self._conn.execute(f"UPDATE assets SET {sets} WHERE id=?",
                               [*fields.values(), asset_id])
            self._conn.commit()

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

    def get_by_ref(self, source_ref: str) -> Optional[Asset]:
        """Look a row up by the SOURCE's own stable id — how a re-crawl finds what it already has."""
        with self._lock:
            r = self._conn.execute("SELECT * FROM assets WHERE source_ref=?",
                                   (source_ref,)).fetchone()
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
             license_contains: Optional[str] = None, limit: Optional[int] = None,
             held: Optional[int] = 1, collection_id: Optional[int] = None
             ) -> List[Asset]:
        """List assets. ``held`` defaults to 1 — the DISCOVERY TIER IS OPT-IN.

        Every caller of this method (search_by_title, backfill_descriptions, the /images UI, the
        acquisition engine's library source) assumes `abs_path(asset)` resolves to a real file.
        A not-held row has no file, so leaking one into these paths is a FileNotFoundError at
        render time in exchange for a search hit that was never usable. Pass held=0 for the
        discovery tier explicitly, or held=None for both.
        """
        sql = "SELECT * FROM assets WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status=?"; params.append(status)
        if held is not None:
            sql += " AND held=?"; params.append(int(held))
        if source:
            sql += " AND source=?"; params.append(source)
        if collection_id is not None:
            sql += " AND collection_id=?"; params.append(int(collection_id))
        if license_contains:
            sql += " AND license LIKE ?"; params.append(f"%{license_contains}%")
        sql += " ORDER BY id DESC"
        if limit:
            sql += " LIMIT ?"; params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row(r) for r in rows]

    def count(self, status: Optional[str] = None, *, held: Optional[int] = None,
              collection_id: Optional[int] = None) -> int:
        sql, params = "SELECT COUNT(*) c FROM assets WHERE 1=1", []
        if status:
            sql += " AND status=?"; params.append(status)
        if held is not None:
            sql += " AND held=?"; params.append(int(held))
        if collection_id is not None:
            sql += " AND collection_id=?"; params.append(int(collection_id))
        with self._lock:
            return self._conn.execute(sql, params).fetchone()["c"]

    def described_count(self, *, held: Optional[int] = None,
                        collection_id: Optional[int] = None) -> int:
        """Rows carrying a MODEL-written description — the numerator of the coverage badge
        ("3% captioned"). Catalog prose doesn't count: every harvested row has some, so counting
        it would report an entirely un-captioned collection as fully covered. No silent caps —
        a partially-enriched collection must SAY so."""
        sql = ("SELECT COUNT(*) c FROM assets WHERE status='active' "
               "AND description IS NOT NULL AND TRIM(description) <> '' "
               "AND description_source IS NOT NULL AND description_source <> 'catalog'")
        params: list = []
        if held is not None:
            sql += " AND held=?"; params.append(int(held))
        if collection_id is not None:
            sql += " AND collection_id=?"; params.append(int(collection_id))
        with self._lock:
            return self._conn.execute(sql, params).fetchone()["c"]

    # ------------------------------------------------------------- collections
    def upsert_collection(self, c: Collection) -> Collection:
        """Insert or update a collection BY SLUG — **provenance is sticky**.

        Only fields the caller actually asserts (non-None) overwrite what is stored. The
        transcript library paid for this rule live: `record_transcript` defaulted its provenance
        args, so a re-caption that knew nothing about the source family silently re-labelled a
        Prelinger public-domain film as copyrighted YouTube. A rights assertion on a collection
        is authoritative and must survive every later pass that doesn't know it.
        """
        prev = self.get_collection(c.slug)
        now = datetime.now(timezone.utc).isoformat()
        if prev is None:
            c.added_at = c.added_at or now
            with self._lock:
                cur = self._conn.execute(
                    """INSERT INTO collections
                       (slug, source, title, description, rights, copyright_free, era, topics,
                        url, item_count, added_at, last_crawled,
                        upstream_count, cursor, cursor_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (c.slug, c.source, c.title, c.description, c.rights,
                     None if c.copyright_free is None else int(c.copyright_free),
                     c.era, c.topics, c.url, c.item_count, c.added_at, c.last_crawled,
                     c.upstream_count, c.cursor, c.cursor_at))
                self._conn.commit()
            c.id = cur.lastrowid
            return c
        fields = {}
        for k in ("source", "title", "description", "rights", "era", "topics", "url",
                  "item_count", "last_crawled", "upstream_count", "cursor", "cursor_at"):
            v = getattr(c, k)
            if v is not None:
                fields[k] = v
        if c.copyright_free is not None:
            fields["copyright_free"] = int(c.copyright_free)
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            with self._lock:
                self._conn.execute(f"UPDATE collections SET {sets} WHERE slug=?",
                                   [*fields.values(), c.slug])
                self._conn.commit()
        return self.get_collection(c.slug)

    def _collection_row(self, row: sqlite3.Row) -> Collection:
        d = {k: row[k] for k in row.keys()}
        if d.get("copyright_free") is not None:
            d["copyright_free"] = bool(d["copyright_free"])
        return Collection(**d)

    def get_collection(self, slug: str) -> Optional[Collection]:
        with self._lock:
            r = self._conn.execute("SELECT * FROM collections WHERE slug=?", (slug,)).fetchone()
        return self._collection_row(r) if r else None

    def list_collections(self) -> List[Collection]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM collections ORDER BY id").fetchall()
        return [self._collection_row(r) for r in rows]
