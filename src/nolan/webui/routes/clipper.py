"""URL clipper — paste a video link (YouTube / direct .mp4 / .m3u8 / local file), scrub it, mark [in, out],
and pull just that range with ffmpeg/yt_dlp into a folder (optionally straight into a HyperFrames project's
pool). Deliberately does NOT go through the ingestion library and never downloads the whole file.

  GET  /clipper                     the page
  POST /api/clipper/probe           {url} -> {kind,title,duration,thumbnail,src|video_id}
  POST /api/clipper/clip            {url,kind,start,end,name,comp?,folder?} -> saves the range, optional pool add
  GET  /api/clipper/proxy?url=      Range-streaming proxy so a direct/HLS <video> is seekable despite CORS
  GET  /api/clipper/file?path=      serve a local source (or a just-made clip) for in-browser playback
  GET  /api/clipper/targets         {comps:[...], default_folder} for the destination picker
"""
import asyncio
import re
import urllib.request
from pathlib import Path

from fastapi import Body, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from nolan import clipper
from nolan.hyperframes import edit as hfedit


def register(app, ctx):
    templates_dir = ctx.templates_dir
    repo_root = ctx.repo_root
    page = templates_dir / "clipper.html"
    default_folder = repo_root / "projects" / "_library" / "source" / "clips"

    def _safe_name(name: str, fallback: str = "clip") -> str:
        base = re.sub(r"[^\w.-]+", "_", (name or "").strip()).strip("._") or fallback
        return base[:-4] if base.lower().endswith(".mp4") else base

    @app.get("/clipper", response_class=HTMLResponse)
    async def clipper_page():
        return page.read_text(encoding="utf-8") if page.exists() else "<h1>clipper template missing</h1>"

    @app.get("/api/clipper/targets")
    async def clipper_targets():
        try:
            comps = [c.get("name") if isinstance(c, dict) else c for c in hfedit.discover_compositions()]
        except Exception:
            comps = []
        return {"comps": comps, "default_folder": str(default_folder)}

    @app.post("/api/clipper/probe")
    async def clipper_probe(payload: dict = Body(...)):
        url = (payload.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="url required")
        try:
            return await asyncio.to_thread(clipper.probe, url)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"could not read that source: {type(e).__name__}: {e}")

    @app.post("/api/clipper/clip")
    async def clipper_clip(payload: dict = Body(...)):
        url = (payload.get("url") or "").strip()
        try:
            start, end = float(payload.get("start")), float(payload.get("end"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="start and end (seconds) required")
        if not url or end <= start:
            raise HTTPException(status_code=400, detail="url + out-after-in required")
        kind = payload.get("kind") or clipper.kind_of(url)
        name = _safe_name(payload.get("name"), fallback=f"clip_{int(start)}_{int(end)}")
        comp = (payload.get("comp") or "").strip() or None

        # destination: a project's assets/ (when adding to a pool — resolve_asset then registers it in place,
        # no second copy) or the chosen/default folder
        if comp:
            try:
                out = hfedit.comp_dir(comp) / "assets" / f"{name}.mp4"
            except Exception as e:
                raise HTTPException(status_code=404, detail=f"comp {comp!r}: {e}")
        else:
            folder = Path(payload.get("folder") or default_folder)
            out = folder / f"{name}.mp4"

        try:
            saved = await asyncio.to_thread(clipper.clip, url, start, end, out, kind=kind)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"clip failed: {type(e).__name__}: {e}")
        if not saved:
            raise HTTPException(status_code=422, detail="clip produced no file (source may be unavailable)")

        pooled = False
        if comp:
            try:
                await asyncio.to_thread(hfedit.resolve_asset, comp, str(saved))   # land in assets/ + register in pool.json
                pooled = True
            except Exception:
                pooled = False
        return {"ok": True, "path": str(saved), "name": saved.name, "pooled": pooled, "comp": comp}

    @app.get("/api/clipper/file")
    async def clipper_file(path: str = Query(...)):
        p = Path(path)
        if not p.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        return FileResponse(str(p))

    @app.get("/api/clipper/proxy")
    async def clipper_proxy(url: str = Query(...), request: Request = None):
        """Range-forwarding proxy so a cross-origin direct/HLS <video> stays seekable (single-file Range).
        Local dev tool: http(s) only (no file:// / SSRF into non-web schemes)."""
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="only http(s) sources can be proxied")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NOLAN clipper)"})
        rng = request.headers.get("range") if request else None
        if rng:
            req.add_header("Range", rng)
        try:
            upstream = await asyncio.to_thread(urllib.request.urlopen, req, None, 20)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"upstream fetch failed: {e}")
        status = getattr(upstream, "status", 200) or 200
        headers = {}
        for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
            v = upstream.headers.get(h)
            if v:
                headers[h] = v
        headers.setdefault("Accept-Ranges", "bytes")

        def _stream():
            try:
                while True:
                    chunk = upstream.read(65536)
                    if not chunk:
                        break
                    yield chunk
            finally:
                upstream.close()

        return StreamingResponse(_stream(), status_code=status,
                                 headers=headers, media_type=headers.get("Content-Type"))
