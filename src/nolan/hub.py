"""Unified Hub for NOLAN web interfaces."""

import json
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

RENDER_SERVICE_URL = "http://127.0.0.1:3010"


def _find_scene_plan(directory: Path) -> Optional[Path]:
    """Find scene_plan.json in a directory or its output/ subdirectory."""
    scene_plan = directory / "scene_plan.json"
    if scene_plan.exists():
        return scene_plan
    scene_plan = directory / "output" / "scene_plan.json"
    if scene_plan.exists():
        return scene_plan
    return None


def _parse_project(directory: Path, scene_plan: Path) -> Dict:
    """Parse a project directory into metadata dict."""
    # Parse scene plan to get metadata
    try:
        data = json.loads(scene_plan.read_text(encoding="utf-8"))
        sections = data.get("sections", {})
        scene_count = sum(len(scenes) for scenes in sections.values())
        section_names = list(sections.keys())
    except (json.JSONDecodeError, IOError):
        scene_count = 0
        section_names = []

    # Check for audio in project's assets folder
    has_audio = False
    voiceover_dir = directory / "assets" / "voiceover"
    if voiceover_dir.exists():
        for ext in [".mp3", ".wav", ".m4a", ".ogg"]:
            if (voiceover_dir / f"voiceover{ext}").exists():
                has_audio = True
                break

    # flow projects self-declare their video type in flow.spec.json (e.g. "art")
    video_type = None
    flow_spec = directory / "flow.spec.json"
    if flow_spec.exists():
        try:
            video_type = json.loads(flow_spec.read_text(encoding="utf-8")).get("flow")
        except (json.JSONDecodeError, IOError):
            pass

    return {
        "name": directory.name,
        "path": str(directory),
        "scene_plan_path": str(scene_plan),
        "scene_count": scene_count,
        "sections": section_names,
        "has_audio": has_audio,
        "video_type": video_type,
    }


# Subdirs that are project *internals*, never separate projects — don't descend.
_PROJECT_SKIP_DIRS = {
    "assets", "clips", "work", "output", "source", "frames", "voiceover",
    "vectors", ".orchestrator", ".nolan", "node_modules", "__pycache__", ".git",
}


def _scan_into(base: Path, projects_dir: Path, projects: List[Dict], depth: int, max_depth: int) -> None:
    scene_plan = _find_scene_plan(base)
    if scene_plan:
        info = _parse_project(base, scene_plan)
        # Name nested projects by their path relative to projects_dir so they stay
        # unique and resolvable by _get_project_dir (projects_dir / name).
        try:
            rel = base.relative_to(projects_dir)
            info["name"] = projects_dir.name if rel == Path(".") else str(rel).replace("\\", "/")
        except ValueError:
            pass
        projects.append(info)
    if depth >= max_depth:
        return
    try:
        children = sorted(base.iterdir())
    except OSError:
        return
    for item in children:
        if item.is_dir() and item.name not in _PROJECT_SKIP_DIRS and not item.name.startswith("."):
            _scan_into(item, projects_dir, projects, depth + 1, max_depth)


def scan_projects(projects_dir: Path, max_depth: int = 3) -> List[Dict]:
    """Scan a directory tree for valid NOLAN projects (dirs with scene_plan.json).

    Recurses up to `max_depth` so nested segment-builder outputs (e.g.
    `<linear project>/segment_xyz/`) are discoverable. Nested projects are named
    by their path relative to `projects_dir` (e.g. "US Economy/segment_xyz").

    Returns:
        List of project info dicts with name, path, scene_count, etc.
    """
    projects: List[Dict] = []
    if not projects_dir.exists():
        return projects
    _scan_into(projects_dir, projects_dir, projects, depth=0, max_depth=max_depth)
    projects.sort(key=lambda p: p["name"].lower())
    return projects


def _resolve_assemble_audio(proj_dir: Path, audio: Optional[str]) -> Optional[Path]:
    """Resolve narration audio for assemble.

    Explicit `audio` (absolute or project-relative), else the project's standard
    voiceover (`assets/voiceover/voiceover.{mp3,wav,m4a,ogg}`). Returns an existing
    Path or None.
    """
    if audio:
        p = Path(audio)
        if p.exists():
            return p
        cand = proj_dir / audio
        return cand if cand.exists() else None
    for ext in (".mp3", ".wav", ".m4a", ".ogg"):
        c = proj_dir / "assets" / "voiceover" / f"voiceover{ext}"
        if c.exists():
            return c
    return None


def create_hub_app(
    db_path: Optional[Path] = None,
    projects_dir: Optional[Path] = None,
    render_service_url: str = RENDER_SERVICE_URL,
) -> FastAPI:
    """Create the unified NOLAN hub application.

    Args:
        db_path: Path to SQLite database for library features.
        projects_dir: Path to directory containing project folders.
        render_service_url: URL of the render service for showcase.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="NOLAN Hub")
    templates_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    uploads_dir = Path(__file__).parent.parent.parent / "render-service" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Shared static assets (theme, nav, job-poll widget).
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Cache-busting for a fast-moving local tool: /static revalidates on every
    # load (unchanged files are free 304s), so nav/css/js changes appear
    # without hard refreshes.
    @app.middleware("http")
    async def _static_no_cache(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    # Tonal b-roll prototype gallery (period/locale-gated evocative b-roll). Served as static
    # so its local poster stills resolve; remote clips stream from the stock CDN. View at
    # /tonal-broll/ (reachable over the Tailscale-exposed hub).
    tonal_dir = Path(__file__).parent.parent.parent / "projects" / "_library" / "_tonal_broll"
    if tonal_dir.exists():
        app.mount("/tonal-broll", StaticFiles(directory=str(tonal_dir), html=True), name="tonal_broll")

    # Generated (Krea-2 / ComfyUI) evocative-b-roll stills, served for the /broll gallery.
    gen_dir = Path(__file__).parent.parent.parent / "projects" / "_library" / "_broll_generated"
    gen_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/broll-gen", StaticFiles(directory=str(gen_dir)), name="broll_gen")

    # Theme × archetype sample renders (themes/scripts/gen_samples.py) for the /themes Samples tab.
    theme_samples_dir = Path(__file__).parent.parent.parent / "themes" / "_samples"
    theme_samples_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/theme-samples", StaticFiles(directory=str(theme_samples_dir)), name="theme_samples")
    # Per-theme theme books (themes/scripts/gen_theme_books.py) for the /themes Books tab — the
    # authoring-facing identity+capability poster per theme.
    theme_books_dir = Path(__file__).parent.parent.parent / "themes" / "_books"
    theme_books_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/theme-books", StaticFiles(directory=str(theme_books_dir)), name="theme_books")

    # ---- shared context for the route modules (split from the former monolith).
    # Route bodies live in nolan.webui.routes.*; each module's register(app, ctx)
    # unpacks these into locals with the original closure names.
    from types import SimpleNamespace
    ctx = SimpleNamespace(
        db_path=db_path,
        projects_dir=projects_dir,
        render_service_url=render_service_url,
        templates_dir=templates_dir,
        uploads_dir=uploads_dir,
        gen_dir=gen_dir,
        repo_root=Path(__file__).resolve().parents[2],
        # published by route modules during registration:
        job_manager=None,            # routes.core
        _render_service_up=None,     # routes.core
        style_store=None,            # routes.script_styles
        script_project_store=None,   # routes.script_projects
    )

    # Register route modules in the ORIGINAL section order (route order can
    # matter for path matching). Imported lazily to avoid an import cycle
    # (route modules import helpers from nolan.hub).
    from nolan.webui.routes import (
        core, ingest_process, broll, images_extract, lottie, settings,
        match_generate, render_assemble, studio_landing, library, sfx, transcripts,
        script_styles, script_projects, voices, video_styles,
        deconstruct, showcase, scenes, hf_scenes, agents, shortlist, system_map, taste,
        pool, kb, clipper, themes, sessions, data_panel,
    )
    for module in (core, ingest_process, broll, images_extract, lottie, settings,
                   match_generate, render_assemble, studio_landing, library, sfx, transcripts,
                   script_styles, script_projects, voices, video_styles,
                   deconstruct, showcase, scenes, hf_scenes, agents, shortlist, system_map, taste,
                   pool, kb, clipper, themes, sessions, data_panel):
        module.register(app, ctx)

    # One /api convention: every API route lives at /api/<domain>/... — the
    # legacy /<domain>/api/ prefixes were removed once all callers migrated.
    return app


def _format_duration(seconds: Optional[float]) -> str:
    """Format duration to HH:MM:SS or MM:SS."""
    if seconds is None or seconds <= 0:
        return "0:00"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _segment_to_dict(segment) -> dict:
    """Convert VideoSegment to dict."""
    return {
        "video_path": segment.video_path,
        "video_name": Path(segment.video_path).name,
        "timestamp_start": segment.timestamp_start,
        "timestamp_end": segment.timestamp_end,
        "timestamp_formatted": segment.timestamp_formatted,
        "duration": segment.duration,
        "frame_description": segment.frame_description,
        "transcript": segment.transcript,
        "combined_summary": segment.combined_summary,
        "inferred_context": segment.inferred_context.to_dict() if segment.inferred_context else None,
        "sample_reason": segment.sample_reason,
    }


def _computed_cluster_to_dict(cluster) -> dict:
    """Convert computed cluster to dict."""
    return {
        "id": cluster.id,
        "timestamp_start": cluster.timestamp_start,
        "timestamp_end": cluster.timestamp_end,
        "timestamp_formatted": cluster.timestamp_formatted,
        "duration": cluster.duration,
        "segment_count": len(cluster.segments),
        "cluster_summary": cluster.cluster_summary,
        "people": cluster.people,
        "locations": cluster.locations,
        "combined_transcript": cluster.combined_transcript,
        "segments": [_segment_to_dict(s) for s in cluster.segments],
    }


def _stored_cluster_to_dict(cluster: dict, index) -> dict:
    """Convert stored cluster to dict."""
    start = cluster.get("timestamp_start", 0)
    end = cluster.get("timestamp_end", 0)
    timestamp_formatted = f"{int(start // 60):02d}:{int(start % 60):02d} - {int(end // 60):02d}:{int(end % 60):02d}"
    segments = []
    video_path = cluster.get("video_path")
    if video_path:
        all_segments = index.get_segments(video_path)
        segments = [_segment_to_dict(s) for s in all_segments if s.timestamp_start >= start and s.timestamp_end <= end + 0.1]
    return {
        "id": cluster.get("cluster_index", cluster.get("id", 0)),
        "timestamp_start": start, "timestamp_end": end,
        "timestamp_formatted": timestamp_formatted,
        "duration": end - start, "segment_count": len(segments),
        "cluster_summary": cluster.get("cluster_summary"),
        "people": cluster.get("people", []),
        "locations": cluster.get("locations", []),
        "combined_transcript": "",
        "segments": segments,
    }


def run_hub(
    host: str = "127.0.0.1",
    port: int = 8011,  # 8001 belongs to SPARTA; the hub uses 8011
    db_path: Optional[Path] = None,
    projects_dir: Optional[Path] = None,
):
    """Run the unified hub server."""
    import uvicorn
    app = create_hub_app(db_path=db_path, projects_dir=projects_dir)
    uvicorn.run(app, host=host, port=port)
