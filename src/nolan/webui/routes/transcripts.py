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
            force=bool(body.get("force", False)), densify=bool(body.get("densify", False)),
            min_sec=int(body.get("min_sec", 0) or 0), max_sec=int(body.get("max_sec", 0) or 0))
        return {"job_id": job.id, "type": "transcript-batch-caption"}

    def _collection_free(channel: str, kind: str) -> bool:
        """Whether a source's WHOLE set is curator-asserted copyright-free (stored on the source when added).
        Applies to archive collections and copyright-free YouTube channels; documentary `youtube` is never free."""
        if kind not in ("archive", "youtube_cc"):
            return False
        from nolan import transcript_lib as tl
        from nolan import archive_source as ar
        norm = (lambda r: ar.collection_ref(r)) if kind == "archive" else (lambda r: tl._channel_key(r))
        want = norm(channel)
        for ref, s in tl.load_sources().items():
            if s.get("kind") == kind and norm(ref) == want:
                return bool(s.get("copyright_free"))
        return kind == "youtube_cc"                              # a cc channel defaults free (e.g. curate-before-add)

    @app.get("/api/transcripts/survey")
    async def transcripts_survey(channel: str = Query(...), limit: int = Query(default=0),
                                 refresh: bool = Query(default=False), kind: str = Query(default="youtube")):
        """CHEAP survey: all of a source's titles (no download) + in_library flags. PERSISTED — served from
        surveys.json unless refresh=true. `kind='archive'` surveys an archive.org collection."""
        import asyncio
        from nolan import transcript_lib as tl
        cfree = _collection_free(channel, kind)
        items = await asyncio.to_thread(tl.survey_channel, channel, (limit or None), None, bool(refresh),
                                        kind, cfree)
        # archive.org's deep-paging window (~10k) truncates a bigger collection — report the shortfall so a
        # partial crawl can't read as complete coverage (Prelinger: 10,000 fetched of 10,376)
        sv = tl.load_surveys().get(tl._survey_key(channel, kind)) or {}
        total = int(sv.get("total") or 0)
        return {"items": items, "count": len(items), "new": sum(1 for i in items if not i["in_library"]),
                "cached": (items[0].get("_cached", "") if items else ""), "kind": kind,
                "source_total": total, "truncated": max(0, total - len(items))}

    @app.post("/api/transcripts/recommend")
    async def transcripts_recommend(body: dict = Body(...)):
        """DeepSeek recommends a diverse, non-redundant add-list (topic/verdict/reason + coverage note)."""
        from nolan.config import load_config
        from nolan import transcript_lib as tl
        channel = (body.get("channel") or "").strip()
        if not channel:
            raise HTTPException(status_code=400, detail="channel required")
        kind = body.get("kind") or "youtube"
        return await tl.recommend_from_channel(channel, load_config(), limit=int(body.get("limit", 200) or 200),
                                               min_sec=int(body.get("min_sec", 0) or 0),
                                               max_sec=int(body.get("max_sec", 0) or 0), kind=kind,
                                               copyright_free_only=bool(body.get("copyright_free", False)),
                                               collection_free=_collection_free(channel, kind))

    @app.get("/api/transcripts/topics")
    async def transcripts_topics(channel: str = Query(...), k: int = Query(default=0),
                                 refresh: bool = Query(default=False),
                                 min_sec: int = Query(default=0), max_sec: int = Query(default=0),
                                 kind: str = Query(default="youtube"),
                                 copyright_free: bool = Query(default=False),
                                 cap: int = Query(default=0)):
        """Topic-model a source's DISTINCT titles into ~k clusters (no LLM) for browse-by-topic + hand-pick.
        `cap` bounds how many of the newest candidates are clustered (0 = the 2500 default); raise it to
        cluster a giant source in full, at the cost of embedding every title."""
        import asyncio
        from nolan import transcript_lib as tl
        channel = channel.strip()
        if not channel:
            raise HTTPException(status_code=400, detail="channel required")
        return await asyncio.to_thread(tl.topic_view, channel, int(k or 0), None, bool(refresh),
                                       int(min_sec or 0), int(max_sec or 0), kind, bool(copyright_free),
                                       _collection_free(channel, kind), int(cap or tl.MAX_CANDIDATES))

    @app.post("/api/transcripts/diverse-sample")
    async def transcripts_diverse_sample(body: dict = Body(...)):
        """NO-LLM recommender: cluster into exactly N topics, return one medoid each — max spread, zero cost."""
        import asyncio
        from nolan import transcript_lib as tl
        channel = (body.get("channel") or "").strip()
        if not channel:
            raise HTTPException(status_code=400, detail="channel required")
        kind = body.get("kind") or "youtube"
        return await asyncio.to_thread(tl.diverse_sample, channel, int(body.get("n", 20) or 20),
                                       None, bool(body.get("refresh", False)),
                                       int(body.get("min_sec", 0) or 0), int(body.get("max_sec", 0) or 0),
                                       kind, bool(body.get("copyright_free", False)),
                                       _collection_free(channel, kind),
                                       int(body.get("cap", 0) or tl.MAX_CANDIDATES))

    @app.get("/api/transcripts/coverage")
    async def transcripts_coverage(k: int = Query(default=0), refresh: bool = Query(default=False),
                                   min_sec: int = Query(default=0), max_sec: int = Query(default=0),
                                   kind: str = Query(default="youtube"),
                                   copyright_free: bool = Query(default=False),
                                   cap: int = Query(default=0), detail: str = Query(default="")):
        """COVERAGE map for ONE source kind (youtube channels or archive collections — kept separate).
        `cap` bounds the newest candidates clustered PER SOURCE (0 = the 2500 default). `detail=<label>`
        returns that ONE topic's members in full instead of the six-sample preview — clustering is
        deterministic (`random_state=0`) and now costs no embedding, so the recompute is honest."""
        import asyncio
        from nolan import transcript_lib as tl
        return await asyncio.to_thread(tl.coverage_map, None, int(k or 0), None, bool(refresh), 0,
                                       int(min_sec or 0), int(max_sec or 0), kind, bool(copyright_free),
                                       int(cap or tl.MAX_CANDIDATES), detail)

    @app.post("/api/transcripts/add-collection")
    async def transcripts_add_collection(body: dict = Body(...)):
        """Register an archive.org COLLECTION as a source (kind='archive'); optional copyright-free assertion."""
        from nolan import transcript_lib as tl
        from nolan import archive_source as ar
        ref = (body.get("collection") or "").strip()
        if not ref:
            raise HTTPException(status_code=400, detail="collection required")
        coll = ar.collection_ref(ref)
        tl.upsert_source(coll, label=(body.get("label") or coll), kind="archive",
                         copyright_free=bool(body.get("copyright_free", False)))
        return {"collection": coll, "kind": "archive", "copyright_free": bool(body.get("copyright_free", False))}

    @app.post("/api/transcripts/add-cc-channel")
    async def transcripts_add_cc_channel(body: dict = Body(...)):
        """Register a copyright-free YouTube CHANNEL as a source (kind='youtube_cc') — a separate family from
        documentary channels, all videos treated as copyright-free (stock / b-roll)."""
        from nolan import transcript_lib as tl
        ref = (body.get("channel") or "").strip()
        if not ref:
            raise HTTPException(status_code=400, detail="channel required")
        tl.upsert_source(ref, label=(body.get("label") or ref), kind="youtube_cc", copyright_free=True)
        return {"channel": ref, "kind": "youtube_cc", "copyright_free": True}

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
        kind = body.get("kind") or "youtube"
        from nolan import archive_source as ar
        collection = ar.collection_ref(body.get("collection") or "") if kind == "archive" else ""
        cfree = kind == "youtube_cc" or (kind == "archive" and _collection_free(collection or (body.get("collection") or ""), "archive"))
        if body.get("copyright_free") is not None:            # explicit caller assertion (the Topic tab knows
            cfree = bool(body["copyright_free"])              # each row's cf from the survey/licence) wins
        job = job_manager.start(
            "transcript-ingest-videos", operations.ingest_videos, meta={"count": len(vids), "kind": kind},
            config=cfg, db_path=idb, videos=vids, visual=(body.get("visual") or "off"),
            source=(body.get("channel") or "").strip(),      # the source the caller was browsing
            delay=float(body.get("delay", 1.0) or 1.0), kind=kind, collection=collection,
            broll_max_sec=float(body.get("broll_max_sec", 0) or 0), copyright_free=bool(cfree),
            min_sec=int(body.get("min_sec", 0) or 0), max_sec=int(body.get("max_sec", 0) or 0))
        return {"job_id": job.id, "type": "transcript-ingest-videos"}

    @app.get("/api/transcripts/browsable")
    async def transcripts_browsable():
        """Every source you can browse BY TOPIC right now — registered sources plus any collection or
        channel with a cached survey (a survey is all clustering needs; ingesting is a later step).
        `titles` is 0 when a registered source has never been surveyed: selectable, but Grab first."""
        from nolan import transcript_lib as tl
        out, seen = [], set()
        surveys = tl.load_surveys()
        by_ref = {}
        for row in surveys.values():
            ref = row.get("channel")
            if ref:
                by_ref[(ref, row.get("kind") or "youtube")] = row
        for ref, src in tl.load_sources().items():
            kind = src.get("kind") or "youtube"
            row = by_ref.get((ref, kind)) or {}
            out.append({"ref": ref, "kind": kind, "label": src.get("label") or ref, "registered": True,
                        "titles": int(row.get("count") or 0), "cached": row.get("fetched", "")})
            seen.add((ref, kind))
        for (ref, kind), row in by_ref.items():
            if (ref, kind) not in seen:
                out.append({"ref": ref, "kind": kind, "label": ref, "registered": False,
                            "titles": int(row.get("count") or 0), "cached": row.get("fetched", "")})
        out.sort(key=lambda r: (not r["registered"], -r["titles"]))
        return {"sources": out, "count": len(out)}

    @app.get("/api/transcripts/videos")
    async def transcripts_videos():
        """Browse the indexed transcript videos (newest first) from the sidecar, plus the per-channel
        facets the list filters by — `{channel, kind, count, registered, url, url_exact, promotable}`.
        Channel is a property of the VIDEOS, so this (not the Sources registry) is where an unregistered
        channel is browsed, promoted to a real source, or cleared out."""
        from nolan import transcript_lib as tl
        cat = tl.load_catalog()
        vids = sorted(cat.values(), key=lambda x: (x.get("added") or ""), reverse=True)
        return {"videos": vids, "count": len(vids), "channels": tl.channel_facets()}

    @app.post("/api/transcripts/register-source")
    async def transcripts_register_source(body: dict = Body(...)):
        """PROMOTE an unregistered channel to a real source — registration only, no crawl. The path from
        "this collection in my video list is actually good" to a source Sync all will keep current."""
        from nolan import transcript_lib as tl
        ref = (body.get("channel") or "").strip()
        if not ref:
            raise HTTPException(status_code=400, detail="channel required")
        kind = body.get("kind") or "youtube"
        _, exact = tl.source_url(ref, kind)
        if not exact:                          # a bare uploader name: list_channel could never enumerate it
            raise HTTPException(status_code=400,
                                detail=f"'{ref}' is an uploader name, not a resolvable channel — no sync "
                                       "could ever crawl it. Add the channel by URL or @handle instead.")
        if kind == "archive":
            from nolan import archive_source as ar
            ref = ar.collection_ref(ref)
        tl.upsert_source(ref, label=(body.get("label") or ref), kind=kind,
                         copyright_free=bool(body.get("copyright_free", False)))
        return {"channel": ref, "kind": kind, "registered": True}

    @app.get("/api/transcripts/search")
    async def transcripts_search(q: str = Query(...), n: int = Query(default=25),
                                 channel: str = Query(default="")):
        """`channel` (comma-separated) scopes the search to those sources. The scope goes INTO the
        vector query, so N results are N results however big the rest of the library gets."""
        import asyncio
        from nolan import transcript_lib as tl
        from nolan.indexer import VideoIndex
        from nolan.vector_search import VectorSearch
        idb = _db()
        if not Path(idb).exists():
            return {"results": [], "count": 0}
        index = VideoIndex(idb)
        vs = VectorSearch(Path(idb).parent / "vectors", index=index)
        chans = [c for c in (channel or "").split(",") if c.strip()]
        results = await asyncio.to_thread(tl.search_transcripts, q, index, vs, int(n), None,
                                          chans or None)
        return {"results": results, "count": len(results), "scoped_to": chans}

    @app.post("/api/transcripts/suggest-topic")
    async def transcripts_suggest_topic(body: dict = Body(...)):
        """ON-DEMAND: a rough topic → videos worth captioning. Tier 1 = ingested-but-not-captioned (vector
        search); tier 2 = surveyed-but-not-ingested (title match). deepseek expands the topic. (web = Phase 2)"""
        from nolan.config import load_config
        from nolan import transcript_lib as tl
        from nolan.indexer import VideoIndex
        from nolan.vector_search import VectorSearch
        topic = (body.get("topic") or "").strip()
        if not topic:
            raise HTTPException(status_code=400, detail="topic required")
        idb = _db()
        if not Path(idb).exists():
            return {"topic": topic, "suggestions": [], "queries": [], "ingested": 0, "surveyed": 0}
        index = VideoIndex(idb)
        vs = VectorSearch(Path(idb).parent / "vectors", index=index)
        return await tl.suggest_by_topic(topic, index, vs, load_config(), int(body.get("n", 12) or 12),
                                         copyright_free_only=bool(body.get("copyright_free", False)),
                                         queries=(body.get("queries") or None),
                                         web=bool(body.get("web", True)),
                                         rerank=bool(body.get("rerank", True)),
                                         min_sec=int(body.get("min_sec", 0) or 0),
                                         max_sec=int(body.get("max_sec", 0) or 0),
                                         refresh_queries=bool(body.get("refresh_queries", False)),
                                         length_kinds=body.get("length_kinds"))

    @app.post("/api/transcripts/broaden")
    async def transcripts_broaden(body: dict = Body(...)):
        """BROADEN THE LIBRARY: LLM-proposed topics the library lacks → the 3-tier search per topic (with
        the caller's filters) → X picks spanning as many subjects as possible. Returns a PROPOSAL for review
        in the Topic tab; ingest is the user's next click. Runs as a job — it is minutes of LLM + network."""
        from nolan.config import load_config
        from nolan import transcript_broaden as tb
        from nolan.indexer import VideoIndex
        from nolan.vector_search import VectorSearch
        idb = _db()
        if not Path(idb).exists():
            raise HTTPException(status_code=400, detail="no transcript index yet")
        cfg = load_config()

        async def _run(job):
            index = VideoIndex(idb)
            vs = VectorSearch(Path(idb).parent / "vectors", index=index)
            return await tb.broaden_library(
                cfg, index, vs,
                count=int(body.get("count", 20) or 20), theme=(body.get("theme") or "").strip(),
                topics=(body.get("topics") or None), per_topic=int(body.get("per_topic", 1) or 1),
                min_sec=int(body.get("min_sec", 0) or 0), max_sec=int(body.get("max_sec", 0) or 0),
                copyright_free_only=bool(body.get("copyright_free", False)),
                kinds=(body.get("kinds") or None), web=bool(body.get("web", False)),
                rerank=bool(body.get("rerank", True)), min_fit=(body.get("min_fit") or "medium"),
                concurrency=int(body.get("concurrency", 4) or 4),
                topic_source=(body.get("topic_source") or "corpus"),
                expand=bool(body.get("expand", False)),
                length_kinds=(body.get("length_kinds")
                              if body.get("length_kinds") is not None else tb.LENGTH_RELIABLE_KINDS),
                progress=lambda f, m: job.set_progress(min(0.99, f), m))
        job = job_manager.start("transcript-broaden", _run, meta={"count": int(body.get("count", 20) or 20)})
        return {"job_id": job.id, "type": "transcript-broaden"}

    @app.post("/api/transcripts/accepted")
    async def transcripts_accepted(body: dict = Body(...)):
        """Record which suggestions the human actually ingested — the only ground truth in this loop, and
        what every threshold here (the 0.42 floor, the fit bar, the re-rank prompt) should be tuned against."""
        from nolan import transcript_memory as mem
        n = mem.record_accepted(body.get("picks") or [], (body.get("source") or "topic"))
        return {"recorded": n, **mem.stats()}

    @app.get("/api/transcripts/memory")
    async def transcripts_memory(limit: int = Query(default=25)):
        """What the topic memory holds — judgements, cached expansions, and accepted picks."""
        from nolan import transcript_memory as mem
        return {**mem.stats(), "recent_accepted": mem.load_accepted()[:max(1, int(limit))]}

    @app.get("/api/transcripts/quality")
    async def transcripts_quality(limit: int = Query(default=0)):
        """What the caption runs actually bought, per video — `frames > 0` is not the same as useful."""
        import asyncio
        from nolan import transcript_lib as tl
        return await asyncio.to_thread(tl.library_quality, None, int(limit or 0))

    @app.get("/api/transcripts/coverage-topics")
    async def transcripts_coverage_topics():
        """Per-subject coverage + where high-fit material is still on the table (no new search needed)."""
        from nolan import transcript_memory as mem
        return mem.coverage()

    @app.get("/api/transcripts/topics-used")
    async def transcripts_topics_used():
        """Topics already searched by a broaden run — what the library has DELIBERATELY covered so far."""
        from nolan import transcript_broaden as tb
        rows = tb.load_used_topics()
        return {"topics": sorted(rows, key=lambda r: r.get("last_used") or "", reverse=True),
                "count": len(rows), "picked": sum(int(r.get("picked") or 0) for r in rows)}

    @app.get("/api/transcripts/topic-index")
    async def transcripts_topic_index():
        """Coverage of the surveyed-title vector index the topic search ranks against."""
        import asyncio
        from nolan import transcript_vectors as tvec
        return await asyncio.to_thread(tvec.status)

    @app.post("/api/transcripts/topic-index/build")
    async def transcripts_topic_index_build():
        """(Re)build the surveyed-title vector index — one job, resumable (it only embeds what's missing)."""
        from nolan import transcript_vectors as tvec

        async def _build(job):
            def prog(done, total):
                job.set_progress(min(0.99, done / max(1, total)), f"embedding titles {done}/{total}")
            import asyncio as _a
            out = await _a.to_thread(tvec.build, None, prog)
            job.set_progress(1.0, f"{out['indexed']} titles indexed")
            return out
        job = job_manager.start("transcript-topic-index", _build)
        return {"job_id": job.id, "type": "transcript-topic-index"}

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
                                      content_kind: str = Query(default=""),
                                      channel: str = Query(default="")):
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
        chans = [c for c in (channel or "").split(",") if c.strip()]
        results = await asyncio.to_thread(tl.search_both, q, index, vs, int(n), content_kind, None,
                                          chans or None)
        return {"results": results, "count": len(results), "scoped_to": chans}

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
        """SOURCES ARE ONLY WHAT SOMEONE ADDED — the sources.json registry, with a live video count per
        source (recomputed from the catalog) and a `url`/`url_exact` link to the source's own page.

        Channels that merely HAVE indexed videos are not sources and no longer get a tile here: the card's
        own actions never applied to them (Sync all iterates sources.json; Curate surveys a whole
        collection, meaningless for an archive.org inbox). They are reported as an `unregistered` summary
        so the tab still can't understate what is indexed, and are browsable/actionable per channel on the
        Indexed-videos list (`/api/transcripts/videos` → `channels`), which is where they belong."""
        from nolan import transcript_lib as tl
        rows = tl.sources_view()
        managed = [r for r in rows if r.get("origin") == "managed"]
        unreg = [r for r in rows if r.get("origin") != "managed"]
        return {"sources": managed, "count": len(managed),
                "unregistered": {"channels": len(unreg),
                                 "videos": sum(int(r.get("video_count") or 0) for r in unreg),
                                 "search": sum(1 for r in unreg if r.get("origin") == "search")}}

    @app.delete("/api/transcripts/sources")
    async def transcripts_remove_source(channel: str = Query(...), purge: bool = Query(default=False)):
        """Drop a channel from the managed list. Its already-indexed videos stay searchable — and so the
        TILE STAYS, re-derived as `unregistered` (that surprise is why `purge` exists).

        `purge=true` deletes the channel's videos everywhere first (DB rows + vectors + frames + catalog),
        which is what actually makes the tile disappear — and the only removal a derived tile has at all,
        since it has no source row to drop."""
        import asyncio
        from nolan import transcript_lib as tl
        if not purge:
            return {"removed": tl.remove_source(channel), "purged": False}
        from nolan.indexer import VideoIndex
        return {**await asyncio.to_thread(tl.purge_source, VideoIndex(_db()), channel), "purged": True}

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
