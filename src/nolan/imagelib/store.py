"""Picture library — persistent, searchable, license-aware image store.

Ties together file storage + the SQLite :class:`AssetCatalog` (provenance,
dedup, licensing) + a ChromaDB collection of CLIP embeddings (semantic search).

Two scopes (both live inside the project tree per workspace rules):
  * **global**  -> ``_library/images/``           (shared across projects)
  * **project** -> ``projects/<name>/imagelib/``   (per-project collection)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from nolan.imagelib.catalog import Asset, AssetCatalog
from nolan.imagelib.embeddings import ClipEmbedder

_COLLECTION = "images"
_DESC_COLLECTION = "descriptions"
_UA = "NOLAN-PictureLibrary/1.0"


def library_paths(scope: str = "global", project: Optional[str] = None) -> Path:
    """Resolve the base directory for a library scope."""
    if scope == "project":
        if not project:
            raise ValueError("project scope requires a project name")
        return Path("projects") / project / "imagelib"
    return Path("_library") / "images"


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


class ImageLibrary:
    def __init__(self, scope: str = "global", project: Optional[str] = None,
                 base_dir: Optional[Path] = None, embedder: Optional[ClipEmbedder] = None,
                 describer=None):
        self.scope = scope
        self.project = project
        self.base = Path(base_dir) if base_dir else library_paths(scope, project)
        self.files_dir = self.base / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.catalog = AssetCatalog(self.base / "catalog.db")
        self._embedder = embedder
        # describer(path) -> str: generates a vision description for an image.
        # Optional; when set, add_file auto-describes assets that lack one.
        self.describer = describer
        self._client = None
        self._collection = None
        self._desc_collection = None

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
        """Download an image URL into a temp file, then add it."""
        import tempfile
        from nolan.http_client import download_file_sync
        ext = _ext_for(url, None)
        tmp = Path(tempfile.gettempdir()) / f"nolan_piclib_{abs(hash(url))}{ext}"
        download_file_sync(url, str(tmp), headers={"User-Agent": _UA})
        try:
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

    # ------------------------------------------------------------------ search
    def search(self, query: str, *, k: int = 12, license_contains: Optional[str] = None
               ) -> List[LibraryHit]:
        """Semantic search (CLIP text->image). Filters to active assets."""
        qvec = self.embedder.embed_text(query)
        try:
            res = self._coll().query(query_embeddings=[qvec], n_results=k * 3)
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
            for coll in (self._coll, self._desc_coll):
                try:
                    coll().delete(ids=[str(asset_id)])
                except Exception:
                    pass

    def abs_path(self, asset: Asset) -> Path:
        """Absolute path to an asset's file in this library."""
        return (self.base / asset.path).resolve()

    def list(self, **filters) -> List[Asset]:
        return self.catalog.list(**filters)

    def stats(self) -> dict:
        return {"scope": self.scope, "project": self.project, "base": str(self.base),
                "active": self.catalog.count("active"), "total": self.catalog.count()}


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
