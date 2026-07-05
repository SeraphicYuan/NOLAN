"""Library routes for the NOLAN hub.

Moved verbatim from ``nolan.hub.create_hub_app`` (hub split). ``register(app,
ctx)`` unpacks the shared hub context into locals with the original closure
names, then registers the routes unchanged.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict

import httpx
from urllib.parse import quote
from fastapi import HTTPException, Query, UploadFile, File, Form, Body
from fastapi.responses import HTMLResponse, FileResponse

from nolan.hub import _format_duration, _segment_to_dict, _computed_cluster_to_dict, _stored_cluster_to_dict


def register(app, ctx):
    templates_dir = ctx.templates_dir
    db_path = ctx.db_path
    job_manager = ctx.job_manager

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
            """List all indexed videos, each with its full (many-to-many) project list."""
            with sqlite3.connect(db_path) as conn:
                # resolve a project filter (slug or id) to an id, then filter via the join table
                pid = None
                if project:
                    prow = conn.execute("SELECT id FROM projects WHERE slug = ? OR id = ?",
                                        (project, project)).fetchone()
                    pid = prow[0] if prow else project
                # video → its projects (join table ∪ legacy videos.project_id)
                vp = {}
                for vidid, ppid, pslug, pname in conn.execute("""
                        SELECT vp.video_id, p.id, p.slug, p.name FROM video_projects vp
                        JOIN projects p ON p.id = vp.project_id"""):
                    vp.setdefault(vidid, []).append({"id": ppid, "slug": pslug, "name": pname})
                for vidid, ppid, pslug, pname in conn.execute("""
                        SELECT v.id, p.id, p.slug, p.name FROM videos v
                        JOIN projects p ON p.id = v.project_id WHERE v.project_id IS NOT NULL"""):
                    lst = vp.setdefault(vidid, [])
                    if not any(x["id"] == ppid for x in lst):
                        lst.append({"id": ppid, "slug": pslug, "name": pname})
                where = ("WHERE v.id IN (SELECT video_id FROM video_projects WHERE project_id = ?) "
                         "OR v.project_id = ?") if pid else ""
                params = (pid, pid) if pid else ()
                cursor = conn.execute(f"""
                    SELECT v.id, v.path, v.duration, v.indexed_at, v.has_transcript, COUNT(s.id)
                    FROM videos v LEFT JOIN segments s ON v.id = s.video_id
                    {where}
                    GROUP BY v.id ORDER BY v.indexed_at DESC
                """, params)
                videos = []
                for row in cursor.fetchall():
                    projs = vp.get(row[0], [])
                    videos.append({
                        "id": row[0], "path": row[1], "name": Path(row[1]).name,
                        "duration": row[2], "duration_formatted": _format_duration(row[2]),
                        "indexed_at": row[3], "has_transcript": bool(row[4]),
                        "segment_count": row[5], "projects": projs,
                        "project_slug": projs[0]["slug"] if projs else None,
                        "project_name": projs[0]["name"] if projs else None,
                    })
                # all projects (for the add-to-project dropdown)
                all_projects = [{"id": r[0], "slug": r[1], "name": r[2]}
                                for r in conn.execute("SELECT id, slug, name FROM projects ORDER BY name")]
                return {"videos": videos, "total": len(videos), "project_filter": project,
                        "all_projects": all_projects}

        @app.post("/library/api/videos/{video_path:path}/projects")
        async def library_video_projects(video_path: str, body: dict = Body(...)):
            """Add/remove a video's project association (many-to-many, no re-embed)."""
            from nolan.indexer import VideoIndex
            action = (body.get("action") or "add").strip()
            project = (body.get("project") or "").strip()
            if not project:
                raise HTTPException(status_code=400, detail="project is required")
            idx = VideoIndex(db_path)
            vid = idx.get_video_id_by_path(video_path)
            if vid is None:
                raise HTTPException(status_code=404, detail="video not found")
            ppid = idx.resolve_project(project) or project
            if action == "remove":
                idx.remove_video_from_project(vid, ppid)
            else:
                idx.add_video_to_project(vid, ppid)
            return {"video_id": vid, "action": action, "project": ppid,
                    "projects": idx.get_video_projects(vid)}

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

        @app.get("/library/api/embedding-status")
        async def library_embedding_status(project: Optional[str] = Query(default=None)):
            """Per-video embedding state (searchable / stale / unembedded) + summary."""
            from nolan.vector_search import VectorSearch
            vector_db_path = db_path.parent / "vectors"
            vs = VectorSearch(vector_db_path, index=index)
            project_id = index.resolve_project(project) if project else None
            return vs.get_embedding_status(project_id=project_id)

        @app.post("/library/api/videos/{video_path:path}/embed")
        async def library_embed_video(video_path: str):
            """Manually embed ONE indexed video so it becomes semantically searchable."""
            from nolan.webui import operations
            path = unquote(video_path)
            with sqlite3.connect(db_path) as conn:
                row = conn.execute("SELECT id FROM videos WHERE path = ?", (path,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"No indexed video at {path}")
            job = job_manager.start(
                "embed-video", operations.embed_video,
                db_path=db_path, video_id=row[0],
            )
            return {"job_id": job.id, "type": "embed-video", "video_id": row[0]}

        @app.post("/library/api/reconcile-vectors")
        async def library_reconcile_vectors():
            """Embed ALL unembedded/stale videos in one incremental pass (idempotent)."""
            from nolan.webui import operations
            job = job_manager.start(
                "sync-vectors", operations.sync_vectors, db_path=db_path, project_id=None,
            )
            return {"job_id": job.id, "type": "sync-vectors"}

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

        # ==================== Saved Clips (manual cuts) ====================

        clips_template = templates_dir / "clips.html"

        @app.get("/clips", response_class=HTMLResponse)
        async def clips_home():
            """Serve the clips search / library page."""
            if clips_template.exists():
                return clips_template.read_text(encoding="utf-8")
            return "<h1>clips.html not found</h1>"

        def _resolve_scope(projects: Optional[str]) -> Optional[List[str]]:
            """Turn a comma-separated list of slugs/ids into project ids.

            Returns None for 'all projects' (empty / 'all')."""
            if not projects or projects.strip().lower() in ("all", ""):
                return None
            ids = []
            for token in projects.split(","):
                token = token.strip()
                if not token:
                    continue
                resolved = index.resolve_project(token) or token
                ids.append(resolved)
            return ids or None

        @app.get("/library/api/clips")
        async def clips_list(projects: Optional[str] = Query(default=None)):
            """List saved clips, optionally scoped to a set of projects."""
            scope = _resolve_scope(projects)
            return {"clips": index.list_saved_clips(project_ids=scope),
                    "scope": scope}

        @app.post("/library/api/clips")
        async def clips_create(body: dict = Body(...)):
            """Create a saved clip from a manual in/out selection."""
            source = (body.get("source_video_path") or "").strip()
            if not source:
                raise HTTPException(status_code=400, detail="source_video_path is required")
            try:
                clip_start = float(body.get("clip_start"))
                clip_end = float(body.get("clip_end"))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="clip_start and clip_end must be numbers")
            if clip_end <= clip_start:
                raise HTTPException(status_code=400, detail="clip_end must be greater than clip_start")
            tags = body.get("tags") or None
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()] or None
            project = (body.get("project") or "").strip() or None
            project_id = index.resolve_project(project) if project else None
            clip_id = index.add_saved_clip(
                source_video_path=source,
                clip_start=clip_start, clip_end=clip_end,
                label=(body.get("label") or None),
                tags=tags, project_id=project_id,
            )
            return {"clip": index.get_saved_clip(clip_id)}

        @app.delete("/library/api/clips/{clip_id}")
        async def clips_delete(clip_id: str):
            if not index.delete_saved_clip(clip_id):
                raise HTTPException(status_code=404, detail="clip not found")
            return {"deleted": clip_id}

        @app.post("/library/api/clips/{clip_id}/materialize")
        async def clips_materialize(clip_id: str, body: dict = Body(default={})):
            """Materialize a saved clip (none|file|frames) as a background job."""
            from nolan.webui import operations
            if not index.get_saved_clip(clip_id):
                raise HTTPException(status_code=404, detail="clip not found")
            form = (body.get("form") or "file").strip()
            job = job_manager.start(
                "materialize-clip", operations.materialize_clip,
                meta={"clip_id": clip_id, "form": form},
                db_path=db_path, clip_id=clip_id, form=form,
                num_frames=int(body.get("num_frames", 6)),
                force=bool(body.get("force", False)),
            )
            return {"job_id": job.id, "type": "materialize-clip"}

        @app.post("/library/api/clips/{clip_id}/analyze-effect")
        async def clips_analyze_effect(clip_id: str, body: dict = Body(default={})):
            """Dispatch a clip to a tmux Claude agent for effect analysis."""
            from nolan.webui import operations
            if not index.get_saved_clip(clip_id):
                raise HTTPException(status_code=404, detail="clip not found")
            session = (body.get("session") or "nolan2").strip() or "nolan2"
            job = job_manager.start(
                "analyze-effect", operations.analyze_effect,
                meta={"clip_id": clip_id, "session": session},
                db_path=db_path, clip_id=clip_id,
                num_frames=int(body.get("num_frames", 10)),
                session=session,
            )
            return {"job_id": job.id, "type": "analyze-effect"}

        @app.get("/library/api/clips/{clip_id}/analysis")
        async def clips_analysis(clip_id: str):
            """Return the nolan2 agent's effect-analysis findings, if written yet."""
            analysis = Path("projects") / "_clips" / clip_id / "effect_analysis.md"
            if not analysis.exists():
                raise HTTPException(status_code=404, detail="no analysis yet")
            return {"clip_id": clip_id, "content": analysis.read_text(encoding="utf-8")}

        @app.get("/library/api/clips/search")
        async def clips_search(
            q: str = Query(default="", description="keyword query (optional)"),
            projects: Optional[str] = Query(default=None),
            limit: int = Query(default=50, le=200),
        ):
            """Scoped search across saved clips + auto-snippets (segments/clusters)."""
            scope = _resolve_scope(projects)
            saved = index.list_saved_clips(project_ids=scope)
            if q:
                ql = q.lower()
                saved = [c for c in saved
                         if ql in (c.get("label") or "").lower()
                         or any(ql in str(t).lower() for t in (c.get("tags") or []))
                         or ql in (c.get("video_name") or "").lower()]
            result = {"query": q, "scope": scope, "saved_clips": saved,
                      "saved_clip_count": len(saved)}
            if q:
                segs = index.search(q, limit=limit, project_ids=scope)
                clus = index.search_clusters(q, limit=limit, project_ids=scope)
                result["segments"] = [_segment_to_dict(s) for s in segs]
                result["segment_count"] = len(segs)
                result["clusters"] = clus
                result["cluster_count"] = len(clus)
            else:
                result["segments"] = []
                result["segment_count"] = 0
                result["clusters"] = []
                result["cluster_count"] = 0
            return result
