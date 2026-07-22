"""SFX library routes — the sound umbrella's webUI.

Two surfaces (the /sfx page's two tabs):
  • VIEWER  — browse/search the catalog: the curated bank (in-library, playable wavs) + the crawled
              candidate pool, one FTS search over both (SoundCatalog).
  • CONTROL — run a source adapter's ops (Freesound crawl/add/remove; extensible via nolan.sound.sources)
              as background jobs on the shared JobManager.
"""
from pathlib import Path

from fastapi import Body, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse


def register(app, ctx):
    templates_dir = ctx.templates_dir
    job_manager = ctx.job_manager

    @app.get("/sfx", response_class=HTMLResponse)
    async def sfx_page():
        tpl = templates_dir / "sfx.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>sfx.html not found</h1>"

    @app.get("/api/sfx/stats")
    async def sfx_stats():
        from nolan.sound.catalog import SoundCatalog
        cat = SoundCatalog()
        try:
            return cat.stats()
        finally:
            cat.close()

    @app.get("/api/sfx/kinds")
    async def sfx_kinds():
        """The cue-kind registry (for the Add form + viewer filter) — purpose per kind."""
        from nolan.sound.registry import BY_ID, KINDS
        return {"kinds": [{"id": k, "purpose": getattr(BY_ID.get(k), "purpose", "")} for k in KINDS]}

    @app.get("/api/sfx/search")
    async def sfx_search(q: str = Query(default=""), scope: str = Query(default="all"),
                         kind: str = Query(default=""), limit: int = Query(default=60)):
        """Text search over the catalog. scope: all | curated (in library) | available (not yet).
        Curated rows carry `file` (a playable wav) + `cue_kind` + `rating`."""
        from nolan.sound.catalog import SoundCatalog
        in_lib = {"curated": True, "available": False}.get(scope, None)
        cat = SoundCatalog()
        try:
            rows = cat.search(q, limit=int(limit), in_library=in_lib)
        finally:
            cat.close()
        if kind:
            rows = [r for r in rows if r.get("library_kind") == kind]
        results = [{
            "id": r.get("ext_id"), "provider": r.get("provider", "freesound"),
            "name": r.get("name"), "tags": r.get("tags"), "duration": r.get("duration"),
            "downloads": r.get("num_downloads"), "license": r.get("license"),
            "page_url": r.get("page_url"), "in_library": bool(r.get("in_library")),
            "cue_kind": r.get("library_kind"), "rating": r.get("rating"),
            "file": r.get("library_file"),
        } for r in rows]
        return {"results": results, "count": len(results)}

    @app.get("/api/sfx/file")
    async def sfx_file(file: str = Query(...)):
        """Serve a curated wav for in-browser playback (basename-only — no path traversal)."""
        from nolan.sound.crawl import library_dir
        base = library_dir().resolve()
        fp = (base / Path(file).name).resolve()
        if base not in fp.parents or not fp.is_file():
            raise HTTPException(status_code=404, detail="sound not found")
        return FileResponse(fp, media_type="audio/wav")

    @app.get("/api/sfx/sources")
    async def sfx_sources():
        """The registered source adapters + their control schemas (drives the control tab)."""
        from nolan.sound.sources import list_sources
        return {"sources": [s.describe() for s in list_sources()]}

    @app.post("/api/sfx/run")
    async def sfx_run(body: dict = Body(...)):
        """Run a source op (crawl/add/remove) as a background job — reuses the shared JobManager."""
        import asyncio
        from nolan.sound.sources import get_source
        source_id, op, params = body.get("source"), body.get("op"), (body.get("params") or {})
        src = get_source(source_id)
        if not src:
            raise HTTPException(status_code=404, detail=f"unknown sfx source {source_id!r}")

        async def worker(job, src, op, params):
            job.set_progress(0.05, f"{src.label}: {op}…")
            res = await asyncio.get_event_loop().run_in_executor(None, lambda: src.run(op, params, job.log))
            job.set_progress(1.0, "done")
            return res

        job = job_manager.start(f"sfx-{op}", worker, meta={"source": source_id, "op": op},
                                src=src, op=op, params=params)
        return {"job_id": job.id, "type": f"sfx-{op}"}
