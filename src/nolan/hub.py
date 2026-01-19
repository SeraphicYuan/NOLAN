"""Unified Hub for NOLAN web interfaces."""

import json
from pathlib import Path
from typing import Optional, List, Dict

import httpx
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
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

    return {
        "name": directory.name,
        "path": str(directory),
        "scene_plan_path": str(scene_plan),
        "scene_count": scene_count,
        "sections": section_names,
        "has_audio": has_audio,
    }


def scan_projects(projects_dir: Path) -> List[Dict]:
    """Scan a directory for valid NOLAN projects.

    A valid project is a directory containing scene_plan.json.
    Also checks:
    - If the directory itself is a project (has scene_plan.json)
    - Subdirectories for scene_plan.json or output/scene_plan.json

    Returns:
        List of project info dicts with name, path, scene_count, etc.
    """
    projects = []
    if not projects_dir.exists():
        return projects

    # First check if the directory itself is a project
    scene_plan = _find_scene_plan(projects_dir)
    if scene_plan:
        projects.append(_parse_project(projects_dir, scene_plan))

    # Then scan subdirectories
    for item in projects_dir.iterdir():
        if not item.is_dir():
            continue

        scene_plan = _find_scene_plan(item)
        if not scene_plan:
            continue

        projects.append(_parse_project(item, scene_plan))

    # Sort by name
    projects.sort(key=lambda p: p["name"].lower())
    return projects


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
    uploads_dir = Path(__file__).parent.parent.parent / "render-service" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # ==================== Landing Page ====================

    @app.get("/", response_class=HTMLResponse)
    async def landing():
        """Serve the hub landing page."""
        hub_template = templates_dir / "hub.html"
        if hub_template.exists():
            return hub_template.read_text(encoding="utf-8")
        return "<h1>Hub template not found</h1>"

    @app.get("/api/status")
    async def hub_status():
        """Get hub status info for landing page."""
        library_available = db_path and db_path.exists()
        projects = scan_projects(projects_dir) if projects_dir else []

        return {
            "library": {
                "available": library_available,
                "db_path": str(db_path) if db_path else None,
            },
            "showcase": {
                "available": True,
                "render_service_url": render_service_url,
            },
            "projects": projects,
        }

    # ==================== Library Routes ====================

    if db_path and db_path.exists():
        import sqlite3
        from nolan.indexer import VideoIndex
        from urllib.parse import unquote

        index = VideoIndex(db_path)
        library_template = templates_dir / "library.html"

        @app.get("/library", response_class=HTMLResponse)
        async def library_home():
            """Serve the library viewer page."""
            return library_template.read_text(encoding="utf-8")

        @app.get("/library/api/projects")
        async def library_list_projects():
            """List all projects with video counts."""
            with sqlite3.connect(db_path) as conn:
                cursor = conn.execute("""
                    SELECT p.id, p.slug, p.name, p.description, p.path,
                           COUNT(v.id) as video_count
                    FROM projects p
                    LEFT JOIN videos v ON p.id = v.project_id
                    GROUP BY p.id
                    ORDER BY p.name
                """)
                projects = []
                for row in cursor.fetchall():
                    projects.append({
                        "id": row[0], "slug": row[1], "name": row[2],
                        "description": row[3], "path": row[4], "video_count": row[5],
                    })
                return {"projects": projects, "total": len(projects)}

        @app.get("/library/api/videos")
        async def library_list_videos(
            project: Optional[str] = Query(default=None),
        ):
            """List all indexed videos."""
            with sqlite3.connect(db_path) as conn:
                if project:
                    cursor = conn.execute("""
                        SELECT v.path, v.duration, v.indexed_at, v.has_transcript,
                               COUNT(s.id) as segment_count, v.project_id,
                               p.slug as project_slug, p.name as project_name
                        FROM videos v
                        LEFT JOIN segments s ON v.id = s.video_id
                        LEFT JOIN projects p ON v.project_id = p.id
                        WHERE p.slug = ? OR p.id = ?
                        GROUP BY v.id ORDER BY v.indexed_at DESC
                    """, (project, project))
                else:
                    cursor = conn.execute("""
                        SELECT v.path, v.duration, v.indexed_at, v.has_transcript,
                               COUNT(s.id) as segment_count, v.project_id,
                               p.slug as project_slug, p.name as project_name
                        FROM videos v
                        LEFT JOIN segments s ON v.id = s.video_id
                        LEFT JOIN projects p ON v.project_id = p.id
                        GROUP BY v.id ORDER BY v.indexed_at DESC
                    """)
                videos = []
                for row in cursor.fetchall():
                    video_path = Path(row[0])
                    videos.append({
                        "path": row[0], "name": video_path.name,
                        "duration": row[1], "duration_formatted": _format_duration(row[1]),
                        "indexed_at": row[2], "has_transcript": bool(row[3]),
                        "segment_count": row[4], "project_id": row[5],
                        "project_slug": row[6], "project_name": row[7],
                    })
                return {"videos": videos, "total": len(videos), "project_filter": project}

        @app.get("/library/api/videos/{video_path:path}/segments")
        async def library_get_segments(video_path: str):
            """Get segments for a video."""
            video_path = unquote(video_path)
            segments = index.get_segments(video_path)
            if not segments:
                raise HTTPException(status_code=404, detail="Video not found")
            return {
                "video_path": video_path,
                "segments": [_segment_to_dict(s) for s in segments],
                "total": len(segments),
            }

        @app.get("/library/api/videos/{video_path:path}/clusters")
        async def library_get_clusters(video_path: str):
            """Get clusters for a video."""
            from nolan.clustering import cluster_segments
            video_path = unquote(video_path)
            clusters = index.get_clusters(video_path)
            if not clusters:
                segments = index.get_segments(video_path)
                if not segments:
                    raise HTTPException(status_code=404, detail="Video not found")
                computed = cluster_segments(segments)
                clusters = [_computed_cluster_to_dict(c) for c in computed]
            else:
                clusters = [_stored_cluster_to_dict(c, index) for c in clusters]
            return {"video_path": video_path, "clusters": clusters, "total": len(clusters)}

        @app.get("/library/api/search")
        async def library_search(
            q: str = Query(..., min_length=1),
            limit: int = Query(default=50, le=200),
            fields: Optional[str] = Query(default=None),
            search_type: str = Query(default="all"),
            project: Optional[str] = Query(default=None),
        ):
            """Search segments and clusters."""
            field_list = fields.split(",") if fields else None
            project_id = index.resolve_project(project) if project else None
            results = {"query": q, "fields": field_list, "search_type": search_type}
            if search_type in ("all", "segments"):
                segment_results = index.search(q, limit=limit, fields=field_list, project_id=project_id)
                results["segments"] = [_segment_to_dict(s) for s in segment_results]
                results["segment_count"] = len(segment_results)
            if search_type in ("all", "clusters"):
                cluster_results = index.search_clusters(q, limit=limit, fields=field_list, project_id=project_id)
                results["clusters"] = cluster_results
                results["cluster_count"] = len(cluster_results)
            return results

        @app.get("/library/api/search/semantic")
        async def library_semantic_search(
            q: str = Query(..., min_length=1),
            limit: int = Query(default=20, le=100),
            search_type: str = Query(default="both"),
            project: Optional[str] = Query(default=None),
        ):
            """Semantic search using vector embeddings."""
            from nolan.vector_search import VectorSearch
            vector_db_path = db_path.parent / "vectors"
            if not vector_db_path.exists():
                raise HTTPException(status_code=503, detail="Run 'nolan sync-vectors' first")
            vector_search = VectorSearch(vector_db_path, index=index)
            stats = vector_search.get_stats()
            if stats['segments'] == 0 and stats['clusters'] == 0:
                raise HTTPException(status_code=503, detail="Vector database empty")
            project_id = index.resolve_project(project) if project else None
            results = vector_search.search(query=q, limit=limit, search_level=search_type, project_id=project_id)
            formatted = [{
                "score": r.score, "score_percent": f"{r.score * 100:.1f}%",
                "content_type": r.content_type, "video_path": r.video_path,
                "video_name": Path(r.video_path).name if r.video_path else "",
                "timestamp_start": r.timestamp_start, "timestamp_end": r.timestamp_end,
                "timestamp_formatted": f"{int(r.timestamp_start // 60):02d}:{int(r.timestamp_start % 60):02d}",
                "description": r.description, "transcript": r.transcript,
                "people": r.people, "location": r.location, "objects": r.objects,
            } for r in results]
            return {"query": q, "results": formatted, "total": len(formatted), "vector_stats": stats}

        @app.get("/library/api/stats")
        async def library_stats():
            """Get library statistics."""
            with sqlite3.connect(db_path) as conn:
                video_count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
                segment_count = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
                total_duration = conn.execute("SELECT SUM(duration) FROM videos").fetchone()[0] or 0
                return {
                    "video_count": video_count, "segment_count": segment_count,
                    "total_duration": total_duration,
                    "total_duration_formatted": _format_duration(total_duration),
                }

        @app.get("/library/video/{video_path:path}")
        async def library_serve_video(video_path: str):
            """Serve video file."""
            from urllib.parse import unquote
            video_path = unquote(video_path)
            file_path = Path(video_path)
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="Video not found")
            media_types = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}
            return FileResponse(file_path, media_type=media_types.get(file_path.suffix.lower(), "video/mp4"))

    # ==================== Showcase Routes ====================

    showcase_template = templates_dir / "showcase.html"

    @app.get("/showcase", response_class=HTMLResponse)
    async def showcase_home():
        """Serve the showcase page."""
        return showcase_template.read_text(encoding="utf-8")

    @app.get("/showcase/api/effects")
    async def showcase_list_effects(category: Optional[str] = None):
        """List effects from render service."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{render_service_url}/effects"
                if category:
                    url += f"?category={category}"
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")
        except httpx.HTTPStatusError:
            raise HTTPException(status_code=503, detail="Render service error")

    @app.get("/showcase/api/effects/{effect_id}")
    async def showcase_get_effect(effect_id: str):
        """Get specific effect details."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{render_service_url}/effects/{effect_id}")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Effect not found")
            raise HTTPException(status_code=500, detail=str(e))
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")

    @app.post("/showcase/api/upload")
    async def showcase_upload(file: UploadFile = File(...)):
        """Upload file for effects."""
        import uuid
        ext = Path(file.filename).suffix if file.filename else ".bin"
        filename = f"{uuid.uuid4()}{ext}"
        filepath = uploads_dir / filename
        content = await file.read()
        filepath.write_bytes(content)
        return {"filename": filename, "path": str(filepath.absolute()), "size": len(content)}

    @app.post("/showcase/api/render")
    async def showcase_render(effect: str = Form(...), params: str = Form(...)):
        """Submit render job."""
        try:
            params_dict = json.loads(params)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid params JSON")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{render_service_url}/render",
                    json={"effect": effect, "params": params_dict},
                )
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")

    @app.get("/showcase/api/render/status/{job_id}")
    async def showcase_render_status(job_id: str):
        """Get render job status."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{render_service_url}/render/status/{job_id}")
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")

    @app.get("/showcase/api/render/result/{job_id}")
    async def showcase_render_result(job_id: str):
        """Get render job result."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{render_service_url}/render/result/{job_id}")
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")

    @app.get("/showcase/preview/{filename:path}")
    async def showcase_preview(filename: str):
        """Serve preview files."""
        locations = [
            Path(__file__).parent.parent.parent / "render-service" / "public" / "previews" / filename,
            Path(__file__).parent.parent.parent / "render-service" / "output" / filename,
        ]
        for path in locations:
            if path.exists():
                return FileResponse(path)
        raise HTTPException(status_code=404, detail="Preview not found")

    @app.get("/showcase/output/{filename:path}")
    async def showcase_output(filename: str):
        """Serve rendered output."""
        path = Path(__file__).parent.parent.parent / "render-service" / "output" / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path)

    # ==================== Scenes Routes (Dynamic Project Selection) ====================

    scenes_template = templates_dir / "scenes.html"

    def _get_project_dir(project_name: str) -> Optional[tuple]:
        """Get project directory and scene_plan path by name.

        Returns:
            Tuple of (project_path, scene_plan_path) or None if not found.
        """
        if not projects_dir:
            return None

        # Check if projects_dir itself matches (e.g., "output" project)
        if projects_dir.name == project_name:
            scene_plan = _find_scene_plan(projects_dir)
            if scene_plan:
                return (projects_dir, scene_plan)

        # Check subdirectory
        project_path = projects_dir / project_name
        if project_path.exists():
            scene_plan = _find_scene_plan(project_path)
            if scene_plan:
                return (project_path, scene_plan)

        return None

    @app.get("/scenes", response_class=HTMLResponse)
    async def scenes_home():
        """Serve the scenes viewer page."""
        if scenes_template.exists():
            return scenes_template.read_text(encoding="utf-8")
        return "<h1>Scenes template not found</h1>"

    @app.get("/scenes/api/projects")
    async def scenes_list_projects():
        """List available projects for scenes viewer."""
        projects = scan_projects(projects_dir) if projects_dir else []
        return {"projects": projects, "total": len(projects)}

    @app.get("/scenes/api/scenes/flat")
    async def scenes_get_flat(project: str = Query(..., description="Project name")):
        """Get scenes as flat list for a specific project."""
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")

        project_path, scene_plan_path = result
        data = json.loads(scene_plan_path.read_text(encoding="utf-8"))
        scenes = []
        sections = list(data.get("sections", {}).keys())
        for section_name, section_scenes in data.get("sections", {}).items():
            for scene in section_scenes:
                scene["_section"] = section_name
                scenes.append(scene)
        scenes.sort(key=lambda s: s.get("start_seconds") or 0)
        return {"scenes": scenes, "sections": sections, "project": project}

    @app.get("/scenes/api/audio-info")
    async def scenes_audio_info(project: str = Query(..., description="Project name")):
        """Get voiceover audio info for a specific project."""
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")

        project_path, _ = result
        voiceover_dir = project_path / "assets" / "voiceover"
        if voiceover_dir.exists():
            for ext in [".mp3", ".wav", ".m4a", ".ogg"]:
                audio_file = voiceover_dir / f"voiceover{ext}"
                if audio_file.exists():
                    return {
                        "path": f"/scenes/assets/{project}/voiceover/voiceover{ext}",
                        "exists": True,
                        "project": project,
                    }
        return {"path": None, "exists": False, "project": project}

    @app.get("/scenes/assets/{project}/{asset_path:path}")
    async def scenes_serve_asset(project: str, asset_path: str):
        """Serve asset files for a specific project."""
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")

        project_path, _ = result
        file_path = project_path / "assets" / asset_path
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Asset not found")

        # Determine media type
        suffix = file_path.suffix.lower()
        media_types = {
            ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
            ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
        }
        return FileResponse(file_path, media_type=media_types.get(suffix, "application/octet-stream"))

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
    port: int = 8001,
    db_path: Optional[Path] = None,
    projects_dir: Optional[Path] = None,
):
    """Run the unified hub server."""
    import uvicorn
    app = create_hub_app(db_path=db_path, projects_dir=projects_dir)
    uvicorn.run(app, host=host, port=port)
