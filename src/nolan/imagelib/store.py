"""Picture library â€” persistent, searchable, license-aware image store.

Ties together file storage + the SQLite :class:`AssetCatalog` (provenance,
dedup, licensing) + a ChromaDB collection of CLIP embeddings (semantic search).

Two scopes (both live inside the project tree per workspace rules):
  * **global**  -> ``_library/images/``           (shared across projects)
  * **project** -> ``projects/<name>/imagelib/``   (per-project collection)
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from nolan.imagelib.catalog import Asset, AssetCatalog, Collection
from nolan.imagelib.embeddings import ClipEmbedder

_COLLECTION = "images"
_DESC_COLLECTION = "descriptions"
# The discovery tier keeps its OWN vector collections. Not a style choice: `search()` looks a
# chroma id up in the catalog and returns the asset, so one shared collection would leak not-held
# rows (no file on disk) into every existing caller. Separate collections make that impossible
# rather than merely unlikely.
_DISC_COLLECTION = "discovery_images"
_DISC_IDENT_COLLECTION = "discovery_identity"
_THUMB_PX = 512
# How much of a catalog TITLE a query must cover before the query counts as NAMING that work (and
# retrieval routes to the identity channel). The lexical matcher itself admits a hit at 0.5, which
# is right for "is this title relevant"; it is too loose for "is this query an identity question" â€”
# a pure LOOK need, "two girls on a terrace with a basket of yarn", covers 2 of the 3 distinctive
# tokens in "Two Sisters (On the Terrace)" and was mis-routed to the identity channel. Measured
# through the real search path (scripts/eval_visuallib_recall.py, 19 needs): see search_discovery.
_NAMED_MIN_COVER = 0.75
_UA = "NOLAN-PictureLibrary/1.0"
_LOG = logging.getLogger("nolan.imagelib")
_REPO = Path(__file__).resolve().parents[3]   # src/nolan/imagelib/store.py -> repo root

# Stop-words dropped before a lexical title match, so a title's DISTINCTIVE tokens carry the signal.
_STOP = {"the", "a", "an", "of", "and", "or", "in", "on", "to", "for", "with", "by", "at", "from",
         "is", "are", "was", "its", "it", "this", "that", "as", "into", "s"}


def _distinctive_tokens(text: str) -> List[str]:
    """Lowercased content tokens (punctuation stripped, stop-words + single chars dropped)."""
    return [t for t in re.sub(r"[^\w\s]", " ", (text or "").lower()).split()
            if len(t) > 1 and t not in _STOP]


_SHARED: Dict[tuple, "ImageLibrary"] = {}


def shared_library(scope: str = "global", project: Optional[str] = None,
                   base_dir: Optional[Path] = None) -> "ImageLibrary":
    """A PROCESS-WIDE ImageLibrary per scope. Build it once; never per request.

    An ImageLibrary is expensive to construct and cheap to keep: it owns a `ClipEmbedder` (a
    ~150 MB model loaded on first use) and a `chromadb.PersistentClient` (which opens the store
    and its HNSW indexes). Constructing one per call re-pays both.

    THE INCIDENT: the hub's `_open_imagelib` did exactly that, and at 1,091 rows nobody noticed.
    At 97,610 rows a single `/api/images/discover` request took **90 seconds** â€” while the same
    search against a reused library took **2.4 s**. The search was never slow; the setup was, and
    it was being paid on every keystroke.

    Long-lived by design, because the hub is one process and chroma's PersistentClient assumes
    single-process ownership anyway. Callers that genuinely need an isolated instance (tests, a
    throwaway scope) construct `ImageLibrary` directly.
    """
    # Keyed on the RESOLVED directory, not on (scope, project). Two scopes pointing at one
    # directory are one library â€” and, more practically, `library_paths` is patchable, so a key
    # that ignored the resolved path would hand a test the instance a previous test built
    # against a different tmp dir. Caught exactly that way.
    base = Path(base_dir) if base_dir else library_paths(scope, project)
    key = str(Path(base).resolve())
    lib = _SHARED.get(key)
    if lib is None:
        lib = ImageLibrary(scope=scope, project=project, base_dir=base)
        _SHARED[key] = lib
    return lib


def reset_shared_libraries() -> None:
    """Drop the process-wide cache. For tests and for a scope whose files moved underneath it."""
    _SHARED.clear()


def library_paths(scope: str = "global", project: Optional[str] = None) -> Path:
    """Resolve the ABSOLUTE base directory for a library scope, anchored to the repo root.

    NOT os.getcwd()-relative: a relative base silently resolved against whatever CWD the process
    ran under, so running acquisition from render-service/_lab_hyperframes/bridge/ (as the hub's
    run_pool does) opened an EMPTY library â€” every library-first need returned 0 with no error, and
    the headline feature was dead on the default path (holbein POST_MORTEM #1)."""
    if scope == "project":
        if not project:
            raise ValueError("project scope requires a project name")
        return _REPO / "projects" / project / "imagelib"
    return _REPO / "_library" / "images"


def _ext_for(url: Optional[str], path: Optional[str]) -> str:
    for cand in (path, url):
        if cand:
            suffix = Path(urlparse(cand).path if "://" in cand else cand).suffix.lower()
            if suffix in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".tiff", ".tif", ".bmp"):
                return suffix
    return ".jpg"


@dataclass
class LibraryHit:
    asset: Asset
    score: float  # cosine similarity (0..1)


@dataclass
class _GateCandidate:
    """The duck-typed shape `asset_gate.check_candidate` reads (url / source_url / thumbnail_url /
    source / license / width / height) â€” so the discovery door gates on the SAME policy tables as
    every provider result, without inventing a second dialect."""
    url: Optional[str] = None
    source_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    source: Optional[str] = None
    license: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


def _shrink(path: Path, max_edge: int) -> None:
    """Cap a thumbnail's long edge in place. Storage is the point of the not-held tier: 512px is
    enough for CLIP (which sees 224px), for a human to recognise the picture, and for the banner
    heuristic â€” a full-size cache would just be the Picture Library again."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            if max(im.size) <= max_edge:
                return
            im = im.convert("RGB") if im.mode in ("P", "CMYK") else im
            im.thumbnail((max_edge, max_edge))
            im.save(path)
    except Exception as e:                       # a thumbnail we can't shrink is still usable
        _LOG.warning("thumbnail shrink failed for %s: %s", path, e)


class ImageLibrary:
    def __init__(self, scope: str = "global", project: Optional[str] = None,
                 base_dir: Optional[Path] = None, embedder: Optional[ClipEmbedder] = None,
                 describer=None):
        self.scope = scope
        self.project = project
        self.base = Path(base_dir) if base_dir else library_paths(scope, project)
        self.files_dir = self.base / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir = self.base / "thumbs"
        self.catalog = AssetCatalog(self.base / "catalog.db")
        self._embedder = embedder
        # describer(path) -> str: generates a vision description for an image.
        # Optional; when set, add_file auto-describes assets that lack one.
        self.describer = describer
        self._client = None
        self._collection = None
        self._desc_collection = None
        self._disc_collection = None
        self._disc_ident_collection = None
        # Pending identity rows, flushed in batches â€” see `flush_index`.
        self._ident_buf: List[tuple] = []

    # ----------------------------------------------------------- lazy backends
    @property
    def embedder(self) -> ClipEmbedder:
        if self._embedder is None:
            self._embedder = ClipEmbedder()
        return self._embedder

    def _coll(self):
        if self._collection is None:
            import chromadb
            from chromadb.config import Settings
            self._client = chromadb.PersistentClient(
                path=str(self.base / "chroma"),
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=_COLLECTION, metadata={"hnsw:space": "cosine"})
        return self._collection

    def _desc_coll(self):
        """Lazy ChromaDB collection of BGE text embeddings of asset descriptions."""
        if self._desc_collection is None:
            from nolan.imagelib.embeddings import description_embedding_function
            self._coll()  # ensure self._client exists
            self._desc_collection = self._client.get_or_create_collection(
                name=_DESC_COLLECTION, metadata={"hnsw:space": "cosine"},
                embedding_function=description_embedding_function())
        return self._desc_collection

    def _disc_coll(self):
        """CLIP embeddings of DISCOVERY thumbnails (the look channel of the not-held tier)."""
        if self._disc_collection is None:
            self._coll()
            self._disc_collection = self._client.get_or_create_collection(
                name=_DISC_COLLECTION, metadata={"hnsw:space": "cosine"})
        return self._disc_collection

    def _disc_ident_coll(self):
        """BGE embeddings of DISCOVERY identity text (title/creator/date/institution).

        The channel CLIP cannot serve: named works cluster tightly in CLIP space (all 46 Holbein
        woodcuts sit at 0.29-0.36 for any query), so a query that NAMES something has to be
        answered from the catalog's own words."""
        if self._disc_ident_collection is None:
            from nolan.imagelib.embeddings import description_embedding_function
            self._coll()
            self._disc_ident_collection = self._client.get_or_create_collection(
                name=_DISC_IDENT_COLLECTION, metadata={"hnsw:space": "cosine"},
                embedding_function=description_embedding_function())
        return self._disc_ident_collection

    # ------------------------------------------------------------------ ingest
    def add_file(self, path, *, url=None, source=None, source_url=None,
                 license=None, title=None, description=None, width=None, height=None,
                 tags=None, query=None, embed=True, describe=True):
        """Add a local image file. Returns (Asset, created: bool).

        Dedups by content hash â€” re-adding the same bytes returns the existing row.
        If ``describe`` and no ``description`` is given and a ``self.describer`` is
        set, a vision description is generated and indexed (BGE text->text search).
        """
        path = Path(path)
        data = path.read_bytes()
        content_hash = hashlib.sha256(data).hexdigest()

        existing = self.catalog.get_by_hash(content_hash)
        if existing:
            return existing, False

        if (width is None or height is None):
            width, height = _probe_dims(path) or (width, height)

        ext = _ext_for(url, str(path))
        rel = Path("files") / content_hash[:2] / f"{content_hash}{ext}"
        dest = self.base / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

        if description is None and describe and self.describer is not None:
            try:
                description = self.describer(dest) or None
            except Exception:
                description = None

        asset = self.catalog.add(Asset(
            content_hash=content_hash, path=str(rel).replace("\\", "/"), url=url,
            source=source, source_url=source_url, license=license, title=title,
            description=description, width=width, height=height, bytes=len(data),
            tags=tags, query=query,
        ))

        if embed:
            vec = self.embedder.embed_image(dest)
            if vec:
                self._coll().add(
                    ids=[str(asset.id)], embeddings=[vec],
                    metadatas=[{"source": source or "", "license": license or ""}])
        if description:
            self._index_description(asset.id, description, source)
        return asset, True

    def _index_description(self, asset_id: int, description: str,
                           source: Optional[str] = None) -> None:
        """Add/replace an asset's description in the BGE text collection."""
        try:
            self._desc_coll().upsert(
                ids=[str(asset_id)], documents=[description],
                metadatas=[{"source": source or ""}])
        except Exception:
            pass

    def add_url(self, url: str, **meta):
        """Download an image URL into a temp file, gate it, then add it.

        The library is a REUSE surface â€” a watermarked or preview-domain file
        ingested once poisons every future project. Gate rejections raise
        ValueError (loud, caller-visible), never a silent skip.
        """
        import tempfile
        from nolan.asset_gate import blocked_host, check_file
        from nolan.http_client import download_file_sync
        host = blocked_host(url)
        if host:
            raise ValueError(f"ingest refused: stock-preview domain ({host}): {url}")
        ext = _ext_for(url, None)
        tmp = Path(tempfile.gettempdir()) / f"nolan_piclib_{abs(hash(url))}{ext}"
        download_file_sync(url, str(tmp), headers={"User-Agent": _UA})
        try:
            verdict = check_file(tmp, tier="stock")
            if not verdict.ok:
                raise ValueError(
                    f"ingest refused ({'; '.join(verdict.reasons)}): {url}")
            meta.setdefault("url", url)
            return self.add_file(tmp, **meta)
        finally:
            tmp.unlink(missing_ok=True)

    def add_result(self, result, *, query=None, embed=True, describe=True):
        """Add an ImageSearchResult / extractor result (downloads its url)."""
        return self.add_url(
            result.url, source=getattr(result, "source", None),
            source_url=getattr(result, "source_url", None),
            license=getattr(result, "license", None),
            title=getattr(result, "title", None),
            description=getattr(result, "description", None),
            width=getattr(result, "width", None), height=getattr(result, "height", None),
            tags=getattr(result, "tags", None), query=query, embed=embed, describe=describe)

    # --------------------------------------------------- discovery tier (Visual Lib)
    def upsert_collection(self, collection: Collection) -> Collection:
        """Register/refresh a harvest unit. Rights assertions are STICKY (see the catalog)."""
        return self.catalog.upsert_collection(collection)

    def _thumb_dest(self, source_ref: str, url: Optional[str]) -> Path:
        h = hashlib.sha256(source_ref.encode("utf-8")).hexdigest()
        return self.thumbs_dir / h[:2] / f"{h}{_ext_for(url, None)}"

    def add_discovery(self, *, source_ref: str, thumb_url: str, source: str,
                      title=None, creator=None, date_text=None, institution=None,
                      description=None, license=None, url=None, source_url=None,
                      width=None, height=None, wikidata_qid=None, collection_id=None,
                      identity_source: str = "catalog", description_source: str = "catalog",
                      tags=None, tier: str = "archival", embed: bool = True,
                      pixels: bool = True,
                      medium=None, classification=None, department=None,
                      culture=None, place=None):
        """Index an image we do NOT hold: catalog metadata + (optionally) a local thumbnail.
        Returns ``(Asset, created)``; re-indexing a known `source_ref` refreshes it in place.

        TWO PHASES, because the pixels dominate the cost. `pixels=False` writes the catalog row
        and NOTHING ELSE â€” no fetch, no thumbnail, no CLIP vector.

        BENCHMARKED, not estimated (60 records then 30 backfills, models pre-warmed):

            Phase A, record + identity index      87 ms/row
            Phase A, record only (embed=False)     9 ms/row   <- BGE is 78 of the 87
            Phase B, fetch + CV + CLIP            470 ms/row
                                                  ------
            ratio                                 5.4x

        Over the 62,035-row artic public-domain catalog that is **1.5 h for records alone
        against 9.6 h for records and pixels** â€” a real 8-hour saving, and deliberately not
        dressed up as more: an earlier estimate of "~50x / 29 hours" did not survive measurement,
        and this module's own history (the artic adapter's unreproducible "11 of every 12" claim)
        is what a comfortable unverified number costs.

        The trade is quantified on the retrieval side too. Identity-only (no pixels at all)
        measures **named 94.7 / 100 / 100** and **look 47.4 / 78.9 / 84.2**; with pixels, look@1
        rises 47.4 â†’ 63.2. So a record-only row is at FULL strength for "find me the Holbein
        woodcut" and materially weaker for "find me something stormy" â€” pixels buy ranking, not
        reach. `backfill_pixels` closes the gap progressively and `discovery_stats` reports how
        far it has got rather than implying it is done.

        ACQUISITION DOOR â€” this fetches bytes from the open internet, so it calls
        ``asset_gate.check_candidate`` before the fetch (blocklisted host / rights floor /
        resolution floor, judged on the FULL image's dimensions, not the thumbnail's) and
        ``asset_gate.banner_suspect`` on the stored thumbnail â€” for every source EXCEPT the
        institutions the gate already classifies as open-access-by-construction (see the
        measurement at the call site). A watermark strip is plainly visible at 512px; gating here
        is what stops the discovery tier becoming a laundering route around the gate that
        `add_url` applies to held assets (the Alamy lesson).

        Rejections raise ValueError. Loud, per the workspace's failure rule: a discovery row that
        silently skipped the gate would be indistinguishable from one that passed it.
        """
        from nolan.asset_gate import (OPEN_ACCESS_SOURCES, banner_suspect,
                                      check_candidate)
        from nolan.http_client import download_file_sync

        if not source_ref:
            raise ValueError("add_discovery requires a stable source_ref (e.g. 'artic:27992')")
        cand = _GateCandidate(url=url or thumb_url, source_url=source_url,
                              thumbnail_url=thumb_url, source=source, license=license,
                              width=width, height=height)
        verdict = check_candidate(cand, tier=tier)
        if not verdict.ok:
            raise ValueError(f"discovery refused ({'; '.join(verdict.reasons)}): {source_ref}")

        existing = self.catalog.get_by_ref(source_ref)
        dest = self._thumb_dest(source_ref, thumb_url)

        if not pixels:
            # PHASE A â€” the record only. No bytes are fetched at all, so the pixel-dependent
            # checks below have nothing to run on and are skipped rather than faked. The RIGHTS
            # gate above still ran: a row entering the library on a bad licence is refused
            # whether or not we downloaded its picture.
            return self._write_discovery_row(
                source_ref=source_ref, existing=existing, rel=None, fresh_thumb=False,
                embed=embed, url=url, source=source, source_url=source_url, title=title,
                description=description, description_source=description_source,
                width=width, height=height, tags=tags, creator=creator, date_text=date_text,
                institution=institution, identity_source=identity_source,
                wikidata_qid=wikidata_qid, collection_id=collection_id, license=license,
                thumb_url=thumb_url, medium=medium, classification=classification,
                department=department, culture=culture, place=place)

        fresh_thumb = not dest.exists()
        if fresh_thumb:
            dest.parent.mkdir(parents=True, exist_ok=True)
            download_file_sync(thumb_url, str(dest), headers={"User-Agent": _UA})
            _shrink(dest, _THUMB_PX)
        # The pixel gate runs on EVERY call, not only after a fresh download: a thumbnail cached by
        # an earlier crawl would otherwise re-enter the library ungated, making the door's behaviour
        # depend on cache state. It is one local PIL read; the cost is noise.
        #
        # The banner heuristic hunts a RIGHTS-MANAGED AGENCY's watermark strip. An institution
        # serving its own CC0 IIIF derivative cannot be serving one, and on museum photography the
        # heuristic's signature â€” a near-uniform band, discontinuous with the body, carrying a few
        # contrasting pixels â€” is just an object shot on a plain mount. CHARACTERISED before
        # scoping it (checklist #11: a check whose failures are all false positives): 4 of 4
        # refusals inspected by eye were false â€” a Piranesi etching on its white paper margin
        # (artic:19), a bed rug and a gold-ground crucifix on black studio ground (artic:49691 /
        # 16231), a Spanish retable on white (artic:88793) â€” at ~1% of a shallow crawl rising to
        # ~5% deeper in, where object photography outnumbers framed paintings. It still runs for
        # every other source, so the Alamy shape it was written for is still caught.
        if source not in OPEN_ACCESS_SOURCES and banner_suspect(dest):
            dest.unlink(missing_ok=True)
            raise ValueError(f"discovery refused (watermark banner strip): {source_ref}")

        # THE CONTENT FLOOR. `check_candidate` above judged the museum's declared dimensions,
        # which describe the FILE â€” and museum object photography is an object on a wide sweep,
        # so the file routinely overstates the asset. Now that a thumbnail is on disk we can
        # measure the content's share and apply the floor to what is actually there: a
        # 3000x1511 coin photo at 31% content is a 2197x644 asset, and 644px does not clear the
        # archival floor however the file is cropped. Characterised over the live corpus before
        # wiring (checklist #10/#11): 7 of 841 rows with declared dimensions newly refused, all
        # coins or small objects on large grounds, every content box inspected by eye; 834 still
        # pass. Rows whose source publishes no pixel dimensions (the Met, which publishes
        # physical size) are unaffected â€” there is nothing to scale.
        if width and height:
            from nolan.asset_gate import clears_floor
            from nolan.pixels import effective_dims
            eff = effective_dims(dest, declared=(int(width), int(height)))
            if eff and not clears_floor(eff[0], eff[1], tier):
                dest.unlink(missing_ok=True)
                raise ValueError(
                    f"discovery refused (content {eff[0]}x{eff[1]} below the {tier} floor; "
                    f"declared {width}x{height} is mostly dead margin): {source_ref}")

        rel = str(dest.relative_to(self.base)).replace("\\", "/")
        return self._write_discovery_row(
            source_ref=source_ref, existing=existing, rel=rel, fresh_thumb=fresh_thumb,
            embed=embed, url=url, source=source, source_url=source_url, title=title,
            description=description, description_source=description_source,
            width=width, height=height, tags=tags, creator=creator, date_text=date_text,
            institution=institution, identity_source=identity_source,
            wikidata_qid=wikidata_qid, collection_id=collection_id, license=license,
            thumb_url=thumb_url, medium=medium, classification=classification,
            department=department, culture=culture, place=place)

    def _write_discovery_row(self, *, source_ref, existing, rel, fresh_thumb, embed,
                             thumb_url, description_source="catalog", **fields):
        """Insert-or-refresh one discovery row and index its channels.

        Shared by both crawl phases. `rel` is the stored thumbnail path, or None for a Phase-A
        record-only row â€” in which case `path` is empty and the CLIP channel is simply not
        populated, because there are no pixels to embed. `thumb_url` is recorded either way, so
        Phase B can fetch the picture later without re-walking the source.
        """
        from nolan.imagelib.taxonomy import image_kind as _kind

        fields = {k: v for k, v in fields.items()}
        fields["thumb_path"] = rel
        fields["thumb_url"] = thumb_url
        # DERIVED, never asked of a model: the institution already catalogued the object, and a
        # regex over its own words beat the VLM on every row where the two disagreed. Order is
        # authority order â€” classification, then the type tag, then the medium (the Art Institute
        # puts "painting" and "oil on canvas" in the SAME column, so one field is not enough).
        fields["image_kind"] = _kind(fields.get("classification"), fields.get("tags"),
                                     fields.get("medium"), fields.get("description"))
        # The museum's date STRING, parsed into something a filter can compare. Derived, so it is
        # re-derivable â€” `rederive_kinds` recomputes both without a network call.
        from nolan.imagelib.dates import parse_years
        yrs = parse_years(fields.get("date_text"))
        if yrs:
            fields["year_from"], fields["year_to"] = yrs
        if fields.get("description"):
            fields["description_source"] = description_source
        if existing is not None:
            # A re-crawl refreshes the CATALOG's own facts, but must not clobber a T2 caption with
            # the source's one-line prose â€” so a row already carrying a model description keeps it.
            if (existing.description_source or "catalog") != "catalog":
                fields.pop("description", None)
                fields.pop("description_source", None)
            self.catalog.update(existing.id, **{k: v for k, v in fields.items() if v is not None})
            asset = self.catalog.get(existing.id)
            created = False
        else:
            asset = self.catalog.add(Asset(
                content_hash=f"ref:{hashlib.sha256(source_ref.encode('utf-8')).hexdigest()}",
                path=rel or "", held=0, source_ref=source_ref, **fields))
            created = True
        if embed:
            # A re-crawl re-embedded every unchanged row â€” at catalog scale that is the whole cost
            # of the crawl for no new information. Embed the thumbnail only when it is actually new,
            # and the identity text only when it actually changed.
            thumb = (self.base / rel) if rel else None
            self._index_discovery(
                asset, thumb, clip=bool(rel) and (created or fresh_thumb),
                ident=created or (existing.identity_text() != asset.identity_text()))
        return asset, created

    def locate_subjects(self, *, limit: int = 200, collection_id: Optional[int] = None,
                        prefer: str = "energy", progress=None) -> dict:
        """Fill the `regions` column â€” the producer it has been waiting for.

        The column shipped unpopulated because it was consumer-blocked; the camera umbrella
        un-blocked it with `solve_push(target=)`. This is the other half, and it is a DETECTOR
        (`nolan.regions`), never a vision model: asked for a focal cell, a VLM answered
        middle-centre on 50 of 50 rows.

        Rows with no separable subject are left NULL rather than given a centre box â€” "we could
        not locate one" and "it is in the middle" must stay distinguishable, or every consumer
        inherits a guess it cannot detect.
        """
        from nolan.regions import detect_subject, regions_json

        out = {"examined": 0, "located": 0, "no_subject": 0}
        for a in self.catalog.list(status="active", held=0, collection_id=collection_id,
                                   limit=max(limit * 4, 200)):
            if out["examined"] >= limit:
                break
            if not a.thumb_path or a.regions:
                continue
            thumb = (self.base / a.thumb_path)
            if not thumb.exists():
                continue
            out["examined"] += 1
            r = detect_subject(thumb, prefer=prefer)
            if r is None:
                out["no_subject"] += 1
                continue
            self.catalog.update(a.id, regions=regions_json([r]))
            out["located"] += 1
            if progress:
                progress(out)
        return out

    def rederive_kinds(self, *, collection_id: Optional[int] = None) -> dict:
        """Recompute every DERIVED catalog column from data already on disk. No network, no model.

        This is what makes the derivations safe to change. A caption is expensive to redo (the
        reason `caption_schema` is versioned), but a bucket derived from the institution's own
        words costs one SQL pass â€” so the vocabulary can be corrected the moment a source turns
        out to catalogue garments as "Collar" and "Cap" rather than as textiles.

        Four columns, one pass, because they share the expensive part (walking 97k rows):
        `image_kind` from the classification vocabulary, `year_from`/`year_to` from the date
        prose, and `artist_key` from the creator string. `movement` is derived too but needs the
        artists table, so it delegates to `backfill_movements`.

        Returns the kind histogram INCLUDING `unknown`, because a derivation whose fallthrough
        rate nobody looks at is a silent cap.
        """
        from nolan.imagelib.catalog import folded_artist
        from nolan.imagelib.dates import parse_years
        from nolan.imagelib.taxonomy import IMAGE_KINDS, image_kind as _kind

        counts = {k: 0 for k in IMAGE_KINDS}
        changed = dated = undated = attributed = anonymous = 0
        patches: dict = {}
        for a in self.catalog.list(status="active", held=None,
                                   collection_id=collection_id, limit=1_000_000):
            patch = {}
            k = _kind(a.classification, a.tags, a.medium, a.description)
            counts[k] += 1
            if k != (a.image_kind or None):
                patch["image_kind"] = k
            yrs = parse_years(a.date_text)
            if yrs:
                dated += 1
                if (a.year_from, a.year_to) != yrs:
                    patch["year_from"], patch["year_to"] = yrs
            else:
                undated += 1
            ak = folded_artist(a.creator)
            if ak:
                attributed += 1
            elif a.creator:
                anonymous += 1           # a creator string that names no one â€” see _is_anonymous
            if ak != (a.artist_key or None):
                patch["artist_key"] = ak
            if patch:
                patches[a.id] = patch
                # ONE transaction per chunk, not per row â€” see `update_many`. Chunked rather than
                # held to the end so a long pass makes durable progress and can be interrupted.
                if len(patches) >= 2000:
                    changed += self.catalog.update_many(patches)
                    patches = {}
        changed += self.catalog.update_many(patches)
        mv = self.backfill_movements(collection_id=collection_id)
        total = sum(counts.values()) or 1
        return {"counts": counts, "changed": changed, "total": total,
                "unknown_pct": round(100.0 * counts["unknown"] / total, 1),
                "dated": dated, "undated": undated,
                "dated_pct": round(100.0 * dated / total, 1),
                "attributed": attributed, "anonymous": anonymous,
                "attributed_pct": round(100.0 * attributed / total, 1),
                "movement": mv}

    def enrich_pdia_details(self, *, limit: int = 500, workers: int = 4,
                            recheck_rights: bool = False, progress=None) -> dict:
        """PHASE A2 for PDIA: the fields its listing does not carry.

        The listing is enough to index a row; this pass is what makes the row good. It adds:

        * **THE HOLDING INSTITUTION.** PDIA is an aggregator â€” its images are re-hosted from the
          Met, the Library of Congress, the Internet Archive. `source` stays `pdia` (where we
          found it) and `institution` becomes the holder (whose picture it is), which is both
          more honest and what a credit line needs.
        * **SUBJECT, for the first time in this library.** `classification` is a medium and
          `culture` is a place; nothing until now answered "pictures about ghosts". PDIA's themes
          ("Ghosts & Occult", "The Future", "Natural World") and tags ("yokai", "retrofuturism",
          "thunderbolts") go into `tags`, which is already filterable and already embedded.
        * **THE TWO RIGHTS CLAIMS**, verified rather than assumed. The site declares CC0
          throughout and every sample agrees, but an aggregator's blanket statement is not a
          per-item guarantee â€” the exact trap the Library of Congress probe flagged. A row whose
          rights code is not in `_PDIA_RIGHTS_OPEN` is NOT relabelled and is reported, so an
          unreadable claim surfaces instead of being waved through.

        Bounded by `limit` and re-runnable: rows already carrying a holder are skipped, so this
        can be run in slices against 11,197 rows without redoing work.
        """
        from nolan.imagelib.harvest import (pdia_details, pdia_is_free_worldwide,
                                            pdia_license)

        # `recheck_rights` re-reads rows that ALREADY have a holder. Needed when the rights
        # PARSER changes rather than the data: 873 pages link to `/rights-labelling-on-our-site#`
        # with an empty fragment, so before that was handled they parsed as unreadable, kept the
        # harvest's default CC0 label, and were skipped by the ordinary selector precisely
        # BECAUSE the same pass had already given them an institution. A row wrongly labelled CC0
        # is the one kind of staleness that cannot be left to the next crawl.
        pool = self.catalog.list(status="active", held=0, limit=limit * 4, source="pdia")
        if recheck_rights:
            rows = [a for a in pool
                    if a.license == "CC0 (Public Domain Image Archive)"][:limit]
        else:
            rows = [a for a in pool
                    if a.institution in (None, "", "Public Domain Image Archive")][:limit]
        out = {"attempted": len(rows), "enriched": 0, "unparsed": 0,
               "rights_unrecognised": 0, "not_free_worldwide": 0, "themes_seen": 0, "reasons": []}
        if not rows:
            return out

        # CHUNKED, so the pass makes DURABLE PROGRESS. A first version fetched all 11,197 pages
        # and then wrote once: nothing landed for the best part of an hour, a kill lost the whole
        # run, and a progress monitor watching the database saw a flat line and could not tell a
        # working pass from a dead one. Same checkpoint rule as the crawl cursor — write as you
        # go, at a boundary you can resume from.
        for i in range(0, len(rows), self._PDIA_DETAIL_CHUNK):
            self._enrich_pdia_chunk(rows[i:i + self._PDIA_DETAIL_CHUNK], out,
                                    workers=workers, progress=progress)
        return out

    # ~60s of fetching per chunk at 4 workers — often enough that a kill costs a minute, rare
    # enough that the write and re-embed overhead stays noise.
    _PDIA_DETAIL_CHUNK = 200

    def _enrich_pdia_chunk(self, rows, out: dict, *, workers: int, progress=None) -> None:
        """One chunk: fetch, patch, re-embed, commit. See `enrich_pdia_details`."""
        from nolan.imagelib.harvest import (pdia_details, pdia_is_free_worldwide,
                                            pdia_license)

        by_uuid = {(a.source_ref or "").split(":", 1)[-1]: a for a in rows}
        got = pdia_details(list(by_uuid), workers=workers)
        out["unparsed"] += len(by_uuid) - len(got)

        patches: Dict[int, dict] = {}
        for uuid, d in got.items():
            a = by_uuid.get(uuid)
            if a is None:
                continue
            subject = [*(d.get("themes") or []), *(d.get("tags") or [])]
            patch: Dict[str, Any] = {}
            if d.get("institution"):
                patch["institution"] = d["institution"]
            if d.get("styles"):
                patch["classification"] = ", ".join(d["styles"])
            if subject:
                patch["tags"] = ", ".join(subject)
                out["themes_seen"] += len(d.get("themes") or [])
            # The description is what BGE embeds, so the subject words have to reach it or the
            # themes would be filterable but not FINDABLE â€” an authored field with only half a
            # consumer.
            bits = [d.get("encompassing_work"), *(d.get("styles") or []), *subject]
            desc = ", ".join(b for b in bits if b)
            if desc and desc != (a.description or ""):
                patch["description"] = desc
            # RIGHTS ARE CORRECTED HERE, not merely recorded. The harvest stamps every row CC0
            # from the site's blanket claim; the per-image page is the first place we learn that
            # a work is `pd-us` â€” public domain in the United States ONLY. Leaving those labelled
            # CC0 would be the transcript library's re-labelling incident in reverse: a
            # permissive label asserted by a pass that did not know better.
            lic = pdia_license(d.get("underlying_rights"), d.get("digital_rights"))
            if lic is None:
                out["rights_unrecognised"] += 1
                if len(out["reasons"]) < 12:
                    codes = sorted({d.get("underlying_rights"), d.get("digital_rights")} - {None})
                    out["reasons"].append(f"pdia:{uuid}: unrecognised rights {codes} â€” "
                                          f"left as harvested, NOT relabelled")
            else:
                if lic != (a.license or ""):
                    patch["license"] = lic
                if not pdia_is_free_worldwide(d.get("underlying_rights"),
                                              d.get("digital_rights")):
                    out["not_free_worldwide"] += 1
            if patch:
                patches[a.id] = patch
        out["enriched"] += self.catalog.update_many(patches)
        # RE-EMBED, don't "reindex". The identity text changed for every enriched row, and
        # `reindex_identity` only fills rows MISSING from the vector store â€” it would examine
        # these, find them present, and do nothing, leaving the themes filterable but not
        # findable. Re-buffering upserts the new text over the old.
        if patches:
            for a in self.catalog.get_many(list(patches)).values():
                self._buffer_identity(a)
            out["reembedded"] = out.get("reembedded", 0) + self.flush_index()
        if progress:
            progress(out)

    def enrich_pdia_collections(self, *, limit: int = 600, workers: int = 4,
                                progress=None) -> dict:
        """Give each curated PDIA collection its real title and the editors' blurb.

        TWO REQUESTS PER COLLECTION, NOT PER IMAGE. The Public Domain Review URL appears only on
        an image's own page, so this samples ONE member per collection to learn it, then fetches
        the essay once. For 577 collections that is ~1,154 requests instead of re-walking 11,197
        — and it is the dedup you get for free by keying on the collection rather than the row.

        Idempotent: a collection that already has a description is skipped, so this can be run in
        slices and re-run after a new harvest without re-fetching what it already knows.
        `upsert_collection` is rights-sticky, so nothing here can disturb the CC0 assertion.
        """
        from concurrent.futures import ThreadPoolExecutor

        from nolan.imagelib import Collection
        from nolan.imagelib.harvest import pdia_detail, pdr_collection_page

        todo = [c for c in self.catalog.list_collections()
                if c.source == "pdia" and c.upstream_count is None and not c.description][:limit]
        out = {"attempted": len(todo), "described": 0, "no_pdr_link": 0, "errors": 0,
               "reasons": []}
        if not todo:
            return out

        counts = self.catalog.collection_counts(held=0)

        def _one(c):
            try:
                # one member is enough to learn where the collection lives
                rows = self.catalog.list(status="active", held=0, limit=1, collection_id=c.id)
                if not rows:
                    return c, None, "no members"
                uuid = (rows[0].source_ref or "").split(":", 1)[-1]
                det = pdia_detail(uuid)
                url = det.get("collection_url")
                if not url:
                    return c, None, "no PDR link on the member page"
                page = pdr_collection_page(url)
                return c, {"url": url, "title": det.get("collection_title") or page.get("title"),
                           "description": page.get("description")}, None
            except Exception as e:
                return c, None, f"{type(e).__name__}: {e}"

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for c, got, err in pool.map(_one, todo):
                if err or not got:
                    if err == "no PDR link on the member page":
                        out["no_pdr_link"] += 1
                    else:
                        out["errors"] += 1
                    if len(out["reasons"]) < 12:
                        out["reasons"].append(f"{c.slug}: {err or 'nothing returned'}")
                    continue
                if not got.get("description"):
                    out["no_pdr_link"] += 1
                    continue
                self.upsert_collection(Collection(
                    slug=c.slug, source="pdia",
                    # The harvest guessed a title from the slug; the real one is better and this
                    # is where it lands.
                    title=got.get("title") or c.title,
                    description=got["description"], url=got["url"]))
                out["described"] += 1
                if progress:
                    progress(out)
        out["collections_total"] = len(counts)
        return out

    def backfill_movements(self, *, collection_id: Optional[int] = None) -> dict:
        """Copy `artists.movement` down onto every row that artist made.

        DERIVED AND THEREFORE STALE-ABLE: the artists table grows one LLM call at a time, so a
        movement learned today belongs on rows harvested last week. Idempotent and cheap (one
        catalog walk, no network), called by `rederive_kinds` and on the way out of
        `enrich_artists` â€” which is what keeps the facet honest without anyone remembering to.

        The join is on the FOLDED key, not the raw name: exact-name matching reaches 24,946 rows
        where the folded key reaches 31,091, because Cleveland writes "Auguste Louis LepÃ¨re
        (French, 1849-1918)" for artic's "Louis Auguste LepÃ¨re".

        Normalisation is not a `.lower()`. Measured over the live table, 106 raw strings fold to
        101 by case alone â€” the real mess is elsewhere: "aestheticism, tonalism" is two movements
        in one cell, "early photography, topographical photography" and "early photography /
        topographic" are the same one written twice, and "none; primarily a documentarian" is not
        a movement at all. See `normalise_movement`.
        """
        from nolan.imagelib.artists import normalise_movement
        from nolan.imagelib.catalog import artist_key

        # key -> display form, picking the dominant original casing so the UI shows "Ukiyo-e" and
        # "Dutch Golden Age" rather than the lowercased key used to group them.
        by_key: "Dict[str, str]" = {}
        votes: "Dict[str, Dict[str, int]]" = {}
        for ar in self.catalog.list_artists(limit=100_000):
            m = normalise_movement(ar.movement)
            if not m:
                continue
            k = artist_key(ar.name)
            if k:
                by_key[k] = m
            votes.setdefault(m.casefold(), {})
            votes[m.casefold()][m] = votes[m.casefold()].get(m, 0) + 1
        # CAPITALISATION WINS BEFORE POPULARITY. Movements are proper nouns, and every other
        # entry in the facet is written that way â€” a bare vote gave "ukiyo-e" (14 artists) over
        # "Ukiyo-e" (10) and the list read as though one entry had been mis-entered. 14-vs-10 is
        # a coin flip on a house style, not evidence about how the movement is spelled.
        display = {k: max(v.items(), key=lambda t: (t[0][:1].isupper(), t[1], -len(t[0])))[0]
                   for k, v in votes.items()}

        changed = covered = 0
        patches: dict = {}
        for a in self.catalog.list(status="active", held=None,
                                   collection_id=collection_id, limit=1_000_000):
            m = by_key.get(artist_key(a.creator)) if a.creator else None
            m = display.get(m.casefold()) if m else None
            if m:
                covered += 1
            if m != (a.movement or None):
                patches[a.id] = {"movement": m}
                if len(patches) >= 2000:
                    changed += self.catalog.update_many(patches)
                    patches = {}
        changed += self.catalog.update_many(patches)
        return {"changed": changed, "covered": covered,
                "movements": len(display), "artists_with_movement": len(by_key)}

    def _fetch_thumb(self, source_ref: str, thumb_url: str) -> Path:
        """Download + shrink one thumbnail. Pure I/O, safe to run on a worker thread."""
        from nolan.http_client import download_file_sync

        dest = self._thumb_dest(source_ref, thumb_url)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            download_file_sync(thumb_url, str(dest), headers={"User-Agent": _UA})
            _shrink(dest, _THUMB_PX)
        return dest

    def warm_pixels(self, assets, *, concurrency: int = 8, tier: str = "archival",
                    embed: bool = True) -> dict:
        """Fetch pixels for a HANDFUL of rows right now â€” the on-demand path behind search.

        Retrieval returns a page of results; the ones a human is about to look at are exactly the
        ones worth spending pixels on.

        WHAT IS ACTUALLY PARALLEL, stated precisely because a first version of the test measured
        the wrong thing and "reported" a speed-up it had not achieved: the **fetch** runs
        `concurrency`-wide, because it is nearly all network. The gates, the CLIP embed and the
        SQLite write stay SERIAL â€” the embedder is not documented thread-safe and the catalog
        serialises writes through one lock anyway.

        So the honest cost model for a page of 24 is: fetch â‰ˆ (24/8) x one round-trip, plus
        ~103 ms/row of embedding that does not parallelise. The embed is therefore the floor,
        not the network â€” which is the opposite of what the original 1.7 s/row estimate implied,
        and worth knowing before anyone tries to make this faster by widening the pool.

        `embed=False` fetches the thumbnail and runs the gates but SKIPS the CLIP vector.
        Measured: the download-and-gate is ~48 ms/row concurrent, the CLIP embed ~103 ms/row â€”
        so a page that only needs pictures to LOOK AT costs about a third. The row keeps its
        `thumb_path`, so it displays and is never re-fetched; it simply does not join the look
        channel until something embeds it. `backfill_pixels` remains the way to do that in bulk.
        """
        from concurrent.futures import ThreadPoolExecutor

        # RESOLVE FIRST, so the button does the same thing whichever museum a row came from.
        # Met rows indexed from the bulk dump carry no `thumb_url` (the CSV has no image column),
        # and filtering on it here meant "Get thumbnails" quietly filled in the artic and
        # Cleveland cards and left every Met card blank with nothing said. A page of 24 costs ~3
        # round trips 8-wide, which is the right price for an explicit click.
        candidates = [a for a in assets if a is not None and not a.thumb_path]
        self._resolve_missing_thumb_urls(candidates)
        todo = [a for a in candidates if a.thumb_url]
        out = {"attempted": len(todo), "fetched": 0, "refused": 0, "errors": 0, "reasons": []}
        # NOT SILENT: a row the source has no image for is a real outcome and is counted, not
        # dropped on the floor.
        unresolvable = len(candidates) - len(todo)
        if unresolvable:
            out["no_image_upstream"] = unresolvable
        if not todo:
            return out

        downloaded: Dict[int, Path] = {}
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = {pool.submit(self._fetch_thumb, a.source_ref, a.thumb_url): a
                       for a in todo}
            for fut, a in futures.items():
                try:
                    downloaded[a.id] = fut.result()
                except Exception as e:
                    out["errors"] += 1
                    if len(out["reasons"]) < 12:
                        out["reasons"].append(f"{a.source_ref}: {type(e).__name__}: {e}")

        for a in todo:
            dest = downloaded.get(a.id)
            if dest is None:
                continue
            verdict = self._gate_fetched_thumb(a, dest, tier=tier)
            if verdict is not None:
                out["refused"] += 1
                if len(out["reasons"]) < 12:
                    out["reasons"].append(f"{a.source_ref}: {verdict}")
                self.catalog.set_status(a.id, "rejected")
                continue
            rel = str(dest.relative_to(self.base)).replace("\\", "/")
            self.catalog.update(a.id, thumb_path=rel, path=rel)
            if embed:
                self._index_discovery(self.catalog.get(a.id), dest, clip=True, ident=False)
            out["fetched"] += 1
        out["embedded"] = out["fetched"] if embed else 0
        return out

    def _gate_fetched_thumb(self, asset: Asset, dest: Path, *, tier: str) -> Optional[str]:
        """Run the gates that need pixels. Returns a refusal reason, or None if it passes.

        One implementation for both the batch backfill and the on-demand warm path â€” the same
        picture must not be admitted by one door and refused by the other.
        """
        from nolan.asset_gate import OPEN_ACCESS_SOURCES, banner_suspect, clears_floor
        from nolan.pixels import effective_dims

        if asset.source not in OPEN_ACCESS_SOURCES and banner_suspect(dest):
            dest.unlink(missing_ok=True)
            return "watermark banner strip"
        if asset.width and asset.height:
            eff = effective_dims(dest, declared=(int(asset.width), int(asset.height)))
            if eff and not clears_floor(eff[0], eff[1], tier):
                dest.unlink(missing_ok=True)
                return f"content {eff[0]}x{eff[1]} below the {tier} floor"
        return None

    def _resolve_missing_thumb_urls(self, rows) -> int:
        """Fill in `thumb_url` for record-only rows whose source enumerates records WITHOUT
        image urls. Returns how many were resolved.

        This is the second half of the Met's CSV-first Phase A. The dump has 54 columns and
        every field the catalog indexes, but no image column â€” so Phase A reads 248,472 records
        for zero requests and the per-object request lands HERE instead, on rows something has
        decided are worth 470 ms of pixel work. Spending it per row that wants pixels rather
        than per row that exists is the whole saving: ~11% on top of Phase B, against ~7.6 hours
        on top of Phase A.

        A row the source has no usable image for keeps `thumb_url = NULL` and is simply never a
        pixel candidate again â€” the resolver returns that as a real answer, so it costs one
        request ever, not one per backfill run.
        """
        from nolan.imagelib.harvest import SOURCES

        by_source: Dict[str, list] = {}
        for a in rows:
            if a.thumb_url or not a.source_ref:
                continue
            adapter = SOURCES.get(a.source or "")
            if adapter is not None and adapter.resolve_image_urls is not None:
                by_source.setdefault(a.source, []).append(a)

        n = 0
        for source, pending in by_source.items():
            got = SOURCES[source].resolve_image_urls([a.source_ref for a in pending])
            patches = {}
            for a in pending:
                found = got.get(a.source_ref)
                if not found or not found.get("thumb_url"):
                    continue
                a.thumb_url, a.url = found["thumb_url"], found.get("url") or a.url
                patches[a.id] = {"thumb_url": a.thumb_url, "url": a.url}
            n += self.catalog.update_many(patches)
        return n

    def backfill_pixels(self, *, limit: int = 200, collection_id: Optional[int] = None,
                        tier: str = "archival", concurrency: int = 8, progress=None) -> dict:
        """PHASE B â€” fetch thumbnails for record-only rows, so `look` retrieval grows over time.

        Deliberately incremental and bounded: measured at 470 ms/row, the whole artic
        public-domain catalog is ~8 hours of pixels, so this is meant to be run repeatedly (a
        cron, a background job, an idle hour) with coverage reported honestly in between rather
        than as one heroic job that must not fail.

        Every gate that Phase A could not run â€” the banner heuristic and the content-resolution
        floor â€” runs HERE, at the moment the pixels first exist, through the SAME
        `_gate_fetched_thumb` the on-demand `warm_pixels` path uses. One implementation, because
        the same picture must not be admitted by one door and refused by the other.

        The fetch runs `concurrency`-wide: it is nearly all network, and a serial batch spends
        its whole wall-clock waiting on museum CDNs.
        """
        pool_rows = [a for a in self.catalog.list(status="active", held=0,
                                                  collection_id=collection_id,
                                                  limit=max(limit * 4, 200))
                     if not a.thumb_path]
        resolved = self._resolve_missing_thumb_urls(pool_rows[:limit * 2])
        rows = [a for a in pool_rows if a.thumb_url][:limit]

        out = {"attempted": 0, "fetched": 0, "refused": 0, "errors": 0,
               "urls_resolved": resolved, "reasons": []}
        # Chunked so `progress` still ticks during a long run and a crash loses at most a chunk.
        step = max(1, concurrency * 2)
        for i in range(0, len(rows), step):
            res = self.warm_pixels(rows[i:i + step], concurrency=concurrency, tier=tier)
            for k in ("attempted", "fetched", "refused", "errors"):
                out[k] += res[k]
            out["reasons"].extend(res["reasons"][:max(0, 12 - len(out["reasons"]))])
            if progress:
                progress(out)
        return out

    # ------------------------------------------------------- batched identity indexing
    #
    # The identity channel used to upsert ONE document per row, so chroma ran a BGE forward pass
    # at batch size 1, once per row. Measured: 78 of the 87 ms it costs to index a record â€” the
    # SQLite write itself is 9 ms. At catalog scale that is the whole cost of a crawl.
    #
    # Buffering turns it into one forward pass per BATCH. MEASURED over a 300-row crawl:
    # **87 -> 32 ms/row, a 2.7x speed-up** â€” worth having, and worth stating exactly, because the
    # estimate before measuring was 15-20 ms/row and that would have been wrong by 2x. Across the
    # ~290k rows still to crawl it is 7.0 h against 2.6 h.
    #
    # The correctness hazard is a row landing in SQLite while its embedding is still in memory:
    # it would be invisible to identity search and a re-crawl would NOT fix it, because a refresh
    # with unchanged identity deliberately skips re-embedding. Three things contain that â€”
    # `flush_index()` runs before the crawl cursor is ever advanced (so the cursor can never run
    # ahead of the index), any READ flushes first (so batching is invisible to a reader), and
    # `reindex_identity()` repairs a gap a hard kill still manages to leave.
    _IDENT_BATCH = 128

    def flush_index(self) -> int:
        """Embed and upsert everything buffered. Returns how many rows were written."""
        buf, self._ident_buf = self._ident_buf, []
        if not buf:
            return 0
        try:
            self._disc_ident_coll().upsert(
                ids=[b[0] for b in buf],
                documents=[b[1] for b in buf],
                metadatas=[b[2] for b in buf])
        except Exception as e:
            _LOG.warning("batched identity index failed for %d rows: %s", len(buf), e)
            return 0
        return len(buf)

    def reindex_identity(self, *, limit: int = 100_000, collection_id: Optional[int] = None,
                         progress=None) -> dict:
        """Repair: embed any discovery row missing from the identity collection.

        Exists because batching makes a gap POSSIBLE (a hard kill between the SQLite write and
        the flush) and a re-crawl cannot close it â€” `_index_discovery` skips re-embedding a
        refreshed row whose identity has not changed, which is the right call for cost and the
        wrong one for a hole.
        """
        self.flush_index()
        coll = self._disc_ident_coll()
        rows = [a for a in self.catalog.list(status="active", held=0,
                                             collection_id=collection_id, limit=limit)
                if a.identity_text()]
        out = {"examined": len(rows), "missing": 0, "indexed": 0}
        step = 500
        for i in range(0, len(rows), step):
            chunk = rows[i:i + step]
            try:
                have = set(coll.get(ids=[str(a.id) for a in chunk]).get("ids") or [])
            except Exception as e:
                _LOG.warning("reindex probe failed: %s", e)
                continue
            for a in chunk:
                if str(a.id) in have:
                    continue
                out["missing"] += 1
                self._buffer_identity(a)
            out["indexed"] += self.flush_index()
            if progress:
                progress(out)
        return out

    def _buffer_identity(self, asset: Asset) -> None:
        text = asset.identity_text()
        if not text:
            return
        self._ident_buf.append((str(asset.id), text, {
            "source": asset.source or "", "license": asset.license or "",
            "collection_id": asset.collection_id or 0}))
        if len(self._ident_buf) >= self._IDENT_BATCH:
            self.flush_index()

    def _index_discovery(self, asset: Asset, thumb: Optional[Path], *, clip: bool = True,
                         ident: bool = True) -> None:
        """Both discovery channels for one row: CLIP over the thumbnail (look) and BGE over the
        catalog identity (names). Either may fail independently without losing the other.

        `thumb` is None on a Phase-A record-only row; the identity channel still indexes, which
        is why such a row is at full strength for named queries and absent from look ranking.
        """
        meta = {"source": asset.source or "", "license": asset.license or "",
                "collection_id": asset.collection_id or 0}
        if clip and thumb is not None:
            try:
                vec = self.embedder.embed_image(thumb)
                if vec:
                    self._disc_coll().upsert(ids=[str(asset.id)], embeddings=[vec],
                                             metadatas=[meta])
            except Exception as e:
                _LOG.warning("discovery CLIP index failed for %s: %s", asset.source_ref, e)
        if ident:
            # BUFFERED, not written â€” see the batching note above. Callers that need it durable
            # right now (a single add, a test, the end of a crawl) call `flush_index()`.
            self._buffer_identity(asset)

    def promote_to_held(self, asset_id: int, *, tier: str = "archival", embed: bool = True,
                        describe: bool = False):
        """Fetch a discovery row's real bytes and flip it to held=1 â€” the ONE edge between the
        two tiers. Returns ``(Asset, promoted)``; ``promoted=False`` means the bytes were already
        in the library under another row (deduped by content hash) and this row was retired.

        Named for the axis it moves along: `promote_to_global` (module level) moves an asset
        between SCOPES (project â†’ global). This moves it between TIERS. One word for two
        different decisions is how dialects start.

        ACQUISITION DOOR: gates the downloaded FILE (`check_file`) exactly as `add_url` does.
        """
        import tempfile

        from nolan.asset_gate import blocked_host, check_file
        from nolan.http_client import download_file_sync

        a = self.catalog.get(asset_id)
        if a is None:
            raise ValueError(f"asset {asset_id} not found")
        if a.held:
            return a, False
        if not a.url:
            raise ValueError(f"asset {asset_id} ({a.source_ref}) has no full-image url to fetch")
        host = blocked_host(a.url)
        if host:
            raise ValueError(f"promotion refused: stock-preview domain ({host}): {a.url}")

        ext = _ext_for(a.url, None)
        tmp = Path(tempfile.gettempdir()) / f"nolan_piclib_promote_{asset_id}{ext}"
        download_file_sync(a.url, str(tmp), headers={"User-Agent": _UA})
        try:
            verdict = check_file(tmp, tier=tier)
            if not verdict.ok:
                raise ValueError(
                    f"promotion refused ({'; '.join(verdict.reasons)}): {a.source_ref}")
            data = tmp.read_bytes()
            content_hash = hashlib.sha256(data).hexdigest()
            twin = self.catalog.get_by_hash(content_hash)
            if twin is not None and twin.id != a.id:
                # These bytes are already held under another row. Retire the discovery row rather
                # than creating a second copy â€” but KEEP it (status, not delete) so its source_ref
                # stays claimed and a re-crawl doesn't resurrect the duplicate every pass.
                self.set_status(a.id, "duplicate")
                return twin, False
            rel = Path("files") / content_hash[:2] / f"{content_hash}{ext}"
            dest = self.base / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            w, h = _probe_dims(dest) or (a.width, a.height)
            self.catalog.update(a.id, content_hash=content_hash,
                                path=str(rel).replace("\\", "/"), held=1,
                                bytes=len(data), width=w, height=h)
        finally:
            tmp.unlink(missing_ok=True)

        asset = self.catalog.get(a.id)
        for coll in (self._disc_coll, self._disc_ident_coll):   # it is held now; leave the tier
            try:
                coll().delete(ids=[str(asset.id)])
            except Exception:
                pass
        if embed:
            vec = self.embedder.embed_image(self.abs_path(asset))
            if vec:
                self._coll().add(ids=[str(asset.id)], embeddings=[vec],
                                 metadatas=[{"source": asset.source or "",
                                             "license": asset.license or ""}])
        if describe and self.describer is not None and not (asset.description or "").strip():
            try:
                desc = self.describer(self.abs_path(asset))
            except Exception:
                desc = None
            if desc:
                self.catalog.set_description(asset.id, desc)
                asset = self.catalog.get(asset.id)
        if (asset.description or "").strip():
            self._index_description(asset.id, asset.description, asset.source)
        return asset, True

    def facets(self, field: str, **filters) -> List[tuple]:
        """Value â†’ count for one facet, under the active filters. See `AssetCatalog.facets`."""
        return self.catalog.facets(field, **filters)

    def search_discovery(self, query: str, *, k: int = 12, offset: int = 0,
                         collection_id: Optional[int] = None,
                         warm: bool = False, warm_concurrency: int = 8,
                         warm_embed: bool = True, use_clip: bool = True,
                         **facets) -> List[LibraryHit]:
        """Search the NOT-HELD tier. Three channels, ROUTED by what the query is asking for.

        A query that NAMES something ("Seurat, La Grande Jatte") is an identity question, answered
        from the catalog's own words; a query about LOOK ("a rainy cobbled boulevard under
        umbrellas") is answered by CLIP over the thumbnail. The routing decides which channel
        DOMINATES â€” the other stays as a small assist, and the lexical title cover rides in as a
        BONUS rather than a hard prefix.

        Every part of that shape was measured through THIS code path, not assumed
        (`scripts/eval_visuallib_recall.py`, 19 golden needs over an 841-row corpus, recall@1/5/10):

            blended 0.6/0.4 + hard title prefix   look 31.6/ 78.9/ 89.5   named 84.2/ 100/100
            CLIP only                             look 47.4/ 89.5/100.0   named 84.2/94.7/100
            identity only                         look 47.4/ 78.9/ 84.2   named 94.7/ 100/100
            THIS (dominant + assist + bonus)      look 63.2/100.0/100.0   named 94.7/ 100/100
            (the provider's own keyword search    look 31.6/ 47.4/ 57.9   named 94.7/ 100/100)

        Three lessons are baked in. Blending near-equally was worse than EITHER pure channel on
        its own kind of query â€” the wrong channel demotes the right answer. The hard prefix
        (exact titles first, unconditionally) cost 10 points of named recall@1, because "first by
        lexical cover" is not "most likely": a short wrong title can cover perfectly. And the
        ROUTING DETECTOR needs its own, stricter threshold (`_NAMED_MIN_COVER`) â€” at the lexical
        matcher's own 0.5 a pure look need was mis-read as an identity question and lost 16 points
        of look recall@1 and 10 of recall@5.

        The weights are a SHAPE, not a tuning: dominant ~0.9, assist ~0.1, bonus ~0.4. The golden
        set is 19 needs, far too small to justify a third decimal â€” 0.8/0.2 scored within one need
        of 0.9/0.1, and `_NAMED_MIN_COVER` is flat across 0.67-0.9. Re-run the eval after touching
        any of them.
        """
        # ONE lexical pass, used for both jobs: deciding whether the query names something, and
        # supplying the title-cover bonus. (It is a full scan over the not-held rows â€” fine at
        # 10^3-10^4, and the place to add an FTS5 index beyond that.)
        # FILTERS FIRST, and applied to the RESULT rather than to each channel. The two vector
        # channels live in chroma and cannot join against SQLite columns, so narrowing is done by
        # resolving the allowed id set once and intersecting. That keeps one definition of "which
        # rows are eligible" â€” the same `_filter_sql` that `facets()` counts â€” instead of a
        # filter per channel that could drift apart.
        allowed = None
        # Every channel must reach PAST the requested page, or "load more" returns nothing: a
        # channel asked for k candidates cannot supply rows k..2k. `depth` is what the ranking
        # needs to see; `k` is only how much of it the caller keeps.
        depth = k + max(0, int(offset))
        if facets:
            allowed = {a.id for a in self.catalog.list(
                status="active", held=0, collection_id=collection_id,
                limit=1_000_000, **facets)}
            if not allowed:
                return []
            # A narrowed corpus needs a wider net from each channel, or the filter throws away
            # everything the channels returned and the page comes back empty.
            k_ch = max(depth * 3, min(300, len(allowed)))
        else:
            k_ch = depth * 3

        cover_hits = [h for h in self.search_by_title(
            query, k=depth * 2, held=0, collection_id=collection_id)
            if allowed is None or h.asset.id in allowed]
        cover = {h.asset.id: h.score for h in cover_hits}
        named = any(s >= _NAMED_MIN_COVER for s in cover.values())
        ident = {h.asset.id: h for h in self._search_discovery_identity(
            query, k=k_ch, collection_id=collection_id)
            if allowed is None or h.asset.id in allowed}
        # `use_clip=False` skips the look channel ENTIRELY â€” and because `self.embedder` is lazy,
        # a process that never asks for it never loads the ~150 MB model at all. That is the
        # point: a facet-and-catalog search page has no use for it.
        clip = {}
        if use_clip:
            clip = {h.asset.id: h for h in self._search_discovery_clip(
                query, k=k_ch, collection_id=collection_id)
                if allowed is None or h.asset.id in allowed}
        if use_clip:
            wi, wc, wcov = (0.7, 0.1, 0.4) if named else (0.1, 0.9, 0.0)
        else:
            # Without CLIP the look weighting would hand 0.9 to a channel that returns nothing
            # and leave look queries scoring on a 0.1 assist. Identity takes the full weight
            # instead, which is the identity-only system the eval measures at
            # look 7.1/25.0/32.1 and named 92.9/100/100 â€” honest about what it gives up.
            wi, wc, wcov = (1.0, 0.0, 0.4 if named else 0.0)
        assets = {h.asset.id: h.asset
                  for h in [*cover_hits, *ident.values(), *clip.values()]}
        merged = []
        for aid, asset in assets.items():
            i = ident[aid].score if aid in ident else 0.0
            c = clip[aid].score if aid in clip else 0.0
            merged.append(LibraryHit(asset=asset,
                                     score=round(wi * i + wc * c + wcov * cover.get(aid, 0.0), 4)))
        # PAGING A RANKED LIST means ranking deeper and slicing, not re-querying from an offset:
        # the score ordering is only meaningful over one merged candidate set, so page 2 has to
        # come from the same ranking that produced page 1 or the two can disagree. The channels
        # were asked for `k + offset` candidates above for exactly this reason.
        top = sorted(merged, key=lambda h: h.score, reverse=True)[offset:offset + k]

        # ON-DEMAND PIXELS. The phase-split crawl leaves most rows record-only, and the rows a
        # human is about to LOOK at are exactly the ones worth spending a fetch on. Opt-in
        # (`warm=True`) because a plain programmatic search must stay free of network I/O.
        #
        # This deliberately runs AFTER ranking, not before: warming first would mean fetching for
        # every candidate the three channels touched (k*3 of them) to serve a page of k.
        # Re-reading the rows afterwards keeps the returned hits consistent with what was stored.
        if warm and top:
            fetched = self.warm_pixels([h.asset for h in top], concurrency=warm_concurrency,
                                       embed=warm_embed)
            if fetched.get("fetched") or fetched.get("refused"):
                fresh = self.catalog.get_many([h.asset.id for h in top])
                top = [LibraryHit(asset=fresh.get(h.asset.id, h.asset), score=h.score)
                       for h in top
                       if fresh.get(h.asset.id, h.asset).status == "active"]
        return top

    def _search_discovery_identity(self, query: str, *, k: int, collection_id=None
                                   ) -> List[LibraryHit]:
        # A READ makes pending writes durable. Batching is a write-side optimisation and must be
        # invisible to a reader: a row indexed a moment ago has to be findable now, whether it
        # happened during a 56,000-row crawl or a single `add_discovery`.
        self.flush_index()
        return self._query_disc(self._disc_ident_coll, {"query_texts": [query]}, k, collection_id)

    def _search_discovery_clip(self, query: str, *, k: int, collection_id=None
                               ) -> List[LibraryHit]:
        try:
            qvec = self.embedder.embed_text(query)
        except Exception as e:
            _LOG.warning("discovery CLIP query failed for %r: %s", query, e)
            return []
        return self._query_disc(self._disc_coll, {"query_embeddings": [qvec]}, k, collection_id)

    def _query_disc(self, coll_fn, kwargs, k: int, collection_id) -> List[LibraryHit]:
        where = {"collection_id": int(collection_id)} if collection_id is not None else None
        try:
            res = coll_fn().query(n_results=k, **({"where": where} if where else {}), **kwargs)
        except Exception as e:
            _LOG.warning("discovery query failed @ %s: %s", self.base, e)
            return []
        ids = [int(i) for i in (res.get("ids") or [[]])[0]]
        dists = (res.get("distances") or [[]])[0]
        assets = self.catalog.get_many(ids)
        hits = []
        for aid, dist in zip(ids, dists):
            a = assets.get(aid)
            if a and a.status == "active":
                hits.append(LibraryHit(asset=a, score=round(1.0 - float(dist), 4)))
        return hits

    def effective_description(self, asset: Asset) -> str:
        """What this row can say about itself, INCLUDING what it inherits.

        Knowledge inherits downward in this tier, and read time is the right place to apply it:
        an inherited fact written INTO the row would be indistinguishable from something observed
        about that row, and re-deriving it after the collection's dialect changed would mean
        rewriting every member.

        Order of authority: the row's own caption, then the collection's visual dialect, then the
        artist's manner. Each is labelled in the text rather than blended, so nothing reads as a
        claim about this picture that was actually a claim about its neighbours.
        """
        from nolan.imagelib.artists import artist_context
        from nolan.imagelib.caption import dialect_text

        own = (asset.description or "").strip()
        if asset.caption_json:
            return own                     # captioned individually â€” it speaks for itself

        parts = [own] if own else []
        if asset.collection_id is not None:
            col = self.catalog.get_collection_by_id(asset.collection_id)
            if col is not None:
                parts.append(dialect_text(col.dialect()))
        parts.append(artist_context(self, asset.creator))
        return ". ".join(p for p in parts if p)

    def discovery_stats(self, collection_id: Optional[int] = None) -> dict:
        """Coverage, stated honestly, on BOTH axes a discovery row can be partial along.

        A row can lack a caption (T3) and it can lack PIXELS (Phase B) â€” and the second is new
        with the phase-split crawl, where a catalog-scale Phase A indexes records ~50x faster
        than it could fetch their thumbnails. Reporting only the row count would make a
        records-only collection look fully indexed while its `look` channel was empty.
        """
        n = self.catalog.count("active", held=0, collection_id=collection_id)
        described = self.catalog.described_count(held=0, collection_id=collection_id)
        # COUNT in SQL, never a Python scan. The first version of this materialised every
        # discovery row as an Asset object just to test `thumb_path` â€” 2.1 s at 97,610 rows, paid
        # on EVERY search, because the hub calls discovery_stats to render the result footer.
        with_pixels = self.catalog.count_with_pixels(held=0, collection_id=collection_id)
        return {"discovery": n, "held": self.catalog.count("active", held=1),
                "described": described,
                "described_pct": round(100.0 * described / n, 1) if n else 0.0,
                "with_pixels": with_pixels,
                "pixels_pct": round(100.0 * with_pixels / n, 1) if n else 0.0}

    # ------------------------------------------------------------------ search
    def search(self, query: str, *, k: int = 12, license_contains: Optional[str] = None
               ) -> List[LibraryHit]:
        """Semantic search (CLIP text->image). Filters to active assets."""
        qvec = self.embedder.embed_text(query)
        try:
            res = self._coll().query(query_embeddings=[qvec], n_results=k * 3)
        except Exception as e:
            _LOG.warning("library CLIP search failed for %r @ %s: %s", query, self.base, e)
            return []
        ids = [int(i) for i in (res.get("ids") or [[]])[0]]
        dists = (res.get("distances") or [[]])[0]
        assets = self.catalog.get_many(ids)
        hits: List[LibraryHit] = []
        for asset_id, dist in zip(ids, dists):
            a = assets.get(asset_id)
            if not a or a.status != "active":
                continue
            if license_contains and (license_contains.lower() not in (a.license or "").lower()):
                continue
            hits.append(LibraryHit(asset=a, score=round(1.0 - float(dist), 4)))
            if len(hits) >= k:
                break
        return hits

    def search_by_title(self, query: str, *, k: int = 12, min_cover: float = 0.5,
                        license_contains: Optional[str] = None,
                        held: Optional[int] = 1,
                        collection_id: Optional[int] = None) -> List[LibraryHit]:
        """Lexical TITLE match â€” the retrieval CLIP can't do for NAMED works.

        All 46 Holbein woodcuts cluster at CLIP 0.29-0.36 for any query, so text->image similarity
        returns 'a Holbein woodcut' (and often the WRONG one â€” 'the knight' ranked THE WAGGONER above
        THE KNIGHT, 'the abbot' missed THE ABBOT entirely), but the asset TITLE is an exact string.

        Scores by how much of the asset's (short, distinctive) TITLE is NAMED IN THE QUERY â€”
        ``|title_tokens âˆ© query_tokens| / |title_tokens|`` â€” so a verbose beat query ('a merchant
        robbed by death') still fully matches the titled asset ('THE MERCHANT'). An un-named query
        ('candle flame flickering') matches no title and returns [] (â†’ pure CLIP handles it)."""
        qset = set(_distinctive_tokens(query))
        if not qset:
            return []
        # PRE-FILTER IN SQL. Scoring is `|title âˆ© query| / |title|`, so a title can only clear
        # `min_cover` if it shares at least one distinctive token with the query â€” which means
        # SQLite can throw away the rows that share none before Python ever builds an Asset.
        #
        # This method's own docstring predicted the failure ("a full scan over the not-held rows
        # â€” fine at 10^3-10^4, and the place to add an FTS5 index beyond that") and the corpus
        # crossed it: at 97,610 rows the scan was 2.35 s of a 2.43 s search. The prediction was
        # right about where and slightly wrong about what â€” a LIKE pre-filter recovers most of it
        # without the schema cost of FTS5, and FTS5 remains the answer if this grows again.
        scored: List[tuple] = []
        for aid, title, lic in self.catalog.title_candidates(
                sorted(qset), status="active", held=held, collection_id=collection_id):
            if license_contains and (license_contains.lower() not in (lic or "").lower()):
                continue
            htok = _distinctive_tokens(title or "")
            if not htok:
                continue
            cover = sum(1 for t in htok if t in qset) / len(htok)
            if cover >= min_cover:
                scored.append((cover, aid))
        if not scored:
            return []
        scored.sort(key=lambda p: p[0], reverse=True)
        top = scored[:k]
        # Hydrate ONLY the winners. Scoring ran on three columns; a full Asset is built for the
        # handful that survived, not for every title that shared a word with the query.
        assets = self.catalog.get_many([aid for _, aid in top])
        return [LibraryHit(asset=assets[aid], score=round(cover, 4))
                for cover, aid in top if aid in assets]

    def search_by_description(self, query: str, *, k: int = 12,
                              license_contains: Optional[str] = None) -> List[LibraryHit]:
        """Semantic search over asset *descriptions* (BGE text->text).

        Matches a scene's description against each asset's generated description â€”
        the same approach the video library uses for segments.
        """
        try:
            res = self._desc_coll().query(query_texts=[query], n_results=k * 3)
        except Exception:
            return []
        ids = [int(i) for i in (res.get("ids") or [[]])[0]]
        dists = (res.get("distances") or [[]])[0]
        assets = self.catalog.get_many(ids)
        hits: List[LibraryHit] = []
        for asset_id, dist in zip(ids, dists):
            a = assets.get(asset_id)
            if not a or a.status != "active":
                continue
            if license_contains and (license_contains.lower() not in (a.license or "").lower()):
                continue
            hits.append(LibraryHit(asset=a, score=round(1.0 - float(dist), 4)))
            if len(hits) >= k:
                break
        return hits

    def search_hybrid(self, query: str, *, k: int = 12, w_desc: float = 0.6,
                      w_clip: float = 0.4, license_contains: Optional[str] = None
                      ) -> List[LibraryHit]:
        """Combine description (BGE text->text) and CLIP (image<-text) scores.

        Description match captures meaning/context; CLIP captures visual look.
        Assets are merged by id and scored ``w_desc*desc + w_clip*clip``.
        """
        desc = {h.asset.id: h for h in self.search_by_description(
            query, k=k * 2, license_contains=license_contains)}
        clip = {h.asset.id: h for h in self.search(
            query, k=k * 2, license_contains=license_contains)}
        merged: dict = {}
        for aid in set(desc) | set(clip):
            d = desc[aid].score if aid in desc else 0.0
            c = clip[aid].score if aid in clip else 0.0
            asset = (desc.get(aid) or clip.get(aid)).asset
            merged[aid] = LibraryHit(asset=asset, score=round(w_desc * d + w_clip * c, 4))
        return sorted(merged.values(), key=lambda h: h.score, reverse=True)[:k]

    def backfill_descriptions(self, describer=None, *, limit: Optional[int] = None) -> int:
        """Generate + index descriptions for active assets that lack one.

        Returns the number described. ``describer`` defaults to ``self.describer``.
        """
        describer = describer or self.describer
        if describer is None:
            raise ValueError("no describer provided")
        done = 0
        for a in self.catalog.list(status="active", limit=limit):
            if (a.description or "").strip():
                continue
            f = self.abs_path(a)
            if not f.exists():
                continue
            try:
                desc = describer(f)
            except Exception:
                continue
            if not desc:
                continue
            self.catalog.set_description(a.id, desc)
            self._index_description(a.id, desc, a.source)
            done += 1
        return done

    # ------------------------------------------------------------------ curate
    def set_status(self, asset_id: int, status: str) -> None:
        self.catalog.set_status(asset_id, status)
        if status != "active":
            # All four collections: a de-activated row's vectors must leave the DISCOVERY index
            # too, or its stale hits keep consuming result slots that `_query_disc` then drops.
            for coll in (self._coll, self._desc_coll, self._disc_coll, self._disc_ident_coll):
                try:
                    coll().delete(ids=[str(asset_id)])
                except Exception:
                    pass

    def hard_delete(self, asset_id: int) -> None:
        """Fully remove an asset: drop its CLIP + description vectors AND its catalog row (frees the content
        hash). Use for a true REPLACE (e.g. re-capturing a video's frames) where set_status('deleted') would
        keep the row and block re-adding identical bytes."""
        self.set_status(asset_id, "deleted")
        self.catalog.delete(asset_id)

    def abs_path(self, asset: Asset) -> Path:
        """Absolute path to an asset's file in this library."""
        return (self.base / asset.path).resolve()

    def list(self, **filters) -> List[Asset]:
        return self.catalog.list(**filters)

    def stats(self) -> dict:
        return {"scope": self.scope, "project": self.project, "base": str(self.base),
                "active": self.catalog.count("active", held=1),
                "discovery": self.catalog.count("active", held=0),
                "total": self.catalog.count()}


def _probe_dims(path: Path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def promote_to_global(project: str, asset_id: int,
                      embedder: Optional[ClipEmbedder] = None):
    """Copy a project-library asset into the global library (dedup by hash).

    Returns (global_asset, created). Raises if the asset isn't found.
    """
    proj_lib = ImageLibrary("project", project=project, embedder=embedder)
    a = proj_lib.catalog.get(asset_id)
    if not a:
        raise ValueError(f"asset {asset_id} not found in project '{project}'")
    src = proj_lib.abs_path(a)
    if not src.exists():
        raise FileNotFoundError(f"file missing for asset {asset_id}: {src}")
    glob = ImageLibrary("global", embedder=embedder)
    return glob.add_file(
        src, url=a.url, source=a.source, source_url=a.source_url, license=a.license,
        title=a.title, width=a.width, height=a.height, tags=a.tags, query=a.query)


def search_all(query: str, *, project: Optional[str] = None, k: int = 12,
               license_contains: Optional[str] = None,
               embedder: Optional[ClipEmbedder] = None) -> List[LibraryHit]:
    """Search the global library plus a project library (if given), merged by score."""
    libs = [ImageLibrary("global", embedder=embedder)]
    if project:
        libs.append(ImageLibrary("project", project=project, embedder=embedder))
    hits: List[LibraryHit] = []
    for lib in libs:
        hits.extend(lib.search(query, k=k, license_contains=license_contains))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k]
