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
    async def visuallib_sources(scope: str = "global", project: str = None):
        """The harvest registry, as the UI's menu — PLUS what each source has actually delivered.

        ONE ROW PER SOURCE. The Sources tab used to render the collections table, which was the
        same thing while every source produced exactly one collection and became 581 lines the
        moment the Public Domain Image Archive contributed 577. A source is an institution we
        crawl; how many collections it yielded is a FACT ABOUT IT, not a reason to list it 577
        times.

        Derived from the registry, so a new adapter appears in the form the moment it is
        registered and a removed one cannot linger as a dead button. Each entry names the
        `enumeration` its crawler uses, because that is what decides whether the generic form can
        drive it: `curated-collection` (pdia) walks a JSON API and files rows under per-item
        collections, `bulk-dump` (met) reads a 300 MB CSV, `bulk-listing` (artic, cleveland)
        pages an endpoint. `harvest()` dispatches on `SOURCES[name].items`, so selecting a source
        in the form runs THAT source's crawler — there is no generic walker.
        """
        from nolan.imagelib.harvest import ENUMERATION, MET_DEPARTMENTS, SOURCES
        lib = _open(scope, project)
        counts = lib.catalog.collection_counts(held=0)
        per_source: dict = {}
        for c in lib.catalog.list_collections():
            agg = per_source.setdefault(c.source, {"rows": 0, "collections": 0,
                                                   "upstream": None, "last_crawled": None,
                                                   "rights": None})
            agg["rows"] += counts.get(c.id or -1, {}).get("indexed", 0)
            agg["collections"] += 1
            if c.upstream_count:
                agg["upstream"] = (agg["upstream"] or 0) + c.upstream_count
            if c.rights and not agg["rights"]:
                agg["rights"] = c.rights
            if c.last_crawled and (agg["last_crawled"] or "") < c.last_crawled:
                agg["last_crawled"] = c.last_crawled

        out = []
        for name, adapter in sorted(SOURCES.items()):
            col = adapter.collection()
            got = per_source.get(name, {})
            out.append({"id": name, "title": col.title, "rights": got.get("rights") or col.rights,
                        "description": col.description,
                        # what this source has ACTUALLY delivered, not what it could
                        "indexed": got.get("rows", 0),
                        "collections": got.get("collections", 0),
                        "upstream": got.get("upstream"),
                        "last_crawled": got.get("last_crawled"),
                        "gate_tier": adapter.gate_tier,
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
                               movement: str = None, source: str = None,
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
                               ("source", source),
                               ("year_from", year_from), ("year_to", year_to))
             if v not in (None, "")}
        try:
            out = {name: [{"value": v, "count": c}
                          for v, c in lib.catalog.facets(name, held=0, limit=30, **f)]
                   # `source` first: once one institution can outweigh all the others, "which
                   # library am I even looking at" is the OUTERMOST question, not the innermost.
                   for name in ("source", "image_kind", "department", "classification",
                                "place", "movement")}
            artists = [{"name": n, "key": k, "count": c}
                       for n, k, c in lib.catalog.artist_facets(held=0, limit=24, **f)]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"total": lib.catalog.count("active", held=0, **f), "applied": f,
                "facets": out, "artists": artists}

    @app.get("/api/visuallib/artists")
    async def visuallib_artists(scope: str = "global", project: str = None,
                                q: str = None, limit: int = 200, offset: int = 0,
                                kind: str = None, known: str = None):
        """The visual knowledge table — one row per MAKER, with the work count it earns.

        A separate resource from `/facets`'s artist strip, which answers "which artists are in the
        current result set" in 24 chips. This answers "who is in this library, and what do we know
        about them" — the table itself, browsable and sortable, which until now had no surface at
        all: 4,115 rows of dates, nationality, movement and biography reachable only from a card
        that happened to show one of their pictures.

        Counts come from ONE grouped query over `assets.artist_key`, not a lookup per artist —
        the same shape the collections list had to be rewritten into when 581 collections cost
        119 seconds.
        """
        lib = _open(scope, project)
        counts = {k: n for k, _, n in lib.catalog.creator_histogram(held=0)}
        needle = (q or "").strip().lower()
        rows = []
        for a in lib.catalog.list_artists(limit=100_000):
            n = counts.get(a.name_key or "", 0)
            if kind and (a.kind or "") != kind:
                continue
            # "known" means we actually learned something — as opposed to a row that exists only
            # to record that we looked and Wikidata did not have them.
            has = bool(a.birth_year or a.nationality or a.movement or a.biography)
            if known == "yes" and not has:
                continue
            if known == "no" and has:
                continue
            if needle and needle not in f"{a.name} {a.nationality or ''} {a.movement or ''}".lower():
                continue
            d = a.to_dict()
            d.update({"works": n, "lifespan": a.lifespan(), "sources": a.sources,
                      "active_years": a.active_years(), "known": has})
            d.pop("sources_json", None)
            rows.append(d)
        rows.sort(key=lambda d: -d["works"])
        total = len(rows)
        off = max(0, int(offset))
        page = rows[off:off + max(1, int(limit))]
        # What the TABLE covers, not what this page shows — a list that renders 200 of 4,115 and
        # says nothing about the rest reads as "that is all there is".
        return {"artists": page, "total": total, "offset": off,
                "stats": {"rows": len(counts), "in_table": total,
                          "with_dates": sum(1 for d in rows if d.get("birth_year")),
                          "with_qid": sum(1 for d in rows if d.get("wikidata_qid")),
                          "organizations": sum(1 for d in rows if d.get("kind") == "organization")}}

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
                      # a member with pixels, so the card can show the collection instead of
                      # describing it — comes free with the counts query
                      "cover_id": got.get("cover"),
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
