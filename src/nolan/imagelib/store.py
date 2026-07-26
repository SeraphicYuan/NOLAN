"""Picture library — persistent, searchable, license-aware image store.

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
# is right for "is this title relevant"; it is too loose for "is this query an identity question" —
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


def library_paths(scope: str = "global", project: Optional[str] = None) -> Path:
    """Resolve the ABSOLUTE base directory for a library scope, anchored to the repo root.

    NOT os.getcwd()-relative: a relative base silently resolved against whatever CWD the process
    ran under, so running acquisition from render-service/_lab_hyperframes/bridge/ (as the hub's
    run_pool does) opened an EMPTY library — every library-first need returned 0 with no error, and
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
    source / license / width / height) — so the discovery door gates on the SAME policy tables as
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
    heuristic — a full-size cache would just be the Picture Library again."""
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

        Dedups by content hash — re-adding the same bytes returns the existing row.
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

        The library is a REUSE surface — a watermarked or preview-domain file
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
                      tags=None, tier: str = "archival", embed: bool = True):
        """Index an image we do NOT hold: catalog metadata + a local thumbnail. Returns
        ``(Asset, created)``; re-indexing a known `source_ref` refreshes its identity in place.

        ACQUISITION DOOR — this fetches bytes from the open internet, so it calls
        ``asset_gate.check_candidate`` before the fetch (blocklisted host / rights floor /
        resolution floor, judged on the FULL image's dimensions, not the thumbnail's) and
        ``asset_gate.banner_suspect`` on the stored thumbnail — for every source EXCEPT the
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
        # heuristic's signature — a near-uniform band, discontinuous with the body, carrying a few
        # contrasting pixels — is just an object shot on a plain mount. CHARACTERISED before
        # scoping it (checklist #11: a check whose failures are all false positives): 4 of 4
        # refusals inspected by eye were false — a Piranesi etching on its white paper margin
        # (artic:19), a bed rug and a gold-ground crucifix on black studio ground (artic:49691 /
        # 16231), a Spanish retable on white (artic:88793) — at ~1% of a shallow crawl rising to
        # ~5% deeper in, where object photography outnumbers framed paintings. It still runs for
        # every other source, so the Alamy shape it was written for is still caught.
        if source not in OPEN_ACCESS_SOURCES and banner_suspect(dest):
            dest.unlink(missing_ok=True)
            raise ValueError(f"discovery refused (watermark banner strip): {source_ref}")

        rel = str(dest.relative_to(self.base)).replace("\\", "/")
        fields = dict(url=url, source=source, source_url=source_url, license=license,
                      title=title, description=description, width=width, height=height,
                      tags=tags, creator=creator, date_text=date_text, institution=institution,
                      identity_source=identity_source, wikidata_qid=wikidata_qid,
                      collection_id=collection_id, thumb_path=rel)
        if description:
            fields["description_source"] = description_source
        if existing is not None:
            # A re-crawl refreshes the CATALOG's own facts, but must not clobber a T2 caption with
            # the source's one-line prose — so a row already carrying a model description keeps it.
            if (existing.description_source or "catalog") != "catalog":
                fields.pop("description", None)
                fields.pop("description_source", None)
            self.catalog.update(existing.id, **{k: v for k, v in fields.items() if v is not None})
            asset = self.catalog.get(existing.id)
            created = False
        else:
            asset = self.catalog.add(Asset(
                content_hash=f"ref:{hashlib.sha256(source_ref.encode('utf-8')).hexdigest()}",
                path=rel, held=0, source_ref=source_ref, **fields))
            created = True
        if embed:
            # A re-crawl re-embedded every unchanged row — at catalog scale that is the whole cost
            # of the crawl for no new information. Embed the thumbnail only when it is actually new,
            # and the identity text only when it actually changed.
            self._index_discovery(
                asset, dest, clip=created or fresh_thumb,
                ident=created or (existing.identity_text() != asset.identity_text()))
        return asset, created

    def _index_discovery(self, asset: Asset, thumb: Path, *, clip: bool = True,
                         ident: bool = True) -> None:
        """Both discovery channels for one row: CLIP over the thumbnail (look) and BGE over the
        catalog identity (names). Either may fail independently without losing the other."""
        meta = {"source": asset.source or "", "license": asset.license or "",
                "collection_id": asset.collection_id or 0}
        if clip:
            try:
                vec = self.embedder.embed_image(thumb)
                if vec:
                    self._disc_coll().upsert(ids=[str(asset.id)], embeddings=[vec],
                                             metadatas=[meta])
            except Exception as e:
                _LOG.warning("discovery CLIP index failed for %s: %s", asset.source_ref, e)
        text = asset.identity_text()
        if ident and text:
            try:
                self._disc_ident_coll().upsert(ids=[str(asset.id)], documents=[text],
                                               metadatas=[meta])
            except Exception as e:
                _LOG.warning("discovery identity index failed for %s: %s", asset.source_ref, e)

    def promote_to_held(self, asset_id: int, *, tier: str = "archival", embed: bool = True,
                        describe: bool = False):
        """Fetch a discovery row's real bytes and flip it to held=1 — the ONE edge between the
        two tiers. Returns ``(Asset, promoted)``; ``promoted=False`` means the bytes were already
        in the library under another row (deduped by content hash) and this row was retired.

        Named for the axis it moves along: `promote_to_global` (module level) moves an asset
        between SCOPES (project → global). This moves it between TIERS. One word for two
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
                # than creating a second copy — but KEEP it (status, not delete) so its source_ref
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

    def search_discovery(self, query: str, *, k: int = 12,
                         collection_id: Optional[int] = None) -> List[LibraryHit]:
        """Search the NOT-HELD tier. Three channels, ROUTED by what the query is asking for.

        A query that NAMES something ("Seurat, La Grande Jatte") is an identity question, answered
        from the catalog's own words; a query about LOOK ("a rainy cobbled boulevard under
        umbrellas") is answered by CLIP over the thumbnail. The routing decides which channel
        DOMINATES — the other stays as a small assist, and the lexical title cover rides in as a
        BONUS rather than a hard prefix.

        Every part of that shape was measured through THIS code path, not assumed
        (`scripts/eval_visuallib_recall.py`, 19 golden needs over an 841-row corpus, recall@1/5/10):

            blended 0.6/0.4 + hard title prefix   look 31.6/ 78.9/ 89.5   named 84.2/ 100/100
            CLIP only                             look 47.4/ 89.5/100.0   named 84.2/94.7/100
            identity only                         look 47.4/ 78.9/ 84.2   named 94.7/ 100/100
            THIS (dominant + assist + bonus)      look 63.2/100.0/100.0   named 94.7/ 100/100
            (the provider's own keyword search    look 31.6/ 47.4/ 57.9   named 94.7/ 100/100)

        Three lessons are baked in. Blending near-equally was worse than EITHER pure channel on
        its own kind of query — the wrong channel demotes the right answer. The hard prefix
        (exact titles first, unconditionally) cost 10 points of named recall@1, because "first by
        lexical cover" is not "most likely": a short wrong title can cover perfectly. And the
        ROUTING DETECTOR needs its own, stricter threshold (`_NAMED_MIN_COVER`) — at the lexical
        matcher's own 0.5 a pure look need was mis-read as an identity question and lost 16 points
        of look recall@1 and 10 of recall@5.

        The weights are a SHAPE, not a tuning: dominant ~0.9, assist ~0.1, bonus ~0.4. The golden
        set is 19 needs, far too small to justify a third decimal — 0.8/0.2 scored within one need
        of 0.9/0.1, and `_NAMED_MIN_COVER` is flat across 0.67-0.9. Re-run the eval after touching
        any of them.
        """
        # ONE lexical pass, used for both jobs: deciding whether the query names something, and
        # supplying the title-cover bonus. (It is a full scan over the not-held rows — fine at
        # 10^3-10^4, and the place to add an FTS5 index beyond that.)
        cover_hits = self.search_by_title(query, k=k * 2, held=0)
        cover = {h.asset.id: h.score for h in cover_hits}
        named = any(s >= _NAMED_MIN_COVER for s in cover.values())
        ident = {h.asset.id: h for h in self._search_discovery_identity(
            query, k=k * 3, collection_id=collection_id)}
        clip = {h.asset.id: h for h in self._search_discovery_clip(
            query, k=k * 3, collection_id=collection_id)}
        wi, wc, wcov = (0.7, 0.1, 0.4) if named else (0.1, 0.9, 0.0)
        assets = {h.asset.id: h.asset
                  for h in [*cover_hits, *ident.values(), *clip.values()]}
        merged = []
        for aid, asset in assets.items():
            i = ident[aid].score if aid in ident else 0.0
            c = clip[aid].score if aid in clip else 0.0
            merged.append(LibraryHit(asset=asset,
                                     score=round(wi * i + wc * c + wcov * cover.get(aid, 0.0), 4)))
        return sorted(merged, key=lambda h: h.score, reverse=True)[:k]

    def _search_discovery_identity(self, query: str, *, k: int, collection_id=None
                                   ) -> List[LibraryHit]:
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

    def discovery_stats(self, collection_id: Optional[int] = None) -> dict:
        """Coverage, stated honestly: how much of the not-held tier carries a description.
        A partially-enriched collection must SAY it is partial."""
        n = self.catalog.count("active", held=0, collection_id=collection_id)
        described = self.catalog.described_count(held=0, collection_id=collection_id)
        return {"discovery": n, "held": self.catalog.count("active", held=1),
                "described": described,
                "described_pct": round(100.0 * described / n, 1) if n else 0.0}

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
                        held: Optional[int] = 1) -> List[LibraryHit]:
        """Lexical TITLE match — the retrieval CLIP can't do for NAMED works.

        All 46 Holbein woodcuts cluster at CLIP 0.29-0.36 for any query, so text->image similarity
        returns 'a Holbein woodcut' (and often the WRONG one — 'the knight' ranked THE WAGGONER above
        THE KNIGHT, 'the abbot' missed THE ABBOT entirely), but the asset TITLE is an exact string.

        Scores by how much of the asset's (short, distinctive) TITLE is NAMED IN THE QUERY —
        ``|title_tokens ∩ query_tokens| / |title_tokens|`` — so a verbose beat query ('a merchant
        robbed by death') still fully matches the titled asset ('THE MERCHANT'). An un-named query
        ('candle flame flickering') matches no title and returns [] (→ pure CLIP handles it)."""
        qset = set(_distinctive_tokens(query))
        if not qset:
            return []
        hits: List[LibraryHit] = []
        for a in self.catalog.list(status="active", held=held):
            if license_contains and (license_contains.lower() not in (a.license or "").lower()):
                continue
            htok = _distinctive_tokens(a.title or "")
            if not htok:
                continue
            cover = sum(1 for t in htok if t in qset) / len(htok)
            if cover >= min_cover:
                hits.append(LibraryHit(asset=a, score=round(cover, 4)))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    def search_by_description(self, query: str, *, k: int = 12,
                              license_contains: Optional[str] = None) -> List[LibraryHit]:
        """Semantic search over asset *descriptions* (BGE text->text).

        Matches a scene's description against each asset's generated description —
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
