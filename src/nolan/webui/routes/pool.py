"""/pool — the project asset pool (media bin) routes.

GET  /pool                       the page
GET  /api/pool?project=          the derived pool (nolan.asset_pool)
POST /api/pool/shortlist         add a pool item to the shortlist
                                 {project, path, kind, scene_hint?, note?}

The pool is a DERIVED view; the only mutation here goes through the existing
shortlist store (usage tags are render-only by design — nothing in this
module can mark an asset "in-video").
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Body, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".m4v": "video/mp4",
}


def register(app, ctx):
    templates_dir = ctx.templates_dir
    projects_dir = ctx.projects_dir

    def _project_dir(project: str) -> Path:
        if not projects_dir:
            raise HTTPException(status_code=400, detail="no projects dir")
        p = Path(projects_dir) / project
        if not p.is_dir():
            raise HTTPException(status_code=404,
                                detail=f"project {project!r} not found")
        return p

    @app.get("/pool", response_class=HTMLResponse)
    async def pool_page():
        tpl = templates_dir / "pool.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        raise HTTPException(status_code=404, detail="pool.html missing")

    @app.get("/api/pool")
    async def pool_get(project: str = Query(...)):
        from nolan.asset_pool import build_pool
        return build_pool(_project_dir(project))

    @app.get("/api/pool/file")
    async def pool_file(path: str = Query(...)):
        """Serve a pool media file. Pool paths are absolute; unlike
        /scenes/file this is contained to the PROJECTS root so shortlist
        items resolved from projects/_library/** are viewable too."""
        if not projects_dir:
            raise HTTPException(status_code=400, detail="no projects dir")
        root = Path(projects_dir).resolve()
        try:
            fp = Path(path).resolve()
        except OSError:
            raise HTTPException(status_code=400, detail="bad path")
        if root not in fp.parents or not fp.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(str(fp), media_type=_MEDIA_TYPES.get(
            fp.suffix.lower(), "application/octet-stream"))

    # ---- HyperFrames comp pools (the compose-first acquisition pool) ----------------------------
    # A DIFFERENT bin from the pipeline pool: HF assets are pre-selection CANDIDATES grouped by NEED
    # (a1..aN), each carrying its acquisition provenance (source, CLIP relevance) + the VLM curation
    # verdict (usable/flags). Doubles as the per-need contact sheet.
    _THIN = 3                                     # a need with fewer usable candidates than this is "thin"

    def _hf_dir(comp: str) -> Path:
        from nolan.hyperframes import edit as hfedit
        try:
            d = hfedit.comp_dir(comp)
        except Exception:
            raise HTTPException(status_code=404, detail=f"comp {comp!r} not found")
        return d

    def _hf_comps():
        from nolan.hyperframes import edit as hfedit
        import json
        out = []
        for source, root in (("lab", hfedit.LAB_VIDEOS), ("project", hfedit.PROJECTS)):
            if not Path(root).exists():
                continue
            for d in sorted(p for p in Path(root).iterdir() if p.is_dir()):
                pj = d / "pool.json"
                if not pj.is_file():
                    continue
                try:
                    pool = json.loads(pj.read_text(encoding="utf-8"))
                except Exception:
                    continue
                needs = {it.get("id") for it in pool}
                gen = sum(1 for it in pool if "generat" in str(it.get("source", "")).lower())
                out.append({"name": d.name, "source": source, "assets": len(pool),
                            "needs": len(needs), "generated": gen})
        return out

    @app.get("/api/pool/hf/comps")
    async def hf_comps():
        return {"comps": _hf_comps()}

    @app.get("/api/pool/hf")
    async def hf_pool(comp: str = Query(...)):
        import json
        d = _hf_dir(comp)
        pj = d / "pool.json"
        if not pj.is_file():
            raise HTTPException(status_code=404, detail="no pool.json for this comp")
        pool = json.loads(pj.read_text(encoding="utf-8"))
        needs = {}
        nf = d / "capture" / "needs.json"
        if nf.is_file():
            try:
                needs = {n["id"]: n for n in json.loads(nf.read_text(encoding="utf-8"))}
            except Exception:
                needs = {}
        assets = d / "capture" / "assets"
        from nolan.hyperframes import edit as hfedit
        try:                                                    # reverse index: which SCENES reference each file
            usage = hfedit.asset_scene_usage(comp)
        except Exception:
            usage = {"by_file": {}, "scene_order": []}
        by_file = usage.get("by_file", {})

        def _provider(src: str) -> str:
            s = str(src or "?")
            if "generat" in s.lower():
                return "generated"
            return s.split(":")[-1]

        bins, providers = {}, set()
        for it in pool:
            nid = it.get("id", "?")
            src = it.get("source", "?")
            prov = _provider(src)
            providers.add(prov)
            kind = it.get("media_type") or "image"
            f = it.get("file")
            # the working copy under <comp>/assets/ is what renders (frame grounds ref assets/…); quick-edit
            # targets it via the /api/hf/asset/* routes as a comp-relative `assets/<file>` path.
            item = {"file": f, "kind": kind, "source": src, "provider": prov,
                    "relevance": it.get("relevance"), "usable": it.get("usable"),
                    "selected": bool(it.get("selected", True)),   # refine-scope: in the author's menu?
                    "flags": it.get("flags") or "", "caption": it.get("caption") or "",
                    "license": it.get("license") or "", "source_url": it.get("source_url") or "",
                    "photographer": it.get("photographer") or "",
                    "exists": bool(f) and ((assets / f).is_file() or (d / "assets" / f).is_file()),
                    "path": f"assets/{f}" if f else None,
                    "editable": bool(f) and (d / "assets" / f).is_file(),
                    "scenes": by_file.get(f, []) if f else [],   # scenes that actually reference this file
                    "url": f"/api/pool/hf/file?comp={comp}&file={f}"}
            b = bins.setdefault(nid, {"need": nid, "query": (needs.get(nid) or {}).get("query", it.get("query", "")),
                                      "evocative": bool((needs.get(nid) or {}).get("evocative")),
                                      "media_type": (needs.get(nid) or {}).get("media_type", kind), "items": []})
            b["items"].append(item)

        def _nkey(nid):
            return (0, int(nid[1:])) if nid[:1] == "a" and nid[1:].isdigit() else (1, nid)
        binlist = []
        thin = []
        for nid in sorted(bins, key=_nkey):
            b = bins[nid]
            b["count"] = len(b["items"])
            b["generated"] = sum(1 for i in b["items"] if i["provider"] == "generated")
            b["real"] = b["count"] - b["generated"]
            b["thin"] = b["count"] < _THIN
            if b["thin"]:
                thin.append(nid)
            binlist.append(b)
        return {"comp": comp, "total": len(pool), "providers": sorted(providers),
                "thin_needs": thin, "bins": binlist, "scene_order": usage.get("scene_order", [])}

    @app.get("/api/pool/hf/file")
    async def hf_file(comp: str = Query(...), file: str = Query(...)):
        # serve from capture/assets/ (acquisition mirror) OR fall back to assets/ (the working set) — so
        # cleaned/edited outputs that land in assets/ are viewable here too.
        d = _hf_dir(comp)
        for root in ((d / "capture" / "assets").resolve(), (d / "assets").resolve()):
            try:
                fp = (root / file).resolve()
            except OSError:
                raise HTTPException(status_code=400, detail="bad path")
            if root in fp.parents and fp.is_file():
                return FileResponse(str(fp), media_type=_MEDIA_TYPES.get(
                    fp.suffix.lower(), "application/octet-stream"))
        raise HTTPException(status_code=404, detail="not found")

    @app.post("/api/pool/hf/select")
    async def hf_select(body: dict = Body(...)):
        """Refine-scope for the HF pool: toggle an asset in/out of the FINAL pool. Persists to pool.json
        AND re-writes asset-descriptions.md filtered to selected — so a deselected asset leaves the HF
        author's menu (closing the 'human curation never reaches the HF author' gap)."""
        comp = (body.get("comp") or "").strip()
        file = (body.get("file") or "").strip()
        if not (comp and file):
            raise HTTPException(status_code=400, detail="comp and file are required")
        from nolan.hyperframes.pool_select import set_pool_selected
        if not set_pool_selected(_hf_dir(comp), file, bool(body.get("selected"))):
            raise HTTPException(status_code=404, detail="asset not found in pool.json")
        return {"comp": comp, "file": file, "selected": bool(body.get("selected"))}

    @app.post("/api/pool/shortlist")
    async def pool_shortlist(body: dict = Body(...)):
        project = (body.get("project") or "").strip()
        path = (body.get("path") or "").strip()
        if not (project and path):
            raise HTTPException(status_code=400,
                                detail="project and path are required")
        pdir = _project_dir(project)
        from nolan import shortlist
        item = {
            "key": f"path:{path}",
            "kind": body.get("kind") or "image",
            "label": Path(path).name,
            "payload": {"op": "add", "source": "path", "path": path,
                        "kind": body.get("kind") or "image"},
        }
        if body.get("scene_hint"):
            item["scene_hint"] = body["scene_hint"]
        if body.get("note"):
            item["note"] = body["note"]
        items = shortlist.add(pdir, [item])
        return {"project": project, "count": len(items), "added": item["key"]}
