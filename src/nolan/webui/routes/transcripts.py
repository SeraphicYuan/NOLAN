"""Transcript Library routes — index YouTube CHANNEL transcripts (captions only, no video) as a cheap
DISCOVERY tier of the library, then search "which video / roughly when" a topic is discussed.

  GET  /transcripts                       the page
  POST /api/transcripts/add-channel       {channel, limit?} -> background job (enumerate->fetch->chunk->ingest->embed)
  GET  /api/transcripts/videos            the indexed transcript videos (browse, from the sidecar catalog)
  GET  /api/transcripts/search?q=&n=      semantic search scoped to the transcript tier (timestamped hits)
"""
from pathlib import Path

from fastapi import Body, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse


def register(app, ctx):
    templates_dir = ctx.templates_dir
    job_manager = ctx.job_manager

    def _db():
        from nolan.config import load_config
        return ctx.db_path or Path(load_config().indexing.database).expanduser()

    @app.get("/transcripts", response_class=HTMLResponse)
    async def transcripts_page():
        tpl = templates_dir / "transcripts.html"
        return tpl.read_text(encoding="utf-8") if tpl.exists() else "<h1>transcripts.html not found</h1>"

    @app.post("/api/transcripts/add-channel")
    async def transcripts_add_channel(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        channel = (body.get("channel") or "").strip()
        if not channel:
            raise HTTPException(status_code=400, detail="channel (URL, @handle, or id) required")
        cfg = load_config()
        idb = ctx.db_path or Path(cfg.indexing.database).expanduser()
        job = job_manager.start(
            "transcript-channel", operations.ingest_channel_transcripts,
            meta={"channel": channel},
            config=cfg, db_path=idb, channel=channel,
            limit=int(body.get("limit", 10) or 10),
            window_s=float(body.get("window_s", 45) or 45),
            overlap_s=float(body.get("overlap_s", 10) or 10),
            # visual tier: "keyframe" (full-res + gemma caption, default) | "storyboard" (free/coarse) | "off"
            visual=(body.get("visual") or ("off" if body.get("no_visual") else "keyframe")),
            max_frames=int(body.get("max_frames", 0) or 0),   # 0 = uncapped; adaptive 30–50s density governs
            densify=bool(body.get("densify", False)),          # OPT-IN b-roll densify (default off)
            refresh=bool(body.get("refresh", False)),          # force re-process vs dedup-skip already-indexed
        )
        return {"job_id": job.id, "type": "transcript-channel"}

    @app.post("/api/transcripts/sync-all")
    async def transcripts_sync_all(body: dict = Body(default={})):
        """Crawl EVERY registered source channel for NEW uploads (incremental — dedup skips already-indexed).
        One background crawl job per channel; run it periodically to keep the library current."""
        from nolan.config import load_config
        from nolan import transcript_lib as tl
        from nolan.webui import operations
        cfg = load_config()
        idb = ctx.db_path or Path(cfg.indexing.database).expanduser()
        srcs = tl.load_sources()
        started = []
        for ch in srcs:
            job = job_manager.start(
                "transcript-channel", operations.ingest_channel_transcripts, meta={"channel": ch},
                config=cfg, db_path=idb, channel=ch, limit=int(body.get("limit", 50) or 50),
                visual=(body.get("visual") or "keyframe"), refresh=False)
            started.append(job.id)
        return {"started": len(started), "channels": list(srcs.keys())}

    @app.post("/api/transcripts/crawl-all")
    async def transcripts_crawl_all(body: dict = Body(...)):
        """Crawl a WHOLE channel's transcripts (ALL videos) — TEXT-ONLY by default (fast, cheap, no video
        download), rate-limit-paced between videos. Add the visual tier per-video later (Refresh). Dedup
        makes it resumable — re-run to continue."""
        from nolan.config import load_config
        from nolan.webui import operations
        channel = (body.get("channel") or "").strip()
        if not channel:
            raise HTTPException(status_code=400, detail="channel (URL, @handle, or id) required")
        cfg = load_config()
        idb = ctx.db_path or Path(cfg.indexing.database).expanduser()
        job = job_manager.start(
            "transcript-crawl-all", operations.ingest_channel_transcripts, meta={"channel": channel},
            config=cfg, db_path=idb, channel=channel,
            limit=0,                                          # 0 -> list_channel enumerates ALL videos
            visual=(body.get("visual") or "off"),             # TEXT-ONLY default; keyframes are a separate pass
            delay=float(body.get("delay", 1.5) or 1.5),       # seconds between videos (rate-limit aware)
            refresh=bool(body.get("refresh", False)))
        return {"job_id": job.id, "type": "transcript-crawl-all"}

    @app.post("/api/transcripts/batch-caption")
    async def transcripts_batch_caption(body: dict = Body(...)):
        """Caption the visual tier for a BATCH of already-text-indexed videos (skip already-captioned unless
        force). ONE governed job — the global gemma/download semaphores keep it rate-safe no matter what
        else is running."""
        from nolan.config import load_config
        from nolan.webui import operations
        ids = body.get("video_ids") or []
        if not ids:
            raise HTTPException(status_code=400, detail="video_ids required")
        cfg = load_config()
        idb = ctx.db_path or Path(cfg.indexing.database).expanduser()
        job = job_manager.start(
            "transcript-batch-caption", operations.batch_caption_videos, meta={"count": len(ids)},
            config=cfg, db_path=idb, video_ids=[str(v) for v in ids],
            force=bool(body.get("force", False)), densify=bool(body.get("densify", False)))
        return {"job_id": job.id, "type": "transcript-batch-caption"}

    @app.get("/api/transcripts/survey")
    async def transcripts_survey(channel: str = Query(...), limit: int = Query(default=0)):
        """CHEAP survey: all of a channel's titles (no download) + in_library flags."""
        import asyncio
        from nolan import transcript_lib as tl
        items = await asyncio.to_thread(tl.survey_channel, channel, (limit or None))
        return {"items": items, "count": len(items), "new": sum(1 for i in items if not i["in_library"])}

    @app.post("/api/transcripts/recommend")
    async def transcripts_recommend(body: dict = Body(...)):
        """DeepSeek recommends a diverse, non-redundant add-list (topic/verdict/reason + coverage note)."""
        from nolan.config import load_config
        from nolan import transcript_lib as tl
        channel = (body.get("channel") or "").strip()
        if not channel:
            raise HTTPException(status_code=400, detail="channel required")
        return await tl.recommend_from_channel(channel, load_config(), limit=int(body.get("limit", 200) or 200))

    @app.get("/api/transcripts/topics")
    async def transcripts_topics(channel: str = Query(...), k: int = Query(default=0)):
        """Topic-model a channel's DISTINCT titles into ~k clusters (no LLM) for browse-by-topic + hand-pick."""
        import asyncio
        from nolan import transcript_lib as tl
        channel = channel.strip()
        if not channel:
            raise HTTPException(status_code=400, detail="channel required")
        return await asyncio.to_thread(tl.topic_view, channel, int(k or 0))

    @app.post("/api/transcripts/diverse-sample")
    async def transcripts_diverse_sample(body: dict = Body(...)):
        """NO-LLM recommender: cluster into exactly N topics, return one medoid each — max spread, zero cost."""
        import asyncio
        from nolan import transcript_lib as tl
        channel = (body.get("channel") or "").strip()
        if not channel:
            raise HTTPException(status_code=400, detail="channel required")
        return await asyncio.to_thread(tl.diverse_sample, channel, int(body.get("n", 20) or 20))

    @app.post("/api/transcripts/ingest-videos")
    async def transcripts_ingest_videos(body: dict = Body(...)):
        """Ingest a SELECTED list of videos (transcript-only by default); the 'add selected' action."""
        from nolan.config import load_config
        from nolan.webui import operations
        vids = body.get("videos") or []
        if not vids:
            raise HTTPException(status_code=400, detail="videos required")
        cfg = load_config()
        idb = ctx.db_path or Path(cfg.indexing.database).expanduser()
        job = job_manager.start(
            "transcript-ingest-videos", operations.ingest_videos, meta={"count": len(vids)},
            config=cfg, db_path=idb, videos=vids, visual=(body.get("visual") or "off"),
            delay=float(body.get("delay", 1.0) or 1.0))
        return {"job_id": job.id, "type": "transcript-ingest-videos"}

    @app.get("/api/transcripts/videos")
    async def transcripts_videos():
        """Browse the indexed transcript videos (newest first), grouped by channel, from the sidecar."""
        from nolan import transcript_lib as tl
        cat = tl.load_catalog()
        vids = sorted(cat.values(), key=lambda x: (x.get("added") or ""), reverse=True)
        channels = sorted({(v.get("channel") or "?") for v in vids})
        return {"videos": vids, "count": len(vids), "channels": channels}

    @app.get("/api/transcripts/search")
    async def transcripts_search(q: str = Query(...), n: int = Query(default=25)):
        import asyncio
        from nolan import transcript_lib as tl
        from nolan.indexer import VideoIndex
        from nolan.vector_search import VectorSearch
        idb = _db()
        if not Path(idb).exists():
            return {"results": [], "count": 0}
        index = VideoIndex(idb)
        vs = VectorSearch(Path(idb).parent / "vectors", index=index)
        results = await asyncio.to_thread(tl.search_transcripts, q, index, vs, int(n))
        return {"results": results, "count": len(results)}

    @app.get("/api/transcripts/visual-search")
    async def transcripts_visual_search(q: str = Query(...), n: int = Query(default=24),
                                        content_kind: str = Query(default="")):
        """CLIP text→image over the transcript-frame visual tier — retrieve by APPEARANCE, timestamped.
        `content_kind` (e.g. broll) filters to that shot class — the "b-roll only" toggle."""
        import asyncio
        from nolan import transcript_frames as tf
        results = await asyncio.to_thread(tf.visual_search, q, int(n), None, None, content_kind)
        return {"results": results, "count": len(results)}

    @app.get("/api/transcripts/search-both")
    async def transcripts_search_both(q: str = Query(...), n: int = Query(default=25),
                                      content_kind: str = Query(default="")):
        """BOTH search: RRF blend of transcript (said) + visual (shown) into ranked moments."""
        import asyncio
        from nolan import transcript_lib as tl
        from nolan.indexer import VideoIndex
        from nolan.vector_search import VectorSearch
        idb = _db()
        if not Path(idb).exists():
            return {"results": [], "count": 0}
        index = VideoIndex(idb)
        vs = VectorSearch(Path(idb).parent / "vectors", index=index)
        results = await asyncio.to_thread(tl.search_both, q, index, vs, int(n), content_kind)
        return {"results": results, "count": len(results)}

    @app.get("/api/transcripts/frame")
    async def transcripts_frame(path: str = Query(...)):
        """Serve a stored frame thumbnail (contained to the transcript-frame store — no traversal)."""
        from nolan.transcript_frames import FRAMES_DIR
        base = FRAMES_DIR.resolve()
        fp = Path(path).resolve()
        if base not in fp.parents or not fp.is_file():
            raise HTTPException(status_code=404, detail="frame not found")
        return FileResponse(fp, media_type="image/jpeg")

    # ---- Sources (managed channels) --------------------------------------------------------------
    @app.get("/api/transcripts/sources")
    async def transcripts_sources():
        """The managed source channels + a live video count per source (recomputed from the catalog).
        Channels that have indexed videos but were never formally added (e.g. pre-sidecar crawls) are
        surfaced as `managed:false` derived tiles so the tab reflects reality and can't hide indexed work."""
        from nolan import transcript_lib as tl
        srcs = tl.load_sources()
        counts: dict = {}
        for e in tl.load_catalog().values():
            ch = e.get("channel")
            if ch:
                counts[ch] = counts.get(ch, 0) + 1
        out = [{**s, "managed": True, "video_count": counts.get(ch, s.get("video_count", 0))}
               for ch, s in srcs.items()]
        for ch, n in counts.items():                                   # derive tiles for un-managed channels
            if ch not in srcs:
                out.append({"channel": ch, "label": ch, "managed": False,
                            "last_crawled": None, "video_count": n})
        out.sort(key=lambda s: (s.get("managed") is False, -(s.get("video_count") or 0)))
        return {"sources": out, "count": len(out)}

    @app.delete("/api/transcripts/sources")
    async def transcripts_remove_source(channel: str = Query(...)):
        """Drop a channel from the managed list (its already-indexed videos stay searchable)."""
        from nolan import transcript_lib as tl
        return {"removed": tl.remove_source(channel)}

    # ---- Per-video: detail drill-down, delete, refresh -------------------------------------------
    @app.get("/api/transcripts/video")
    async def transcripts_video_detail(id: str = Query(...)):
        """A video's drill-down: transcript windows joined to their keyframe snapshots + gemma captions."""
        import asyncio
        from nolan import transcript_lib as tl
        from nolan.indexer import VideoIndex
        idb = _db()
        if not Path(idb).exists():
            raise HTTPException(status_code=404, detail="library not found")
        return await asyncio.to_thread(tl.video_detail, VideoIndex(idb), id)

    @app.delete("/api/transcripts/video")
    async def transcripts_delete_video(id: str = Query(...)):
        """Delete a transcript video everywhere (DB rows + vectors + visual frames + catalog entry)."""
        import asyncio
        from nolan import transcript_lib as tl
        from nolan.indexer import VideoIndex
        return await asyncio.to_thread(tl.delete_transcript, VideoIndex(_db()), id)

    @app.post("/api/transcripts/refresh-video")
    async def transcripts_refresh_video(body: dict = Body(...)):
        """Re-index ONE transcript video (background job) — re-fetch, re-chunk, re-caption."""
        from nolan.config import load_config
        from nolan import transcript_lib as tl
        from nolan.webui import operations
        yid = (body.get("id") or "").strip()
        entry = tl.load_catalog().get(yid, {})
        url = (body.get("url") or entry.get("url")
               or (f"https://www.youtube.com/watch?v={yid}" if yid else "")).strip()
        if not url:
            raise HTTPException(status_code=400, detail="id or url required")
        cfg = load_config()
        job = job_manager.start(
            "transcript-refresh", operations.refresh_transcript_video, meta={"video": yid},
            config=cfg, db_path=ctx.db_path or Path(cfg.indexing.database).expanduser(),
            url=url, channel=entry.get("channel", ""),
            visual=(body.get("visual") or "keyframe"), max_frames=int(body.get("max_frames", 0) or 0),
            densify=bool(body.get("densify", False)))
        return {"job_id": job.id, "type": "transcript-refresh"}
