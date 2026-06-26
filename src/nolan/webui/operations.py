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
                 whisper_fallback: bool = True, whisper_model: str = "base"):
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

    job.set_progress(1.0, f"Indexed {segments} segments from {video_path.name}")
    return {
        "video_path": str(video_path),
        "segments": segments,
        "provider": provider,
        "model": vision_config.model,
    }


async def process_essay(job, *, config, essay_text: str, project_name: str,
                        skip_scenes: bool = False, style_id: str = None):
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


def _scene_plan_path(project_name: str) -> Path:
    return Path("projects") / project_name / "scene_plan.json"


def build_query_variants(scene) -> list:
    """Generate search queries broad→specific for a scene.

    The scene designer's queries are often too literal (proper nouns, years) for
    stock/archival libraries. We try the original, then progressively broader
    variants (drop years/proper-nouns), then a generic phrase from the description.
    """
    import re as _re
    out = []
    q = (getattr(scene, "search_query", "") or "").strip()
    if q:
        out.append(q)
        broad = _re.sub(r"\b\d{4}\b", "", q)                       # drop years
        broad = _re.sub(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", "", broad)  # drop Proper Nouns
        broad = _re.sub(r"\s+", " ", broad).strip()
        if broad and broad.lower() != q.lower():
            out.append(broad)
    vd = (getattr(scene, "visual_description", "") or "").strip()
    if vd:
        out.append(" ".join(vd.split()[:6]))
    seen, res = set(), []
    for x in out:
        if x and x.lower() not in seen:
            seen.add(x.lower())
            res.append(x)
    return res or ["archival documentary footage"]


async def match_broll_v2(job, *, config, project_name: str, prefer_video: bool = True,
                         max_results: int = 4, concurrency: int = 6, score_cap: int = 4,
                         scorer_model: str = "qwen/qwen3-vl-8b-instruct"):
    """Video-first, multi-source b-roll matcher with query-variant fallback.

    Speed-optimized: (1) scenes processed concurrently, (2) candidates cheaply
    pre-filtered to the top `score_cap` by quality before vision-scoring,
    (3) a fast small vision model (`scorer_model`) does relevance scoring.
    Videos are attached by reference; images downloaded. assemble detects type by ext.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor
    import httpx as _httpx
    from nolan.scenes import ScenePlan
    from nolan.image_search import ImageSearchClient, ImageScorer
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

        state = {"done": 0, "matched": 0}
        lock = threading.Lock()

        def process_scene(scene):
            variants = build_query_variants(scene)
            cands = []
            if prefer_video and vid_sources:
                for variant in variants:
                    cands = client.search_assets(variant, media_type="video",
                                                 sources=vid_sources, max_results=max_results)
                    if cands:
                        break
            if not cands:
                for variant in variants:
                    cands = client.search_assets(variant, media_type="image", max_results=max_results)
                    if cands:
                        break
            ok = False
            if cands:
                # (2) Cheap pre-filter: rank by quality (resolution/aspect), keep top score_cap.
                for c in cands:
                    qs, _ = scorer.calculate_quality_score(c)
                    c.quality_score = qs
                cands = sorted(cands, key=lambda c: c.quality_score or 0, reverse=True)[:score_cap]
                ctx = f"for a documentary scene: {scene.visual_description or ''}"
                scored = scorer.score_results(
                    cands, getattr(scene, "search_query", "") or scene.visual_description or "", context=ctx)
                best = scored[0] if scored else None
                if best and (best.score or 0) >= 4:
                    if best.media_type == "video":
                        # Resolve the actual mp4 URL for the winner only (lazy).
                        resolved = client.resolve_video(best)
                        if resolved and resolved.url:
                            job.log(f"{scene.id}: video from {resolved.source} (score {best.score})")
                            scene.matched_clip = {
                                "external_url": resolved.url, "source": resolved.source,
                                "source_url": resolved.source_url, "title": resolved.title,
                                "license": resolved.license, "duration": resolved.duration,
                                "media_type": "video",
                                "preview_image_url": resolved.preview_image_url or resolved.thumbnail_url,
                                "score": best.score, "external": True,
                            }
                            ok = True
                    else:
                        dest = out_dir / f"{scene.id}.jpg"
                        try:
                            data = _httpx.get(best.url, follow_redirects=True, timeout=30.0,
                                              headers={"User-Agent": "Mozilla/5.0"}).content
                            dest.write_bytes(data)
                            scene.matched_asset = str(dest.relative_to(plan_path.parent)).replace("\\", "/")
                            job.log(f"{scene.id}: image from {best.source} (score {best.score})")
                            ok = True
                        except Exception:
                            ok = False
            with lock:
                state["done"] += 1
                if ok:
                    state["matched"] += 1
                job.set_progress(0.05 + 0.9 * state["done"] / max(1, len(broll)),
                                 f"b-roll {state['done']}/{len(broll)} · {state['matched']} matched")

        # (1) Process scenes concurrently.
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(process_scene, broll))

        plan.save(str(plan_path))
        return {"project": project_name, "broll_scenes": len(broll), "matched": state["matched"],
                "video_sources": vid_sources, "scorer_model": scorer_model}

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
                         download: bool = True, dest: Optional[str] = None) -> dict:
    """Extract high-def image assets from a page URL via the parser registry.

    Picks the matching extractor (Gutenberg / Wikimedia / Met / generic),
    optionally downloads the full-res files into ``dest`` (or
    ``.scratch/extracted/<host>``) and writes a manifest.
    """
    import json
    from urllib.parse import urlparse

    from nolan.extractors import download_assets, extract_from_url, get_extractor

    ex = get_extractor(url)
    job.set_progress(0.1, f"Extracting via '{ex.name}'...")
    results = await asyncio.to_thread(extract_from_url, url, limit=limit)
    job.set_progress(0.5, f"Found {len(results)} asset(s)")

    records = [r.to_dict() for r in results]
    out_dir = None
    if download and results:
        host = urlparse(url).netloc.replace(":", "_") or "page"
        out_dir = Path(dest) if dest else Path(".scratch/extracted") / host
        job.set_progress(0.6, f"Downloading {len(results)} asset(s) -> {out_dir}")
        records = await download_assets(results, out_dir)
        (out_dir / "manifest.json").write_text(
            json.dumps({"url": url, "extractor": ex.name, "count": len(records),
                        "results": records}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    ok = sum(1 for r in records if r.get("local_path")) if download else 0
    msg = f"{len(records)} asset(s)" + (f", {ok} downloaded" if download else "")
    job.set_progress(1.0, f"Done - {msg}")
    return {"url": url, "extractor": ex.name, "count": len(records),
            "downloaded": ok, "out_dir": str(out_dir) if out_dir else None,
            "results": records}


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
                         steps: Optional[int] = None):
    """Generate a single sample image from a registered workflow → scratch preview."""
    from nolan.workflow_registry import get_registry
    reg = get_registry()
    overrides = {k: v for k, v in (("width", width), ("height", height), ("steps", steps)) if v}
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
3. If **new**, assess **replicability** and pick a backend:
   - **Remotion** → add a composition in `render-service/remotion-lib/src/` + a
     `MotionEffect(..., backend="remotion", target="<CompId>")` row in `registry.py`.
   - **Python** → a scene renderer in `src/nolan/renderer/scenes/` + a
     `MotionEffect(..., backend="python", target="<ClassName>")` row in `registry.py`.
   The executor (`nolan.motion.executor.render`) already handles both backends, so a new
   registry row makes it renderable from a spec immediately. Give a concrete plan.

## Output
Write your findings to `{analysis_posix}` as markdown with sections:
**Effect**, **Dedup result** (registry id + backend if covered), **Replicable?**
(chosen backend), **Plan**. Keep it concise and actionable. (Follow the repo's
"Promoting Techniques to NOLAN" convention if you implement it.)
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
                        session: str = "nolan2", extract_max_chars: int = 20000):
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
        body = t["text"][:extract_max_chars]
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
