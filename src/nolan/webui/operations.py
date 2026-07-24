"""Job-aware wrappers around NOLAN pipeline operations for the hub.

Each function takes a ``job`` (from webui.jobs) it updates with progress, mirrors
the corresponding CLI command, and runs in the hub's asyncio loop. Blocking work
(yt-dlp download) is offloaded to a thread executor.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional


def _select_vision(config, provider: str, model: Optional[str],
                   reasoning_enabled: Optional[bool], reasoning_max_tokens: Optional[int]):
    """Build a VisionConfig like the CLI does, honoring per-request overrides."""
    from nolan.vision import VisionConfig

    model = model or None
    if provider == "gemini":
        vision_model = "gemini-3-flash-preview"
        api_key = config.gemini.api_key
    elif provider == "openrouter":
        cfg_model = model or config.vision.model
        vision_model = cfg_model if "/" in cfg_model else "qwen/qwen3.7-plus"
        api_key = config.vision.openrouter_api_key
    else:  # ollama
        cfg_model = model or config.vision.model
        vision_model = cfg_model if "/" not in cfg_model else "qwen3-vl:8b"
        api_key = None

    re_enabled = config.vision.reasoning_enabled if reasoning_enabled is None else reasoning_enabled
    return VisionConfig(
        provider=provider,
        model=vision_model,
        host=config.vision.host,
        port=config.vision.port,
        timeout=config.vision.timeout,
        api_key=api_key,
        base_url=config.vision.base_url,
        reasoning_enabled=re_enabled,
        reasoning_max_tokens=reasoning_max_tokens if reasoning_max_tokens is not None else config.vision.reasoning_max_tokens,
    )


async def ingest(job, *, config, db_path: Path, source_type: str, target: str,
                 provider: str = "openrouter", model: Optional[str] = None,
                 reasoning_enabled: Optional[bool] = None, reasoning_max_tokens: Optional[int] = None,
                 project_dir: Optional[str] = None, force: bool = False,
                 whisper_fallback: bool = True, whisper_model: str = "base",
                 embed: bool = True):
    """Download (if YouTube) and index a single video into the library.

    Args:
        source_type: 'file' or 'youtube'.
        target: file path (for 'file') or URL (for 'youtube').
        project_dir: optional project folder name; downloads land in projects/<name>/source.
    """
    from nolan.indexer import HybridVideoIndexer, VideoIndex
    from nolan.vision import create_vision_provider
    from nolan.sampler import create_sampler, SamplerConfig, SamplingStrategy
    from nolan.llm import create_text_llm

    job.set_progress(0.02, "Resolving source…")

    # --- 1. obtain the local video path -------------------------------------
    if source_type == "youtube":
        from nolan.youtube import YouTubeClient
        if project_dir:
            out_dir = Path("projects") / project_dir / "source"
        else:
            out_dir = Path("projects") / "_library" / "source"
        out_dir.mkdir(parents=True, exist_ok=True)
        job.set_progress(0.05, f"Downloading {target} …")
        client = YouTubeClient(output_dir=out_dir)
        result = await asyncio.get_event_loop().run_in_executor(None, client.download, target)
        if not getattr(result, "success", False) or not result.output_path:
            raise RuntimeError(f"Download failed: {getattr(result, 'error', 'unknown error')}")
        video_path = Path(result.output_path)
        job.log(f"Downloaded: {video_path.name}")
    else:
        video_path = Path(target)
        if not video_path.exists():
            raise RuntimeError(f"File not found: {video_path}")

    # --- 2. build the indexer (same wiring as `nolan index`) ----------------
    job.set_progress(0.1, "Initializing vision provider…")
    index = VideoIndex(db_path)
    vision_config = _select_vision(config, provider, model, reasoning_enabled, reasoning_max_tokens)
    vision = create_vision_provider(vision_config)
    if not await vision.check_connection():
        raise RuntimeError(f"Cannot connect to vision provider '{provider}' ({vision_config.model}).")
    job.log(f"Vision: {provider} ({vision_config.model}, reasoning={'on' if vision_config.reasoning_enabled else 'off'})")

    sampler = create_sampler(SamplerConfig(
        strategy=SamplingStrategy(config.indexing.sampling_strategy)
        if hasattr(config.indexing, "sampling_strategy") else SamplingStrategy("ffmpeg_scene"),
        min_interval=config.indexing.min_interval,
        max_interval=config.indexing.max_interval,
        scene_threshold=config.indexing.scene_threshold,
        ffmpeg_adaptive_sigma=getattr(config.indexing, "ffmpeg_adaptive_sigma", 5.0),
    ))

    llm = None
    if config.indexing.enable_inference:
        llm = create_text_llm(config)

    # Subtitle-first, Whisper-fallback: the indexer uses a downloaded subtitle if
    # one exists, and only transcribes with Whisper when none is found.
    whisper_transcriber = None
    if whisper_fallback and config.indexing.enable_transcript:
        try:
            from nolan.whisper import WhisperTranscriber, WhisperConfig, check_ffmpeg
            if check_ffmpeg():
                whisper_transcriber = WhisperTranscriber(
                    WhisperConfig(model_size=whisper_model, device="auto", compute_type="auto")
                )
                job.log(f"Whisper fallback ready ({whisper_model}) — used only if no subtitle is found")
            else:
                job.log("Whisper fallback skipped: ffmpeg not available")
        except Exception as e:  # faster-whisper not installed etc.
            job.log(f"Whisper fallback unavailable: {e}")

    indexer = HybridVideoIndexer(
        vision_provider=vision,
        index=index,
        sampler=sampler,
        llm_client=llm,
        whisper_transcriber=whisper_transcriber,
        enable_transcript=config.indexing.enable_transcript,
        enable_inference=config.indexing.enable_inference,
        concurrency=getattr(config.indexing, "concurrency", 6),
        force_reindex=force,
    )

    # --- 3. index with progress --------------------------------------------
    def progress(current, total, message):
        frac = 0.15 + 0.8 * (current / total if total else 0)
        job.set_progress(frac, f"[{current}/{total}] {message}")

    job.set_progress(0.15, "Indexing frames…")
    segments = await indexer.index_video(video_path, progress_callback=progress)

    job.set_progress(0.97, f"Indexed {segments} segments from {video_path.name}")
    # Auto-embed by default: chain a SEPARATE background embed job so the index result is available
    # immediately and an embed failure is isolated + independently re-runnable (via the /embed route
    # or reconcile-vectors). This gives the hub /library ingest the same "ingested => searchable"
    # default the CLI `nolan index` already has (cli/index.py auto-syncs). Never silent-empty.
    embed_job_id = _queue_embed(index, db_path, video_path, job) if embed else None
    job.set_progress(1.0, f"Indexed {segments} segments from {video_path.name}"
                     + (" · embedding…" if embed_job_id else ""))
    return {
        "video_path": str(video_path),
        "segments": segments,
        "provider": provider,
        "model": vision_config.model,
        "embed_job_id": embed_job_id,
    }


def _queue_embed(index, db_path, video_path, job):
    """Chain a background embed job for a freshly-indexed video (the auto-embed default). Returns the
    embed job id, or None if it couldn't be queued — logged LOUDLY either way. Never raises: an
    embed-enqueue failure must not lose the completed index. The embed job lands in the same
    process-wide JobManager the routes use (visible in /jobs; failures surface there + in the
    /library embedding-status)."""
    try:
        vid = index.get_video_id_by_path(str(video_path))
    except Exception as e:                                    # id lookup blew up — keep the index, flag it loudly
        job.log(f"⚠ embed enqueue failed (id lookup): {type(e).__name__}: {e} — run reconcile-vectors")
        return None
    if vid is None:
        job.log("⚠ indexed video not found for embedding — run reconcile-vectors to make it searchable")
        return None
    from nolan.webui.jobs import get_job_manager
    ej = get_job_manager().start("embed-video", embed_video, meta={"video": Path(video_path).name},
                                 db_path=db_path, video_id=vid)
    job.log(f"→ embedding queued (job {ej.id}) — searchable when it finishes")
    return ej.id


async def process_essay(job, *, config, essay_text: str, project_name: str,
                        skip_scenes: bool = False, style_id: str = None,
                        style_pack: str = None):
    """Run the authoring pipeline: parse essay -> script -> scene plan.

    Writes into projects/<project_name>/ (essay.md, script.md, scene_plan.json).
    When ``style_id`` is given, the chosen script style guide is injected into
    narration generation so the script is written in that voice.
    """
    from nolan.parser import parse_essay
    from nolan.script import ScriptConverter
    from nolan.scenes import SceneDesigner
    from nolan.llm import create_text_llm

    if config.llm.provider == "gemini" and not config.gemini.api_key:
        raise RuntimeError("GEMINI_API_KEY required (llm.provider=gemini).")
    if config.llm.provider == "openrouter" and not config.vision.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY required (llm.provider=openrouter).")

    output_path = Path("projects") / project_name
    (output_path / "assets" / "generated").mkdir(parents=True, exist_ok=True)
    (output_path / "assets" / "matched").mkdir(parents=True, exist_ok=True)
    essay_path = output_path / "essay.md"
    essay_path.write_text(essay_text, encoding="utf-8")

    # Style pack chosen at CREATION (where it bites: every downstream
    # authoring step — brief, slides, motion, tempo — reads it). Unknown
    # ids are refused loudly, not silently defaulted.
    if style_pack:
        from nolan.style_packs import load_packs
        if style_pack not in load_packs():
            raise RuntimeError(f"unknown style_pack '{style_pack}' — "
                               f"have: {sorted(load_packs())}")
        import yaml as _yaml
        pyaml = output_path / "project.yaml"
        meta = {}
        if pyaml.exists():
            try:
                meta = _yaml.safe_load(pyaml.read_text(encoding="utf-8")) or {}
            except Exception:
                meta = {}
        meta["style_pack"] = style_pack
        pyaml.write_text(_yaml.safe_dump(meta, sort_keys=False,
                                         allow_unicode=True), encoding="utf-8")
        job.log(f"Style pack: {style_pack} (written to project.yaml)")

    llm = create_text_llm(config)

    job.set_progress(0.1, "Parsing essay…")
    sections = parse_essay(essay_text)
    job.log(f"Found {len(sections)} sections")

    style_guide = None
    if style_id:
        from nolan.script_style import ScriptStyleStore
        style_guide = ScriptStyleStore(Path("script_styles")).read_guide(style_id)
        if style_guide:
            job.log(f"Applying script style guide: {style_id}")
        else:
            job.log(f"Style '{style_id}' has no guide yet — writing in default voice")

    job.set_progress(0.3, "Converting to narration script…")
    converter = ScriptConverter(llm, words_per_minute=config.defaults.words_per_minute,
                                style_guide=style_guide)
    script = await converter.convert_essay(sections)
    script_path = output_path / "script.md"
    script_path.write_text(script.to_markdown(), encoding="utf-8")
    job.log(f"Script: {script.total_duration:.0f}s")

    if skip_scenes:
        job.set_progress(1.0, f"Script generated ({len(sections)} sections)")
        return {"project": project_name, "script_path": str(script_path), "scenes": 0}

    job.set_progress(0.6, "Designing scene plan…")
    designer = SceneDesigner(llm)
    plan = await designer.design_full_plan(script.sections)
    plan_path = output_path / "scene_plan.json"
    plan.save(str(plan_path))
    n = len(plan.all_scenes)

    job.set_progress(1.0, f"Created project '{project_name}' with {n} scenes")
    return {"project": project_name, "script_path": str(script_path),
            "scene_plan": str(plan_path), "scenes": n}


async def sync_vectors(job, *, db_path: Path, project_id: Optional[str] = None):
    """Sync the vector index from the library DB for semantic search."""
    from nolan.indexer import VideoIndex
    from nolan.vector_search import VectorSearch

    index = VideoIndex(db_path)
    vector_db_path = db_path.parent / "vectors"
    vs = VectorSearch(vector_db_path, index=index)

    def progress(current, total, message):
        frac = (current / total) if total else 0
        job.set_progress(min(0.99, frac), f"[{current}/{total}] {message}")

    job.set_progress(0.02, "Syncing embeddings…")
    result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: vs.sync_from_index(project_id=project_id, progress_callback=progress)
    )
    job.set_progress(1.0, "Vector sync complete")
    return result if isinstance(result, dict) else {"synced": True}


async def embed_video(job, *, db_path: Path, video_id: int):
    """Embed a single indexed video into the vector store (manual 'make searchable')."""
    from nolan.indexer import VideoIndex
    from nolan.vector_search import VectorSearch

    index = VideoIndex(db_path)
    vs = VectorSearch(db_path.parent / "vectors", index=index)
    job.set_progress(0.1, "Embedding video…")
    result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: vs.sync_video(video_id)
    )
    job.set_progress(1.0, "Video embedded — now searchable")
    return result


async def promote_to_pool(job, *, comp: str, video_path: str, start: float, end: float, name=None):
    """MANUAL promotion: trim [start,end] from a LIBRARY source video and drop it straight into a
    HyperFrames project's pool.json — bypassing acquisition ranking (the human already chose it). Reuses
    the clipper trim engine (local range → mp4) + hfedit pool registration, so a promoted segment and a
    URL clip land in the pool identically (source 'manual')."""
    import re

    from nolan import clipper
    from nolan.hyperframes import edit as hfedit

    src = Path(video_path)
    if not src.exists():
        raise RuntimeError(f"source video not found: {video_path}")
    nm = re.sub(r"[^\w.-]+", "_", (name or f"{src.stem}_{int(start)}_{int(end)}")).strip("._") or "clip"
    out = hfedit.comp_dir(comp) / "assets" / f"{nm}.mp4"
    job.set_progress(0.1, f"Trimming {start:.1f}–{end:.1f}s from {src.name}…")
    saved = await asyncio.to_thread(clipper.clip, str(src), float(start), float(end), out, kind="local")
    if not saved:
        raise RuntimeError("trim produced no file")
    job.set_progress(0.8, "Registering in the project pool…")
    await asyncio.to_thread(hfedit.resolve_asset, comp, str(saved))
    job.set_progress(1.0, f"Promoted → {comp} pool")
    return {"ok": True, "path": str(saved), "name": Path(saved).name, "comp": comp}


async def _capture_visual_tier(url: str, windows: list, yid: str, title: str, *,
                               visual: str = "keyframe", max_frames: int = 0, densify: bool = False,
                               kind: str = "youtube", job=None) -> int:
    """Capture + embed the visual tier for ONE transcript video: DOWNLOAD the video ONCE to a temp file,
    then run FULL-RES scene-cut detection + one frame per shot (b-roll optionally densified) ALL LOCALLY --
    one sustained transfer instead of ~N throttled googlevideo range requests (batch-scale bottleneck + no
    stalled-stream hangs); caption-only (BGE over the gemma caption incl. its `shot` field), CLIP skipped;
    temp file deleted after. `max_frames` > 0 = an optional safety cap. Returns the frame count. (The free
    storyboard tiles still power the whole-video filmstrip overview in the detail.)"""
    import tempfile
    import shutil as _sh
    import time as _time
    from collections import Counter

    from nolan import transcript_frames as tfr
    tmpd = Path(tempfile.mkdtemp())
    sdir = tfr.storyboard_dir(yid); _sh.rmtree(sdir, ignore_errors=True)

    def _wtext(ts):                                               # the transcript window covering a frame
        for w in windows:
            if w["start"] <= ts <= w["end"]:
                return w["text"]
        return ""

    async def _caption(frames):
        return await tfr.caption_frames_async([(fp, _wtext(t), t) for t, fp in frames], concurrency=12)

    # keyframe (the one visual tier): DOWNLOAD ONCE -> detect + grab LOCALLY (no per-frame CDN throttle / stalled-stream hangs)
    _t = {"dl": 0.0, "det": 0.0, "grab": 0.0, "cap": 0.0, "emb": 0.0}
    _c = _time.time()
    async with tfr.download_sem():                                # GLOBAL download cap (CDN-safe across jobs)
        if kind == "archive":                                    # archive: download the cheap caption derivative directly
            from nolan import archive_source as _ar
            dld, dur = await asyncio.to_thread(_ar.download_video, yid, tmpd, "caption")
        else:
            dld, dur = await asyncio.to_thread(tfr.download_video, url, tmpd)
    _t["dl"] = _time.time() - _c
    local = dld is not None
    src = str(dld) if local else url
    if job and not local:
        job.log("    - download failed; streaming fallback (may throttle)")
    _c = _time.time()
    cuts, ddur = await asyncio.to_thread(tfr.detect_cuts, src, 0.4, 1.5, 120.0, 8, not local, dur)
    if kind == "archive" and local and not cuts:                        # 0 cuts on a real film -> the caption
        from nolan import archive_source as _ar                           # derivative is broken -> retry the largest encode
        dld2, dur2 = await asyncio.to_thread(_ar.download_video, yid, tmpd, "largest")
        if dld2 and str(dld2) != src:
            if job:
                job.log("    - caption derivative unreadable; retried the largest encode")
            dld, dur, src, local = dld2, dur2, str(dld2), True
            cuts, ddur = await asyncio.to_thread(tfr.detect_cuts, src, 0.4, 1.5, 120.0, 8, False, dur)
    _t["det"] = _time.time() - _c
    dur = dur or ddur or (float(windows[-1]["end"]) if windows else 0.0)
    sprites = [] if kind == "archive" else await asyncio.to_thread(tfr.storyboard_tiles, url, sdir, 12.0, 80)   # filmstrip overview (free; yt-dlp storyboard is YouTube-only)
    base = tfr.plan_shots(cuts, dur) if (cuts and dur) else [
        (round((w["start"] + w["end"]) / 2, 1), float(w["start"]), float(w["end"])) for w in windows]
    if max_frames and len(base) > int(max_frames):                # optional safety cap (0 = uncapped)
        stp = len(base) / int(max_frames)
        base = [base[int(k * stp)] for k in range(int(max_frames))]
        if job:
            job.log(f"    - capped to {max_frames} base shots (max_frames=0 for full coverage)")
    if job:
        job.log(f"    - {len(cuts)} cuts -> {len(base)} shots ({'local' if local else 'stream'}), {len(sprites)} sprites")

    async def _grab(times):
        return await asyncio.to_thread(tfr.ranged_keyframes, src, list(times), tmpd, not local, 8)

    _c = _time.time(); base_kfs = await _grab([t for t, _s, _e in base]); _t["grab"] += _time.time() - _c
    _c = _time.time(); base_an = await _caption(base_kfs); _t["cap"] += _time.time() - _c
    tmap = {round(t, 1): (s, e) for t, s, e in base}
    capframes = [(t, tmap.get(round(t, 1), (t, t))[0], tmap.get(round(t, 1), (t, t))[1],
                  a.get("content_kind", "")) for (t, fp), a in zip(base_kfs, base_an)]
    extra_kfs, extra_an = [], []
    extra_times = tfr.densify_broll(capframes) if densify else []
    if extra_times:
        _c = _time.time(); extra_kfs = await _grab(extra_times); _t["grab"] += _time.time() - _c
        _c = _time.time(); extra_an = await _caption(extra_kfs); _t["cap"] += _time.time() - _c
        if job:
            job.log(f"    - +{len(extra_kfs)} b-roll densify frames")
    kfs = base_kfs + extra_kfs
    ans = base_an + extra_an
    caps = [a.get("caption", "") for a in ans]
    ats = [a.get("asset_type", "") for a in ans]
    if job and ats:
        tally = ", ".join(f"{k or '?'}:{c}" for k, c in Counter(ats).most_common())
        job.log(f"    - asset types: {tally}")
    _c = _time.time()
    n = await asyncio.to_thread(tfr.embed_frames, kfs, yid, url, "keyframe", title, None, None, caps, ats)
    _t["emb"] = _time.time() - _c
    if job:
        job.log(f"    ~ timing[{title[:28]}] {len(kfs)}f: dl {_t['dl']:.0f}s detect {_t['det']:.0f}s "
                f"grab {_t['grab']:.0f}s caption {_t['cap']:.0f}s embed {_t['emb']:.0f}s")
    _sh.rmtree(tmpd, ignore_errors=True)                          # delete the temp download + grab jpgs
    return n


async def ingest_channel_transcripts(job, *, config, db_path: Path, channel: str, limit: int = 10,
                                     window_s: float = 45.0, overlap_s: float = 10.0,
                                     visual: str = "keyframe", max_frames: int = 0, densify: bool = False,
                                     delay: float = 0.0, refresh: bool = False):
    """Build/refresh a TRANSCRIPT library from a YouTube channel: list its videos, fetch each transcript
    (captions only — NO video download), chunk into overlapping timestamped windows, ingest as a
    transcript-tier VideoIndex row (has_footage=0) + embed into the unified semantic store. Per-video
    progress; soft-skips videos without captions. A cheap DISCOVERY index — searchable, never footage."""
    import datetime as _dt

    from nolan import transcript_lib as tl
    from nolan.indexer import VideoIndex
    from nolan.vector_search import VectorSearch

    index = VideoIndex(db_path)
    vs = VectorSearch(db_path.parent / "vectors", index=index)
    job.set_progress(0.03, f"Listing {channel} …")
    vids = await asyncio.to_thread(tl.list_channel, channel, int(limit))
    if not vids:
        raise RuntimeError(f"no videos found for channel {channel!r} (check the URL / @handle)")
    now = _dt.datetime.now().isoformat(timespec="seconds")
    got = skipped = already = windows_total = frames_total = 0
    for i, v in enumerate(vids):
        if delay and i:
            await asyncio.sleep(delay)                            # rate-limit pacing for whole-channel crawls
        title = (v.get("title") or v.get("video_id") or "?")[:60]
        job.set_progress(0.05 + 0.9 * (i / len(vids)), f"[{i + 1}/{len(vids)}] {title}")
        yid0 = v.get("video_id") or ""
        if not refresh and yid0 and index.get_video_id(f"yt:{yid0}"):   # DEDUP: skip already-indexed → cheap re-crawl
            job.log(f"  = {title}: already indexed — skipped"); already += 1; continue
        try:
            meta, tr = await asyncio.to_thread(tl.fetch_transcript_with_cues, v["url"])
        except Exception as e:                                # a bad single video must not kill the channel run
            job.log(f"  ✗ {title}: {type(e).__name__}: {e}"); skipped += 1; continue
        if not tr or not getattr(tr, "chunks", None):
            job.log(f"  · {title}: no captions — skipped"); skipped += 1; continue
        windows = tl.chunk_transcript(tr, window_s=float(window_s), overlap_s=float(overlap_s))
        vid = await asyncio.to_thread(tl.ingest_transcript, index, {**meta, "url": v["url"]}, windows, channel)
        if not vid:
            skipped += 1; continue
        await asyncio.to_thread(vs.sync_video, vid)          # embed → unified semantic search
        got += 1
        windows_total += len(windows)
        nframes = 0
        if visual and visual != "off":                       # bonus VISUAL tier — never fails the transcript run
            try:
                yid = meta.get("video_id") or v["video_id"]
                nframes = await _capture_visual_tier(v["url"], windows, yid, title,
                                                     visual=visual, max_frames=max_frames, densify=densify, job=job)
                frames_total += nframes
            except Exception as e:
                job.log(f"    (visual '{visual}' skipped: {type(e).__name__}: {e})")
        tl.record_transcript(meta.get("video_id") or v["video_id"], {**meta, "url": v["url"]},
                             len(windows), channel, frames=nframes, added=now)
        job.log(f"  ✓ {title} ({len(windows)} windows" + (f", +{nframes} frames" if nframes else "") + ")")
    n_for_channel = sum(1 for e in tl.load_catalog().values() if e.get("channel") == channel)
    tl.upsert_source(channel, last_crawled=now, video_count=n_for_channel, added=now)   # first-class source
    job.set_progress(1.0, f"{got} new ({windows_total} windows, {frames_total} frames), "
                     f"{already} already indexed, {skipped} skipped")
    return {"channel": channel, "found": len(vids), "ingested": got, "already": already,
            "skipped": skipped, "windows": windows_total, "frames": frames_total}


async def refresh_transcript_video(job, *, config, db_path: Path, url: str, channel: str = "",
                                   window_s: float = 45.0, overlap_s: float = 10.0,
                                   visual: str = "keyframe", max_frames: int = 0, densify: bool = False):
    """Re-index ONE transcript video (force): re-fetch captions, re-chunk, replace its segments + frames,
    re-embed + re-caption. Powers the per-video Refresh action."""
    import datetime as _dt

    from nolan import transcript_frames as tfr
    from nolan import transcript_lib as tl
    from nolan.indexer import VideoIndex
    from nolan.vector_search import VectorSearch
    index = VideoIndex(db_path)
    vs = VectorSearch(db_path.parent / "vectors", index=index)
    now = _dt.datetime.now().isoformat(timespec="seconds")
    job.set_progress(0.1, "Fetching transcript…")
    meta, tr = await asyncio.to_thread(tl.fetch_transcript_with_cues, url)
    if not tr or not getattr(tr, "chunks", None):
        raise RuntimeError("no captions available for this video")
    yid = meta.get("video_id") or ""
    await asyncio.to_thread(tfr.delete_frames_for_video, yid)         # clear old frames before re-capture
    windows = tl.chunk_transcript(tr, window_s=float(window_s), overlap_s=float(overlap_s))
    job.set_progress(0.4, f"Ingesting {len(windows)} windows…")
    vid = await asyncio.to_thread(tl.ingest_transcript, index, {**meta, "url": url}, windows, channel)
    await asyncio.to_thread(vs.sync_video, vid)
    nframes = 0
    if visual and visual != "off":
        try:
            job.set_progress(0.6, "Re-capturing frames…")
            nframes = await _capture_visual_tier(url, windows, yid, meta.get("title", ""),
                                                 visual=visual, max_frames=max_frames, densify=densify, job=job)
        except Exception as e:
            job.log(f"  (visual refresh skipped: {type(e).__name__}: {e})")
    tl.record_transcript(yid, {**meta, "url": url}, len(windows), channel, frames=nframes, added=now)
    job.set_progress(1.0, f"Re-indexed {len(windows)} windows, {nframes} frames")
    return {"video_id": yid, "windows": len(windows), "frames": nframes}


async def batch_caption_videos(job, *, config, db_path: Path, video_ids: list, force: bool = False,
                               densify: bool = False):
    """Caption the visual tier for a BATCH of already-text-indexed transcript videos, SKIPPING ones already
    captioned (unless force). A few videos run in flight; the GLOBAL gemma/download governors keep total
    concurrency under the API/CDN ceilings regardless of how many are in flight. Resumable -- re-run to
    continue (skip-if-has-frames)."""
    import asyncio
    import sqlite3

    from nolan import transcript_frames as tfr
    from nolan import transcript_lib as tl
    from nolan.indexer import VideoIndex
    index = VideoIndex(db_path)
    cat = tl.load_catalog()
    ids = [str(v) for v in (video_ids or [])]
    total = len(ids)
    done = skipped = failed = 0
    sem = asyncio.Semaphore(4)                                # up to 4 videos IN FLIGHT (governors cap the rest)
    counter = {"i": 0}

    async def _one(yid):
        nonlocal done, skipped, failed
        async with sem:
            counter["i"] += 1
            i = counter["i"]
            meta = cat.get(yid, {})
            url = meta.get("url") or f"https://www.youtube.com/watch?v={yid}"
            title = (meta.get("title") or yid)[:60]
            job.set_progress(0.03 + 0.94 * (i / max(1, total)), f"[{i}/{total}] {title}")
            if not force and any(f.get("kind") == "keyframe" for f in tfr.frames_for_video(yid)):
                job.log(f"  = {title}: already captioned -- skipped"); skipped += 1; return
            vid = index.get_video_id(f"yt:{yid}")
            windows = []
            if vid is not None:
                with sqlite3.connect(index.db_path) as c:
                    for r in c.execute("SELECT timestamp_start, timestamp_end, transcript FROM segments "
                                       "WHERE video_id=? ORDER BY timestamp_start", (vid,)):
                        windows.append({"start": r[0], "end": r[1], "text": r[2] or ""})
            try:
                if force:
                    await asyncio.to_thread(tfr.delete_frames_for_video, yid)
                n = await _capture_visual_tier(url, windows, yid, title, visual="keyframe",
                                               densify=densify, kind=meta.get("kind", "youtube"), job=job)
                tl.record_transcript(yid, {**meta, "url": url, "video_id": yid}, len(windows),
                                     meta.get("channel"), frames=n, added=meta.get("added", ""))
                job.log(f"  ✓ {title}: {n} frames"); done += 1
            except Exception as e:
                job.log(f"  ✗ {title}: {type(e).__name__}: {e}"); failed += 1

    await asyncio.gather(*(_one(y) for y in ids))
    job.set_progress(1.0, f"captioned {done}, skipped {skipped} (already done), {failed} failed of {total}")
    return {"total": total, "captioned": done, "skipped": skipped, "failed": failed}


async def ingest_videos(job, *, config, db_path: Path, videos: list, visual: str = "off",
                        window_s: float = 45.0, overlap_s: float = 10.0, delay: float = 1.0,
                        refresh: bool = False, kind: str = "youtube", collection: str = "",
                        broll_max_sec: float = 0.0, copyright_free: bool = False):
    """Ingest a SPECIFIC list of videos (each {url, video_id?, title?, duration?, channel?}) -- transcript
    (+ optional visual), dedup-skip, rate-paced. Powers 'add selected'. `kind='archive'` fetches archive.org's
    Whisper ASR; items with no transcript are a reported soft-skip (youtube_cc title-indexes instead).

    `broll_max_sec>0`: a video at/under that duration is a READY B-ROLL -- a short single-shot clip that IS the
    asset. We skip the transcript fetch entirely (no network, no wait), index the descriptive TITLE as the
    content, flag it `broll`, and skip the visual tier (the whole clip is the b-roll). No captions needed."""
    import asyncio
    import datetime as _dt

    from nolan import transcript_lib as tl
    from nolan.indexer import VideoIndex
    from nolan.vector_search import VectorSearch
    from nolan.youtube import extract_video_id
    index = VideoIndex(db_path)
    vs = VectorSearch(db_path.parent / "vectors", index=index)
    now = _dt.datetime.now().isoformat(timespec="seconds")
    items = [({"url": v} if isinstance(v, str) else v) for v in (videos or [])]
    total = len(items); got = already = skipped = no_tr = broll = 0
    for i, v in enumerate(items):
        url = (v.get("url") or "").strip()
        title = (v.get("title") or url)[:60]
        if not url:
            skipped += 1; continue
        job.set_progress(0.03 + 0.9 * (i / max(1, total)), f"[{i + 1}/{total}] {title}")
        if kind == "archive":
            from nolan import archive_source as ar
            yid0 = v.get("video_id") or ar.collection_ref(url)
        else:
            yid0 = v.get("video_id") or extract_video_id(url) or ""
        if not refresh and yid0 and index.get_video_id(f"yt:{yid0}"):
            job.log(f"  = {title}: already indexed -- skipped"); already += 1; continue
        try:
            dur_item = float(v.get("duration") or 0)
        except (TypeError, ValueError):
            dur_item = 0.0
        # ready-b-roll mode is only for the copyright-free stock family (youtube_cc)
        is_broll = kind == "youtube_cc" and bool(broll_max_sec) and 0 < dur_item <= float(broll_max_sec)
        if is_broll:
            # ready b-roll: the title IS the content — no transcript fetch, no visual tier
            ttl = (v.get("title") or title) or yid0
            windows = [{"start": 0.0, "end": dur_item, "text": ttl}]
            meta = {"video_id": yid0, "title": ttl, "url": url}
            job.log(f"  ▸ {ttl[:52]}: ready b-roll ({int(dur_item)}s) -- title-indexed")
        else:
            if delay and i:
                await asyncio.sleep(delay)
            try:
                if kind == "archive":
                    from nolan import archive_source as ar
                    meta, tr = await asyncio.to_thread(ar.fetch_transcript, yid0, collection)
                else:
                    meta, tr = await asyncio.to_thread(tl.fetch_transcript_with_cues, url)
            except Exception as e:
                job.log(f"  x {title}: {type(e).__name__}: {e}"); skipped += 1; continue
            has_tr = tr and getattr(tr, "chunks", None)
            if has_tr:
                windows = tl.chunk_transcript(tr, window_s=float(window_s), overlap_s=float(overlap_s))
            elif kind in ("youtube_cc", "archive"):
                # no transcript -> index the descriptive metadata as one window so the item STILL enters the
                # library (and can be VISUALLY captioned). archive: title + subject tags; stock: the title.
                ttl = (meta or {}).get("title") or (v.get("title") or title) or yid0
                text = ttl
                subj = (meta or {}).get("subject") or []
                if kind == "archive" and subj:
                    text = ttl + " -- " + ", ".join(str(s) for s in subj[:10])
                dur = dur_item or float((meta or {}).get("duration") or 0) or 60.0
                windows = [{"start": 0.0, "end": float(dur), "text": text}]
                meta = {**(meta or {}), "video_id": (meta or {}).get("video_id") or yid0,
                        "title": ttl, "url": url}
                job.log(f"  ~ {ttl[:60]}: no transcript -> {'title+subject' if kind=='archive' else 'title'}-indexed")
            else:
                job.log(f"  . {title}: no transcript -- skipped"); no_tr += 1; continue
        vid = await asyncio.to_thread(tl.ingest_transcript, index, {**meta, "url": url}, windows, v.get("channel") or collection)
        if not vid:
            skipped += 1; continue
        await asyncio.to_thread(vs.sync_video, vid)
        got += 1
        if is_broll:
            broll += 1
        nframes = 0
        if visual and visual != "off" and not is_broll:        # b-roll skips (the whole clip IS the asset)
            try:
                nframes = await _capture_visual_tier(url, windows, meta.get("video_id") or yid0, title,
                                                     visual=visual, kind=kind, job=job)
            except Exception as e:
                job.log(f"    (visual skipped: {type(e).__name__}: {e})")
        tl.record_transcript(meta.get("video_id") or yid0, {**meta, "url": url}, len(windows),
                             v.get("channel") or collection, frames=nframes, added=now, broll=is_broll,
                             kind=kind, copyright_free=copyright_free)
        if not is_broll:
            job.log(f"  + {title} ({len(windows)} windows" + (f", +{nframes} frames" if nframes else "") + ")")
    tail = (f", {broll} ready-broll" if broll else "") + (f", {no_tr} no-transcript" if no_tr else "")
    job.set_progress(1.0, f"{got} added, {already} already indexed, {skipped} skipped{tail} of {total}")
    return {"total": total, "added": got, "already": already, "skipped": skipped,
            "no_transcript": no_tr, "broll": broll}


async def evoke_broll(job, *, config, line: str, operator: str = "tonal", mode: str = "stock",
                      period: str = "", locale: str = "", literalness: float = 0.25,
                      mood: Optional[str] = None, sources: Optional[list] = None,
                      project: Optional[str] = None, media: Optional[list] = None,
                      gen_style: str = "Fooocus Cinematic", beat: Optional[int] = None):
    """Narrative→asset pairing search (tonal | conceptual | knowledge …) — stock / library / generate.
    When `project` (+ optional `beat`) is given, the search runs WITH whole-script ScriptContext."""
    from nolan.evoke_broll import EvokeBrollSearch

    searcher = EvokeBrollSearch(config=config, progress=lambda f, m: job.set_progress(min(0.99, f), m))
    result = await searcher.search(line, operator=operator, mode=mode, period=period, locale=locale,
                                   literalness=float(literalness), mood=(mood or None),
                                   sources=(sources or None), project=(project or None),
                                   media=(media or None), gen_style=(gen_style or "Fooocus Cinematic"),
                                   beat=beat)
    job.set_progress(1.0, f"{result['status']} — {len(result['picks'])} clip(s)")
    return result


def list_context_projects() -> list:
    """Projects that carry a script (script.md) → usable as ScriptContext on /broll.
    Returns [{slug, subject, beats:[{idx,title,timecode}]}] for the context dropdowns."""
    from nolan.script_context import ScriptContext
    out = []
    root = Path("projects")
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not (d / "script.md").exists():
            continue
        try:
            ctx = ScriptContext.load(d)
        except Exception:
            continue
        if not ctx.beats:
            continue
        out.append({"slug": ctx.slug, "subject": ctx.subject or ctx.slug,
                    "beats": [{"idx": b.idx, "title": b.title, "timecode": b.timecode,
                               "narration": b.narration[:600]} for b in ctx.beats]})
    return out


async def _local_still(src: str, prev):
    """Resolve a pick's still (served /broll-gen path or remote URL) to a local jpg."""
    import hashlib, io
    from PIL import Image
    from nolan.evoke_broll import GEN_DIR
    from nolan.image_search import ImageScorer
    if src.startswith("/broll-gen/"):
        return GEN_DIR / src.split("/broll-gen/", 1)[1]
    data = await asyncio.get_event_loop().run_in_executor(None, ImageScorer()._download_image, src)
    if not data:
        raise RuntimeError("could not fetch image")
    out = prev / f"src_{hashlib.md5(src.encode()).hexdigest()[:12]}.jpg"
    await asyncio.get_event_loop().run_in_executor(
        None, lambda: Image.open(io.BytesIO(data)).convert("RGB").save(out, "JPEG", quality=90))
    return out


async def preview_motion(job, *, config, src: str, motion_id: str = "ken-burns-in", kind: str = "image"):
    """Render one still pick with its recommended motion → a short served mp4 (the /broll preview)."""
    import hashlib
    from nolan.evoke_broll import GEN_DIR
    from nolan.still_motion import render_still
    prev = GEN_DIR / "previews"; prev.mkdir(parents=True, exist_ok=True)
    job.set_progress(0.12, "Fetching still…")
    local = await _local_still(src, prev)
    out = prev / f"{hashlib.md5((src + '|' + motion_id).encode()).hexdigest()[:12]}.mp4"
    job.set_progress(0.35, f"Rendering {motion_id}…")
    await asyncio.get_event_loop().run_in_executor(None, lambda: render_still(str(local), motion_id, out, 4.0))
    job.set_progress(1.0, "preview ready")
    return {"url": f"/broll-gen/previews/{out.name}", "motion": motion_id}


async def preview_split(job, *, config, left_src: str, right_src: str,
                        left_label: str = "", right_label: str = ""):
    """Render the relational operator's split-screen 'collision' of two picks → served mp4."""
    import hashlib
    from nolan.evoke_broll import GEN_DIR
    from nolan.still_motion import render_split
    prev = GEN_DIR / "previews"; prev.mkdir(parents=True, exist_ok=True)
    job.set_progress(0.15, "Fetching stills…")
    left = await _local_still(left_src, prev)
    right = await _local_still(right_src, prev)
    out = prev / f"split_{hashlib.md5((left_src + '|' + right_src).encode()).hexdigest()[:12]}.mp4"
    job.set_progress(0.4, "Rendering split-screen…")
    await asyncio.get_event_loop().run_in_executor(
        None, lambda: render_split(str(left), str(right), out, 4.0, left_label, right_label))
    job.set_progress(1.0, "split-screen ready")
    return {"url": f"/broll-gen/previews/{out.name}"}


async def preview_stat(job, *, config, src: str, value: float, prefix: str = "", suffix: str = "",
                       caption: str = "", decimals: int = 0, theme: str = "dark-editorial",
                       accent: str = ""):
    """Render the SCALE count-up (StatOver) over a referent still → served mp4, styled by `theme`."""
    import hashlib
    from nolan.evoke_broll import GEN_DIR
    from nolan.still_motion import render_stat_over
    prev = GEN_DIR / "previews"; prev.mkdir(parents=True, exist_ok=True)
    job.set_progress(0.12, "Fetching referent still…")
    local = await _local_still(src, prev)
    key = f"{src}|{value}|{prefix}|{suffix}|{caption}|{theme}|{accent}"
    out = prev / f"stat_{hashlib.md5(key.encode()).hexdigest()[:12]}.mp4"
    job.set_progress(0.35, f"Rendering count-up ({theme})…")
    await asyncio.get_event_loop().run_in_executor(None, lambda: render_stat_over(
        str(local), float(value), out, prefix=prefix, suffix=suffix, caption=caption,
        decimals=int(decimals or 0), theme=(theme or "dark-editorial"), accent=(accent or ""), duration=5.0))
    job.set_progress(1.0, "count-up ready")
    return {"url": f"/broll-gen/previews/{out.name}", "theme": theme}


async def attach_scene_asset(job, *, config, project_name: str, scene_id: str, url: str,
                             kind: str = "image", source: str = "", title: str = ""):
    """Attach a super-search pick to a scene: download an image into assets/broll/ and set
    matched_asset, or reference a video via matched_clip. Persists scene_plan.json."""
    import shutil
    from nolan.scenes import ScenePlan
    plan_path = _scene_plan_path(project_name)
    if not plan_path.exists():
        raise RuntimeError(f"No scene_plan.json for '{project_name}'.")
    plan = ScenePlan.load(str(plan_path))
    scene = next((s for s in plan.all_scenes if s.id == scene_id), None)
    if scene is None:
        raise RuntimeError(f"scene '{scene_id}' not found")
    job.set_progress(0.2, "Attaching…")
    if kind == "video":
        scene.matched_clip = {"external_url": url, "source": source or "super-search", "title": title,
                              "media_type": "video", "external": True, "preview_image_url": None}
        scene.matched_asset = None
        out = f"video:{source or 'super-search'}"
    else:
        out_dir = plan_path.parent / "assets" / "broll"
        out_dir.mkdir(parents=True, exist_ok=True)
        local = await _local_still(url, out_dir)          # downloads (or resolves /broll-gen) → local Path
        dest = out_dir / f"{scene_id}{Path(local).suffix or '.jpg'}"
        if Path(local).resolve() != dest.resolve():
            shutil.copy(local, dest)
        scene.matched_asset = str(dest.relative_to(plan_path.parent)).replace("\\", "/")
        scene.matched_clip = None
        out = f"image:{source or 'super-search'}"
    plan.save(str(plan_path))
    job.set_progress(1.0, "attached")
    return {"scene_id": scene_id, "attached": out, "matched_asset": scene.matched_asset}


async def asset_review_job(job, *, config, project: str, brains=None, beats=None, media=None,
                           agent: str = "nolan4"):
    """Beat-by-beat asset acquisition review (top-5 + tags per beat) across brains → served gallery."""
    from nolan.asset_review import run_review
    brains = tuple(brains or ["engine"])
    r = await run_review(project, brains=brains, beats=beats, media=media, agent=agent,
                         progress=lambda f, m: job.set_progress(min(0.99, f), m))
    job.set_progress(1.0, f"{len(r['beats'])} beats · {', '.join(r['brains'])}")
    return {"project": project, "brains": r["brains"], "beats": len(r["beats"]),
            "gallery": f"/broll-gen/asset_review_{project}.html"}


def _scene_plan_path(project_name: str) -> Path:
    return Path("projects") / project_name / "scene_plan.json"


# Moved to nolan.external_assets (P2) — re-exported here for back-compat.
from nolan.external_assets import build_query_variants  # noqa: E402,F401


async def match_broll_v2(job, *, config, project_name: str, prefer_video: bool = True,
                         max_results: int = 4, concurrency: int = 6, score_cap: int = 4,
                         scorer_model: str = "qwen/qwen3-vl-8b-instruct",
                         use_library: bool = True, library_gate: int = 5,
                         use_vision: bool = False, semantic: bool = True,
                         sim_gate: float = 0.30, knowledge: bool = False,
                         knowledge_kind: str = "any"):
    """Video-first, multi-source b-roll matcher with query-variant fallback.

    Speed-optimized: (1) scenes processed concurrently, (2) candidates cheaply
    pre-filtered to the top `score_cap` by quality before vision-scoring,
    (3) a fast small vision model (`scorer_model`) does relevance scoring.
    Videos are attached by reference; images downloaded. assemble detects type by ext.

    When `use_library`, the picture library (global + this project) is searched
    FIRST (CLIP) and a candidate that vision-scores >= `library_gate` is reused
    directly — free, and it reuses curated/licensed assets — before any external
    provider is queried.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor
    import httpx as _httpx
    from nolan.scenes import ScenePlan
    from nolan.image_search import ImageSearchClient, ImageScorer, ImageSearchResult
    from nolan.cli_legacy import _scoring_vision_config

    plan_path = _scene_plan_path(project_name)
    if not plan_path.exists():
        raise RuntimeError(f"No scene_plan.json for '{project_name}'.")

    def _work():
        plan = ScenePlan.load(str(plan_path))
        broll = [s for s in plan.all_scenes if s.visual_type == "b-roll"
                 and (getattr(s, "search_query", "") or getattr(s, "visual_description", ""))
                 and not getattr(s, "matched_asset", None) and not getattr(s, "matched_clip", None)]
        client = ImageSearchClient(
            pexels_api_key=config.image_sources.pexels_api_key,
            pixabay_api_key=config.image_sources.pixabay_api_key,
            smithsonian_api_key=config.image_sources.smithsonian_api_key,
            keys=config.image_sources.provider_keys(),
        )
        # (3) Fast small vision model for relevance scoring.
        sv = _scoring_vision_config(config, "openrouter")
        sv["model"] = scorer_model
        scorer = ImageScorer(vision_provider="openrouter", vision_config=sv)
        out_dir = plan_path.parent / "assets" / "broll"
        out_dir.mkdir(parents=True, exist_ok=True)
        vid_sources = client.video_providers()

        # Picture-library sources (global + project), one shared CLIP embedder.
        libs = []
        if use_library:
            try:
                from nolan.imagelib import ClipEmbedder, ImageLibrary
                emb = ClipEmbedder()
                libs.append(ImageLibrary("global", embedder=emb))
                if (Path("projects") / project_name / "imagelib").exists():
                    libs.append(ImageLibrary("project", project=project_name, embedder=emb))
            except Exception as e:
                job.log(f"picture library unavailable: {e}")

        # Semantic mode: external candidates are described (vision) + ingested into
        # the project library so the match is description<->description (like the
        # video library) and the library grows/reuses across runs.
        ingest_lib = None
        if semantic:
            try:
                from nolan.imagelib import ImageLibrary
                from nolan.imagelib.describe import make_describer
                describer = make_describer(config)
                ingest_lib = ImageLibrary("project", project=project_name,
                                          embedder=(libs[0].embedder if libs else None),
                                          describer=describer)
                if ingest_lib not in libs:
                    libs.append(ingest_lib)
            except Exception as e:
                job.log(f"semantic match unavailable, falling back: {e}")
                ingest_lib = None

        # Knowledge-driven lead queries: one whole-script-aware pass names specific,
        # era-correct assets per beat (see nolan.knowledge_query), tried FIRST in the
        # external search. Built once, keyed by scene id; empty map = feature off.
        lead_map = {}
        if knowledge:
            try:
                from nolan.script_context import ScriptContext
                from nolan.knowledge_query import build_scene_lead_map
                from nolan.llm import create_text_llm
                kctx = ScriptContext.load(project_name)
                if kctx.beats:
                    lead_map = build_scene_lead_map(kctx, broll, llm=create_text_llm(config),
                                                    kind=knowledge_kind, log=job.log)
                    job.log(f"knowledge queries ready for {sum(1 for v in lead_map.values() if v)} scenes")
                else:
                    job.log("knowledge mode: no script beats found, skipping")
            except Exception as e:
                job.log(f"knowledge mode unavailable: {e}")

        state = {"done": 0, "matched": 0, "from_library": 0}
        lock = threading.Lock()
        lib_lock = threading.Lock()

        def _try_library(scene, variants):
            """Reuse a library asset if one vision-scores >= library_gate.

            Same hybrid (CLIP+BGE) lookup policy as the asset engine's library
            tier; the semantics that differ are deliberate — this op vision-
            gates and COPIES the pick into the project (curated Studio flow),
            while the engine links the library asset in place (auto pipeline).
            """
            import shutil
            q = (getattr(scene, "search_query", "") or scene.visual_description
                 or (variants[0] if variants else ""))
            cands = []
            with lib_lock:
                for lib in libs:
                    try:
                        for h in lib.search_hybrid(q, k=score_cap):
                            cands.append((str(lib.base / h.asset.path), h.asset))
                    except Exception:
                        pass
            if not cands:
                return False
            isrs = [ImageSearchResult(url=p, title=a.title, source=f"library:{a.source or '?'}",
                                      source_url=a.source_url, license=a.license,
                                      width=a.width, height=a.height)
                    for p, a in cands[:score_cap]]
            if use_vision:
                ctx = f"for a documentary scene: {scene.visual_description or ''}"
                scored = scorer.score_results(isrs, q, context=ctx)
                best = scored[0] if scored else None
                if not best or (best.score or 0) < library_gate:
                    return False
            else:
                # Fast default: trust CLIP ranking (lib.search is already CLIP-ranked).
                best = isrs[0] if isrs else None
                if not best:
                    return False
                best.score = best.score if getattr(best, "score", None) is not None else "clip"
            dest = out_dir / f"{scene.id}{Path(best.url).suffix or '.jpg'}"
            try:
                shutil.copy(best.url, dest)
            except Exception:
                return False
            scene.matched_asset = str(dest.relative_to(plan_path.parent)).replace("\\", "/")
            job.log(f"{scene.id}: {best.source} (library, score {best.score})")
            return True

        def process_scene(scene):
            variants = build_query_variants(scene)
            # Library-first: reuse a curated asset before any external provider.
            if libs and _try_library(scene, variants):
                with lock:
                    state["done"] += 1
                    state["matched"] += 1
                    state["from_library"] += 1
                    job.set_progress(0.05 + 0.9 * state["done"] / max(1, len(broll)),
                                     f"b-roll {state['done']}/{len(broll)} · {state['matched']} matched")
                return
            # Shared external-provider match (same logic the resolver uses as external_fn).
            from nolan.external_assets import external_match_for_scene
            kind = external_match_for_scene(
                scene, client=client, scorer=scorer, vid_sources=vid_sources,
                out_dir=out_dir, project_root=plan_path.parent, prefer_video=prefer_video,
                max_results=max_results, score_cap=score_cap, gate=4,
                use_vision=use_vision, lead_queries=lead_map.get(scene.id), log=job.log)
            ok = bool(kind)
            with lock:
                state["done"] += 1
                if ok:
                    state["matched"] += 1
                job.set_progress(0.05 + 0.9 * state["done"] / max(1, len(broll)),
                                 f"b-roll {state['done']}/{len(broll)} · {state['matched']} matched")

        def process_scene_semantic(scene):
            """Unified description-based match (library-first, external=ingest).
            Sequential: ChromaDB/vision aren't thread-safe and the describe step
            is the cost — it caches into the library for reuse."""
            from nolan.external_assets import semantic_match_for_scene
            kind = semantic_match_for_scene(
                scene, libs=libs, client=client, scorer=scorer, vid_sources=vid_sources,
                out_dir=out_dir, project_root=plan_path.parent, ingest_lib=ingest_lib,
                max_results=max_results, score_cap=score_cap, sim_gate=sim_gate,
                lead_queries=lead_map.get(scene.id), log=job.log)
            state["done"] += 1
            if kind:
                state["matched"] += 1
                if kind.startswith("library"):
                    state["from_library"] += 1
            job.set_progress(0.05 + 0.9 * state["done"] / max(1, len(broll)),
                             f"b-roll {state['done']}/{len(broll)} · {state['matched']} matched")

        if semantic and ingest_lib is not None:
            for s in broll:
                process_scene_semantic(s)
        else:
            # (1) Process scenes concurrently (legacy CLIP/quality path).
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                list(pool.map(process_scene, broll))

        plan.save(str(plan_path))
        return {"project": project_name, "broll_scenes": len(broll), "matched": state["matched"],
                "from_library": state["from_library"], "video_sources": vid_sources,
                "scorer_model": scorer_model}

    result = await asyncio.to_thread(_work)
    job.set_progress(1.0, f"Matched {result['matched']}/{result['broll_scenes']} b-roll scenes")
    return result


async def import_script_from_video(job, *, config, video_path: str, project_name: str,
                                   translate: bool = True, section_seconds: float = 30.0):
    """Build a NOLAN script from an existing video's subtitle/transcript.

    Sections the transcript into ~section_seconds beats and (optionally) translates
    to English. Saves script.json (for design), script.md, and the original-language
    reference. This is the "bring your own script" path — no LLM script-writing.
    """
    from nolan.transcript import find_transcript_for_video, TranscriptLoader
    from nolan.script import Script, ScriptSection
    from nolan.llm import create_text_llm

    vp = Path(video_path)
    tp = find_transcript_for_video(vp)
    if not tp:
        raise RuntimeError(f"No subtitle/transcript found next to {vp.name}")
    job.set_progress(0.05, f"Loading transcript: {tp.name}")
    t = TranscriptLoader.load(tp)

    # Group chunks into ~section_seconds beats.
    raw, cur = [], None
    for ch in t.chunks:
        if cur is None:
            cur = {"start": ch.start, "end": ch.end, "text": [ch.text]}
        else:
            cur["text"].append(ch.text); cur["end"] = ch.end
        if cur["end"] - cur["start"] >= section_seconds:
            raw.append(cur); cur = None
    if cur:
        raw.append(cur)
    job.log(f"{len(t.chunks)} transcript chunks -> {len(raw)} sections")

    llm = create_text_llm(config) if translate else None
    sections = []
    for i, sec in enumerate(raw):
        text = " ".join(sec["text"]).strip()
        narration = text
        if translate and text:
            job.set_progress(0.1 + 0.8 * i / max(1, len(raw)), f"Translating section {i+1}/{len(raw)}")
            try:
                narration = (await llm.generate(
                    "Translate this documentary narration to natural, fluent English. "
                    "Output ONLY the English translation, no notes or quotes:\n\n" + text
                )).strip()
            except Exception as e:
                job.log(f"translate failed for section {i+1}: {e}")
                narration = text
        sections.append(ScriptSection(
            title=f"Section {i+1}", narration=narration,
            start_time=sec["start"], end_time=sec["end"],
            word_count=len(narration.split()),
        ))

    out = Path("projects") / project_name
    out.mkdir(parents=True, exist_ok=True)
    # Scaffold project.yaml so the project is orchestrate-ready (Director needs it).
    pyaml = out / "project.yaml"
    if not pyaml.exists():
        import yaml as _yaml
        pyaml.write_text(_yaml.safe_dump({
            "name": project_name.replace("-", " ").title(),
            "slug": project_name,
            "description": f"Imported from {vp.name}",
            "source_videos": ["source/"],
            "output_dir": "output/",
            "assets_dir": "assets/",
        }, sort_keys=False, allow_unicode=True), encoding="utf-8")
    script = Script(sections=sections)
    script.save_json(str(out / "script.json"))
    (out / "script.md").write_text(script.to_markdown(), encoding="utf-8")
    (out / "script_original.md").write_text(
        "\n\n".join(f"[{s['start']:.0f}-{s['end']:.0f}s] {' '.join(s['text'])}" for s in raw),
        encoding="utf-8",
    )
    job.set_progress(1.0, f"Imported {len(sections)} sections ({script.total_duration:.0f}s)")
    return {"project": project_name, "sections": len(sections),
            "duration": round(script.total_duration, 1), "translated": translate}


async def design(job, *, config, project_name: str, llm_provider: Optional[str] = None,
                 llm_model: Optional[str] = None, reasoning: Optional[bool] = None,
                 source_project: Optional[str] = None):
    """Design a scene plan from a script.json using a selectable text LLM.

    source_project: copy the script from another project (so multiple LLMs design
    the identical script for a fair comparison).
    """
    import time
    from nolan.scenes import SceneDesigner, ScenePlan
    from nolan.script import Script

    out = Path("projects") / project_name
    out.mkdir(parents=True, exist_ok=True)
    # Resolve the script (optionally copied from a source project).
    src_dir = Path("projects") / (source_project or project_name)
    src_script = src_dir / "script.json"
    if not src_script.exists():
        raise RuntimeError(f"No script.json in '{src_dir.name}' — import a script first.")
    if source_project and source_project != project_name:
        import shutil
        shutil.copy(src_script, out / "script.json")
        for extra in ("script.md", "script_original.md"):
            if (src_dir / extra).exists():
                shutil.copy(src_dir / extra, out / extra)

    script = Script.load_json(str(out / "script.json"))
    from nolan.llm import create_text_llm
    llm = create_text_llm(config, provider=llm_provider, model=llm_model, reasoning=reasoning)
    model_label = getattr(llm, "model", llm_model or "llm")
    job.set_progress(0.1, f"Designing {len(script.sections)} sections with {model_label}…")

    designer = SceneDesigner(llm, cache_dir=out / ".design_cache", model_id=model_label)

    def on_progress(current, total, scenes_so_far, message):
        # Reserve 0.1–0.98 for section progress; final write completes it.
        job.set_progress(0.1 + 0.88 * (current / total if total else 0),
                         f"{message} ({model_label})")

    t0 = time.monotonic()
    plan = await designer.design_full_plan(script.sections, progress_callback=on_progress,
                                           concurrency=8)
    elapsed = time.monotonic() - t0
    plan.save(str(out / "scene_plan.json"))

    n = len(plan.all_scenes)
    job.set_progress(1.0, f"Designed {n} scenes with {model_label} in {elapsed:.0f}s")
    return {"project": project_name, "scenes": n, "llm": model_label,
            "elapsed_s": round(elapsed, 1)}


async def match_assets(job, *, config, project_name: str, source: str = "wikimedia",
                       max_results: int = 5, kind: str = "broll"):
    """Match b-roll (stock images) or clips (library footage) to a project's scenes.

    Reuses the CLI's async match helpers in-process; writes matched_asset/clip
    fields back into scene_plan.json.
    """
    from nolan.cli_legacy import _match_broll, _match_clips

    plan_path = _scene_plan_path(project_name)
    if not plan_path.exists():
        raise RuntimeError(f"No scene_plan.json for project '{project_name}'. Run process first.")

    job.set_progress(0.1, f"Matching {kind} for '{project_name}' …")
    # Matching does blocking network I/O (search, download, sync scorer). Run the
    # whole flow in a worker thread (its own event loop) so the hub stays responsive.
    if kind == "clips":
        coro_factory = lambda: _match_clips(
            config, str(plan_path), candidates=max_results, min_similarity=0.0,
            project=None, skip_existing=True, dry_run=False,
            search_level="segment", concurrency=8)
    else:
        coro_factory = lambda: _match_broll(
            config, str(plan_path), output_dir=None, source=source,
            max_results=max_results, score=True, vision=config.vision.provider,
            skip_existing=True, dry_run=False)
    await asyncio.to_thread(lambda: asyncio.run(coro_factory()))

    # Summarize coverage from the updated plan.
    from nolan.scenes import ScenePlan
    plan = ScenePlan.load(str(plan_path))
    scenes = plan.all_scenes
    matched = sum(1 for s in scenes
                  if getattr(s, "matched_asset", None) or getattr(s, "matched_clip", None)
                  or getattr(s, "rendered_clip", None))
    job.set_progress(1.0, f"Matched {matched}/{len(scenes)} scenes")
    return {"project": project_name, "scenes": len(scenes), "matched": matched}


def _scene_seconds(scene, default: float = 5.0) -> float:
    """Best-effort scene duration in seconds (handles float/string/timed fields)."""
    s, e = getattr(scene, "start_seconds", None), getattr(scene, "end_seconds", None)
    if s is not None and e is not None and e > s:
        return float(e - s)
    d = getattr(scene, "duration", None)
    if isinstance(d, (int, float)):
        return float(d)
    if isinstance(d, str):
        import re as _re
        m = _re.match(r"(\d+\.?\d*)", d)
        if m:
            return float(m.group(1))
    return default


async def materialize_clips(job, *, config, project_name: str, max_clip_seconds: float = 10.0):
    """Fetch + trim matched video clips into local files assemble can use.

    For every scene whose `matched_clip` is a video (external archival URL or a
    local library clip) and that has no `rendered_clip` yet, extract a segment of
    the scene's duration via ffmpeg and set `rendered_clip` (the highest-priority
    asset in assemble). External archival programs are seeked via HTTP range
    (ffmpeg -ss before -i) — the whole file is never downloaded.
    """
    import subprocess
    from nolan.scenes import ScenePlan

    proj = Path("projects") / project_name
    plan_path = proj / "scene_plan.json"
    if not plan_path.exists():
        raise RuntimeError(f"No scene_plan.json for '{project_name}'.")
    out_dir = proj / "assets" / "broll"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _work():
        plan = ScenePlan.load(str(plan_path))
        targets = [s for s in plan.all_scenes
                   if getattr(s, "matched_clip", None) and not getattr(s, "rendered_clip", None)
                   and isinstance(s.matched_clip, dict)]
        done, failed = 0, 0
        for i, scene in enumerate(targets):
            mc = scene.matched_clip
            dur = max(2.0, min(_scene_seconds(scene), max_clip_seconds))
            external_url = mc.get("external_url")
            video_path = mc.get("video_path") or mc.get("video")
            if external_url:
                src = external_url
                clip_len = mc.get("duration") or 0
                offset = min(0.1 * clip_len, 60.0) if clip_len else 5.0
            elif video_path and Path(video_path).exists():
                src = str(video_path)
                offset = float(mc.get("start") or mc.get("start_seconds") or 0.0)
            else:
                continue
            job.set_progress(0.05 + 0.9 * i / max(1, len(targets)),
                             f"clip {i+1}/{len(targets)} · {done} done")
            dest = out_dir / f"{scene.id}.mp4"
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", str(offset), "-i", src, "-t", str(dur),
                "-an",                                  # drop audio (narration is separate)
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                str(dest),
            ]
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=180)
                if r.returncode == 0 and dest.exists() and dest.stat().st_size > 1000:
                    scene.rendered_clip = str(dest.relative_to(proj)).replace("\\", "/")
                    done += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        plan.save(str(plan_path))
        return {"project": project_name, "candidates": len(targets), "materialized": done, "failed": failed}

    result = await asyncio.to_thread(_work)
    job.set_progress(1.0, f"Materialized {result['materialized']}/{result['candidates']} clips")
    return result


async def extract_assets(job, *, url: str, limit: Optional[int] = None,
                         download: bool = True, dest: Optional[str] = None,
                         save_to_library: bool = False, scope: str = "global",
                         project: Optional[str] = None) -> dict:
    """Extract high-def image assets from a page URL via the parser registry.

    Picks the matching extractor (Gutenberg / Wikimedia / Met / generic),
    optionally downloads the full-res files into ``dest`` (or
    ``.scratch/extracted/<host>``) and writes a manifest. With
    ``save_to_library`` the assets are also ingested into the picture library
    (deduped, CLIP-embedded, tagged with the page URL).
    """
    import json
    from urllib.parse import urlparse

    from nolan.extractors import download_assets, extract_from_url, get_extractor

    ex = get_extractor(url)
    job.set_progress(0.1, f"Extracting via '{ex.name}'...")
    results = await asyncio.to_thread(extract_from_url, url, limit=limit)
    job.set_progress(0.4, f"Found {len(results)} asset(s)")

    records = [r.to_dict() for r in results]
    out_dir = None
    if download and results:
        host = urlparse(url).netloc.replace(":", "_") or "page"
        out_dir = Path(dest) if dest else Path(".scratch/extracted") / host
        job.set_progress(0.5, f"Downloading {len(results)} asset(s) -> {out_dir}")
        records = await download_assets(results, out_dir)
        (out_dir / "manifest.json").write_text(
            json.dumps({"url": url, "extractor": ex.name, "count": len(records),
                        "results": records}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    saved = 0
    if save_to_library and results:
        job.set_progress(0.7, f"Saving {len(results)} to {scope} picture library...")
        saved = await asyncio.to_thread(
            _ingest_results_to_library, results, records, scope, project, url)

    ok = sum(1 for r in records if r.get("local_path")) if download else 0
    msg = f"{len(records)} asset(s)" + (f", {ok} downloaded" if download else "")
    if save_to_library:
        msg += f", {saved} in library"
    job.set_progress(1.0, f"Done - {msg}")
    return {"url": url, "extractor": ex.name, "count": len(records),
            "downloaded": ok, "saved_to_library": saved,
            "out_dir": str(out_dir) if out_dir else None, "results": records}


def _ingest_results_to_library(results, records, scope, project, query_url) -> int:
    """Ingest extractor results into the picture library (one shared embedder).

    Uses an already-downloaded local file when available (no re-fetch), else the
    remote URL. Returns the number of new assets added.
    """
    from nolan.imagelib import ClipEmbedder, ImageLibrary

    lib = ImageLibrary(scope=scope, project=project, embedder=ClipEmbedder())
    local_by_url = {r.get("url"): r.get("local_path") for r in records}
    added = 0
    for r in results:
        try:
            local = local_by_url.get(r.url)
            if local and Path(local).exists():
                _, created = lib.add_file(
                    local, url=r.url, source=r.source, source_url=r.source_url,
                    license=r.license, title=r.title, width=r.width, height=r.height,
                    query=query_url)
            else:
                _, created = lib.add_result(r, query=query_url)
            added += int(created)
        except Exception:
            continue
    return added


async def render_lottie_preview(job, *, template_id: str, overrides: Optional[dict] = None,
                                width: int = 1920, height: int = 1080, fps: int = 30,
                                duration: Optional[float] = None,
                                service_url: Optional[str] = None) -> dict:
    """Render a catalog Lottie template (optionally customized) to MP4 for the showcase.

    Writes to `_library/lottie_previews/<id>.mp4` (served by the hub) and returns the
    filename. Requires the render-service.
    """
    import re as _re

    from nolan.lottie_render import DEFAULT_SERVICE, prepare_lottie, render_lottie_to_mp4
    from nolan.template_catalog import TemplateCatalog

    cat = TemplateCatalog()
    t = cat.get(template_id)
    if not t:
        raise RuntimeError(f"unknown lottie template: {template_id}")
    src = cat.get_full_path(t)
    dur = float(duration or t.duration_seconds or 5.0)

    out_dir = Path("_library") / "lottie_previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    overrides = overrides or {}
    safe = _re.sub(r"[^A-Za-z0-9._-]", "_", template_id)
    job.set_progress(0.2, f"Rendering '{t.name}'…")
    prepared = out_dir / f"{safe}.prepared.json"
    if overrides.get("fields"):
        # schema field-name → value (the showcase editor) -> render_template
        from nolan.lottie import render_template
        try:
            render_template(src, prepared, **overrides["fields"])
            src = prepared
        except Exception:
            pass  # template has no schema / invalid field -> render as-is
    elif overrides.get("text") or overrides.get("colors"):
        prepare_lottie(src, prepared, {**overrides, "duration": dur, "fps": fps})
        src = prepared

    name = f"{safe}.mp4"
    await asyncio.to_thread(
        render_lottie_to_mp4, src, out_dir / name, service_url=service_url or DEFAULT_SERVICE,
        width=width, height=height, fps=fps, duration=dur)
    job.set_progress(1.0, "Rendered")
    return {"file": name, "name": t.name}


async def comfyui_status(config) -> dict:
    """ComfyUI connection + installed checkpoints + queue (for the ComfyUI page)."""
    import httpx as _httpx
    base = f"http://{config.comfyui.host}:{config.comfyui.port}"
    out = {"connected": False, "url": base, "checkpoints": [], "queue_running": 0, "queue_pending": 0}
    try:
        async with _httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{base}/system_stats")
            out["connected"] = r.status_code == 200
            if out["connected"]:
                oi = (await c.get(f"{base}/object_info/CheckpointLoaderSimple")).json()
                out["checkpoints"] = oi["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
                q = (await c.get(f"{base}/queue")).json()
                out["queue_running"] = len(q.get("queue_running", []))
                out["queue_pending"] = len(q.get("queue_pending", []))
    except Exception as e:
        out["error"] = str(e)
    return out


async def comfyui_sample(job, *, config, workflow_name: Optional[str], prompt: str,
                         width: Optional[int] = None, height: Optional[int] = None,
                         steps: Optional[int] = None, style: Optional[str] = None):
    """Generate a single sample image from a registered workflow → scratch preview."""
    from nolan.workflow_registry import get_registry
    reg = get_registry()
    overrides = {k: v for k, v in (("width", width), ("height", height), ("steps", steps), ("style", style)) if v}
    client, entry = reg.build_client(workflow_name, config, **overrides)
    job.set_progress(0.1, f"Generating sample with '{entry.name if entry else workflow_name}'…")
    if not await client.check_connection():
        raise RuntimeError(f"ComfyUI not reachable at {config.comfyui.host}:{config.comfyui.port}.")
    samples = Path("samples")
    samples.mkdir(parents=True, exist_ok=True)
    import uuid
    fname = f"sample_{(entry.name if entry else 'wf')}_{uuid.uuid4().hex[:8]}.png"
    await client.generate(prompt, samples / fname, timeout=300.0)
    job.set_progress(1.0, "Sample ready")
    return {"workflow": entry.name if entry else workflow_name, "preview": fname,
            "prompt": prompt}


async def _distill_style_suffix(config, style_guide_path: Path) -> str:
    """Distill the project's style_guide.md into a short image-prompt style suffix."""
    if not style_guide_path.exists():
        return ""
    from nolan.llm import create_text_llm
    guide = style_guide_path.read_text(encoding="utf-8")[:4000]
    try:
        out = await create_text_llm(config).generate(
            "From this video style guide, output ONE concise comma-separated list of visual style "
            "descriptors (look, color grade, lighting, film treatment) to append to EVERY "
            "image-generation prompt so all shots share a cohesive look. Output ONLY the descriptors "
            "(max ~18 words), no preamble.\n\n" + guide)
        return " ".join(out.strip().strip('"').split())[:200]
    except Exception:
        return ""


async def generate_assets(job, *, config, project_name: str, workflow_name: Optional[str] = None,
                          style_cohesion: bool = True):
    """Generate AI imagery (ComfyUI) for every 'generated' scene, via a registered workflow.

    When style_cohesion and a style_guide.md exists, a distilled style suffix is appended
    to every prompt so all generated images share a consistent look.
    """
    from nolan.cli_legacy import _generate_images
    from nolan.comfyui import ComfyUIClient
    from nolan.scenes import ScenePlan
    from nolan.workflow_registry import get_registry

    proj = Path("projects") / project_name
    if not (proj / "scene_plan.json").exists():
        raise RuntimeError(f"No scene_plan.json for '{project_name}'.")

    job.set_progress(0.05, "Checking ComfyUI connection…")
    if not await ComfyUIClient(host=config.comfyui.host, port=config.comfyui.port).check_connection():
        raise RuntimeError(
            f"ComfyUI not reachable at {config.comfyui.host}:{config.comfyui.port}. Start ComfyUI and retry."
        )

    style_suffix = ""
    if style_cohesion:
        style_suffix = await _distill_style_suffix(config, proj / "style_guide.md")
        if style_suffix:
            job.log(f"Style cohesion suffix: {style_suffix}")

    # Resolve the workflow from the registry → pass its file/prompt-node/resolution.
    reg = get_registry()
    entry = reg.get(workflow_name) if workflow_name else reg.get(reg.default_name())
    wf_path = None
    if entry:
        if entry.file:
            wf_path = Path(entry.file)
        config.comfyui.width, config.comfyui.height, config.comfyui.steps = entry.width, entry.height, entry.steps

    plan = ScenePlan.load(str(proj / "scene_plan.json"))
    n_gen = sum(1 for s in plan.all_scenes if s.visual_type in ("generated", "generated-image"))
    job.set_progress(0.1, f"Generating {n_gen} scenes via ComfyUI ({entry.name if entry else 'default'})…")
    await _generate_images(config, proj, None, workflow_path=wf_path,
                           prompt_node=(entry.prompt_node if entry else None),
                           prompt_suffix=style_suffix)

    plan = ScenePlan.load(str(proj / "scene_plan.json"))
    done = sum(1 for s in plan.all_scenes if getattr(s, "generated_asset", None))
    job.set_progress(1.0, f"Generated {done}/{n_gen} scenes")
    return {"project": project_name, "generated_scenes": n_gen, "generated": done,
            "workflow": entry.name if entry else "default"}


async def run_cli(job, *, args: list, label: str = "cli"):
    """Run a NOLAN CLI command as a subprocess, streaming stdout to the job.

    Reuses the proven CLI for commands not factored into importable helpers
    (render-clips, assemble). Invokes the same interpreter running the hub.
    """
    import sys

    cmd = [sys.executable, "-c", "from nolan.cli import main; main()"] + [str(a) for a in args]
    job.set_progress(0.05, f"$ nolan {' '.join(str(a) for a in args)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    line_count = 0
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip()
        if line:
            job.log(line)
            line_count += 1
            # Indeterminate progress that creeps toward (not past) completion.
            job.set_progress(min(0.95, 0.05 + line_count * 0.01), line[:80])
    rc = await proc.wait()
    if rc != 0:
        raise RuntimeError(f"{label} exited with code {rc}")
    job.set_progress(1.0, f"{label} complete")
    return {"returncode": rc, "lines": line_count}


async def _run_ffmpeg(job, cmd: list, *, label: str) -> None:
    """Run an ffmpeg command async, surfacing stderr to the job on failure."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = (stderr or b"").decode(errors="replace").strip()
        raise RuntimeError(f"{label} failed: {err or 'unknown ffmpeg error'}")


async def materialize_clip(job, *, db_path: Path, clip_id: str, form: str = "file",
                           num_frames: int = 6, force: bool = False):
    """Materialize a saved clip into the form a downstream consumer needs.

    Forms:
        none   - no extraction; return the matched_clip pointer (essay pipeline).
        file   - extract a standalone .mp4 (e.g. for ComfyUI).
        frames - extract evenly-spaced JPG frames (e.g. for Claude to inspect).

    Outputs are cached under ``projects/_clips/<clip_id>/`` and reused unless
    ``force`` is set. The saved-clip record stays the source of truth.
    """
    from nolan.indexer import VideoIndex

    index = VideoIndex(db_path)
    clip = index.get_saved_clip(clip_id)
    if not clip:
        raise RuntimeError(f"saved clip not found: {clip_id}")

    video_path = clip["source_video_path"]
    start = float(clip["clip_start"])
    end = float(clip["clip_end"])
    duration = end - start
    if duration <= 0:
        raise RuntimeError(f"clip {clip_id} has non-positive duration")
    if not Path(video_path).exists():
        raise RuntimeError(f"source video missing: {video_path}")

    matched_clip = {
        "video_path": video_path,
        "clip_start": start,
        "clip_end": end,
        "label": clip.get("label"),
        "source": "manual-cut",
    }

    if form == "none":
        job.set_progress(1.0, "Pointer ready (no extraction needed)")
        return {"clip_id": clip_id, "form": "none", "matched_clip": matched_clip}

    out_base = Path("projects") / "_clips" / clip_id

    if form == "file":
        out_path = out_base / "clip.mp4"
        if out_path.exists() and not force:
            job.set_progress(1.0, f"Cached: {out_path}")
            return {"clip_id": clip_id, "form": "file", "path": str(out_path),
                    "matched_clip": matched_clip, "cached": True}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        job.set_progress(0.2, f"Extracting clip → {out_path.name}")
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(start), "-i", str(video_path),
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(out_path),
        ]
        await _run_ffmpeg(job, cmd, label="clip extract")
        job.set_progress(1.0, f"Materialized {out_path}")
        return {"clip_id": clip_id, "form": "file", "path": str(out_path),
                "matched_clip": matched_clip, "cached": False}

    if form == "frames":
        frames_dir = out_base / "frames"
        existing = sorted(frames_dir.glob("frame_*.jpg")) if frames_dir.exists() else []
        if existing and not force:
            job.set_progress(1.0, f"Cached: {len(existing)} frames")
            return {"clip_id": clip_id, "form": "frames", "dir": str(frames_dir),
                    "frames": [str(p) for p in existing], "matched_clip": matched_clip,
                    "cached": True}
        frames_dir.mkdir(parents=True, exist_ok=True)
        for p in existing:
            p.unlink()
        n = max(1, int(num_frames))
        fps = n / duration if duration > 0 else 1.0
        job.set_progress(0.2, f"Sampling ~{n} frames")
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(start), "-i", str(video_path),
            "-t", f"{duration:.3f}",
            "-vf", f"fps={fps:.6f}",
            "-q:v", "2",
            str(frames_dir / "frame_%04d.jpg"),
        ]
        await _run_ffmpeg(job, cmd, label="frame extract")
        frames = sorted(str(p) for p in frames_dir.glob("frame_*.jpg"))
        job.set_progress(1.0, f"Extracted {len(frames)} frames")
        return {"clip_id": clip_id, "form": "frames", "dir": str(frames_dir),
                "frames": frames, "matched_clip": matched_clip, "cached": False}

    raise RuntimeError(f"unknown materialize form: {form!r} (expected none|file|frames)")


def list_tmux_sessions() -> list:
    """List available tmux session names (empty if no server / not available).

    Works on Linux (plain ``tmux``) or Windows (``wsl.exe tmux``)."""
    import shutil
    import subprocess

    base = ["tmux"] if shutil.which("tmux") else ["wsl.exe", "tmux"]
    try:
        # Parse `tmux ls` (each line "name: N windows …"). We avoid
        # `-F '#{session_name}'` because wsl.exe runs the command via a shell
        # that treats '#' as a comment, dropping the format argument.
        out = subprocess.run(base + ["ls"], capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            return []
        names = []
        for line in out.stdout.splitlines():
            line = line.strip()
            if ":" in line:
                names.append(line.split(":", 1)[0].strip())
        return names
    except Exception:
        return []


def _dispatch_to_tmux(session: str, message: str) -> None:
    """Send a one-line prompt to a Claude Code agent in a tmux session.

    Works whether the hub runs on Linux (plain ``tmux``) or Windows (``wsl.exe
    tmux`` reaching the WSL tmux server). Sends the text literally, waits briefly
    so the TUI registers it, then sends Enter to submit.
    """
    import shutil
    import subprocess
    import time

    base = ["tmux"] if shutil.which("tmux") else ["wsl.exe", "tmux"]
    subprocess.run(base + ["send-keys", "-t", session, "-l", message],
                   check=True, capture_output=True, text=True)
    time.sleep(0.4)
    subprocess.run(base + ["send-keys", "-t", session, "Enter"],
                   check=True, capture_output=True, text=True)


def _motion_catalog_md() -> str:
    """Capability list for the analyze-effect agent, generated from the motion
    registry so it always reflects BOTH backends (Python renderers + Remotion)."""
    try:
        from nolan.motion import REGISTRY
    except Exception:
        return ("   - Scene templates: `src/nolan/renderer/scenes/`\n"
                "   - Remotion compositions: `render-service/remotion-lib/`")
    by_backend: dict = {}
    for e in REGISTRY:
        by_backend.setdefault(e.backend, []).append(e)
    blocks = []
    titles = {
        "remotion": "Remotion compositions (`render-service/remotion-lib/`, ids in `registry.json`)",
        "python": "Python renderers (`src/nolan/renderer/scenes/`)",
    }
    for backend in ("remotion", "python"):
        effects = by_backend.get(backend, [])
        if not effects:
            continue
        lines = "\n".join(f"     - `{e.id}` ({e.target}) — {e.purpose}" for e in effects)
        blocks.append(f"   - **{titles[backend]}**:\n{lines}")
    return "\n".join(blocks)


def _effect_task_markdown(clip: dict, frames_posix: list, file_posix: str,
                          analysis_posix: str) -> str:
    """Build the task brief handed to the nolan2 agent."""
    frame_lines = "\n".join(f"  - {f}" for f in frames_posix)
    motion_catalog = _motion_catalog_md()
    base = analysis_posix.rsplit("/", 1)[0]           # projects/_clips/<clip_id>
    clip_id = base.rsplit("/", 1)[-1]
    return f"""# NOLAN effect-analysis task

A user saved a clip from a source video and wants to know **what visual / motion
effect it uses** and **whether NOLAN can already reproduce it**.

## The clip
- Source video: `{clip.get('source_video_path')}`
- In/out: {clip.get('clip_start')}s → {clip.get('clip_end')}s ({clip.get('duration')}s)
- Label: {clip.get('label') or '(none)'}
- Extracted clip file (watch motion via ffmpeg/your tools): `{file_posix}`
- Sample frames:
{frame_lines}

## What to do (in order)
1. **Inspect** the frames (and the clip file if you need finer motion detail —
   e.g. `ffmpeg -i {file_posix} -vf fps=10 ...`). Describe the effect precisely:
   camera move, transition, text/graphic animation, color/filter, etc.
2. **Dedup against the existing motion library FIRST.** NOLAN can recreate effects on
   **two backends** — pick whichever fits the effect. Check these registered effects
   (the `nolan.motion` registry, `src/nolan/motion/registry.py`) before proposing anything new:
{motion_catalog}
   - Effect primitives (Python): `src/nolan/renderer/effects.py` (FadeIn/Out, Slide*,
     MoveTo, ScaleIn/Out, Pulse, Shake, Glitch, BlurIn/FocusPull, Glow*, Shadow*,
     Letterbox, Scanlines, ColorTint, VHSEffect, Reveal, RotateIn/Spin, …)
   - Remotion is best for kinetic typography, animated charts/SVG, transitions, glossy
     CSS; Python is best for fast simple cards. State clearly: **already covered**
     (name the registry `effect` id + backend) or **new**.
3. If **new** and replicable on Remotion, write a **PROPOSAL** — do NOT edit
   `registry.py` or `Root.tsx` directly (the agent contract: proposals pass a
   deterministic gate before becoming canonical). Write BOTH files:
   - `{base}/proposal/effect.tsx` — the composition. `export default` the
     component; pure function of `useCurrentFrame()` (no Math.random /
     Date.now); accept `durationInFrames` + your content props; use theme
     tokens (`var(--accent)` etc.) like the blocks in
     `render-service/remotion-lib/src/blocks/library/`.
   - `{base}/proposal/entry.json` — the registry entry AS DATA:
     `{{"id": "<kebab-case>", "backend": "remotion", "category": "...",
     "purpose": "<one line>", "target": "<PascalCaseCompId>",
     "content": [{{"name","type","doc","default","required"}}...],
     "style": [], "shared": ["theme"], "duration_default": 4.0,
     "when_to_use": "<the craft guidance: what narration moment this effect
     serves, and when a neighbor beats it — module contract>",
     "sample_props": {{<props that render a REPRESENTATIVE frame>}},
     "provenance": {{"clip_id": "{clip_id}", "agent": "<your session>",
     "date": "<today>"}}}}`
   The human gates + accepts it from the Clips page: the gate renders your
   `sample_props` through a harness and checks blank frames / text escaping
   the frame — make `sample_props` show the effect at its best.
   Python-backend ideas: describe the plan in the analysis only (python
   renderers stay hand-reviewed code).

## Output
Write findings to `{analysis_posix}` as markdown with sections: **Effect**,
**Dedup result** (registry id + backend if covered), **Replicable?**
(chosen backend), **Plan** — and, if new+Remotion, the proposal files above.
"""


async def analyze_effect(job, *, db_path: Path, clip_id: str, num_frames: int = 10,
                         session: str = "nolan2"):
    """Materialize a clip's frames+file and dispatch an analysis task to a tmux
    Claude agent (``session``, default nolan2).

    The agent identifies the effect, dedups it against the motion library, and
    assesses replicability, writing findings to
    ``projects/_clips/<clip_id>/effect_analysis.md``.
    """
    from nolan.indexer import VideoIndex

    index = VideoIndex(db_path)
    clip = index.get_saved_clip(clip_id)
    if not clip:
        raise RuntimeError(f"saved clip not found: {clip_id}")

    # 1. frames (quick visual) + file (for finer motion analysis)
    job.set_progress(0.1, "Extracting frames…")
    frames_res = await materialize_clip(job, db_path=db_path, clip_id=clip_id,
                                        form="frames", num_frames=num_frames)
    job.set_progress(0.55, "Extracting clip file…")
    file_res = await materialize_clip(job, db_path=db_path, clip_id=clip_id, form="file")

    # 2. POSIX paths relative to repo root (the nolan2 agent runs under WSL)
    def _posix(p):
        return Path(p).as_posix()
    base = f"projects/_clips/{clip_id}"
    frames_posix = [_posix(f) for f in frames_res.get("frames", [])]
    file_posix = _posix(file_res.get("path", ""))
    analysis_posix = f"{base}/effect_analysis.md"
    task_path = Path("projects") / "_clips" / clip_id / "effect_task.md"
    task_posix = f"{base}/effect_task.md"

    # 3. write the task brief
    job.set_progress(0.8, "Writing task brief…")
    task_path.write_text(_effect_task_markdown(clip, frames_posix, file_posix, analysis_posix),
                         encoding="utf-8")

    # 4. dispatch to the chosen agent session
    job.set_progress(0.9, f"Dispatching to {session}…")
    message = (f"New NOLAN effect-analysis task — please read and complete "
               f"{task_posix} now, then write findings to {analysis_posix}.")
    dispatched, dispatch_error = True, None
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, _dispatch_to_tmux, session, message)
        job.set_progress(1.0, f"Dispatched to {session}")
    except Exception as e:  # tmux/wsl not available, session missing, etc.
        dispatched, dispatch_error = False, str(e)
        job.set_progress(1.0, f"Frames ready; dispatch failed: {e}")

    return {
        "clip_id": clip_id,
        "session": session,
        "frame_count": len(frames_posix),
        "frames": frames_posix,
        "file": file_posix,
        "task_file": task_posix,
        "analysis_file": analysis_posix,
        "dispatched": dispatched,
        "dispatch_error": dispatch_error,
    }


# ==================== Script-style corpora + style guides ====================

_EXTRACT_PROMPT = """You are a professional script analyst. Analyze the following \
video transcript and extract its SCRIPT-WRITING / STORYTELLING characteristics \
(ignore on-screen visuals — you only have the words).

Return ONLY a JSON object with these keys (values are short strings or string arrays):
- "hook": how the opening grabs attention (first ~30s technique)
- "narrative_structure": the overall arc / how the piece is organized
- "pacing": rhythm, momentum, where it speeds up/slows down
- "sentence_style": sentence length, syntax, spoken-word cadence
- "rhetorical_devices": list of devices used (e.g. repetition, rhetorical questions, contrast, analogy)
- "diction_tone": vocabulary level, register, tone, persona
- "transitions": how it moves between ideas/segments
- "audience_engagement": direct address, callbacks, suspense, CTAs
- "opening": verbatim or paraphrased opening pattern
- "closing": how it ends / sign-off pattern
- "exemplar_lines": 3-6 short verbatim quotes that typify the style
- "notable_techniques": anything else distinctive

Title: {title}

Transcript:
{text}
"""


def _parse_json_object(raw: str) -> dict:
    """Parse an LLM JSON object response, tolerant of surrounding prose/fences."""
    import json as _json
    import re
    raw = (raw or "").strip()
    try:
        return _json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return _json.loads(m.group(0))
        except Exception:
            pass
    return {"_unparsed": raw[:2000]}


_EXTRACT_TRIM_MARKER = "\n\n[…transcript trimmed for length…]\n\n"


def _sample_for_extraction(text: str, max_chars: int) -> str:
    """Cap ``text`` to ``max_chars`` for the extraction LLM, keeping BOTH ends.

    Style analysis needs the opening *and* the closing (hook, sign-off, overall
    arc), so a naive head slice (``text[:max_chars]``) silently discards the
    ending — exactly the part the ``closing``/``narrative_structure`` fields
    depend on. When the text overflows, keep ~60% from the head and ~40% from
    the tail with an elision marker between them. Output length never exceeds
    ``max_chars``.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    budget = max_chars - len(_EXTRACT_TRIM_MARKER)
    if budget <= 0:  # cap smaller than the marker itself — degrade to head slice
        return text[:max_chars]
    head = (budget * 3) // 5
    tail = budget - head
    return text[:head] + _EXTRACT_TRIM_MARKER + text[-tail:]


def _is_rate_limit_error(msg: str) -> bool:
    """True if an error looks like a YouTube rate-limit (HTTP 429)."""
    m = (msg or "").lower()
    return "429" in m or "too many requests" in m


async def fetch_transcripts(job, *, store_root, style_id: str, urls: list,
                            max_chars: int = 0, request_delay: float = 2.0,
                            max_retries: int = 3):
    """Fetch original-language transcripts for YouTube URLs into a style corpus.

    Dedups by video_id (both before fetching, when the id is parseable from the
    URL, and after, against the resolved id) so repeat fetches skip known videos.

    Politeness/robustness:
    - waits ``request_delay`` seconds between hits to avoid tripping HTTP 429;
    - retries a rate-limited URL up to ``max_retries`` times with exponential
      backoff. Non-rate-limit errors (no transcript, private, etc.) fail fast.
    """
    from nolan.script_style import ScriptStyleStore
    from nolan.youtube import YouTubeClient, extract_video_id
    from pathlib import Path as _Path

    store = ScriptStyleStore(_Path(store_root))
    if not store.exists(style_id):
        raise RuntimeError(f"script style not found: {style_id}")

    client = YouTubeClient(output_dir=_Path("script_styles") / style_id / "corpus")
    added, skipped, errors = [], [], []
    total = len(urls)
    loop = asyncio.get_event_loop()

    fetched_any = False  # whether we've made a real network hit yet (for pacing)
    for i, url in enumerate(urls):
        url = (url or "").strip()
        if not url:
            continue
        job.set_progress(0.05 + 0.9 * (i / total if total else 0),
                         f"[{i+1}/{total}] {url}")
        guess = extract_video_id(url)
        if guess and store.has_video(style_id, guess):
            skipped.append({"url": url, "video_id": guess, "reason": "already in corpus"})
            continue

        # Pause between actual network hits to stay under the rate limit.
        if fetched_any and request_delay > 0:
            await asyncio.sleep(request_delay)

        # Fetch with exponential backoff on rate-limit (429); fail fast otherwise.
        res, last_err = None, None
        for attempt in range(max_retries + 1):
            fetched_any = True
            try:
                res = await loop.run_in_executor(None, client.fetch_transcript, url)
                break
            except Exception as e:
                last_err = str(e)
                if _is_rate_limit_error(last_err) and attempt < max_retries:
                    wait = 5 * (3 ** attempt)  # 5s, 15s, 45s, …
                    job.set_progress(0.05 + 0.9 * (i / total if total else 0),
                                     f"[{i+1}/{total}] 429 — backing off {wait}s "
                                     f"(retry {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait)
                    continue
                break
        if res is None:
            errors.append({"url": url, "error": last_err})
            job.log(f"  ! {last_err}")
            continue
        if store.has_video(style_id, res.get("video_id")):
            skipped.append({"url": url, "video_id": res.get("video_id"),
                            "reason": "already in corpus"})
            continue
        text = res.get("text") or ""
        if max_chars and len(text) > max_chars:
            text = text[:max_chars]
        entry = store.add_source(
            style_id, text=text, title=res.get("title") or res.get("video_id") or url,
            source_type="youtube", video_id=res.get("video_id"), url=url,
            channel=res.get("channel"), published_at=res.get("upload_date"),
            language=res.get("language"),
        )
        added.append({"slug": entry["slug"], "title": entry["title"],
                      "word_count": entry["word_count"]})
        job.log(f"  + {entry['title']} ({entry['word_count']} words)")

    job.set_progress(1.0, f"Added {len(added)}, skipped {len(skipped)}, errors {len(errors)}")
    return {"style_id": style_id, "added": added, "skipped": skipped, "errors": errors,
            "added_count": len(added), "skipped_count": len(skipped),
            "error_count": len(errors)}


# Audio helpers + the voiceover core live in nolan.voice_pipeline (shared with
# the Director's `voiceover` step); re-imported here for the ops below.
from nolan.voice_pipeline import (  # noqa: E402
    _atempo, _ffmpeg_exe, _free_comfyui_vram, _tempo_on, _wav_duration,
)


def detect_voice_wpm(wav_path, ref_text=None, baseline: int = 150) -> dict:
    """Measure a reference voice's speaking rate (words/min) + suggest a Pace.

    Uses ref_text if given, else transcribes the clip with Whisper. ``baseline``
    is OmniVoice's approximate default output rate; suggested_pace = wpm/baseline
    (clamped 0.5–1.6) so the output matches the reference's pace.
    """
    from pathlib import Path as _P
    p = _P(wav_path)
    if not p.exists():
        return {"ok": False, "reason": "sample not found"}
    dur = _wav_duration(p)
    if dur <= 0:
        return {"ok": False, "reason": "could not read audio"}
    text = (ref_text or "").strip()
    source = "ref_text"
    if not text:
        try:
            from nolan.whisper import WhisperTranscriber, WhisperConfig, WHISPER_AVAILABLE
            if not WHISPER_AVAILABLE:
                return {"ok": False, "reason": "no transcript & Whisper not installed",
                        "duration": round(dur, 1)}
            # CPU: the nolan env has CPU-only torch (no cublas); a few-second clip
            # transcribes fast on CPU anyway.
            segs = WhisperTranscriber(WhisperConfig(
                model_size="base", device="cpu", compute_type="int8")).transcribe(p)
            text = " ".join(s.text for s in segs).strip()
            source = "whisper"
        except Exception as e:
            return {"ok": False, "reason": f"transcription failed: {e}", "duration": round(dur, 1)}
    words = len(text.split())
    if words == 0:
        return {"ok": False, "reason": "no speech detected", "duration": round(dur, 1)}
    wpm = words / dur * 60
    suggested = max(0.5, min(1.6, round((wpm / baseline) * 20) / 20))  # clamp + round to 0.05
    return {"ok": True, "wpm": round(wpm), "words": words, "duration": round(dur, 1),
            "output_wpm": baseline, "suggested_pace": suggested, "source": source}


async def tts_synthesize(job, *, config, text: str, ref_audio: str = None,
                         ref_text: str = None, instruct: str = None,
                         num_step: int = None, speed: float = None, language_id: str = None,
                         tempo: float = 1.0):
    """Synthesize a single utterance (TTS Studio) and write a wav under voices/_tts_out/.

    Runs under the shared GPU lock so it never overlaps ComfyUI.
    """
    from pathlib import Path as _Path
    from nolan.tts import create_tts_provider
    from nolan.webui.jobs import get_gpu_lock

    if not config.tts.enabled:
        raise RuntimeError("TTS is disabled — set tts.enabled: true in nolan.yaml "
                           "(see docs/OMNIVOICE_SETUP.md)")
    text = (text or "").strip()
    if not text:
        raise RuntimeError("no text to synthesize")
    from nolan.tts_normalize import normalize_for_speech
    text = normalize_for_speech(text)   # A1: speak numbers/currency/percent/years
    if not ref_audio and not instruct:
        job.log("No voice reference or instruct given — using OmniVoice's default voice")

    out_dir = _Path("voices") / "_tts_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{job.id}.wav"

    provider = create_tts_provider(config.tts)
    loop = asyncio.get_event_loop()
    extra = {}
    if instruct:
        extra["instruct"] = instruct
    if speed is not None:
        extra["speed"] = speed
    if language_id:
        extra["language_id"] = language_id

    job.set_progress(0.1, "Waiting for GPU…")
    async with get_gpu_lock():
        if config.tts.omnivoice.free_comfyui_vram:
            job.set_progress(0.15, "Freeing ComfyUI VRAM…")
            await _free_comfyui_vram(config)
        job.set_progress(0.3, "Synthesizing…")

        def _run():
            return provider.synthesize(text, out_path, ref_audio=ref_audio,
                                       ref_text=ref_text, num_step=num_step, **extra)
        wav = await loop.run_in_executor(None, _run)

    if _tempo_on(tempo):
        job.set_progress(0.95, f"Adjusting pace (×{tempo})…")
        tmp = out_path.with_name(out_path.stem + "_t.wav")
        await _atempo(wav, tmp, tempo)
        _Path(tmp).replace(out_path)
        wav = out_path

    job.set_progress(1.0, "Done")
    return {"output": str(wav), "token": job.id}


async def generate_voiceover(job, *, config, project: str = None, script_project: str = None,
                             mode: str = "full", voice_id: str = None, store_root: str = "voices",
                             ref_audio: str = None, ref_text: str = None, instruct: str = None,
                             num_step: int = None, speed: float = None, language_id: str = None,
                             tempo: float = 1.0):
    """Generate a project's voiceover with local TTS.

    Thin job adapter over `nolan.voice_pipeline.synthesize_voiceover` — the
    SAME core the Director's `voiceover` step runs, so webUI and orchestrator
    cannot drift. See that module for the full contract (sources, modes, GPU
    lock, beat anchors in _work/sec_NNNN.wav).
    """
    from nolan.voice_pipeline import synthesize_voiceover

    return await synthesize_voiceover(
        config=config, project=project, script_project=script_project,
        mode=mode, voice_id=voice_id, store_root=store_root,
        ref_audio=ref_audio, ref_text=ref_text, instruct=instruct,
        num_step=num_step, speed=speed, language_id=language_id, tempo=tempo,
        log=job.log, progress=job.set_progress)


async def generate_voiceover_retake(job, *, config, script_project: str, index: int,
                                    voice_id: str = None, ref_audio: str = None,
                                    ref_text: str = None, text: str = None,
                                    delivery: str = None, num_step: int = None):
    """Job adapter over voice_pipeline.retake_section (B2): re-synthesize one section."""
    from nolan.voice_pipeline import retake_section
    return await retake_section(
        config=config, script_project=script_project, index=index, text=text,
        delivery=delivery, voice_id=voice_id, ref_audio=ref_audio, ref_text=ref_text,
        num_step=num_step, log=job.log, progress=job.set_progress)


async def generate_captions(job, *, config, project: str):
    """Build SRT/VTT + word-level JSON for a project's voiceover (hybrid timing).

    Uses the known script text (correct spelling) + Whisper word timestamps. If the
    voiceover has per-section segments, captions each segment AND stitches a full
    timeline; otherwise captions voiceover.mp3 directly.
    """
    import json as _json
    from pathlib import Path as _P
    from nolan import captions as _cap
    from nolan.whisper import WhisperTranscriber, WhisperConfig, WHISPER_AVAILABLE

    if not WHISPER_AVAILABLE:
        raise RuntimeError("captions need Whisper (pip install faster-whisper)")

    base = _P("projects") / project
    vo = base / "assets" / "voiceover"
    if not vo.exists():
        raise RuntimeError(f"no voiceover for '{project}' — generate one first")

    # known section text (correct spelling) from script.md or script.json
    md, sj = base / "script.md", base / "script.json"
    if md.exists():
        from nolan.script import parse_script_sections
        sections = parse_script_sections(md.read_text(encoding="utf-8"))
    elif sj.exists():
        from nolan.script import Script, clean_tts_text
        sc = Script.load_json(str(sj))
        sections = [{"title": s.title, "body": clean_tts_text(s.narration)}
                    for s in sc.sections if (s.narration or "").strip()]
    else:
        raise RuntimeError("no script text found to align against")

    transcriber = WhisperTranscriber(WhisperConfig(
        model_size="base", device="cpu", compute_type="int8"))
    loop = asyncio.get_event_loop()

    seg_dir = vo / "segments"
    manifest_path = seg_dir / "segments.json"
    global_words, per_seg = [], []

    if manifest_path.exists():
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8")).get("segments", [])
        offset, total = 0.0, len(manifest)
        for n, m in enumerate(manifest):
            job.set_progress(0.05 + 0.9 * (n / total if total else 0),
                             f"Captioning [{n+1}/{total}] {(m.get('title') or '')[:40]}")
            wavp = seg_dir / m["file"]
            if not wavp.exists():
                continue
            idx = m.get("index", n)
            known = (sections[idx]["body"] if idx < len(sections) else "").split()
            wt = await loop.run_in_executor(None, transcriber.transcribe_words, wavp)
            words = _cap.align_words(known, wt)
            (seg_dir / (wavp.stem + ".srt")).write_text(_cap.words_to_srt(words), encoding="utf-8")
            (seg_dir / (wavp.stem + ".vtt")).write_text(_cap.words_to_vtt(words), encoding="utf-8")
            (seg_dir / (wavp.stem + ".words.json")).write_text(
                _json.dumps(words, ensure_ascii=False), encoding="utf-8")
            per_seg.append(wavp.stem)
            global_words.extend(_cap.shift_words(words, offset))
            offset += float(m.get("duration") or _wav_duration(wavp))
    else:
        mp3 = vo / "voiceover.mp3"
        if not mp3.exists():
            raise RuntimeError("no segments and no voiceover.mp3 to caption")
        job.set_progress(0.1, "Transcribing voiceover…")
        known = " ".join(s["body"] for s in sections).split()
        wt = await loop.run_in_executor(None, transcriber.transcribe_words, mp3)
        global_words = _cap.align_words(known, wt)

    job.set_progress(0.96, "Writing SRT / VTT / word JSON…")
    (vo / "voiceover.srt").write_text(_cap.words_to_srt(global_words), encoding="utf-8")
    (vo / "voiceover.vtt").write_text(_cap.words_to_vtt(global_words), encoding="utf-8")
    (vo / "voiceover.words.json").write_text(
        _json.dumps(global_words, ensure_ascii=False), encoding="utf-8")

    job.set_progress(1.0, f"Captions ready ({len(global_words)} words)")
    return {"project": project, "words": len(global_words), "per_segment": per_seg,
            "srt": "voiceover.srt", "vtt": "voiceover.vtt", "words_json": "voiceover.words.json"}


async def fetch_channel(job, *, store_root, style_id: str, channel: str,
                        mode: str = "count", count: int = 10,
                        date_after: str = None, date_before: str = None,
                        request_delay: float = 2.0, max_retries: int = 3,
                        enumerate_cap: int = 400):
    """Enumerate a YouTube channel and fetch transcripts into a style corpus.

    mode='count': the ``count`` most recent videos.
    mode='dates': videos whose upload_date is within [date_after, date_before]
        (YYYY-MM-DD or YYYYMMDD). Channel is newest-first, so enumeration stops
        once it passes below date_after. Flat entries often lack dates, so they
        are probed per-video via get_info (paced) when missing.

    Reuses ``fetch_transcripts`` for the actual fetch (dedup + pacing + 429 backoff).
    """
    from nolan.youtube import YouTubeClient
    from nolan.script_style import ScriptStyleStore
    from pathlib import Path as _Path

    store = ScriptStyleStore(_Path(store_root))
    if not store.exists(style_id):
        raise RuntimeError(f"script style not found: {style_id}")
    client = YouTubeClient(output_dir=_Path("script_styles") / style_id / "corpus")
    loop = asyncio.get_event_loop()

    def _norm(d):
        return (d or "").replace("-", "").strip() or None
    date_after, date_before = _norm(date_after), _norm(date_before)

    job.set_progress(0.02, f"Enumerating channel: {channel}")
    try:
        if mode == "count":
            n = max(1, int(count))
            vids = await loop.run_in_executor(None, lambda: client.list_channel_videos(channel, limit=n))
        else:
            vids = await loop.run_in_executor(None, lambda: client.list_channel_videos(channel, limit=enumerate_cap))
    except Exception as e:
        raise RuntimeError(f"could not enumerate channel '{channel}': {e}")

    if mode == "count":
        urls = [v["url"] for v in vids[:max(1, int(count))]]
        job.log(f"Channel: selected {len(urls)} most-recent videos")
    else:
        urls, probed = [], 0
        for v in vids:
            ud = v.get("upload_date")
            if not ud:
                if request_delay:
                    await asyncio.sleep(request_delay)
                try:
                    info = await loop.run_in_executor(None, client.get_info, v["url"])
                    ud = getattr(info, "upload_date", None)
                except Exception:
                    ud = None
                probed += 1
                job.set_progress(0.05, f"Resolving dates… ({probed} probed)")
            if date_before and ud and ud > date_before:
                continue  # too new (newest-first → window is below this)
            if date_after and ud and ud < date_after:
                break      # older than window → everything after is older too
            if ud:
                urls.append(v["url"])
        job.log(f"Channel: {len(urls)} videos in date window (probed {probed} for dates)")

    if not urls:
        job.set_progress(1.0, "No videos matched")
        return {"style_id": style_id, "channel": channel, "selected": 0,
                "added": [], "skipped": [], "errors": [],
                "added_count": 0, "skipped_count": 0, "error_count": 0}

    result = await fetch_transcripts(job, store_root=store_root, style_id=style_id,
                                     urls=urls, request_delay=request_delay,
                                     max_retries=max_retries)
    result["channel"] = channel
    result["selected"] = len(urls)
    return result


def _style_synthesis_task(style_id: str, name: str, slugs: list,
                          extract_max_chars: int) -> str:
    """Brief handed to the synthesis agent (Stage-B reduce step)."""
    base = f"script_styles/{style_id}"
    return f"""# NOLAN script style-guide synthesis: "{name}"

Stage A (acquisition) and the per-transcript Stage-B extraction are done. Your job
is the **synthesis**: distill a single, opinionated, reusable **script-writing
style guide** from this corpus, as a professional scriptwriter/storyteller would.

## Inputs
- Per-transcript feature extracts (JSON): `{base}/per_transcript/*.json`  ({len(slugs)} files)
- Full transcripts (read for exemplars/nuance as needed): `{base}/corpus/*.txt`

## What to do
1. Read all the per-transcript extracts; skim the corpus where you need verbatim detail.
2. Find the **recurring** patterns (not one-off quirks) across the corpus.
3. Write the style guide to `{base}/style_guide.md` with these sections:
   - **Overview** — one paragraph: what this style is and who it's for.
   - **Voice & Tone** — persona, register, attitude.
   - **Hook Patterns** — how openings grab attention (with examples).
   - **Narrative Structure** — the arc / segment formula.
   - **Pacing & Rhythm** — momentum, sentence cadence.
   - **Sentence-level Style** — syntax, length, devices.
   - **Rhetorical Devices** — the toolkit, with examples.
   - **Diction & Vocabulary** — word choice, jargon level.
   - **Transitions** — how ideas connect.
   - **Opening & Closing Formulas**.
   - **Do / Don't** — concrete rules.
   - **Exemplar Lines** — the best verbatim quotes that typify the style.
   - **How to Apply** — a copy-pasteable instruction block a script-writer
     (human or LLM) can follow to write a NEW script in this style. Make this
     section directly usable as a system prompt.

Keep it specific and example-driven — generic advice is useless. Cite which
patterns were consistent across the corpus vs occasional.
"""


async def analyze_style(job, *, config, store_root, style_id: str,
                        session: str = "nolan2", extract_max_chars: int = 200000):
    """Stage B (hybrid): per-transcript LLM extraction, then dispatch the
    synthesis to a tmux Claude agent which writes ``style_guide.md``.
    """
    from nolan.script_style import ScriptStyleStore
    from nolan.llm import create_text_llm
    from pathlib import Path as _Path

    store = ScriptStyleStore(_Path(store_root))
    if not store.exists(style_id):
        raise RuntimeError(f"script style not found: {style_id}")
    name = store.get(style_id).get("name", style_id)
    texts = store.corpus_texts(style_id)
    if not texts:
        raise RuntimeError("corpus is empty — add transcripts before analyzing")

    # --- map: per-transcript feature extraction (inline LLM) ----------------
    llm = create_text_llm(config)
    total = len(texts)
    slugs = []
    for i, t in enumerate(texts):
        job.set_progress(0.05 + 0.7 * (i / total if total else 0),
                         f"Analyzing [{i+1}/{total}] {t['title'][:60]}")
        body = _sample_for_extraction(t["text"], extract_max_chars)
        prompt = _EXTRACT_PROMPT.format(title=t["title"], text=body)
        try:
            raw = await llm.generate(prompt)
            data = _parse_json_object(raw)
        except Exception as e:
            data = {"_error": str(e)}
        data["_meta"] = {"slug": t["slug"], "title": t["title"],
                         "truncated": len(t["text"]) > extract_max_chars}
        store.write_extract(style_id, t["slug"], data)
        slugs.append(t["slug"])
        job.log(f"  extracted: {t['title'][:60]}")

    # --- reduce: dispatch synthesis to a Claude agent -----------------------
    job.set_progress(0.85, "Writing synthesis brief…")
    task_path = _Path(store_root) / style_id / "synthesis_task.md"
    task_path.write_text(_style_synthesis_task(style_id, name, slugs, extract_max_chars),
                         encoding="utf-8")
    task_posix = f"script_styles/{style_id}/synthesis_task.md"
    guide_posix = f"script_styles/{style_id}/style_guide.md"

    job.set_progress(0.92, f"Dispatching synthesis to {session}…")
    message = (f"New NOLAN script style-guide synthesis task — please read and "
               f"complete {task_posix} now, writing the guide to {guide_posix}.")
    dispatched, dispatch_error = True, None
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, _dispatch_to_tmux, session, message)
        job.set_progress(1.0, f"Extracted {total}; synthesis dispatched to {session}")
    except Exception as e:
        dispatched, dispatch_error = False, str(e)
        job.set_progress(1.0, f"Extracted {total}; dispatch failed: {e}")

    return {"style_id": style_id, "session": session, "extracted": total,
            "task_file": task_posix, "guide_file": guide_posix,
            "dispatched": dispatched, "dispatch_error": dispatch_error}


# ==================== Script-writing projects (grounded scripts) ====================


async def write_script(job, *, store_root, slug: str, session: str = "nolan2"):
    """Dispatch a grounded script-writing task to a tmux Claude agent.

    The agent fetches sources, grounds facts, drafts and fact-checks, then writes
    a Director-ready ``script.md``. Mirrors :func:`analyze_style`'s dispatch.
    """
    from nolan.scriptwriter import ScriptProjectStore, write_script_task
    from pathlib import Path as _Path

    store = ScriptProjectStore(_Path(store_root))
    if not store.exists(slug):
        raise RuntimeError(f"script project not found: {slug}")
    session = _pick_run_session(session)   # legacy baseline: resolve 'auto' to an existing worker

    job.set_progress(0.2, "Writing task brief…")
    task_path = store.scriptgen_dir(slug) / "write_task.md"
    task_path.write_text(write_script_task(slug, store), encoding="utf-8")
    task_posix = f"projects/{slug}/scriptgen/write_task.md"
    script_posix = f"projects/{slug}/script.md"

    job.set_progress(0.7, f"Dispatching to {session}…")
    message = (f"New NOLAN script-writing task — please read and complete "
               f"{task_posix} now, writing the script to {script_posix}.")
    dispatched, dispatch_error = True, None
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, _dispatch_to_tmux, session, message)
        job.set_progress(1.0, f"Dispatched to {session}")
    except Exception as e:
        dispatched, dispatch_error = False, str(e)
        job.set_progress(1.0, f"Dispatch failed: {e}")

    return {"slug": slug, "session": session, "task_file": task_posix,
            "script_file": script_posix, "dispatched": dispatched,
            "dispatch_error": dispatch_error}


def _nolan_agents_attached() -> list:
    """[(name, attached_bool)] for live nolan* tmux sessions, parsed from `tmux ls`
    (which prints '(attached)' for sessions a human is viewing)."""
    import shutil
    import subprocess
    base = ["tmux"] if shutil.which("tmux") else ["wsl.exe", "tmux"]
    try:
        out = subprocess.run(base + ["ls"], capture_output=True, text=True, timeout=10)
        rows = []
        for line in out.stdout.splitlines():
            line = line.strip()
            if ":" in line:
                name = line.split(":", 1)[0].strip()
                if name.startswith("nolan"):
                    rows.append((name, "(attached)" in line))
        return rows
    except Exception:
        return []


def _pick_run_session(requested: str, exclude: str = "") -> str:
    """Resolve a dispatch session. An explicit ``nolan*`` name is used as-is; ``'auto'``/'' picks a
    worker agent — preferring an **unattached** idle one (never a session a human is attached to),
    then unattached, then any idle, then any live, then ``nolan2``. ``exclude`` skips a session."""
    req = (requested or "").strip()
    if req and req.lower() != "auto":
        return req
    try:
        from nolan import fleet
        agents = [(n, a) for n, a in _nolan_agents_attached() if n != (exclude or "")]
        if not agents:
            return "nolan2"
        unattached = [n for n, a in agents if not a]
        names = [n for n, _ in agents]
        idle_un = [n for n in unattached if fleet.detect_status(n) == "idle"]
        idle_any = [n for n in names if fleet.detect_status(n) == "idle"]
        return (idle_un or unattached or idle_any or names or ["nolan2"])[0]
    except Exception:
        return "nolan2"


def _pick_reviewer_session(requested: str, store, slug: str) -> str:
    """Fresh-eyes critique: never review with the drafting agent — and never with a session a
    human is attached to. If the requested session is the drafter, swap to an unattached idle
    worker via the attached-aware picker (degrade to the request only if nothing else exists)."""
    try:
        drafted = (store.get(slug).get("draft_session") or "").strip()
    except Exception:
        drafted = ""
    if drafted and requested == drafted:
        return _pick_run_session("auto", exclude=drafted)   # attached-aware, excludes the drafter
    return requested


_PHASE_FILE = {"prep": "prep_task.md", "draft": "draft_task.md", "v3": "v3_task.md",
               "review": "review_task.md", "revise": "revise_task.md"}
_PHASE_LABEL = {"prep": "research + angles", "draft": "beat-map + draft",
                "v3": "full first draft", "review": "fresh-eyes review",
                "revise": "apply approved findings"}


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _phase_builder(phase: str):
    from nolan.scriptwriter import prep_task, draft_task, v3_task, review_task, revise_task
    return {"prep": prep_task, "draft": draft_task, "v3": v3_task,
            "review": review_task, "revise": revise_task}[phase]


def _script_baseline(store, slug: str) -> dict:
    """Pre-dispatch snapshot (no side effects) used to detect the new artifact a phase writes."""
    drafts = store.list_drafts(slug)
    max_draft = max((store._draft_num(d["name"]) for d in drafts), default=0)
    return {"max_draft": max_draft, "reviews": {r["n"] for r in store.list_reviews(slug)}}


def _completion_artifact(store, slug: str, phase: str, baseline: dict):
    """The file whose appearance (+ stability) means the phase finished — the sentinel fallback."""
    if phase in ("draft", "v3", "revise"):
        return store.drafts_dir(slug) / f"draft-{baseline['max_draft'] + 1:02d}.md"
    if phase == "review":
        return store.review_findings_path(slug, baseline["max_draft"] or 1)
    if phase == "prep":
        return store.angles_path(slug)
    return None


def _phase_milestones(store, slug: str, phase: str, baseline: dict):
    """Ordered (step, Path) the hub watches during a phase — it times each sub-step by when the
    artifact is (re)written, needing no agent cooperation. Pre-existing files count only if
    modified during THIS phase (see _await_completion's mtime baseline)."""
    sg = store.scriptgen_dir(slug)
    nd = baseline["max_draft"] + 1          # the draft a draft/v3/revise phase produces
    rn = baseline["max_draft"] or 1         # the review a review phase produces
    M = []
    if phase in ("v3", "prep"):
        M += [("facts", sg / "facts.md"), ("angles", sg / "angles.md")]
    if phase in ("v3", "draft"):
        M += [("beatmap", sg / "beatmap.md"),
              ("draft", store.drafts_dir(slug) / f"draft-{nd:02d}.md"),
              ("factcheck", sg / "factcheck.md"), ("stylecheck", sg / "stylecheck.md"),
              ("report", sg / "report.md")]
    if phase == "review":
        M += [("findings", store.review_findings_path(slug, rn)),
              ("review_md", store.review_path(slug, rn))]
    if phase == "revise":
        M += [("draft", store.drafts_dir(slug) / f"draft-{nd:02d}.md"),
              ("citations", sg / "citations.md"), ("factcheck", sg / "factcheck.md"),
              ("stylecheck", sg / "stylecheck.md"), ("changelog", store.revision_path(slug, rn))]
    return M


async def _await_completion(job, store, slug: str, phase: str, baseline: dict,
                            *, timeout: int = 1800, lo: float = 0.3, hi: float = 0.95) -> dict:
    """Wait for a dispatched agent to finish: primary = the ``.runs/<phase>.done`` sentinel it
    writes last; fallback = the expected output artifact appearing and its size going stable.
    Also records per-sub-step timing (`.runs/<phase>.timing.json`) by watching milestone artifacts."""
    import json as _json
    import time as _t
    sentinel = store.done_path(slug, phase)
    art = _completion_artifact(store, slug, phase, baseline)
    milestones = _phase_milestones(store, slug, phase, baseline)
    base_mtime = {}
    for name, path in milestones:
        try:
            base_mtime[name] = path.stat().st_mtime if path.exists() else 0.0
        except OSError:
            base_mtime[name] = 0.0
    seen: dict = {}
    start = _t.monotonic()
    last_size, stable = -1, 0
    STABLE_POLLS = 50   # × 6s ≈ 300s — the sentinel (authoritative, written last) wins in practice

    def _finish(done: bool, via: str) -> dict:
        timing = {"phase": phase, "total_s": round(_t.monotonic() - start, 1), "via": via,
                  "milestones": [{"step": n, "at_s": seen[n]} for n, _ in milestones if n in seen]}
        try:
            store.runs_dir(slug).mkdir(parents=True, exist_ok=True)
            (store.runs_dir(slug) / f"{phase}.timing.json").write_text(
                _json.dumps(timing, indent=2), encoding="utf-8")
        except OSError:
            pass
        return {"done": done, "via": via, "timing": timing}

    while _t.monotonic() - start < timeout:
        now = round(_t.monotonic() - start, 1)
        for name, path in milestones:            # record each sub-step's first write this phase
            if name not in seen:
                try:
                    if path.exists() and path.stat().st_mtime > base_mtime[name] + 0.5:
                        seen[name] = now
                except OSError:
                    pass
        if sentinel.exists():
            return _finish(True, "sentinel")
        if art is not None and art.exists():
            try:
                sz = art.stat().st_size
            except OSError:
                sz = -1
            if sz > 0 and sz == last_size:
                stable += 1
                if stable >= STABLE_POLLS:
                    return _finish(True, "artifact-stable")
            else:
                last_size, stable = sz, 0
        secs = int(_t.monotonic() - start)
        job.set_progress(min(hi, lo + (hi - lo) * (secs / timeout)),
                         f"{phase}: agent working… ({secs}s)")
        await asyncio.sleep(6)
    return _finish(False, "timeout")


def _is_auto_session(requested: str) -> bool:
    return (requested or "auto").strip().lower() in ("", "auto", "spawn", "ephemeral")


async def _spawn_and_boot(job, name: str, *, timeout: int = 90) -> str:
    """Spawn a fresh ephemeral agent and wait until its Claude TUI is booted (idle). Raises on
    failure (killing the half-spawned session)."""
    from nolan import fleet
    import time as _t
    res = await asyncio.to_thread(fleet.spawn, name)
    if not res.get("ok"):
        raise RuntimeError(f"could not spawn agent {name}: {res.get('error')}")
    start = _t.monotonic()
    while _t.monotonic() - start < timeout:
        st = await asyncio.to_thread(fleet.detect_status, name)
        if st == "idle":
            return name
        job.set_progress(job.progress, f"booting {name}… ({st})")
        await asyncio.sleep(4)
    await asyncio.to_thread(fleet.kill, name)
    raise RuntimeError(f"agent {name} did not boot within {timeout}s")


def _tmux_keys(session: str, keys: list) -> None:
    """Send raw tmux keys (e.g. ['Enter'], ['Escape']) to a session — best-effort."""
    import shutil
    import subprocess
    base = ["tmux"] if shutil.which("tmux") else ["wsl.exe", "tmux"]
    try:
        subprocess.run(base + ["send-keys", "-t", session] + list(keys),
                       capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


async def _dispatch_confirmed(session: str, msg: str, *, tries: int = 4, grace_polls: int = 6) -> bool:
    """Dispatch a task and CONFIRM the agent actually started it (transitioned to busy). A
    freshly-spawned agent sometimes leaves the task queued in the input (the submit-Enter races
    the TUI); this retries with a cleared input until the agent is working, or returns False so
    the caller fails loudly instead of hanging until the phase timeout."""
    from nolan import fleet
    for attempt in range(tries):
        if attempt > 0:                       # clear any queued/partial input before re-sending
            await asyncio.to_thread(_tmux_keys, session, ["Escape"])
            await asyncio.sleep(0.5)
        await asyncio.to_thread(_dispatch_to_tmux, session, msg)
        for _ in range(grace_polls):
            await asyncio.sleep(2)
            try:
                st = await asyncio.to_thread(fleet.detect_status, session)
            except Exception:
                st = "unknown"
            if st == "busy":
                return True                   # confirmed: the agent picked up the task
            if st == "waiting_permission":
                await asyncio.to_thread(_tmux_keys, session, ["Enter"])
    return False


async def _run_on_agent(job, store, slug: str, phase: str, requested: str, *,
                        lo: float, hi: float, do_gate: bool, jobid: str,
                        unattended: bool = False) -> dict:
    """Run one phase on an agent. ``auto``/'' → spawn a DEDICATED ephemeral agent
    (``nolan-run-<jobid>-<phase>``), run, and kill it the instant the phase completes (fresh-eyes
    is automatic since every phase is a new agent). An explicit ``nolanN`` uses that persistent
    session, routing review to a different one for fresh eyes. ``unattended`` trims the
    documentation-only steps (stylecheck/report/prose review/full changelog)."""
    from nolan import fleet
    if _is_auto_session(requested):
        name = f"nolan-run-{(jobid or 'x')[:12]}-{phase}"
        job.set_progress(lo, f"Spawning dedicated agent {name}…")
        sess = await _spawn_and_boot(job, name)
        await asyncio.to_thread(fleet.register_run_agent, name, slug, phase)  # for the reaper
        try:
            return await _dispatch_and_wait(job, store, slug, phase, sess,
                                            lo=lo, hi=hi, do_gate=do_gate, unattended=unattended)
        finally:
            await asyncio.to_thread(fleet.kill, sess)   # clean up the moment the phase is done
            await asyncio.to_thread(fleet.unregister_run_agent, name)
    sess = requested
    if phase == "review":
        sess = _pick_reviewer_session(sess, store, slug)
    return await _dispatch_and_wait(job, store, slug, phase, sess, lo=lo, hi=hi,
                                    do_gate=do_gate, unattended=unattended)


async def _dispatch_and_wait(job, store, slug: str, phase: str, session: str,
                             *, lo: float, hi: float, timeout: int = 1800,
                             do_gate: bool = False, unattended: bool = False) -> dict:
    """Write the brief (+ completion sentinel), dispatch to tmux, WAIT for completion, then
    optionally auto-run the gate. The unit that both run_script_phase and run_full_auto compose.
    ``unattended`` trims documentation-only steps from the brief (full-auto)."""
    from nolan.scriptwriter.tasks import sentinel_block
    from nolan.scriptwriter.gate import run_gate

    sg = f"projects/{slug}/scriptgen"
    fname = _PHASE_FILE[phase]
    brief = _phase_builder(phase)(slug, store, unattended=unattended) + sentinel_block(sg, phase)
    store.runs_dir(slug).mkdir(parents=True, exist_ok=True)
    store.clear_done(slug, phase)
    (store.scriptgen_dir(slug) / fname).write_text(brief, encoding="utf-8")
    task_posix = f"{sg}/{fname}"

    if phase in ("draft", "v3"):
        try:
            store.set_draft_session(slug, session)
        except Exception:
            pass
    baseline = _script_baseline(store, slug)
    disp_at = _now_iso()
    store.write_provenance(slug, phase, session=session, dispatched_at=disp_at)

    job.set_progress(lo, f"Dispatching {phase} → {session}…")
    msg = (f"New NOLAN script task ({_PHASE_LABEL[phase]}) — read and complete "
           f"{task_posix} now, following it exactly.")
    if not await _dispatch_confirmed(session, msg):
        raise RuntimeError(
            f"agent {session} did not start the {phase} task — dispatch never confirmed "
            "(the agent stayed idle after repeated submits).")

    res = await _await_completion(job, store, slug, phase, baseline,
                                  timeout=timeout, lo=lo, hi=hi)
    store.write_provenance(slug, phase, session=session, dispatched_at=disp_at,
                           completed_at=_now_iso(), completed=res["done"], via=res["via"])
    gate = None
    if do_gate and res["done"] and phase in ("draft", "v3", "revise"):
        try:
            rep = await asyncio.to_thread(run_gate, slug, store)
            gate = {"ok": rep.ok, "checks": [{"id": c.id, "level": c.level, "message": c.message}
                                             for c in rep.checks]}
        except Exception as e:
            gate = {"error": str(e)}
    return {"phase": phase, "session": session, "completed": res["done"], "via": res["via"],
            "timing": res.get("timing"), "gate": gate, "task_file": task_posix}


def _gate_result(slug: str, store, phase: str, do_gate: bool):
    """Run the script gate for a completed phase (draft/v3/revise) → the UI gate dict, or None."""
    from nolan.scriptwriter.gate import run_gate
    if not (do_gate and phase in ("draft", "v3", "revise")):
        return None
    try:
        rep = run_gate(slug, store)
        return {"ok": rep.ok, "checks": [{"id": c.id, "level": c.level, "message": c.message}
                                         for c in rep.checks]}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


async def _finalize_completed_phase(job, store, slug: str, phase: str, session: str,
                                    jobid: str, do_gate: bool, lo: float, hi: float) -> dict:
    """Resume path: the phase's ``.done`` sentinel is already present (agent finished during the
    outage) — reap its ephemeral agent, gate the existing artifact, stamp provenance, done."""
    from nolan import fleet
    if _is_auto_session(session):
        name = f"nolan-run-{(jobid or 'x')[:12]}-{phase}"
        await asyncio.to_thread(fleet.kill, name)
        await asyncio.to_thread(fleet.unregister_run_agent, name)
    gate = await asyncio.to_thread(_gate_result, slug, store, phase, do_gate)
    store.write_provenance(slug, phase, session=session, completed=True,
                           via="sentinel(resumed)", resumed=True)
    job.set_progress(hi, f"{phase} already complete (resumed) ✓")
    return {"phase": phase, "session": session, "completed": True, "via": "sentinel(resumed)",
            "timing": None, "gate": gate, "task_file": None, "resumed": True}


async def _attach_and_wait(job, store, slug: str, phase: str, session: str, *,
                           lo: float, hi: float, do_gate: bool, ephemeral: bool) -> dict:
    """Resume path: the agent is still alive and mid-task — re-enter the completion wait WITHOUT
    re-dispatching (the brief is already in the agent's input), then gate. Reaps an ephemeral
    agent when it finishes."""
    from nolan import fleet
    baseline = _script_baseline(store, slug)
    job.set_progress(lo, f"Re-attaching to {session} for {phase} (resumed)…")
    try:
        res = await _await_completion(job, store, slug, phase, baseline, lo=lo, hi=hi)
    finally:
        if ephemeral:
            await asyncio.to_thread(fleet.kill, session)
            await asyncio.to_thread(fleet.unregister_run_agent, session)
    store.write_provenance(slug, phase, session=session, completed_at=_now_iso(),
                           completed=res["done"], via=res["via"], resumed=True)
    gate = await asyncio.to_thread(_gate_result, slug, store, phase, do_gate) if res["done"] else None
    return {"phase": phase, "session": session, "completed": res["done"], "via": res["via"],
            "timing": res.get("timing"), "gate": gate, "task_file": None, "resumed": True}


async def _phase_step(job, store, slug: str, phase: str, session: str, *, lo: float, hi: float,
                      do_gate: bool, jobid: str, unattended: bool, resume: bool) -> dict:
    """Run a phase. On ``resume`` (hub restarted mid-run) first try to salvage in-flight work:
    finalize if the sentinel already landed, or re-attach to the still-live agent — else fall
    through to a fresh dispatch (idempotent)."""
    if resume:
        from nolan import fleet
        if store.done_path(slug, phase).exists():
            return await _finalize_completed_phase(job, store, slug, phase, session,
                                                   jobid, do_gate, lo, hi)
        ephemeral = _is_auto_session(session)
        cand = f"nolan-run-{(jobid or 'x')[:12]}-{phase}" if ephemeral else session
        alive = False
        try:
            alive = bool(cand) and await asyncio.to_thread(fleet.has_session, cand)
        except Exception:  # noqa: BLE001
            alive = False
        if alive:
            return await _attach_and_wait(job, store, slug, phase, cand,
                                          lo=lo, hi=hi, do_gate=do_gate, ephemeral=ephemeral)
        # no sentinel and no live agent → the work was lost across the restart → run it fresh
    return await _run_on_agent(job, store, slug, phase, session, lo=lo, hi=hi,
                               do_gate=do_gate, jobid=jobid, unattended=unattended)


async def run_script_phase(job, *, store_root, slug: str, session: str = "auto",
                           phase: str = "v3", resume: bool = False):
    """Dispatch ONE script-pipeline phase and WAIT for it to complete (then auto-gate).

    phase ∈ {prep, draft, v3, review, revise}. ``session='auto'`` spawns a DEDICATED ephemeral
    agent and kills it when the phase finishes; an explicit ``nolanN`` uses that persistent one.
    Blocks (async) until the agent writes its completion sentinel, so status + gate reflect real work.
    ``resume=True`` (set only by the durable-job reattach on startup) salvages an interrupted run.
    """
    from nolan.scriptwriter import ScriptProjectStore
    from pathlib import Path as _Path

    store = ScriptProjectStore(_Path(store_root))
    if not store.exists(slug):
        raise RuntimeError(f"script project not found: {slug}")
    if phase not in _PHASE_FILE:
        raise RuntimeError(f"unknown phase: {phase}")
    res = await _phase_step(job, store, slug, phase, session, lo=0.15, hi=0.92,
                            do_gate=(phase != "prep"), jobid=job.id, unattended=False, resume=resume)
    tail = " ✓" if res["completed"] else " (timeout — check artifacts)"
    job.set_progress(1.0, f"{phase} complete{tail}")
    return {"slug": slug, **res}


def _auto_approve_all(store, slug: str, review_n: int) -> list:
    """Auto-approve every finding of a review (full-auto gate). Returns the approved list."""
    import json
    fp = store.review_findings_path(slug, review_n)
    findings = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else []
    store.review_approved_path(slug, review_n).write_text(
        json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")
    return findings


async def run_full_auto(job, *, store_root, slug: str, session: str = "auto",
                        resume: bool = False):
    """End-to-end unattended run: draft (v3) → gate → fresh-eyes review → auto-approve → revise →
    gate → verify. With ``session='auto'`` each phase runs on its own DEDICATED ephemeral agent,
    killed when the phase completes (fresh-eyes automatic; no lingering sessions). One review round.

    ``resume=True`` (set only by the durable-job reattach on startup) re-drives the run from wherever
    it was interrupted: already-finished phases finalize instantly (their ``.done`` sentinel), an
    in-flight phase re-attaches to its still-live agent, and remaining phases run fresh."""
    from nolan.scriptwriter import ScriptProjectStore, ledger
    from nolan.scriptwriter.gate import verify_revision
    from nolan import fleet
    from pathlib import Path as _Path

    store = ScriptProjectStore(_Path(store_root))
    if not store.exists(slug):
        raise RuntimeError(f"script project not found: {slug}")
    jobid = job.id
    summary: dict = {"slug": slug, "session": session, "phases": [], "resumed": resume}
    run_prefix = f"nolan-run-{jobid[:12]}-"
    try:
        job.set_progress(0.03, f"Full auto ▸ {'resuming ▸ ' if resume else ''}drafting…")
        r1 = await _phase_step(job, store, slug, "v3", session, lo=0.05, hi=0.40,
                               do_gate=True, jobid=jobid, unattended=True, resume=resume)
        summary["phases"].append(r1)
        if not r1["completed"]:
            return {**summary, "stopped_at": "draft"}

        job.set_progress(0.42, "Full auto ▸ reviewing…")
        r2 = await _phase_step(job, store, slug, "review", session, lo=0.42, hi=0.58,
                               do_gate=False, jobid=jobid, unattended=True, resume=resume)
        summary["phases"].append(r2)
        if not r2["completed"]:
            return {**summary, "stopped_at": "review"}

        n, _ = store.current_draft(slug)                   # the draft that was reviewed
        approved = _auto_approve_all(store, slug, n)
        ledger.record_review_decision(slug, store, n, [f.get("id") for f in approved])
        summary["approved"] = len(approved)
        job.set_progress(0.60, f"Full auto ▸ approved {len(approved)} findings, revising…")

        r3 = await _phase_step(job, store, slug, "revise", session, lo=0.62, hi=0.94,
                               do_gate=True, jobid=jobid, unattended=True, resume=resume)
        summary["phases"].append(r3)
        try:
            summary["verify"] = verify_revision(store, slug, n)
        except Exception as e:
            summary["verify"] = {"error": str(e)}
        job.set_progress(1.0, "Full auto complete ✓" if r3["completed"] else "Full auto: revise timed out")
        return summary
    finally:
        # crash/cancel safety net: reap any ephemeral agent from THIS run that survived
        try:
            for s in list_tmux_sessions():
                if s.startswith(run_prefix):
                    await asyncio.to_thread(fleet.kill, s)
        except Exception:
            pass


def resume_worker_for(job):
    """Map a journaled durable job → a bound, resumable worker (invoked as ``worker(job=job)``),
    or ``None`` if it can't be resumed. Used by the hub's startup reattach (see jobs.reattach)."""
    import functools
    m = job.meta or {}
    slug = m.get("slug")
    if not slug:
        return None
    store_root = m.get("store_root", "projects")
    session = m.get("session", "auto")
    if job.type == "script-auto":
        return functools.partial(run_full_auto, store_root=store_root, slug=slug,
                                 session=session, resume=True)
    if job.type == "script-phase":
        return functools.partial(run_script_phase, store_root=store_root, slug=slug,
                                 session=session, phase=m.get("phase", "v3"), resume=True)
    return None


# ==================== Video-style analysis (visual style guides) ====================


def _vseg_to_dict(seg) -> dict:
    """Map a VideoSegment to the dict shape the video_style modules expect."""
    ic = getattr(seg, "inferred_context", None)
    return {
        "timestamp_start": seg.timestamp_start,
        "timestamp_end": seg.timestamp_end,
        "transcript": seg.transcript,
        "combined_summary": seg.combined_summary,
        "frame_description": seg.frame_description,
        "inferred_context": ic.to_dict() if ic else None,
    }


async def analyze_video_style(job, *, config, store_root, db_path, style_id: str,
                              session: str = "nolan2", provider: str = "openrouter",
                              max_frames: int = 24, vision_max_frames: int = 6,
                              enable_vision: bool = True):
    """Per-video visual extraction (stats + pairing + vision), then dispatch the
    synthesis to a tmux Claude agent which writes ``video_style_guide.md``.
    Mirrors :func:`analyze_style`.
    """
    from pathlib import Path as _Path
    from nolan.video_style import VideoStyleStore, pairing as pairing_mod
    from nolan.video_style.extract import build_extract
    from nolan.video_style.tasks import video_style_synthesis_task
    from nolan.indexer import VideoIndex
    from nolan.vision import create_vision_provider

    store = VideoStyleStore(_Path(store_root))
    if not store.exists(style_id):
        raise RuntimeError(f"video style not found: {style_id}")
    name = store.get(style_id).get("name", style_id)
    sources = store.sources(style_id)
    if not sources:
        raise RuntimeError("no reference videos — add some before analyzing")

    index = VideoIndex(_Path(db_path))
    embedder = pairing_mod.make_bge_embedder()  # loads BGE once

    vision = None
    if enable_vision:
        try:
            vp = create_vision_provider(_select_vision(config, provider, None, None, None))
            vision = vp if await vp.check_connection() else None
            if vision is None:
                job.log(f"vision provider '{provider}' unreachable — skipping cinematography")
        except Exception as e:
            job.log(f"vision setup failed ({e}) — skipping cinematography")

    total = len(sources)
    analyzed, errors = [], []
    for i, s in enumerate(sources):
        slug, vpath = s["slug"], s["video_path"]
        job.set_progress(0.05 + 0.8 * (i / total if total else 0),
                         f"Analyzing [{i+1}/{total}] {s.get('title') or slug}")
        try:
            try:
                segs = [_vseg_to_dict(x) for x in index.get_segments(vpath)]
            except Exception:
                segs = []
            extract = await build_extract(
                _Path(vpath), segments=segs, frames_dir=store.frames_dir(style_id, slug),
                embed=embedder, vision_provider=vision,
                max_frames=max_frames, vision_max_frames=vision_max_frames)
            store.write_extract(style_id, slug, extract)
            store.mark_analyzed(style_id, slug)
            analyzed.append(slug)
            job.log(f"  + {s.get('title') or slug} (segments={len(segs)}, frames={extract['frames_analyzed']})")
        except Exception as e:
            errors.append({"slug": slug, "error": str(e)})
            job.log(f"  ! {slug}: {e}")

    # Deconstruction case studies: if a corpus video has been deconstructed
    # (breakdown written), hand its beat-level analysis to the synthesis agent.
    case_studies = []
    try:
        from nolan.deconstruct import DeconstructionStore
        dstore = DeconstructionStore(_Path("video_deconstructions"))
        for s in sources:
            dslug = dstore.slug_for(s["video_path"])
            m = dstore.get(dslug)
            if m and m.get("has_breakdown"):
                case_studies.append(f"video_deconstructions/{dslug}/breakdown.md")
    except Exception:
        pass
    if case_studies:
        job.log(f"including {len(case_studies)} deconstruction case stud"
                f"{'y' if len(case_studies) == 1 else 'ies'}")

    job.set_progress(0.9, "Writing synthesis brief…")
    store.task_path(style_id).write_text(
        video_style_synthesis_task(style_id, name, analyzed, case_studies=case_studies),
        encoding="utf-8")
    task_posix = f"video_styles/{style_id}/synthesis_task.md"
    guide_posix = f"video_styles/{style_id}/video_style_guide.md"

    job.set_progress(0.94, f"Dispatching synthesis to {session}…")
    message = (f"New NOLAN video style-guide synthesis task — please read and "
               f"complete {task_posix} now, writing the guide to {guide_posix}.")
    dispatched, dispatch_error = True, None
    try:
        await asyncio.get_event_loop().run_in_executor(None, _dispatch_to_tmux, session, message)
        job.set_progress(1.0, f"Analyzed {len(analyzed)}; synthesis dispatched to {session}")
    except Exception as e:
        dispatched, dispatch_error = False, str(e)
        job.set_progress(1.0, f"Analyzed {len(analyzed)}; dispatch failed: {e}")

    return {"style_id": style_id, "session": session, "analyzed": analyzed,
            "errors": errors, "task_file": task_posix, "guide_file": guide_posix,
            "dispatched": dispatched, "dispatch_error": dispatch_error}


# ==================== Video deconstruction (inverse Director) ====================


async def deconstruct_video(job, *, config, store_root, db_path, video_path: str,
                            session: str = "nolan2", provider: str = "openrouter",
                            enable_vision: bool = True, use_llm: bool = True,
                            profile: str = "balanced"):
    """Deconstruct one ingested library video into beats + pairing + tempo.

    API layer (like ingestion): visual facts (OpenCV + vision API), beats and
    operator classification (text LLM), tempo recovery (deterministic). Then
    dispatches ONE synthesis task to a tmux Claude agent which writes
    ``breakdown.md`` and refines ``recovered_plan.json``. Mirrors
    :func:`analyze_video_style`.
    """
    from pathlib import Path as _Path
    from nolan.deconstruct import (DeconstructionStore, build_extract,
                                   deconstruction_synthesis_task)
    from nolan.indexer import VideoIndex
    from nolan.llm import create_text_llm
    from nolan.video_style import pairing as pairing_mod
    from nolan.vision import create_vision_provider

    index = VideoIndex(_Path(db_path))
    if index.get_video_id_by_path(video_path) is None:
        raise RuntimeError(f"video not in library index: {video_path}")

    store = DeconstructionStore(_Path(store_root))
    title = _Path(video_path).stem
    slug = store.create(video_path, title=title)

    job.set_progress(0.05, "Setting up analysis providers…")
    llm = None
    if use_llm:
        try:
            llm = create_text_llm(config)
        except Exception as e:
            job.log(f"text LLM unavailable ({e}) — beats/operators use fallbacks")
    try:
        embedder = pairing_mod.make_bge_embedder()
    except Exception as e:
        embedder = None
        job.log(f"BGE embedder unavailable ({e}) — no directness prior")
    vision = None
    if enable_vision:
        try:
            vp = create_vision_provider(_select_vision(config, provider, None, None, None))
            vision = vp if await vp.check_connection() else None
            if vision is None:
                job.log(f"vision provider '{provider}' unreachable — shot facts stay motion-only")
        except Exception as e:
            job.log(f"vision setup failed ({e}) — shot facts stay motion-only")

    job.set_progress(0.15, "Extracting: shots → motion → beats → operators → tempo…")
    extract, plan = await build_extract(
        video_path, index, llm=llm, embed=embedder, vision_provider=vision,
        frames_dir=store.frames_dir(slug), profile=profile)
    store.write_extract(slug, extract)
    store.write_plan(slug, plan)
    store.set_status(slug, "extracted")
    job.log(f"extract: {extract['shot_count']} shots → {len(extract['beats'])} beats "
            f"(beats:{extract['beat_source']}, operators:{extract['operator_source']})")

    job.set_progress(0.9, "Writing synthesis brief…")
    store.task_path(slug).write_text(
        deconstruction_synthesis_task(slug, title, video_path), encoding="utf-8")
    task_posix = f"video_deconstructions/{slug}/synthesis_task.md"
    breakdown_posix = f"video_deconstructions/{slug}/breakdown.md"

    job.set_progress(0.94, f"Dispatching synthesis to {session}…")
    message = (f"New NOLAN video deconstruction synthesis task — please read and "
               f"complete {task_posix} now, writing the breakdown to {breakdown_posix} "
               f"and refining the recovered plan.")
    dispatched, dispatch_error = True, None
    try:
        await asyncio.get_event_loop().run_in_executor(None, _dispatch_to_tmux, session, message)
        job.set_progress(1.0, f"Extracted {len(extract['beats'])} beats; synthesis dispatched to {session}")
    except Exception as e:
        dispatched, dispatch_error = False, str(e)
        job.set_progress(1.0, f"Extracted; dispatch failed: {e}")

    return {"slug": slug, "session": session, "shots": extract["shot_count"],
            "beats": len(extract["beats"]), "beat_source": extract["beat_source"],
            "operator_source": extract["operator_source"], "task_file": task_posix,
            "breakdown_file": breakdown_posix, "dispatched": dispatched,
            "dispatch_error": dispatch_error}


# ==================== Archival-art sourcing (masterwork raid) ====================


async def source_art(job, *, config, project: str):
    """Source real public-domain artworks for a project's archival-art scenes.

    Thin job wrapper over :func:`nolan.art_sourcing.source_art_for_plan`
    (library-first → museum/Commons providers → describe+ingest →
    ``matched_asset``). Also runs inside Director step 4; this endpoint exists
    for standalone re-runs from the UI.
    """
    from pathlib import Path as _Path
    from nolan.art_sourcing import source_art_for_plan

    project_root = _Path("projects") / project
    plan_path = project_root / "scene_plan.json"
    if not plan_path.exists():
        raise RuntimeError(f"no scene_plan.json in project: {project}")

    job.set_progress(0.1, "Sourcing artworks (library → museums/Commons → ingest)…")
    result = await asyncio.to_thread(
        source_art_for_plan, plan_path, project_root, config, log=job.log)
    job.set_progress(1.0, f"Art sourcing: {result['matched']}/{result['considered']} matched")
    return {"project": project, **result}


# ==================== Publish (source -> beautiful HTML article) ====================

async def publish_article(job, *, src: str, theme: str = "press", type: str = "explainer",
                          width: str = "regular", images: str = "none",
                          brand: Optional[str] = None, cover: bool = True,
                          slug: Optional[str] = None, nolan_config=None):
    """Turn a URL / file / pasted text into a self-contained offline HTML article.

    Mirrors the ``nolan publish`` CLI. The authoring step runs a Claude agent
    (minutes), so progress is staged: scaffold -> author -> build. The deterministic
    scaffold/build steps are blocking (subprocess) so they run in a thread; the
    authoring step is already async.
    """
    from nolan.publish import toolkit
    from nolan.publish.builder import Publisher, PublishConfig

    loop = asyncio.get_event_loop()
    cfg = PublishConfig(theme=theme, type=type, width=width, images=images,
                        brand_color=(brand or None), cover=cover)
    pub = Publisher(cfg, nolan_config=nolan_config)

    job.set_progress(0.05, "Scaffolding workspace…")
    ws, _ = await loop.run_in_executor(None, pub.prepare, src, slug)
    job.log(f"workspace: {ws}")

    job.set_progress(0.15, "Authoring article (agent)…")
    await pub.author(ws)

    sections = list((ws / "article" / "sections").glob("*.tsx"))
    if not sections:
        raise RuntimeError("agent wrote no sections — authoring did not complete")

    job.set_progress(0.85, f"Building ({len(sections)} sections)…")
    html = await loop.run_in_executor(None, pub.finalize, ws)
    ok = html.exists() and toolkit.is_offline(html)
    summary = f"{len(sections)} sections, {html.stat().st_size // 1024} KB, offline={ok}"
    job.set_progress(1.0, f"{ws.name}: {summary}")
    return {"ok": ok, "slug": ws.name, "sections": len(sections),
            "article_html": str(html), "workspace": str(ws), "summary": summary}
