"""Images Extract routes for the NOLAN hub.

Moved verbatim from ``nolan.hub.create_hub_app`` (hub split). ``register(app,
ctx)`` unpacks the shared hub context into locals with the original closure
names, then registers the routes unchanged.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict

import httpx
from urllib.parse import quote
from fastapi import HTTPException, Query, UploadFile, File, Form, Body
from fastapi.responses import HTMLResponse, FileResponse


def register(app, ctx):
    templates_dir = ctx.templates_dir
    job_manager = ctx.job_manager

    # ==================== Asset extraction (link -> assets) ====================

    @app.get("/extract", response_class=HTMLResponse)
    async def extract_page():
        tpl = templates_dir / "extract.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>extract.html not found</h1>"

    @app.post("/api/extract-assets")
    async def api_extract_assets(body: dict = Body(...)):
        """Extract image assets from a URL.

        Without ``download`` runs synchronously and returns the found assets for
        a gallery preview; with ``download`` starts a background job.
        """
        url = (body.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="url is required")
        limit = body.get("limit") or None

        if body.get("download") or body.get("save_to_library"):
            from nolan.webui import operations
            job = job_manager.start(
                "extract-assets", operations.extract_assets, meta={"url": url},
                url=url, limit=limit, download=bool(body.get("download", True)),
                dest=(body.get("dest") or None),
                save_to_library=bool(body.get("save_to_library")),
                scope=(body.get("scope") or "global"),
                project=(body.get("project") or None),
            )
            return {"job_id": job.id, "type": "extract-assets"}

        import asyncio as _asyncio
        from nolan.extractors import extract_from_url, get_extractor
        ex = get_extractor(url)
        try:
            results = await _asyncio.to_thread(extract_from_url, url, limit=limit)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"extract failed: {e}")
        return {"extractor": ex.name, "count": len(results),
                "results": [r.to_dict() for r in results]}

    # ==================== Picture library ====================

    @app.get("/images", response_class=HTMLResponse)
    async def images_page():
        tpl = templates_dir / "images.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>images.html not found</h1>"

    def _open_imagelib(scope: str, project: Optional[str]):
        # SHARED, not per request. This used to build a new ImageLibrary every call, which meant
        # reloading CLIP and re-opening chroma each time: 90 s per search at 97,610 rows against
        # 2.4 s with a reused instance. The search was never the slow part.
        from nolan.imagelib import shared_library
        return shared_library(scope=scope or "global", project=(project or None))

    def _img_dict(asset, score, scope, project):
        return {
            "id": asset.id, "title": asset.title, "license": asset.license,
            "source": asset.source, "source_url": asset.source_url,
            "width": asset.width, "height": asset.height, "score": score,
            "scope": scope, "scope_project": project,
            "raw": f"/api/images/raw?scope={scope}&project={project or ''}&id={asset.id}",
        }

    @app.get("/api/images/search")
    async def api_images_search(q: str, scope: str = "global", project: str = None,
                                k: int = 24, license: str = None):
        import asyncio as _asyncio

        def _do():
            from nolan.imagelib import ImageLibrary
            scopes = []
            if scope in ("global", "both"):
                scopes.append(("global", None))
            if scope in ("project", "both") and project:
                scopes.append(("project", project))
            if not scopes:
                scopes = [("global", None)]
            hits = []
            for sc, pr in scopes:
                lib = ImageLibrary(scope=sc, project=pr)
                for h in lib.search(q, k=k, license_contains=license):
                    hits.append(_img_dict(h.asset, h.score, sc, pr))
            hits.sort(key=lambda d: (d["score"] or 0), reverse=True)
            return hits[:k]

        return {"query": q, "results": await _asyncio.to_thread(_do)}

    @app.get("/api/images/discover")
    async def api_images_discover(q: str = "", scope: str = "global", project: str = None,
                                  k: int = 24, offset: int = 0, collection_id: int = None,
                                  warm: bool = False, warm_embed: bool = False,
                                  use_clip: bool = False,
                                  image_kind: str = None, department: str = None,
                                  creator: str = None, place: str = None,
                                  classification: str = None, artist_key: str = None,
                                  movement: str = None, source: str = None,
                                  year_from: int = None, year_to: int = None):
        """Search the NOT-HELD tier (Visual Lib). A hit is a POINTER, not a file — its `raw`
        serves the 512px thumbnail we do hold, and `fetch` is what pulls the real image.

        `warm` fetches pixels for the rows on THIS page and PERSISTS them — file on disk,
        `thumb_path` on the row, CLIP vector in the look channel. It is **off by default**, and
        that default was corrected after measuring it:

        * On a LOOK query it acquires NOTHING. Look ranking is CLIP-dominant (0.9), and CLIP only
          knows rows that already have pixels — so a row without them cannot rank high enough to
          be warmed. The rows that need pixels can never earn them. Search-driven warming cannot
          escape that loop; `backfill_pixels` is what grows coverage.
        * On a NAMED query it fired 21 fetches and took **32 seconds**, against 0.5 s without.
        * It can also RETIRE rows: pixels that fail the gate set `status='rejected'`. A write
          hiding inside a read is not something to do implicitly on every keystroke.

        So it stays available and deliberate — a button, not a default.

        `use_clip` is OFF for this page. The look channel is the only thing that needs the CLIP
        model, and `self.embedder` is lazy, so a hub whose search page never asks for it never
        loads the ~150 MB model at all. Search is then catalog identity + lexical title + facets,
        which the eval measures at named 92.9/100/100 and look 7.1/25.0/32.1 — stated plainly,
        because turning the look channel off is a real trade, not a free saving.

        `warm_embed` is OFF for the same reason. Warming still downloads the thumbnail and keeps
        it (so the card has a picture and the row is never re-fetched), but skips the CLIP vector
        — measured at ~48 ms/row for the fetch against ~103 ms/row for the embed. Rows join the
        look channel through `backfill_pixels`, in bulk, deliberately.
        """
        import asyncio as _asyncio

        facets = {kk: vv for kk, vv in (
            ("image_kind", image_kind), ("department", department), ("creator", creator),
            ("place", place), ("classification", classification),
            ("artist_key", artist_key), ("movement", movement), ("source", source),
            ("year_from", year_from), ("year_to", year_to)) if vv not in (None, "")}

        def _do():
            lib = _open_imagelib(scope, project)
            if q.strip():
                rows = [(h.asset, h.score) for h in
                        lib.search_discovery(q, k=k, offset=offset, collection_id=collection_id,
                                             warm=warm, warm_embed=warm_embed,
                                             use_clip=use_clip, **facets)]
            else:
                # An EMPTY query with filters is a legitimate browse — "show me Japanese prints"
                # needs no search terms at all, and is exactly what facets are for.
                browsed = lib.catalog.list(status="active", held=0, limit=k, offset=offset,
                                           collection_id=collection_id, **facets)
                # ...and it must honour `warm` too. It did not: warming lived only inside
                # `search_discovery`, so the "Get thumbnails" button silently did NOTHING
                # whenever the query box was empty — which is the normal way to browse a
                # filtered slice. An authored control with no consumer on one of its two paths
                # (WIRING_CHECKLIST pitfall #1), and invisible because the failure was silence.
                if warm and browsed:
                    got = lib.warm_pixels(browsed, embed=warm_embed)
                    if got.get("fetched") or got.get("refused"):
                        fresh = lib.catalog.get_many([a.id for a in browsed])
                        browsed = [fresh.get(a.id, a) for a in browsed
                                   if fresh.get(a.id, a).status == "active"]
                rows = [(a, None) for a in browsed]
            # collection id -> title, built ONCE per request (4 ms for all 581) so a card can
            # name the set a picture belongs to. Per-row it would be 24 lookups.
            _coll = {c.id: c.title for c in lib.catalog.list_collections()}
            # THE VISUAL KNOWLEDGE JOIN. What is true of the maker — dates, nationality, movement,
            # a line of biography — lives once in `artists` and is spent across every work they
            # made, so a card can say "Utagawa Hiroshige (Japan, 1797–1858)" without any of that
            # being copied onto 2,437 rows. One query for the whole page, keyed on the fold
            # `assets.artist_key` already stores.
            _artists = lib.catalog.get_artists(a.artist_key for a, _ in rows)
            out = []
            for a, score in rows:
                d = _img_dict(a, score, scope, project)
                d.update({"held": 0, "source_ref": a.source_ref, "creator": a.creator,
                          # the SUBJECT axis and the collection, both of which the card shows
                          "subject": a.subject, "culture": a.culture,
                          "collection_id": a.collection_id,
                          "collection_title": _coll.get(a.collection_id),
                          "date_text": a.date_text, "institution": a.institution,
                          "wikidata_qid": a.wikidata_qid,
                          "image_kind": a.image_kind, "department": a.department,
                          "classification": a.classification, "place": a.place,
                          "artist_key": a.artist_key, "movement": a.movement,
                          "year_from": a.year_from, "year_to": a.year_to,
                          "has_pixels": bool(a.thumb_path),
                          "captioned": bool(a.description_source
                                            and a.description_source != "catalog")})
                art = _artists.get(a.artist_key or "")
                if art:
                    d["artist"] = {
                        "name": art.name, "key": art.name_key, "kind": art.kind,
                        "lifespan": art.lifespan(), "nationality": art.nationality,
                        "movement": art.movement, "period": art.period, "style": art.style,
                        "biography": art.biography, "wikipedia_url": art.wikipedia_url,
                        "wikidata_qid": art.wikidata_qid,
                        # WHO SAID SO, per field — a looked-up date and a generated one are not
                        # the same claim, and the card is where that has to stay visible.
                        "sources": art.sources}
                out.append(d)
            # `offset` and `total` ride back so the page can say what it is NOT showing. A grid
            # that renders 24 of 5,480 and offers no way to the 25th reads as "that is all there
            # is" — the same silent-cap failure this tier exists to avoid, one layer up.
            # NO COLLECTIONS LIST. This returned every collection on EVERY search — 274 KB of a
            # 402 KB response once PDIA brought the count to 581, re-sent on every keystroke, to
            # populate a dropdown the page already fills from `/api/visuallib/collections`. It
            # was invisible at four collections and is two thirds of the payload at 581.
            return {"results": out, "offset": offset, "k": k,
                    "total": lib.catalog.count("active", held=0,
                                               collection_id=collection_id, **facets),
                    "stats": lib.discovery_stats(collection_id=collection_id)}

        return await _asyncio.to_thread(_do)

    @app.post("/api/images/{asset_id}/fetch")
    async def api_images_fetch(asset_id: int, body: dict = Body(default={})):
        """Promote one discovery row into the held library (downloads + gates the real image)."""
        import asyncio as _asyncio
        lib = _open_imagelib(body.get("scope", "global"), body.get("project"))

        def _do():
            return lib.promote_to_held(asset_id, tier=body.get("tier", "archival"))
        try:
            asset, promoted = await _asyncio.to_thread(_do)
        except ValueError as e:                       # a gate refusal is the caller's business
            raise HTTPException(status_code=422, detail=str(e))
        return {"ok": True, "promoted": promoted,
                "asset": _img_dict(asset, None, body.get("scope", "global"),
                                   body.get("project"))}

    @app.get("/api/images/list")
    async def api_images_list(scope: str = "global", project: str = None,
                              source: str = None, license: str = None,
                              status: str = "active", limit: int = 60):
        lib = _open_imagelib(scope, project)
        items = [_img_dict(a, None, scope, project)
                 for a in lib.list(status=status, source=source,
                                   license_contains=license, limit=limit)]
        return {"results": items, "stats": lib.stats()}

    @app.get("/api/images/raw")
    async def api_images_raw(id: int, scope: str = "global", project: str = None):
        lib = _open_imagelib(scope, project)
        a = lib.catalog.get(id)
        if not a:
            raise HTTPException(status_code=404, detail="asset not found")
        path = (lib.base / a.path).resolve()
        if not str(path).startswith(str(lib.base.resolve())) or not path.exists():
            raise HTTPException(status_code=404, detail="file missing")
        return FileResponse(str(path))

    @app.post("/api/images/{asset_id}/reject")
    async def api_images_reject(asset_id: int, body: dict = Body(default={})):
        lib = _open_imagelib(body.get("scope", "global"), body.get("project"))
        lib.set_status(asset_id, "rejected")
        return {"ok": True, "id": asset_id}

    @app.post("/api/images/add")
    async def api_images_add(body: dict = Body(...)):
        """Ingest an image by URL into the library (tagged with an optional topic)."""
        import asyncio as _asyncio
        url = (body.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="url is required")

        def _do():
            lib = _open_imagelib(body.get("scope", "global"), body.get("project"))
            asset, created = lib.add_url(
                url, source=(body.get("source") or "web"),
                license=body.get("license"), query=body.get("query"))
            return {"id": asset.id, "created": created, "title": asset.title}
        try:
            return await _asyncio.to_thread(_do)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"add failed: {e}")

    @app.post("/api/images/{asset_id}/promote")
    async def api_images_promote(asset_id: int, body: dict = Body(default={})):
        """Copy a project asset into the global library."""
        import asyncio as _asyncio
        project = body.get("project")
        if not project:
            raise HTTPException(status_code=400, detail="project is required")

        def _do():
            from nolan.imagelib import promote_to_global
            asset, created = promote_to_global(project, asset_id)
            return {"ok": True, "global_id": asset.id, "created": created}
        try:
            return await _asyncio.to_thread(_do)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/images/{asset_id}/cutout")
    async def api_images_cutout(asset_id: int, body: dict = Body(default={})):
        """Remove an image's background -> new transparent-PNG asset in the same library."""
        import asyncio as _asyncio
        import os
        import tempfile
        model = body.get("model", "birefnet")
        scope = body.get("scope", "global")
        project = body.get("project")

        def _do():
            from nolan.cutout import remove_background
            lib = _open_imagelib(scope, project)
            a = lib.catalog.get(asset_id)
            if not a:
                raise HTTPException(status_code=404, detail="asset not found")
            src = (lib.base / a.path).resolve()
            if not str(src).startswith(str(lib.base.resolve())) or not src.exists():
                raise HTTPException(status_code=404, detail="file missing")
            rgba = remove_background(str(src), model=model,
                                     alpha_matting=bool(body.get("alpha_matting")))
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            try:
                rgba.save(tmp.name)
                tmp.close()
                title = (a.title or f"asset {asset_id}") + " (cutout)"
                new_asset, created = lib.add_file(
                    tmp.name, source="cutout", title=title,
                    tags=["cutout", model], describe=False)
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
            return {**_img_dict(new_asset, None, scope, project), "created": created}

        try:
            return await _asyncio.to_thread(_do)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"cutout failed: {e}")

    @app.post("/api/images/{asset_id}/cutout/preview")
    async def api_images_cutout_preview(asset_id: int, body: dict = Body(default={})):
        """Preview a cutout as a transparent PNG — does NOT save to the library."""
        import asyncio as _asyncio
        from io import BytesIO
        from starlette.responses import Response
        model = body.get("model", "birefnet")
        scope = body.get("scope", "global")
        project = body.get("project")

        def _do():
            from nolan.cutout import remove_background
            lib = _open_imagelib(scope, project)
            a = lib.catalog.get(asset_id)
            if not a:
                raise HTTPException(status_code=404, detail="asset not found")
            src = (lib.base / a.path).resolve()
            if not str(src).startswith(str(lib.base.resolve())) or not src.exists():
                raise HTTPException(status_code=404, detail="file missing")
            rgba = remove_background(str(src), model=model,
                                     alpha_matting=bool(body.get("alpha_matting")))
            buf = BytesIO()
            rgba.save(buf, format="PNG")
            return buf.getvalue()

        try:
            data = await _asyncio.to_thread(_do)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"cutout failed: {e}")
        return Response(content=data, media_type="image/png")

    @app.get("/api/images/stats")
    async def api_images_stats(scope: str = "global", project: str = None):
        return _open_imagelib(scope, project).stats()
