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


def queue_clip_ingest(job_manager, db_path, config, clip_path):
    """Enqueue a LIGHT background ingest of a freshly-clipped range so it becomes searchable in the
    library (operations.ingest indexes the short clip + auto-embeds, per step-1). Non-blocking — the
    clip is already saved; this just makes it reusable in FUTURE projects, not only the current pool.
    Returns the ingest job id, or None on failure (never raises — a failed enqueue must not fail the
    clip). Jobs run as independent tasks on the shared loop, so multiple clips ingest in parallel."""
    try:
        from nolan.webui import operations
        job = job_manager.start(
            "ingest", operations.ingest,
            meta={"target": Path(clip_path).name, "source": "clipper"},
            config=config, db_path=db_path, source_type="file",
            target=str(clip_path), provider="openrouter",
        )
        return job.id
    except Exception:
        return None


def clipper_vlm_check(paths, query: str) -> dict:
    """Ask the cheap VLM whether the confirm frames actually show `query` — advisory assist for the human
    review. Returns {match: bool|None, note: str}. Same OpenRouter call as the transcript visual tier."""
    import base64
    import json as _json

    import httpx

    from nolan.config import load_config
    from nolan.transcript_frames import CAPTION_MODEL
    key = load_config().vision.openrouter_api_key
    if not key:
        return {"match": None, "note": "no vision API key configured"}
    content = [{"type": "text", "text": (
        f'These frames are sampled evenly from a short video clip. Does this footage show: "{query}"? '
        'Reply ONLY as JSON: {"match": true|false, "note": "<one short sentence of what is actually shown>"}.')}]
    for p in list(paths)[:4]:
        b64 = base64.b64encode(Path(p).read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    body = {"model": CAPTION_MODEL, "reasoning": {"enabled": False},
            "messages": [{"role": "user", "content": content}]}
    r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
                   headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60)
    r.raise_for_status()
    txt = r.json()["choices"][0]["message"]["content"]
    st, en = txt.find("{"), txt.rfind("}")
    try:
        d = _json.loads(txt[st:en + 1]) if st >= 0 and en > st else {}
    except Exception:
        d = {}
    return {"match": d.get("match"), "note": (d.get("note") or txt[:160]).strip()}


def register(app, ctx):
    templates_dir = ctx.templates_dir
    repo_root = ctx.repo_root
    job_manager = ctx.job_manager
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

        # Optionally (default on) ALSO index the clip into the searchable library, as a background job so
        # heavy/rapid clipping in the page isn't blocked. This is the seam that connects clip-from-url to
        # the semantic library — a clipped range becomes reusable across FUTURE projects, not just this pool.
        ingest_job_id = None
        if payload.get("ingest", True):
            from nolan.config import load_config
            cfg = load_config()
            idb = ctx.db_path or Path(cfg.indexing.database).expanduser()
            ingest_job_id = queue_clip_ingest(job_manager, idb, cfg, saved)
        return {"ok": True, "path": str(saved), "name": saved.name, "pooled": pooled,
                "comp": comp, "ingest_job_id": ingest_job_id}

    @app.post("/api/clip-range/preview")
    async def clip_range_preview(payload: dict = Body(...)):
        """feedback-2 REVIEW step: given a search hit's range, grab N confirm frames (low-res, no full
        download) so a human can eyeball + adjust the in/out BEFORE committing. Also resolves the URL the
        commit should pull from — for archive that's the HIGH-DEF derivative (two-tier policy)."""
        import tempfile
        from urllib.parse import quote
        url = (payload.get("url") or "").strip()
        kind = payload.get("kind") or None
        try:
            start, end = float(payload.get("start")), float(payload.get("end"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="start and end (seconds) required")
        if not url or end <= start:
            raise HTTPException(status_code=400, detail="url + out-after-in required")
        n = max(1, min(int(payload.get("n_frames", 4) or 4), 8))
        times = [round(start + (i + 0.5) * (end - start) / n, 2) for i in range(n)]
        out_dir = Path(tempfile.mkdtemp(prefix="cliprange_"))
        try:
            frames = await asyncio.to_thread(clipper.preview_frames, url, times, out_dir, kind)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"could not read that source: {type(e).__name__}: {e}")
        # what the COMMIT should pull: archive -> high-def derivative (kind=direct); else the source itself
        commit_url, commit_kind = url, (kind or clipper.kind_of(url))
        if commit_kind == "archive" or "archive.org/details/" in url:
            try:
                commit_url = await asyncio.to_thread(clipper.resolve_media_url, url, "archive", 720, "clip")
                commit_kind = "direct"
            except Exception:
                commit_url, commit_kind = url, "extractor"        # fall back to yt_dlp's archive.org extractor
        return {"in": start, "out": end, "times": times,
                "frames": [f"/api/clipper/file?path={quote(str(f))}" for f in frames],
                "commit_url": commit_url, "commit_kind": commit_kind}

    @app.post("/api/clip-range/vlm")
    async def clip_range_vlm(payload: dict = Body(...)):
        """Optional AI assist for the review: ask the vision model whether the confirm frames actually show
        what the hit was about. Advisory only — the human still decides."""
        from urllib.parse import unquote, urlparse as _up
        frame_urls = payload.get("frames") or []
        query = (payload.get("query") or "").strip()
        paths = []
        for u in frame_urls[:4]:
            q = _up(u).query
            p = dict(kv.split("=", 1) for kv in q.split("&") if "=" in kv).get("path", "")
            if p:
                paths.append(Path(unquote(p)))
        paths = [p for p in paths if p.is_file()]
        if not paths or not query:
            raise HTTPException(status_code=400, detail="frames + query required")
        try:
            verdict = await asyncio.to_thread(clipper_vlm_check, paths, query)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"AI check failed: {type(e).__name__}: {e}")
        return verdict

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
