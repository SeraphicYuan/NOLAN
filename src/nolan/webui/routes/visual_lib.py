"""Visual Lib routes — the not-held picture tier's own surface (skills/lab/visual-library.md).

A SEPARATE page from /images on purpose, and for the reason the transcript library is separate
from /library: the two tiers answer different questions with different verbs. /images curates what
we HOLD (cutout, reject, shortlist, promote-to-global); this page FINDS what we don't (search a
catalog-scale index, browse collections, harvest more, fetch the bytes when a beat earns one).
Folding them into one toolbar produced two grammars in one control strip — "license contains" and
"scope" applying to one tier while cutout/reject applied to the other.

Split of ownership with `routes.images_extract`, deliberately by RESOURCE rather than by page:
  • row-level ops act on catalog rows and stay there — `/api/images/discover`, `/api/images/{id}/fetch`
  • tier-level ops are new resources and live here — sources, collections, harvest, caption

The source and department pickers are served FROM THE REGISTRY (`harvest.SOURCES`,
`harvest.MET_DEPARTMENTS`), never hand-listed in the template: a catalog an agent or a UI copies
by hand is the catalog that rots (WIRING_CHECKLIST pitfall #5).
"""
from fastapi import Body, HTTPException
from fastapi.responses import HTMLResponse


def _bounded_limit(raw, *, default):
    """Parse a batch bound. `or default` would be wrong here: an explicit 0 is falsy, so a caller
    asking for NOTHING would silently get the default batch — a bounded crawl unbounding itself,
    the exact failure this tier reports against. Absent means default; present means honoured or
    refused."""
    if raw is None or raw == "":
        return default
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="limit must be a number")
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    return limit


def register(app, ctx):
    templates_dir = ctx.templates_dir
    job_manager = ctx.job_manager

    def _open(scope, project):
        # SHARED per process — see `shared_library`. Rebuilding it per request reloaded CLIP and
        # re-opened chroma every time.
        from nolan.imagelib import shared_library
        return shared_library(scope=scope or "global", project=(project or None))

    @app.get("/visual-lib", response_class=HTMLResponse)
    async def visual_lib_page():
        tpl = templates_dir / "visual_lib.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>visual_lib.html not found</h1>"

    @app.get("/api/visuallib/sources")
    async def visuallib_sources():
        """The harvest registry, as the UI's menu. Derived, so a new adapter appears in the form
        the moment it is registered and a removed one cannot linger as a dead button."""
        from nolan.imagelib.harvest import ENUMERATION, MET_DEPARTMENTS, SOURCES
        out = []
        for name, adapter in sorted(SOURCES.items()):
            col = adapter.collection()
            out.append({"id": name, "title": col.title, "rights": col.rights,
                        "description": col.description,
                        # How this source can be walked, and what that costs, straight from the
                        # registry — a crawl measured in hours should say up front whether it can
                        # resume and whether it is capped.
                        "enumeration": adapter.enumeration,
                        "enumeration_constraint": ENUMERATION[adapter.enumeration]["constraint"],
                        "resumable": adapter.resumable,
                        "publishes_pixel_dims": adapter.publishes_pixel_dims,
                        "rights_model": adapter.rights_model,
                        "notes": adapter.notes,
                        "departments": (sorted(MET_DEPARTMENTS.values()) if name == "met" else [])})
        return {"sources": out}

    @app.get("/api/visuallib/facets")
    async def visuallib_facets(scope: str = "global", project: str = None,
                               image_kind: str = None, department: str = None,
                               creator: str = None, place: str = None,
                               classification: str = None, artist_key: str = None,
                               movement: str = None,
                               year_from: int = None, year_to: int = None):
        """What can this search be narrowed by, and what does each choice cost?

        The counts are the point. Filters change the DENOMINATOR — narrowing to one department
        turns a 97,625-row ranking problem into a few-thousand-row one — and a count is what lets
        someone see that before clicking. They run through the same WHERE clause as the results,
        so a facet can never promise rows the search will not return.

        `artists` is served separately from `facets` because it is not a dropdown: 8,604 names
        with a 55% singleton tail cannot be a menu, so the UI spends it as a top-N browse strip
        beside a contains-match box. See `catalog.artist_facets` for why a raw GROUP BY creator
        is the wrong answer.
        """
        lib = _open(scope, project)
        f = {k: v for k, v in (("image_kind", image_kind), ("department", department),
                               ("creator", creator), ("place", place),
                               ("classification", classification),
                               ("artist_key", artist_key), ("movement", movement),
                               ("year_from", year_from), ("year_to", year_to))
             if v not in (None, "")}
        try:
            out = {name: [{"value": v, "count": c}
                          for v, c in lib.catalog.facets(name, held=0, limit=30, **f)]
                   for name in ("image_kind", "department", "classification", "place",
                                "movement")}
            artists = [{"name": n, "key": k, "count": c}
                       for n, k, c in lib.catalog.artist_facets(held=0, limit=24, **f)]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"total": lib.catalog.count("active", held=0, **f), "applied": f,
                "facets": out, "artists": artists}

    @app.get("/api/visuallib/collections")
    async def visuallib_collections(scope: str = "global", project: str = None,
                                    q: str = None, source: str = None,
                                    limit: int = 400, curated_only: bool = False):
        """Every harvested collection with its OWN coverage — the T0 tier, browsable before any
        member is captioned.

        COUNTS COME FROM ONE GROUPED QUERY. This used to call `discovery_stats(collection_id=…)`
        per collection, which was invisible at four collections and cost **119 seconds** at 581
        — the Public Domain Image Archive alone contributes 577, because it is the first source
        that yields many collections from a single crawl. Same query, one pass, 248 ms.

        `q` filters by title/slug and `curated_only` drops the whole-source harvest rows, which
        is what the Collections tab wants: a curated set someone chose, not "everything Cleveland
        has".
        """
        lib = _open(scope, project)
        counts = lib.catalog.collection_counts(held=0)
        out = []
        needle = (q or "").strip().lower()
        for c in lib.catalog.list_collections():
            got = counts.get(c.id or -1, {"indexed": 0, "described": 0})
            if source and c.source != source:
                continue
            if needle and needle not in f"{c.title} {c.slug}".lower():
                continue
            # A whole-source harvest is not a curated collection, and `upstream_count` is the
            # clean tell: only a source-wide crawl is in a position to know how big the source
            # is, so a curated set never has one. That separates "Aubrey Beardsley" (74 pictures
            # someone chose) from "Cleveland Museum of Art — CC0 artworks" (everything they have)
            # and from the `pdia-uncollected` fallback, which is a harvest bucket wearing a
            # collection's clothes.
            curated = c.upstream_count is None
            if curated_only and not curated:
                continue
            d = c.to_dict()
            n = got["indexed"] or 0
            d.update({"indexed": n, "described": got["described"],
                      "described_pct": round(100.0 * got["described"] / n, 1) if n else 0.0,
                      "curated": bool(curated)})
            out.append(d)
        out.sort(key=lambda d: -d["indexed"])
        return {"collections": out[:max(1, int(limit))], "total": len(out),
                "stats": lib.discovery_stats()}

    @app.post("/api/visuallib/harvest")
    async def visuallib_harvest(body: dict = Body(...)):
        """Start a harvest. Long by nature (~25 min for 900 artic rows; the Met costs an extra
        request per object), so it is a background job with progress, not a request."""
        from nolan.imagelib.harvest import SOURCES
        from nolan.webui import operations
        source = (body.get("source") or "").strip()
        if source not in SOURCES:
            raise HTTPException(status_code=400,
                                detail=f"unknown source {source!r} (known: {sorted(SOURCES)})")
        limit = _bounded_limit(body.get("limit"), default=200)
        job = job_manager.start(
            "visuallib-harvest", operations.harvest_visual_lib,
            meta={"source": source, "limit": limit,
                  "dept": body.get("dept") or None, "query": body.get("query") or None},
            source=source, limit=limit, dept=(body.get("dept") or None),
            query=(body.get("query") or None), scope=body.get("scope", "global"),
            project=body.get("project") or None)
        return {"job_id": job.id, "type": "visuallib-harvest"}

    @app.post("/api/visuallib/caption")
    async def visuallib_caption(body: dict = Body(default={})):
        """Caption a BOUNDED batch of not-held rows (T2, on demand). Never the whole catalog."""
        from nolan.webui import operations
        limit = _bounded_limit(body.get("limit"), default=25)
        cid = body.get("collection_id")
        job = job_manager.start(
            "visuallib-caption", operations.caption_visual_lib,
            meta={"limit": limit, "collection_id": cid},
            limit=limit, collection_id=(int(cid) if cid not in (None, "") else None),
            scope=body.get("scope", "global"), project=body.get("project") or None,
            provider=body.get("provider") or None)
        return {"job_id": job.id, "type": "visuallib-caption"}
