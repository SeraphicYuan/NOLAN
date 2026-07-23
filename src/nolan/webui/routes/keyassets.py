"""/keyassets — the Key-Assets Anchored Pool: the hero pull-list (plan) + collected-asset gallery.

Kept SEPARATE from /pool (acquisition pool) — distinct artifacts — but both feed authoring.

GET  /keyassets                       the page (static shell; data fetched client-side)
GET  /api/keyassets?project=<slug>    the pull-list view (nolan.keyassets.view.build_view)
GET  /api/keyassets/file?project=&path=   serve a collected asset file (guarded to the project dir)
"""
import json
from pathlib import Path

from fastapi import Body, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse


def _patch_entity(project_dir: Path, entity_id: str, field: str, asset_index, values: list) -> list:
    """Patch an entity's `queries` (needs asset_index) or `identifiers` in BOTH the proposal and the
    canonical key_assets.json (whichever exist), and lock the entity so a re-run won't overwrite the
    human edit. Raw-JSON patch so canonical's resolved data is untouched. Returns the files changed."""
    changed = []
    for name in ("key_assets.proposal.json", "key_assets.json"):
        p = project_dir / name
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for e in data.get("entities", []):
            if e.get("id") != entity_id:
                continue
            if field == "identifiers":
                e["identifiers"] = values
            elif field == "queries" and asset_index is not None:
                das = e.get("desired_assets", [])
                if 0 <= asset_index < len(das):
                    das[asset_index]["queries"] = values
            e["queries_locked"] = True
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            changed.append(name)
            break
    return changed


def _set_selected(project_dir: Path, file: str, selected: bool) -> bool:
    """Toggle a collected asset's `selected` flag in canonical key_assets.json (matched by file path).
    `selected` = in the FINAL key-assets pool → what P3 authoring stages. Returns True if the file matched."""
    p = project_dir / "key_assets.json"
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    hit = False
    for e in data.get("entities", []):
        for a in e.get("resolved", []) or []:
            if a.get("file") == file:
                a["selected"] = bool(selected)
                hit = True
    if hit:
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return hit


def register(app, ctx):
    templates_dir = Path(ctx.templates_dir)

    def _project_dir(project: str) -> Path:
        # Resolve at REQUEST time (not register time): ctx.projects_dir may be None when the hub is
        # built without a projects directory, and Path(None) would crash create_hub_app for EVERY route.
        if not project:
            raise HTTPException(status_code=400, detail="project required")
        if not ctx.projects_dir:
            raise HTTPException(status_code=503, detail="projects directory not configured")
        d = Path(ctx.projects_dir) / project
        if not d.is_dir():
            raise HTTPException(status_code=404, detail=f"project not found: {project}")
        return d

    @app.get("/keyassets", response_class=HTMLResponse)
    async def keyassets_page():
        return (templates_dir / "keyassets.html").read_text(encoding="utf-8")

    @app.get("/api/keyassets/projects")
    async def keyassets_projects():
        """Projects that HAVE a key-assets plan (proposal or canonical) — the dropdown source, so a
        scriptgen-only project (no scene plan, excluded from /api/scenes/projects) still shows up."""
        base = Path(ctx.projects_dir) if ctx.projects_dir else None
        if not base or not base.is_dir():
            return []
        return [d.name for d in sorted(base.iterdir())
                if d.is_dir() and ((d / "key_assets.proposal.json").exists() or (d / "key_assets.json").exists())]

    @app.get("/api/keyassets")
    async def keyassets_get(project: str = Query(...)):
        from nolan.keyassets.view import build_view
        return build_view(_project_dir(project))

    @app.post("/api/keyassets/edit")
    async def keyassets_edit(payload: dict = Body(...)):
        """Save human-edited queries/identifiers (locks the entity so a re-run won't overwrite them)."""
        base = _project_dir(str(payload.get("project") or ""))
        entity_id = str(payload.get("entity_id") or "")
        field = str(payload.get("field") or "")
        if field not in ("queries", "identifiers"):
            raise HTTPException(status_code=400, detail="field must be 'queries' or 'identifiers'")
        values = [str(v).strip() for v in (payload.get("values") or []) if str(v).strip()]
        ai = payload.get("asset_index")
        ai = int(ai) if ai is not None else None
        changed = _patch_entity(base, entity_id, field, ai, values)
        if not changed:
            raise HTTPException(status_code=404, detail="entity not found")
        return {"ok": True, "updated": changed, "values": values}

    @app.post("/api/keyassets/select")
    async def keyassets_select(payload: dict = Body(...)):
        """Refine-scope: toggle a collected asset in/out of the FINAL pool (persists to key_assets.json)."""
        base = _project_dir(str(payload.get("project") or ""))
        file = str(payload.get("file") or "")
        if not file:
            raise HTTPException(status_code=400, detail="file required")
        if not _set_selected(base, file, bool(payload.get("selected"))):
            raise HTTPException(status_code=404, detail="asset not found")
        return {"ok": True, "file": file, "selected": bool(payload.get("selected"))}

    @app.post("/api/keyassets/collect")
    async def keyassets_collect(payload: dict = Body(...)):
        """Collect (resolve → download → condition → verify) the heroes for a CURATED pull-list, then stage
        them into the author's menu. Slow (VLM-gated, ~minutes) → runs as a background job the UI polls.
        `stage` (default True) prepends the HERO block onto asset-descriptions.md after collect."""
        import asyncio

        project = str(payload.get("project") or "")
        base = _project_dir(project)
        stage = bool(payload.get("stage", True))

        async def _worker(job, base=base, stage=stage):
            from nolan.config import load_config
            from nolan.keyassets import collect
            from nolan.keyassets.inventory import write_hero_section
            from nolan.keyassets.schema import KeyAssetsProposal
            prop = KeyAssetsProposal.load(base / "key_assets.proposal.json")
            if prop is None:
                return {"ok": False, "error": "no key_assets.proposal.json — build the pull-list first"}
            job.set_progress(0.1, f"collecting {len(prop.entities)} heroes (research → download → verify)…")
            res = await asyncio.to_thread(collect, load_config(), base, prop)
            if stage:
                job.message = "staging heroes into the author's menu…"
                await asyncio.to_thread(write_hero_section, base)
            job.message = f"collected {res.get('collected', 0)} hero asset(s)"
            return {"ok": True, "collected": res.get("collected", 0), "staged": stage}

        job = ctx.job_manager.start("keyassets_collect", _worker, meta={"project": project})
        return {"ok": True, "job": job.id}

    @app.get("/api/keyassets/file")
    async def keyassets_file(project: str = Query(...), path: str = Query(...)):
        base = _project_dir(project).resolve()
        f = (base / path).resolve()
        if not str(f).startswith(str(base)) or not f.is_file():   # no path escape out of the project
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(str(f))
