"""Collection harvest — fill the not-held (Visual Lib) tier from a source's own catalog.

A HARVEST is the picture analogue of the transcript library's channel crawl: walk a collection's
catalog API, write one discovery row per item (identity + rights + a 512px thumbnail), and leave
the bytes where they are. What you get is a searchable index over a corpus far larger than any
library you would download — the Art Institute alone publishes ~132k artworks — for the price of
a thumbnail each.

THREE KNOWLEDGE TIERS, and a harvest only produces the middle one:

  T0  collection-only  — the `Collection` row: title, blurb, rights, count. Searchable before a
                         single member is indexed; a hit says "this collection probably has it".
  T1  shallow item     — what this module writes: the source's OWN catalog metadata (title,
                         creator, date, medium, place) + thumbnail + stable id. No model calls.
  T2  captioned item   — a VLM description (and one day labelled regions) on top. DEMAND-DRIVEN,
                         never bulk: captioning 132k items is not a plan. `describe_discovery`
                         enriches what retrieval or a human actually surfaced, and
                         `discovery_stats` reports the coverage so a 3%-captioned collection can
                         never look complete.

ADAPTERS. `SOURCES` maps a source id to a function yielding `HarvestItem`s. Add a museum by
adding one adapter — the gate, the thumbnail handling, the identity columns and the dedup are
shared. Every adapter MUST supply a stable `source_ref` ('<source>:<their id>'), because a
not-held row keyed on a CDN url cannot survive that url rotating.

Identity is CATALOG-DERIVED here by construction (`identity_source='catalog'`) — these fields
come from the institution's own record, never from a model looking at the picture.

CLI:  python -X utf8 -m nolan.imagelib.harvest artic --limit 500 [--query "..."] [--dept "..."]
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional

from nolan.imagelib.catalog import Collection

_UA = "NOLAN-VisualLib/1.0"


@dataclass
class HarvestItem:
    """One catalog record, normalised. `thumb_url` is fetched; `url` is what promotion fetches."""
    source_ref: str
    thumb_url: str
    url: Optional[str] = None
    source_url: Optional[str] = None
    title: Optional[str] = None
    creator: Optional[str] = None
    date_text: Optional[str] = None
    institution: Optional[str] = None
    description: Optional[str] = None       # catalog prose (medium/place), NOT a model caption
    license: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    wikidata_qid: Optional[str] = None
    tags: Optional[str] = None


@dataclass
class HarvestReport:
    """What a harvest did — and, loudly, what it dropped. A bounded crawl that reports only its
    successes reads as full coverage; every refusal is counted and the first few are quoted."""
    collection: str
    scanned: int = 0
    added: int = 0
    refreshed: int = 0
    skipped_no_image: int = 0
    skipped_rights: int = 0
    refused_gate: int = 0
    errors: int = 0
    reasons: List[str] = field(default_factory=list)

    def note(self, reason: str) -> None:
        if len(self.reasons) < 12:
            self.reasons.append(reason)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------- Art Institute of Chicago

ARTIC_API = "https://api.artic.edu/api/v1/artworks"
ARTIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search"
ARTIC_IIIF = "https://www.artic.edu/iiif/2"
# The catalog fields worth indexing. `thumbnail` carries the SOURCE image's real dimensions, which
# is what the gate's resolution floor must judge — the 512px derivative we store would fail it.
ARTIC_FIELDS = ("id,title,artist_title,date_display,image_id,is_public_domain,medium_display,"
                "place_of_origin,department_title,classification_title,thumbnail,artwork_type_title")


def artic_collection(dept: Optional[str] = None, query: Optional[str] = None) -> Collection:
    """The T0 row for an Art Institute harvest. Rights are asserted at COLLECTION level and are
    sticky: we harvest only `is_public_domain` items, so CC0 is a property of the harvest, not a
    guess a later pass may overwrite."""
    slug = "artic-public-domain" + (f"-{dept.lower().replace(' ', '-')}" if dept else "") \
                                 + (f"-{query.lower().replace(' ', '-')[:24]}" if query else "")
    title = "Art Institute of Chicago — public-domain artworks"
    if dept:
        title += f" ({dept})"
    return Collection(
        slug=slug, source="artic", title=title,
        description=("Open-access artworks from the Art Institute of Chicago: paintings, prints, "
                     "drawings, photographs, textiles and objects from antiquity to the present, "
                     "each with catalogued title, artist, date, medium and place of origin. "
                     "Images are served over IIIF, so any region can be requested at any size."),
        rights="CC0 (Art Institute of Chicago) — public-domain artworks only",
        copyright_free=True, url="https://www.artic.edu/open-access",
        topics="art, painting, print, drawing, photography, historical object")


def artic_items(limit: int = 200, *, dept: Optional[str] = None, query: Optional[str] = None,
                page_size: int = 100, report: Optional[HarvestReport] = None
                ) -> Iterator[HarvestItem]:
    """Walk the Art Institute catalog. Keyless, paginated, ~100 records per request.

    Filtered SERVER-SIDE to `is_public_domain` (61,568 of the 132,018 artworks). Measured: the
    unfiltered listing spent 11 of every 12 records on items we must refuse on rights, so this is
    a 12x saving on a keyless API's goodwill, not a nicety. `query` additionally biases the
    ranking toward a theme. The API refuses offsets past 10,000, so a bounded harvest is the only
    kind — `limit` is honoured exactly and the report says what was scanned.
    """
    import httpx

    fetched = 0
    page = 1
    with httpx.Client(headers={"User-Agent": _UA}, timeout=45.0) as c:
        while fetched < limit:
            n = min(page_size, limit - fetched)
            params = {"query[term][is_public_domain]": "true", "limit": n, "page": page,
                      "fields": ARTIC_FIELDS}
            if query:
                params["q"] = query
            try:
                r = c.get(ARTIC_SEARCH, params=params)
                r.raise_for_status()
                data = r.json().get("data") or []
            except Exception as e:
                if report:
                    report.errors += 1
                    report.note(f"page {page}: {type(e).__name__}: {e}")
                return
            if not data:
                return
            for a in data:
                fetched += 1
                img = a.get("image_id")
                if not img:
                    if report:
                        report.skipped_no_image += 1
                    continue
                if not a.get("is_public_domain"):
                    if report:
                        report.skipped_rights += 1
                    continue
                if dept and (a.get("department_title") or "") != dept:
                    continue
                thumb = a.get("thumbnail") or {}
                bits = [a.get("medium_display"), a.get("place_of_origin"),
                        a.get("classification_title") or a.get("artwork_type_title"),
                        a.get("department_title")]
                yield HarvestItem(
                    source_ref=f"artic:{a.get('id')}",
                    thumb_url=f"{ARTIC_IIIF}/{img}/full/600,/0/default.jpg",
                    url=f"{ARTIC_IIIF}/{img}/full/1686,/0/default.jpg",
                    source_url=f"https://www.artic.edu/artworks/{a.get('id')}",
                    title=a.get("title"), creator=a.get("artist_title"),
                    date_text=a.get("date_display"),
                    institution="Art Institute of Chicago",
                    description=", ".join(b for b in bits if b),
                    license="CC0 (Art Institute of Chicago)",
                    width=thumb.get("width"), height=thumb.get("height"),
                    tags=a.get("classification_title") or a.get("artwork_type_title"))
            page += 1
            time.sleep(0.2)                                   # be a good citizen on a keyless API


SOURCES: Dict[str, Dict[str, Callable]] = {
    "artic": {"collection": artic_collection, "items": artic_items},
}


# ------------------------------------------------------------------------------ the harvest loop

def harvest(source: str, *, limit: int = 200, scope: str = "global",
            project: Optional[str] = None, library=None, progress=None,
            **source_kwargs) -> HarvestReport:
    """Harvest `limit` items from one source into the discovery tier. Idempotent: a re-run
    refreshes rows by `source_ref` instead of duplicating them."""
    if source not in SOURCES:
        raise ValueError(f"unknown harvest source {source!r} (known: {sorted(SOURCES)})")
    from nolan.imagelib import ImageLibrary

    adapter = SOURCES[source]
    lib = library or ImageLibrary(scope=scope, project=project)
    col_kwargs = {k: v for k, v in source_kwargs.items() if k in ("dept", "query")}
    collection = lib.upsert_collection(adapter["collection"](**col_kwargs))
    report = HarvestReport(collection=collection.slug)

    for item in adapter["items"](limit=limit, report=report, **source_kwargs):
        report.scanned += 1
        try:
            # RETRY transient CDN failures. Measured on a 899-record crawl: 44 items (~5%) were
            # lost to 502/504 from the IIIF host under our own request rate — noise, not a
            # property of the item, and a harvest that drops 5% of a collection for noise silently
            # under-covers it. A gate refusal (ValueError) is a VERDICT and never retried.
            for attempt in range(3):
                try:
                    asset, created = lib.add_discovery(
                        source_ref=item.source_ref, thumb_url=item.thumb_url, url=item.url,
                        source=source, source_url=item.source_url, title=item.title,
                        creator=item.creator, date_text=item.date_text,
                        institution=item.institution, description=item.description,
                        license=item.license, width=item.width, height=item.height,
                        wikidata_qid=item.wikidata_qid, tags=item.tags,
                        collection_id=collection.id, identity_source="catalog")
                    break
                except ValueError:
                    raise
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(1.5 * (attempt + 1))
            report.added += int(created)
            report.refreshed += int(not created)
        except ValueError as e:                     # a gate refusal — counted, quoted, never silent
            report.refused_gate += 1
            report.note(str(e))
        except Exception as e:
            report.errors += 1
            report.note(f"{item.source_ref}: {type(e).__name__}: {e}")
        if progress:
            progress(report)

    lib.upsert_collection(Collection(
        slug=collection.slug, source=source, title=collection.title,
        item_count=lib.catalog.count("active", held=0, collection_id=collection.id),
        last_crawled=time.strftime("%Y-%m-%dT%H:%M:%S")))
    return report


def describe_discovery(library, *, limit: int = 25, collection_id: Optional[int] = None,
                       describer=None, model: str = "vlm") -> int:
    """T2, on demand: caption not-held rows that lack a description, from their THUMBNAIL.

    Bounded by `limit` on purpose — this is the expensive tier and it is spent on what retrieval
    or a human surfaced, not on the whole catalog. The collection's own blurb is prepended as
    context, the same trick that makes video-frame captions entity-aware by feeding them the
    transcript window: a describer told "these are Art Institute open-access artworks" writes a
    materially better caption than one shown a bare image.

    A caption NEVER becomes an identity: `identity_source` is untouched, and the generated text
    lands in `description` only. Returns the number described.
    """
    describer = describer or library.describer
    if describer is None:
        raise ValueError("no describer provided")
    blurb = ""
    if collection_id is not None:
        for c in library.catalog.list_collections():
            if c.id == collection_id:
                blurb = c.description or ""
                break
    done = 0
    for a in library.catalog.list(status="active", held=0, collection_id=collection_id,
                                  limit=max(limit * 8, 200)):
        if done >= limit:
            break
        if (a.description_source or "catalog") != "catalog":
            continue                                  # already captioned — never pay for it twice
        thumb = (library.base / (a.thumb_path or "")).resolve()
        if not a.thumb_path or not thumb.exists():
            continue
        try:
            desc = describer(thumb, context=blurb) if _takes_context(describer) else describer(thumb)
        except Exception:
            continue
        if not desc:
            continue
        merged = " | ".join(x for x in [(a.description or "").strip(), desc.strip()] if x)
        library.catalog.set_description(a.id, merged)
        library.catalog.update(a.id, description_source=model)
        library._index_discovery(library.catalog.get(a.id), thumb)
        done += 1
    return done


def _takes_context(fn) -> bool:
    import inspect
    try:
        return "context" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _main(argv=None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="nolan.imagelib.harvest",
                                 description="Harvest a collection into the Visual Lib tier")
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--query", default=None, help="themed slice (search endpoint)")
    ap.add_argument("--dept", default=None, help="filter to one department")
    ap.add_argument("--scope", default="global", choices=("global", "project"))
    ap.add_argument("--project", default=None)
    args = ap.parse_args(argv)

    kw = {k: v for k, v in (("query", args.query), ("dept", args.dept)) if v}
    rep = harvest(args.source, limit=args.limit, scope=args.scope, project=args.project, **kw)
    print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False))
    return 0 if rep.added or rep.refreshed else 1


if __name__ == "__main__":
    raise SystemExit(_main())
