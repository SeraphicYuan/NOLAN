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
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

-- ARTIST KNOWLEDGE — the third knowledge source, and the best value on the list.
--
-- Movement, period, style and typical palette are facts about a PERSON, not about a picture, so
-- asking a vision model for them is both wasteful and wrong: it pays per artwork for something
-- that is true of the artist's whole output, and it invites a confident guess where world
-- knowledge already has an answer. Monet has ~50 works in a mid-sized harvest and needs ONE
-- call, not fifty — the saving is the corpus's works-per-artist ratio, and it compounds as the
-- library grows.
--
-- Keyed by a normalised name because that is what catalogs agree on; `wikidata_qid` rides along
-- when a source hands it over free (the Met dump publishes Artist Wikidata URL on 35% of its
-- public-domain rows).
CREATE TABLE IF NOT EXISTS artists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name_key    TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    wikidata_qid TEXT,
    movement    TEXT,
    period      TEXT,
    style       TEXT,
    subjects    TEXT,
    palette     TEXT,
    note        TEXT,
    source      TEXT,
    added_at    TEXT NOT NULL
);

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
    # `date_text` parsed into a filterable range (nolan.imagelib.dates). It is 99% populated and
    # 100% unfilterable as prose — 14,069 distinct strings. NULL where the museum says "n.d.",
    # which is a real answer and must not become a range.
    "year_from": "INTEGER",
    "year_to": "INTEGER",
    # Coarse subject bucket DERIVED from the above (nolan.imagelib.taxonomy). Stored so it can be
    # filtered in SQL; derived by a pure function so the vocabulary can change without a
    # re-crawl — `nolan images rederive` recomputes it from columns already on disk.
    "image_kind": "TEXT",
    # THE STRUCTURED CAPTION (nolan.imagelib.caption) — the one thing a vision model may produce:
    # what is DEPICTED. `description` still holds the human-readable sentence, so the BGE channel
    # the retrieval eval was measured through keeps working unchanged; this is the filterable and
    # re-processable form beside it.
    "caption_json": "TEXT",
    # The schema VERSION, and not decoration: it is what lets a v2 re-caption target only stale
    # rows across a corpus too large to redo wholesale. Half of v0's fields died on measurement,
    # so a v2 is a question of when.
    "caption_schema": "INTEGER",
    # Reserved for the labelled-region pass (subject/face/text/watermark/negative_space boxes).
    # DELIBERATELY UNPOPULATED: the executor (a focal point in compose's media_ground) does not
    # exist yet, and an authored field with no consumer is the repo's most-repeated bug. The column
    # ships now only because adding one to a populated table is the expensive part.
    "regions": "TEXT",
    # `creator` folded into a join key (see `artist_key`). STORED rather than computed per query
    # for two reasons, both measured: an artist picker built on the raw column offers "James
    # McNeill Whistler" and "James McNeill Whistler (American, 1834-1903)" as two artists (artic
    # writes the bare name, Cleveland appends the nationality), and grouping 97k rows in Python on
    # every facet request is work SQLite will do in an index scan. NULL where the creator string is
    # an anonymity placeholder — see `_is_anonymous`: "Unknown artist" is not an identity, and
    # 1,855 such rows would otherwise crowd the top of every artist list.
    "artist_key": "TEXT",
    # The artist's movement, denormalised DOWN from `artists.movement` onto the row.
    # `_filter_sql` is the one WHERE-clause builder shared by list/count/facets, and teaching it a
    # join would change every caller; a column costs a backfill instead. It is DERIVED, so it goes
    # stale when `enrich_artists` learns about a new painter — `backfill_movements` is idempotent
    # and re-runnable, and `enrich_artists` calls it on the way out.
    "movement": "TEXT",
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
    # THE VISUAL DIALECT — the consensus of a spanning sample of captions, inherited by every
    # member that has not been captioned individually. Cheap (a dozen calls) and it gives every
    # row in the collection something useful to say about how the collection LOOKS, long before
    # the row itself is worth a vision call. Matches how this tier already works: knowledge
    # inherits downward.
    "dialect_json": "TEXT",
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
    artist_key: Optional[str] = None
    movement: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    caption_json: Optional[str] = None
    caption_schema: Optional[int] = None

    def caption(self) -> Optional[dict]:
        """The structured caption, or None. Never raises on a malformed blob — a caption that
        cannot be read is absent, not fatal."""
        if not self.caption_json:
            return None
        try:
            import json as _json
            obj = _json.loads(self.caption_json)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

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


def artist_key(name: Optional[str]) -> str:
    """Normalise a creator string into a join key.

    Catalogs write the same person several ways — "Claude Monet", "Monet, Claude", "Claude Monet
    (French, 1840-1926)". Without a key the amortisation this table exists for silently fails:
    fifty works by one painter become fifty artists and fifty LLM calls, which is the exact cost
    the design was avoiding.

    ORDER-INDEPENDENT, because different institutions order names differently and the words
    themselves are the identity: "Auguste Louis Lepère" (Cleveland) and "Louis Auguste Lepère"
    (Art Institute) are one man, as are "Baiitsu Yamamoto" and "Yamamoto Baiitsu". Measured over
    the live corpus, sorting the tokens folds **19 groups covering 2,073 rows**, and every one
    inspected is a genuine duplicate.

    WHAT IT DELIBERATELY WILL NOT DO is match on a surname. That was measured too, and it is a
    trap: grouping by surname merged **Hiroshige with Hiroshige II and III** (father, son,
    grandson), **James McNeill Whistler with Beatrix Godwin Whistler** (his wife), Ancient Roman
    with Ancient Greek, and 134 distinct people under "Charles". Attributing one artist's
    movement and palette to another's works is far worse than paying for a duplicate call, so
    the rule is: same WORDS, any order — never merely a shared word.

    The residue this leaves is real and named: "Francisco José de Goya y Lucientes" and
    "Francisco de Goya" have different word sets and stay separate. Folding those needs entity
    knowledge, not string rules — see the Wikidata deferral in the bound skill.
    """
    import re as _re
    s = (name or "").strip()
    if not s:
        return ""
    s = _re.sub(r"\((?:[^()]*)\)", " ", s)          # drop "(French, 1840-1926)"
    s = _re.sub(r"\b\d{3,4}\s*[-–]\s*\d{0,4}\b", " ", s)   # drop bare life dates
    if "," in s and s.count(",") == 1:              # "Monet, Claude" -> "Claude Monet"
        last, first = (p.strip() for p in s.split(","))
        if last and first and " " not in first.strip().rstrip("."):
            s = f"{first} {last}"
    s = _re.sub(r"[^\w\s]", " ", s, flags=_re.UNICODE)
    s = _re.sub(r"\s+", " ", s).strip().casefold()
    return " ".join(sorted(s.split()))


# Words a catalog uses to say IT DOES NOT KNOW, and the generic roles that survive removing them.
# Measured over the corpus: 33 distinct anonymity-shaped creator strings covering 1,969 rows.
_ANON_WORDS = frozenset({"unknown", "unidentified", "anonymous", "unattributed"})
_GENERIC_ROLE = frozenset({
    "artist", "artists", "maker", "makers", "photographer", "illuminator", "painter",
    "sculptor", "designer", "author", "printer", "publisher", "craftsman", "workshop",
    "manufacturer", "engraver", "draftsman", "weaver", "potter", "master"})


def _is_anonymous(key: str) -> bool:
    """Is this folded key a statement of ANONYMITY rather than an identity?

    The distinction has to survive a real corpus, and the corpus makes it sharp. These are NOT
    identities and must not head an artist list:

        Unknown artist (728)   Artist unknown (428)   Unknown (427)
        Unknown Maker (126)    Anonymous (102)        Unidentified Photographer (2)

    These ARE, and dropping them would lose a genuinely useful narrowing:

        Unknown Italian (41)   Unknown Florentine (13)   Unknown Genoese (12)

    So the rule is not "contains the word unknown". It is: remove the anonymity words, and if
    what remains is nothing or only a generic job title, there is no identity left. A residue
    like "italian" or "florentine" IS one — the catalog is telling us a school even though it
    cannot name a hand.

    It runs on the KEY, after `artist_key` has stripped parentheticals, which is what saves
    "Sakai Basai (Japanese, dates unknown)" and "Master Na Dat with the Mousetrap (Italian)"
    from being read as anonymous.
    """
    words = [w for w in key.split() if w]
    if not words:
        return True
    if not any(w in _ANON_WORDS for w in words):
        return False
    return all(w in _ANON_WORDS or w in _GENERIC_ROLE for w in words)


def folded_artist(name: Optional[str]) -> Optional[str]:
    """The value stored in `assets.artist_key`: a join key, or NULL for an anonymous attribution.

    Separate from `artist_key` because the two answer different questions. `artist_key` asks
    "which artists table row is this?" and is happy to key an anonymous group; this asks "is
    there a person to filter by?" and must say no.
    """
    key = artist_key(name)
    if not key or _is_anonymous(key):
        return None
    return key


@dataclass
class Artist:
    """What is true of a PERSON's whole output — fetched once, spent across every work."""
    name: str
    name_key: Optional[str] = None
    wikidata_qid: Optional[str] = None
    movement: Optional[str] = None
    period: Optional[str] = None
    style: Optional[str] = None
    subjects: Optional[str] = None
    palette: Optional[str] = None
    note: Optional[str] = None
    source: Optional[str] = None            # the model that asserted it — provenance, always
    added_at: Optional[str] = None
    id: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def context_line(self) -> str:
        """One sentence a caption pass can be handed as context. Empty when we know nothing —
        an empty string is honest, a confident-sounding placeholder is not."""
        bits = [b for b in (self.movement, self.period, self.style) if b]
        line = f"{self.name}"
        if bits:
            line += f" — {'; '.join(bits)}"
        if self.subjects:
            line += f". Typical subjects: {self.subjects}"
        if self.palette:
            line += f". Palette: {self.palette}"
        return line if (bits or self.subjects or self.palette) else ""


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
    dialect_json: Optional[str] = None

    def dialect(self) -> Optional[dict]:
        if not self.dialect_json:
            return None
        try:
            import json as _json
            obj = _json.loads(self.dialect_json)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

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
        self._batching = False              # see batched_writes()
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
            # The artist picker GROUPs BY this over the whole discovery tier on every facet
            # request; without the index that is a full scan of 97k rows per keystroke-driven
            # re-count.
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_artist_key "
                               "ON assets(artist_key) WHERE artist_key IS NOT NULL")
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------ bulk write mode
    @contextmanager
    def batched_writes(self):
        """Defer per-write commits to the end of the block. ONE fsync instead of one per row.

        Profiled on the real Met dump, Phase A: `add()` costs **5.48 ms/row**, of which the
        insert itself is ~0.01 — the rest is the commit. Over 248,472 rows that is 23 minutes
        spent entirely on fsync, and it is the same defect `update_many` was written to fix on
        the UPDATE side ("97,625 separate fsyncs, and the pass ran for tens of minutes doing
        almost no work"). The insert path never got the same treatment.

        Correctness is not weakened, it is TIGHTENED. A crawl's durability boundary is already
        the cursor checkpoint, not the row: rows used to commit individually while the cursor
        advanced every 50, so a kill could leave rows committed *past* the recorded cursor and
        the next run re-walked them (harmless only because dedup caught it). Committing the
        batch and the cursor together makes "what is on disk" and "where we resume" the same
        point.

        NESTS SAFELY — an inner block does not commit early and end the outer transaction. Any
        exception rolls the batch back rather than leaving it half-applied, so an interrupted
        crawl resumes from the last checkpoint instead of from a partial one.
        """
        if self._batching:
            yield self                      # inner block: the outer one owns the commit
            return
        self._batching = True
        try:
            yield self
        except BaseException:
            with self._lock:
                self._conn.rollback()
            raise
        finally:
            self._batching = False
        self.commit()

    def commit(self) -> None:
        """Flush whatever `batched_writes` has been holding.

        UNCONDITIONAL — it does not consult `_batching`, because the only reason to call it is
        to end a batch early (the crawl's cursor checkpoint). Routing it through `_commit` would
        make it a no-op in exactly the situation it exists for.
        """
        with self._lock:
            self._conn.commit()

    def _commit(self) -> None:
        """The per-write commit, skipped while a batch owns the transaction.

        Callers already hold `self._lock`, so this must not take it.
        """
        if not self._batching:
            self._conn.commit()

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
        # DERIVED HERE, not by the caller. Every write path (three harvest adapters, promotion,
        # the acquisition engine) would otherwise have to remember, and the one that forgets
        # produces a row invisible to the artist picker with no error to say so.
        if asset.artist_key is None:
            asset.artist_key = folded_artist(asset.creator)
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO assets
                   (content_hash, path, url, source, source_url, license, title,
                    description, width, height, bytes, tags, query, status, added_at,
                    held, source_ref, wikidata_qid, creator, date_text, institution,
                    identity_source, description_source, thumb_path, thumb_url,
                    collection_id, regions,
                    medium, classification, department, culture, place, image_kind,
                    artist_key, movement, year_from, year_to, caption_json, caption_schema)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                           ?,?,?,?,?,?,?,?,?,?,?,?)""",
                (asset.content_hash, asset.path, asset.url, asset.source,
                 asset.source_url, asset.license, asset.title, asset.description,
                 asset.width, asset.height, asset.bytes, asset.tags, asset.query,
                 asset.status, asset.added_at,
                 int(asset.held), asset.source_ref, asset.wikidata_qid, asset.creator,
                 asset.date_text, asset.institution, asset.identity_source,
                 asset.description_source, asset.thumb_path, asset.thumb_url,
                 asset.collection_id, asset.regions,
                 asset.medium, asset.classification, asset.department, asset.culture,
                 asset.place, asset.image_kind, asset.artist_key, asset.movement,
                 asset.year_from, asset.year_to,
                 asset.caption_json, asset.caption_schema),
            )
            self._commit()
        asset.id = cur.lastrowid
        return asset

    # Columns a promotion (or a re-crawl) may rewrite. `content_hash`/`path`/`held` change when a
    # discovery row's bytes land; the identity columns refresh from the source's catalog.
    _UPDATABLE = frozenset({
        "content_hash", "path", "url", "source", "source_url", "license", "title", "description",
        "width", "height", "bytes", "tags", "query", "held", "source_ref", "wikidata_qid",
        "creator", "date_text", "institution", "identity_source", "description_source",
        "thumb_path", "thumb_url", "collection_id", "regions",
        "medium", "classification", "department", "culture", "place", "image_kind",
        "artist_key", "movement",
        "year_from", "year_to", "caption_json", "caption_schema"})

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
            self._commit()

    def update_many(self, patches: "Dict[int, dict]") -> int:
        """Patch many rows in ONE transaction. Returns rows written.

        `update()` commits per call, which is right for a single edit and catastrophic for a
        catalog-wide pass: re-deriving `image_kind` and the parsed year range across 97,625 rows
        meant 97,625 separate fsyncs, and the pass ran for tens of minutes doing almost no work.
        Same SQL, one commit.
        """
        if not patches:
            return 0
        bad = set()
        for f in patches.values():
            bad |= set(f) - self._UPDATABLE
        if bad:
            raise ValueError(f"not updatable columns: {sorted(bad)}")
        n = 0
        with self._lock:
            for asset_id, fields in patches.items():
                if not fields:
                    continue
                sets = ", ".join(f"{k}=?" for k in fields)
                self._conn.execute(f"UPDATE assets SET {sets} WHERE id=?",
                                   [*fields.values(), asset_id])
                n += 1
            self._commit()
        return n

    def set_status(self, asset_id: int, status: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE assets SET status=? WHERE id=?", (status, asset_id))
            self._commit()

    def delete(self, asset_id: int) -> None:
        """Hard-remove a row — frees its content-hash so re-adding the SAME bytes creates a fresh asset.
        A re-ingest/refresh needs this: set_status('deleted') keeps the row, and get_by_hash still finds it,
        so identical re-captured bytes would silently dedup back to the stale (deleted) asset."""
        with self._lock:
            self._conn.execute("DELETE FROM assets WHERE id=?", (asset_id,))
            self._commit()

    def set_description(self, asset_id: int, description: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE assets SET description=? WHERE id=?",
                               (description, asset_id))
            self._commit()

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
             held: Optional[int] = 1, collection_id: Optional[int] = None,
             **facets) -> List[Asset]:
        """List assets. ``held`` defaults to 1 — the DISCOVERY TIER IS OPT-IN.

        `**facets` narrows on the catalog's own vocabularies — `image_kind`, `classification`,
        `department`, `culture` (exact), `creator`, `place`, `medium`, `title` (contains), plus
        `year_from`/`year_to`. Those columns were populated across 97k rows and, until this
        existed, **nothing could filter on any of them** — an authored field with no consumer,
        which is the first pitfall in the wiring checklist. An unknown key raises rather than
        being ignored, because a silently-dropped filter returns a plausible wrong answer.

        Every caller of this method (search_by_title, backfill_descriptions, the /images UI, the
        acquisition engine's library source) assumes `abs_path(asset)` resolves to a real file.
        A not-held row has no file, so leaking one into these paths is a FileNotFoundError at
        render time in exchange for a search hit that was never usable. Pass held=0 for the
        discovery tier explicitly, or held=None for both.
        """
        where, params = self._filter_sql(
            status=status, held=held, source=source, collection_id=collection_id,
            license_contains=license_contains, **facets)
        sql = f"SELECT * FROM assets WHERE {where} ORDER BY id DESC"
        if limit:
            sql += " LIMIT ?"; params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row(r) for r in rows]

    # Fields a caller may narrow on. EXACT match, because these are catalog vocabularies rather
    # than free text — `image_kind` has 14 values, `department` 30. `creator`/`place`/`medium`
    # are matched as a CONTAINS, because they are long-tailed and nobody types them exactly.
    # `artist_key` is EXACT while `creator` is CONTAINS, and both exist on purpose: typing "monet"
    # should find Claude Monet without knowing how his catalog spells him, but CLICKING an artist
    # must return exactly the count the picker promised — and a contains-match on a short name
    # cannot ("Millet" is inside "Jean-François Millet" and also inside nothing else, but "Bosch"
    # is inside "Bosch" and "Boschaert"). Same reason `movement` is exact: it is a stored
    # vocabulary, not free text.
    FACET_EXACT = ("image_kind", "classification", "department", "culture",
                   "artist_key", "movement")
    FACET_LIKE = ("creator", "place", "medium", "title")

    def _filter_sql(self, *, status=None, held=1, source=None, collection_id=None,
                    license_contains=None, year_from=None, year_to=None, **facets):
        """Build the shared WHERE clause. ONE implementation for list(), count() and facets(),
        so a facet count can never disagree with the result set it is supposed to describe."""
        bad = set(facets) - set(self.FACET_EXACT) - set(self.FACET_LIKE)
        if bad:
            raise ValueError(f"not filterable: {sorted(bad)} "
                             f"(known: {sorted(set(self.FACET_EXACT) | set(self.FACET_LIKE))})")
        sql, params = "1=1", []
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
        for k in self.FACET_EXACT:
            v = facets.get(k)
            if v:
                sql += f" AND {k}=?"; params.append(v)
        for k in self.FACET_LIKE:
            v = facets.get(k)
            if v:
                sql += f" AND {k} LIKE ?"; params.append(f"%{v}%")
        # A date filter OVERLAPS the row's range rather than containing it: an object dated
        # 1830-1833 belongs in a search for 1831, and requiring containment would drop every
        # imprecisely-dated row — which in a museum corpus is most of them. Rows with NO parsed
        # date are excluded, because "we don't know when" cannot honestly answer "before 1850".
        if year_from is not None:
            sql += " AND year_to IS NOT NULL AND year_to >= ?"; params.append(int(year_from))
        if year_to is not None:
            sql += " AND year_from IS NOT NULL AND year_from <= ?"; params.append(int(year_to))
        return sql, params

    def title_candidates(self, tokens: "List[str]", *, status: Optional[str] = "active",
                         held: Optional[int] = 1, collection_id: Optional[int] = None
                         ) -> List[Tuple[int, str, Optional[str]]]:
        """`(id, title, license)` for every row whose title contains one of `tokens`.

        Title-cover scoring is `|title ∩ query| / |title|`, so a title sharing NO query token
        scores zero and can never clear the threshold. Letting SQLite discard those is the whole
        win: the caller used to materialise all 97,610 rows as Asset objects to find a handful.

        Returns TUPLES, not Assets, and does NOT truncate — both on purpose. A first version
        returned full rows under a LIMIT, and the limit lost a right answer: "El Greco The
        Assumption of the Virgin" shares "virgin" with a great many titles, so the cut dropped
        the target and its named recall@1 fell from rank 1 to rank 4. Scoring three columns is
        cheap enough that the cap is unnecessary, and the caller hydrates only the top k.

        Deliberately a LIKE-OR rather than FTS5: no second table to keep in sync with a catalog
        four passes already write to. If this grows again, FTS5 is the next step — not a limit.
        """
        toks = [t for t in tokens if t][:24]      # a pathological query must not build 500 ORs
        if not toks:
            return []
        where, params = self._filter_sql(status=status, held=held,
                                         collection_id=collection_id)
        ors = " OR ".join("LOWER(title) LIKE ?" for _ in toks)
        params = [*params, *(f"%{t.lower()}%" for t in toks)]
        with self._lock:
            # `id DESC` is not cosmetic. Cover scores tie constantly (a museum holds several
            # impressions of one print), Python's sort is stable, and the caller used to inherit
            # this order from `catalog.list`. Returning rowid order instead silently flipped
            # every tie-break and cost named recall.
            rows = self._conn.execute(
                f"SELECT id, title, license FROM assets WHERE {where} "
                f"AND title IS NOT NULL AND ({ors}) ORDER BY id DESC", params).fetchall()
        return [(int(r["id"]), r["title"], r["license"]) for r in rows]

    def count_with_pixels(self, *, held: Optional[int] = 0,
                          collection_id: Optional[int] = None) -> int:
        """How many rows have their thumbnail — the Phase-B coverage numerator, in SQL."""
        where, params = self._filter_sql(status="active", held=held,
                                         collection_id=collection_id)
        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) c FROM assets WHERE {where} "
                f"AND thumb_path IS NOT NULL AND TRIM(thumb_path)<>''", params).fetchone()
        return int(row["c"])

    def facets(self, field: str, *, status: Optional[str] = "active", held: Optional[int] = 0,
               limit: int = 40, **filters) -> List[Tuple[str, int]]:
        """Value → count for one field, UNDER the currently active filters.

        The counts are what make a filter usable instead of guesswork: "print (35,777)" tells you
        what narrowing will cost before you click it. They run through `_filter_sql`, so a facet
        can never promise rows the result set will not deliver.
        """
        if field not in self.FACET_EXACT and field not in self.FACET_LIKE:
            raise ValueError(f"not a facet field: {field!r}")
        filters.pop(field, None)            # a facet never narrows by itself
        where, params = self._filter_sql(status=status, held=held, **filters)
        sql = (f"SELECT {field} v, COUNT(*) c FROM assets WHERE {where} "
               f"AND {field} IS NOT NULL AND TRIM({field})<>'' "
               f"GROUP BY {field} ORDER BY c DESC LIMIT ?")
        with self._lock:
            rows = self._conn.execute(sql, [*params, int(limit)]).fetchall()
        return [(r["v"], int(r["c"])) for r in rows]

    def artist_facets(self, *, status: Optional[str] = "active", held: Optional[int] = 0,
                      limit: int = 40, **filters) -> List[Tuple[str, str, int]]:
        """`(display_name, artist_key, count)` for the artists in the current result set.

        This is the browse surface the corpus most wants and least supports by default. The
        distribution is why it needs its own method rather than `facets("creator")`:

            8,604 artists over 68,376 attributed rows (70% of the corpus)
            top 50 reach 23% of all rows, top 500 reach 49%
            4,726 artists — 55% of them — have exactly ONE work

        So a dropdown is out, and a raw GROUP BY creator is worse than useless at the top, where
        it offers "Unknown artist", "Artist unknown" and "Unknown" as three of the five biggest
        names. Grouping on the stored key fixes both: anonymity is already NULL, and the
        institutional spellings of one person have already collapsed.

        The DISPLAY name is a raw spelling from the group, not the key — nobody wants to click
        "hiroshige utagawa". Which spelling is chosen matters, and popularity alone gets it wrong:
        Cleveland writes "Auguste Louis Lepère (French, 1849-1918)" and holds more of him than
        artic, so the most common spelling for three of the top twenty artists was the one with
        the biography bolted on. A parenthetical is a catalog's annotation, not part of the name,
        so a clean spelling wins over a popular one; only then does frequency, and then length,
        decide. The count is the whole group's either way.
        """
        filters.pop("artist_key", None)         # a facet never narrows by itself
        where, params = self._filter_sql(status=status, held=held, **filters)
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT artist_key k, creator v, COUNT(*) c FROM assets WHERE {where}
                    AND artist_key IS NOT NULL AND creator IS NOT NULL
                    GROUP BY artist_key, creator""", params).fetchall()
        totals: "Dict[str, int]" = {}
        best: "Dict[str, Tuple[int, int, str]]" = {}
        for r in rows:
            k, v, c = r["k"], r["v"], int(r["c"])
            totals[k] = totals.get(k, 0) + c
            rank = ("(" in v, -c, len(v), v)   # clean, then common, then short, then stable
            if k not in best or rank < best[k]:
                best[k] = rank
        # `[-1]` and not `[2]`: the name is the LAST element of the rank tuple, so extending the
        # ranking cannot silently start returning a tiebreak field as the display name.
        out = [(best[k][-1], k, n) for k, n in totals.items()]
        out.sort(key=lambda t: (-t[2], t[0]))
        return out[:int(limit)]

    def count(self, status: Optional[str] = None, *, held: Optional[int] = None,
              collection_id: Optional[int] = None, **facets) -> int:
        where, params = self._filter_sql(status=status, held=held,
                                         collection_id=collection_id, **facets)
        sql = f"SELECT COUNT(*) c FROM assets WHERE {where}"
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

    # ------------------------------------------------------------------ artists
    def upsert_artist(self, a: Artist) -> Artist:
        """Insert or update by normalised name. Only asserted (non-None) fields overwrite —
        the same stickiness rule collections have, for the same reason: a later pass that knows
        less must not erase what an earlier one established."""
        key = a.name_key or artist_key(a.name)
        if not key:
            raise ValueError("upsert_artist needs a name")
        a.name_key = key
        prev = self.get_artist(key)
        now = datetime.now(timezone.utc).isoformat()
        if prev is None:
            with self._lock:
                cur = self._conn.execute(
                    """INSERT INTO artists (name_key, name, wikidata_qid, movement, period,
                                            style, subjects, palette, note, source, added_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (key, a.name, a.wikidata_qid, a.movement, a.period, a.style,
                     a.subjects, a.palette, a.note, a.source, a.added_at or now))
                self._commit()
            a.id = cur.lastrowid
            a.added_at = a.added_at or now
            return a
        fields = {k: getattr(a, k) for k in
                  ("name", "wikidata_qid", "movement", "period", "style", "subjects",
                   "palette", "note", "source")
                  if getattr(a, k) is not None}
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            with self._lock:
                self._conn.execute(f"UPDATE artists SET {sets} WHERE name_key=?",
                                   [*fields.values(), key])
                self._commit()
        return self.get_artist(key)

    def rekey_artists(self) -> dict:
        """Recompute every `name_key` after a change to `artist_key`.

        Without this, changing the key silently strands what has already been learned: the old
        rows become unreachable, the next enrichment re-pays for artists we already know, and two
        entries for one person sit in the table pointing at different keys. Rows that collide
        after re-keying are MERGED — that is the fold, arriving.
        """
        with self._lock:
            rows = self._conn.execute("SELECT * FROM artists").fetchall()
        seen: Dict[str, dict] = {}
        merged = rekeyed = 0
        for r in rows:
            d = {k: r[k] for k in r.keys()}
            key = artist_key(d["name"]) or d["name_key"]
            if key != d["name_key"]:
                rekeyed += 1
            prev = seen.get(key)
            if prev is None:
                seen[key] = d
                continue
            merged += 1
            # Keep whichever entry actually knows something; a "not recognised" miss must never
            # overwrite a real answer just because it sorted first.
            keeps = sum(1 for f in ("movement", "period", "style", "subjects", "palette")
                        if prev.get(f))
            cands = sum(1 for f in ("movement", "period", "style", "subjects", "palette")
                        if d.get(f))
            if cands > keeps:
                seen[key] = d
        with self._lock:
            self._conn.execute("DELETE FROM artists")
            for key, d in seen.items():
                self._conn.execute(
                    """INSERT INTO artists (name_key, name, wikidata_qid, movement, period,
                                            style, subjects, palette, note, source, added_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (key, d["name"], d["wikidata_qid"], d["movement"], d["period"], d["style"],
                     d["subjects"], d["palette"], d["note"], d["source"], d["added_at"]))
            self._commit()
        return {"examined": len(rows), "rekeyed": rekeyed, "merged": merged,
                "remaining": len(seen)}

    def get_artist(self, name_or_key: str) -> Optional[Artist]:
        key = artist_key(name_or_key) or (name_or_key or "").strip()
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM artists WHERE name_key=?", (key,)).fetchone()
        return Artist(**{k: row[k] for k in row.keys()}) if row else None

    def list_artists(self, limit: int = 1000) -> List[Artist]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM artists ORDER BY name LIMIT ?", (limit,)).fetchall()
        return [Artist(**{k: r[k] for k in r.keys()}) for r in rows]

    def creator_histogram(self, *, held: Optional[int] = 0,
                          collection_id: Optional[int] = None) -> List[Tuple[str, str, int]]:
        """(name_key, a display name, work count) for every creator in the tier, commonest first.

        The ordering IS the budget: enriching the top 200 creators of a 60k-row corpus covers far
        more rows than 200 arbitrary ones, and the histogram is what makes that visible instead
        of guessed.
        """
        sql = ["SELECT creator, COUNT(*) n FROM assets",
               "WHERE status='active' AND creator IS NOT NULL AND TRIM(creator) <> ''"]
        args: List[Any] = []
        if held is not None:
            sql.append("AND held=?")
            args.append(int(held))
        if collection_id is not None:
            sql.append("AND collection_id=?")
            args.append(collection_id)
        sql.append("GROUP BY creator")
        with self._lock:
            rows = self._conn.execute(" ".join(sql), args).fetchall()
        agg: Dict[str, Tuple[str, int]] = {}
        for r in rows:
            k = artist_key(r["creator"])
            if not k:
                continue
            name, n = agg.get(k, (r["creator"], 0))
            agg[k] = (name, n + int(r["n"]))
        return sorted(((k, v[0], v[1]) for k, v in agg.items()),
                      key=lambda t: -t[2])

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
                        upstream_count, cursor, cursor_at, dialect_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (c.slug, c.source, c.title, c.description, c.rights,
                     None if c.copyright_free is None else int(c.copyright_free),
                     c.era, c.topics, c.url, c.item_count, c.added_at, c.last_crawled,
                     c.upstream_count, c.cursor, c.cursor_at, c.dialect_json))
                self._commit()
            c.id = cur.lastrowid
            return c
        fields = {}
        for k in ("source", "title", "description", "rights", "era", "topics", "url",
                  "item_count", "last_crawled", "upstream_count", "cursor", "cursor_at",
                  "dialect_json"):
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
                self._commit()
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

    def get_collection_by_id(self, collection_id: int) -> Optional[Collection]:
        with self._lock:
            r = self._conn.execute("SELECT * FROM collections WHERE id=?",
                                   (collection_id,)).fetchone()
        return self._collection_row(r) if r else None

    def list_collections(self) -> List[Collection]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM collections ORDER BY id").fetchall()
        return [self._collection_row(r) for r in rows]
