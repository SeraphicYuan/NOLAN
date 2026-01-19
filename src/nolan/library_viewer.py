"""Video Index Library Viewer for NOLAN."""

import sqlite3
from pathlib import Path
from typing import Optional, List
from urllib.parse import unquote

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from starlette.responses import Response

from nolan.indexer import VideoIndex, VideoSegment


def create_library_app(db_path: Path) -> FastAPI:
    """Create the library viewer FastAPI application.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="NOLAN Library Viewer")
    db_path = Path(db_path)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    index = VideoIndex(db_path)
    template_path = Path(__file__).parent / "templates" / "library.html"

    @app.get("/", response_class=HTMLResponse)
    async def home():
        """Serve the main library viewer page."""
        return template_path.read_text(encoding="utf-8")

    @app.get("/api/projects")
    async def list_projects():
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
                    "id": row[0],
                    "slug": row[1],
                    "name": row[2],
                    "description": row[3],
                    "path": row[4],
                    "video_count": row[5],
                })

            return {"projects": projects, "total": len(projects)}

    @app.get("/api/videos")
    async def list_videos(
        project: Optional[str] = Query(default=None, description="Filter by project slug or ID"),
    ):
        """List all indexed videos with metadata, optionally filtered by project."""
        with sqlite3.connect(db_path) as conn:
            if project:
                # Filter by project slug or ID
                cursor = conn.execute("""
                    SELECT v.path, v.duration, v.indexed_at, v.has_transcript,
                           COUNT(s.id) as segment_count, v.project_id,
                           p.slug as project_slug, p.name as project_name
                    FROM videos v
                    LEFT JOIN segments s ON v.id = s.video_id
                    LEFT JOIN projects p ON v.project_id = p.id
                    WHERE p.slug = ? OR p.id = ?
                    GROUP BY v.id
                    ORDER BY v.indexed_at DESC
                """, (project, project))
            else:
                cursor = conn.execute("""
                    SELECT v.path, v.duration, v.indexed_at, v.has_transcript,
                           COUNT(s.id) as segment_count, v.project_id,
                           p.slug as project_slug, p.name as project_name
                    FROM videos v
                    LEFT JOIN segments s ON v.id = s.video_id
                    LEFT JOIN projects p ON v.project_id = p.id
                    GROUP BY v.id
                    ORDER BY v.indexed_at DESC
                """)

            videos = []
            for row in cursor.fetchall():
                video_path = Path(row[0])
                videos.append({
                    "path": row[0],
                    "name": video_path.name,
                    "duration": row[1],
                    "duration_formatted": _format_duration(row[1]),
                    "indexed_at": row[2],
                    "has_transcript": bool(row[3]),
                    "segment_count": row[4],
                    "project_id": row[5],
                    "project_slug": row[6],
                    "project_name": row[7],
                })

            return {"videos": videos, "total": len(videos), "project_filter": project}

    @app.get("/api/videos/{video_path:path}/segments")
    async def get_video_segments(video_path: str):
        """Get all segments for a specific video."""
        video_path = unquote(video_path)
        segments = index.get_segments(video_path)

        if not segments:
            raise HTTPException(status_code=404, detail="Video not found or has no segments")

        return {
            "video_path": video_path,
            "video_name": Path(video_path).name,
            "segments": [_segment_to_dict(s) for s in segments],
            "total": len(segments),
        }

    @app.get("/api/videos/{video_path:path}/clusters")
    async def get_video_clusters(video_path: str):
        """Get stored clusters for a specific video."""
        video_path = unquote(video_path)
        clusters = index.get_clusters(video_path)

        if not clusters:
            # Fall back to computing clusters on-the-fly
            from nolan.clustering import cluster_segments
            segments = index.get_segments(video_path)
            if not segments:
                raise HTTPException(status_code=404, detail="Video not found or has no segments")
            computed = cluster_segments(segments)
            clusters = [_computed_cluster_to_dict(c) for c in computed]
        else:
            # Enhance stored clusters with segment data
            clusters = [_stored_cluster_to_dict(c, index) for c in clusters]

        return {
            "video_path": video_path,
            "video_name": Path(video_path).name,
            "clusters": clusters,
            "total": len(clusters),
        }

    @app.get("/api/search")
    async def search_segments(
        q: str = Query(..., min_length=1, description="Search query"),
        limit: int = Query(default=50, le=200, description="Max results"),
        fields: Optional[str] = Query(default=None, description="Comma-separated fields to search"),
        search_type: str = Query(default="all", description="Search type: all, segments, clusters"),
        project: Optional[str] = Query(default=None, description="Filter by project slug or ID"),
    ):
        """Search across indexed segments and/or clusters.

        Fields for segments: frame_description, transcript, combined_summary,
                            people, location, story_context, objects
        Fields for clusters: cluster_summary, people, locations
        """
        field_list = fields.split(",") if fields else None

        # Resolve project slug to project ID if provided
        project_id = None
        if project:
            resolved = index.resolve_project(project)
            if resolved:
                project_id = resolved
            else:
                # Try using the value directly as project_id (for backward compat)
                project_id = project

        results = {
            "query": q,
            "fields": field_list,
            "search_type": search_type,
            "project_filter": project,
        }

        if search_type in ("all", "segments"):
            segment_results = index.search(q, limit=limit, fields=field_list, project_id=project_id)
            results["segments"] = [_segment_to_dict(s) for s in segment_results]
            results["segment_count"] = len(segment_results)

        if search_type in ("all", "clusters"):
            cluster_results = index.search_clusters(q, limit=limit, fields=field_list, project_id=project_id)
            results["clusters"] = cluster_results
            results["cluster_count"] = len(cluster_results)

        return results

    @app.get("/api/search/semantic")
    async def semantic_search(
        q: str = Query(..., min_length=1, description="Search query"),
        limit: int = Query(default=20, le=100, description="Max results"),
        search_type: str = Query(default="both", description="Search type: segments, clusters, both"),
        project: Optional[str] = Query(default=None, description="Filter by project slug or ID"),
    ):
        """Semantic search using vector embeddings.

        Unlike keyword search, semantic search understands meaning:
        - "person looking worried" finds "anxious expression", "concerned face"
        - "establishing shot of city" finds "urban skyline", "downtown aerial"
        """
        from nolan.vector_search import VectorSearch

        # Vector DB path alongside SQLite
        vector_db_path = db_path.parent / "vectors"

        if not vector_db_path.exists():
            raise HTTPException(
                status_code=503,
                detail="Vector database not found. Run 'nolan sync-vectors' first."
            )

        vector_search = VectorSearch(vector_db_path, index=index)

        # Check if vectors exist
        stats = vector_search.get_stats()
        if stats['segments'] == 0 and stats['clusters'] == 0:
            raise HTTPException(
                status_code=503,
                detail="Vector database is empty. Run 'nolan sync-vectors' first."
            )

        # Resolve project
        project_id = None
        if project:
            resolved = index.resolve_project(project)
            if resolved:
                project_id = resolved
            else:
                project_id = project

        # Perform search
        results = vector_search.search(
            query=q,
            limit=limit,
            search_level=search_type,
            project_id=project_id
        )

        # Format results for API response
        formatted_results = []
        for r in results:
            formatted_results.append({
                "score": r.score,
                "score_percent": f"{r.score * 100:.1f}%",
                "content_type": r.content_type,
                "video_path": r.video_path,
                "video_name": Path(r.video_path).name if r.video_path else "",
                "timestamp_start": r.timestamp_start,
                "timestamp_end": r.timestamp_end,
                "timestamp_formatted": f"{int(r.timestamp_start // 60):02d}:{int(r.timestamp_start % 60):02d}",
                "description": r.description,
                "transcript": r.transcript,
                "people": r.people,
                "location": r.location,
                "objects": r.objects,
            })

        return {
            "query": q,
            "search_type": search_type,
            "project_filter": project,
            "results": formatted_results,
            "total": len(formatted_results),
            "vector_stats": stats,
        }

    @app.get("/api/search/fields")
    async def get_search_fields():
        """Get available search fields."""
        return {
            "segment_fields": [
                {"id": "frame_description", "label": "Frame Description"},
                {"id": "transcript", "label": "Transcript"},
                {"id": "combined_summary", "label": "Combined Summary"},
                {"id": "people", "label": "People"},
                {"id": "location", "label": "Location"},
                {"id": "story_context", "label": "Story Context"},
                {"id": "objects", "label": "Objects"},
            ],
            "cluster_fields": [
                {"id": "cluster_summary", "label": "Cluster Summary"},
                {"id": "people", "label": "People"},
                {"id": "locations", "label": "Locations"},
            ],
        }

    @app.get("/api/stats")
    async def get_stats():
        """Get library statistics."""
        with sqlite3.connect(db_path) as conn:
            video_count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            segment_count = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
            total_duration = conn.execute("SELECT SUM(duration) FROM videos").fetchone()[0] or 0

            return {
                "video_count": video_count,
                "segment_count": segment_count,
                "total_duration": total_duration,
                "total_duration_formatted": _format_duration(total_duration),
            }

    @app.get("/video/{video_path:path}")
    async def serve_video(video_path: str):
        """Serve a video file for playback."""
        video_path = unquote(video_path)
        file_path = Path(video_path)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")

        # Determine media type
        suffix = file_path.suffix.lower()
        media_types = {
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
        }
        media_type = media_types.get(suffix, "video/mp4")

        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=file_path.name,
        )

    return app


def _format_duration(seconds: Optional[float]) -> str:
    """Format duration in seconds to HH:MM:SS or MM:SS."""
    if seconds is None or seconds <= 0:
        return "0:00"

    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _segment_to_dict(segment: VideoSegment) -> dict:
    """Convert a VideoSegment to a dictionary for JSON response."""
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
    """Convert a computed SceneCluster to a dictionary for JSON response."""
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


def _stored_cluster_to_dict(cluster: dict, index: VideoIndex) -> dict:
    """Convert a stored cluster dict to response format with segment data."""
    # Format timestamp
    start = cluster.get("timestamp_start", 0)
    end = cluster.get("timestamp_end", 0)
    start_min = int(start // 60)
    start_sec = int(start % 60)
    end_min = int(end // 60)
    end_sec = int(end % 60)
    timestamp_formatted = f"{start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}"

    # Get segments for this cluster
    segments = []
    video_path = cluster.get("video_path")
    if video_path:
        all_segments = index.get_segments(video_path)
        # Filter to segments within cluster time range
        segments = [
            _segment_to_dict(s) for s in all_segments
            if s.timestamp_start >= start and s.timestamp_end <= end + 0.1
        ]

    return {
        "id": cluster.get("cluster_index", cluster.get("id", 0)),
        "timestamp_start": start,
        "timestamp_end": end,
        "timestamp_formatted": timestamp_formatted,
        "duration": end - start,
        "segment_count": len(segments),
        "cluster_summary": cluster.get("cluster_summary"),
        "people": cluster.get("people", []),
        "locations": cluster.get("locations", []),
        "combined_transcript": "",  # Would need to be computed from segments
        "segments": segments,
    }


def run_library_server(db_path: Path, host: str = "127.0.0.1", port: int = 8001):
    """Run the library viewer server.

    Args:
        db_path: Path to SQLite database.
        host: Server host.
        port: Server port.
    """
    import uvicorn
    import webbrowser

    app = create_library_app(db_path)

    # Open browser
    webbrowser.open(f"http://{host}:{port}")

    # Run server
    uvicorn.run(app, host=host, port=port)
