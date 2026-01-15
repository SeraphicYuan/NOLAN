"""Video library indexing for NOLAN."""

import sqlite3
import hashlib
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class InferredContext:
    """Inferred context from visual + audio analysis."""
    people: List[str] = field(default_factory=list)
    location: Optional[str] = None
    story_context: Optional[str] = None
    objects: List[str] = field(default_factory=list)
    confidence: str = "low"  # high, medium, low

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "people": self.people,
            "location": self.location,
            "story_context": self.story_context,
            "objects": self.objects,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InferredContext":
        """Create from dictionary."""
        if data is None:
            return cls()
        return cls(
            people=data.get("people", []),
            location=data.get("location"),
            story_context=data.get("story_context"),
            objects=data.get("objects", []),
            confidence=data.get("confidence", "low"),
        )


@dataclass
class VideoSegment:
    """A segment of indexed video with hybrid data."""
    video_path: str
    timestamp_start: float
    timestamp_end: float
    frame_description: str
    transcript: Optional[str] = None
    combined_summary: Optional[str] = None
    inferred_context: Optional[InferredContext] = None
    sample_reason: Optional[str] = None

    # Legacy alias for backward compatibility
    @property
    def timestamp(self) -> float:
        """Legacy timestamp property."""
        return self.timestamp_start

    @property
    def description(self) -> str:
        """Legacy description property (returns combined or frame description)."""
        return self.combined_summary or self.frame_description

    @property
    def timestamp_formatted(self) -> str:
        """Format timestamp as MM:SS."""
        minutes = int(self.timestamp_start // 60)
        seconds = int(self.timestamp_start % 60)
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def duration(self) -> float:
        """Duration of this segment in seconds."""
        return self.timestamp_end - self.timestamp_start


class VideoIndex:
    """SQLite-backed video index with content-based fingerprints."""

    # Schema version for migrations
    SCHEMA_VERSION = 3

    def __init__(self, db_path: Path):
        """Initialize the index.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            # Check schema version
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
            cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            current_version = row[0] if row else 0

            if current_version < 2:
                self._migrate_to_v2(conn, current_version)
            if current_version < 3:
                self._migrate_to_v3(conn)

            # Create tables with new schema
            conn.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT UNIQUE NOT NULL,
                    path TEXT,
                    duration REAL,
                    checksum TEXT,
                    indexed_at TEXT,
                    has_transcript INTEGER DEFAULT 0,
                    project_id TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL,
                    timestamp_start REAL,
                    timestamp_end REAL,
                    frame_description TEXT,
                    transcript TEXT,
                    combined_summary TEXT,
                    inferred_context TEXT,
                    sample_reason TEXT,
                    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL,
                    cluster_index INTEGER,
                    timestamp_start REAL,
                    timestamp_end REAL,
                    cluster_summary TEXT,
                    people TEXT,
                    locations TEXT,
                    segment_ids TEXT,
                    created_at TEXT,
                    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_segments_video ON segments(video_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_video ON clusters(video_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_fingerprint ON videos(fingerprint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_project ON videos(project_id)")
            conn.commit()

    def _migrate_to_v2(self, conn: sqlite3.Connection, from_version: int) -> None:
        """Migrate from old schema to v2 (fingerprint-based)."""
        # Check if old tables exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='videos'")
        if cursor.fetchone() is None:
            # Fresh install, no migration needed
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))
            return

        # Check if already migrated (has fingerprint column)
        cursor = conn.execute("PRAGMA table_info(videos)")
        columns = {row[1] for row in cursor.fetchall()}
        if "fingerprint" in columns:
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))
            return

        # Migrate old schema: rename old tables, create new, copy data
        conn.execute("ALTER TABLE videos RENAME TO videos_old")
        conn.execute("ALTER TABLE segments RENAME TO segments_old")

        # Create new tables
        conn.execute("""
            CREATE TABLE videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT UNIQUE NOT NULL,
                path TEXT,
                duration REAL,
                checksum TEXT,
                indexed_at TEXT,
                has_transcript INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER NOT NULL,
                timestamp_start REAL,
                timestamp_end REAL,
                frame_description TEXT,
                transcript TEXT,
                combined_summary TEXT,
                inferred_context TEXT,
                sample_reason TEXT,
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
            )
        """)

        # Copy videos with checksum as temporary fingerprint (will be updated on next index)
        conn.execute("""
            INSERT INTO videos (fingerprint, path, duration, checksum, indexed_at, has_transcript)
            SELECT COALESCE(checksum, path), path, duration, checksum, indexed_at,
                   COALESCE(has_transcript, 0)
            FROM videos_old
        """)

        # Check which columns exist in old segments table
        cursor = conn.execute("PRAGMA table_info(segments_old)")
        old_seg_columns = {row[1] for row in cursor.fetchall()}

        # Build the SELECT clause based on available columns
        desc_col = "s.frame_description" if "frame_description" in old_seg_columns else "s.description"
        ts_start = "s.timestamp_start" if "timestamp_start" in old_seg_columns else "s.timestamp"
        ts_end = "s.timestamp_end" if "timestamp_end" in old_seg_columns else "NULL"

        # Copy segments with video_id lookup
        conn.execute(f"""
            INSERT INTO segments (video_id, timestamp_start, timestamp_end, frame_description,
                                  transcript, combined_summary, inferred_context, sample_reason)
            SELECT v.id, {ts_start}, {ts_end},
                   {desc_col},
                   {"s.transcript" if "transcript" in old_seg_columns else "NULL"},
                   {"s.combined_summary" if "combined_summary" in old_seg_columns else "NULL"},
                   {"s.inferred_context" if "inferred_context" in old_seg_columns else "NULL"},
                   {"s.sample_reason" if "sample_reason" in old_seg_columns else "NULL"}
            FROM segments_old s
            JOIN videos v ON v.path = s.video_path
        """)

        # Drop old tables
        conn.execute("DROP TABLE segments_old")
        conn.execute("DROP TABLE videos_old")

        # Update schema version
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (2,))

        conn.commit()

    def _migrate_to_v3(self, conn: sqlite3.Connection) -> None:
        """Migrate to v3 schema (add project_id column)."""
        # Check if project_id column exists
        cursor = conn.execute("PRAGMA table_info(videos)")
        columns = {row[1] for row in cursor.fetchall()}

        if "project_id" not in columns:
            conn.execute("ALTER TABLE videos ADD COLUMN project_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_project ON videos(project_id)")

        # Update schema version
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))
        conn.commit()

    def add_video(self, path: str, duration: float, checksum: str, fingerprint: str,
                  project_id: Optional[str] = None) -> int:
        """Add or update a video in the index.

        Args:
            path: Path to video file.
            duration: Video duration in seconds.
            checksum: File checksum for change detection.
            fingerprint: Content-based fingerprint for stable identification.
            project_id: Optional project ID to associate this video with.

        Returns:
            The video_id of the inserted/updated video.
        """
        with sqlite3.connect(self.db_path) as conn:
            # Check if video exists by fingerprint
            cursor = conn.execute(
                "SELECT id FROM videos WHERE fingerprint = ?", (fingerprint,)
            )
            row = cursor.fetchone()

            if row:
                # Update existing video (path and project may have changed)
                video_id = row[0]
                conn.execute("""
                    UPDATE videos SET path = ?, duration = ?, checksum = ?, indexed_at = ?,
                                      project_id = COALESCE(?, project_id)
                    WHERE id = ?
                """, (path, duration, checksum, datetime.now().isoformat(), project_id, video_id))
            else:
                # Insert new video
                cursor = conn.execute("""
                    INSERT INTO videos (fingerprint, path, duration, checksum, indexed_at, project_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (fingerprint, path, duration, checksum, datetime.now().isoformat(), project_id))
                video_id = cursor.lastrowid

            conn.commit()
            return video_id

    def get_video_id(self, fingerprint: str) -> Optional[int]:
        """Get video ID by fingerprint.

        Args:
            fingerprint: Video fingerprint.

        Returns:
            Video ID or None if not found.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id FROM videos WHERE fingerprint = ?", (fingerprint,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_video_id_by_path(self, path: str) -> Optional[int]:
        """Get video ID by path (for backwards compatibility).

        Args:
            path: Video file path.

        Returns:
            Video ID or None if not found.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id FROM videos WHERE path = ?", (path,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_videos_by_project(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all videos belonging to a project.

        Args:
            project_id: Project ID to filter by.

        Returns:
            List of video dictionaries with id, path, duration, indexed_at.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, path, duration, indexed_at, fingerprint
                FROM videos
                WHERE project_id = ?
                ORDER BY indexed_at DESC
            """, (project_id,))
            return [
                {
                    "id": row[0],
                    "path": row[1],
                    "duration": row[2],
                    "indexed_at": row[3],
                    "fingerprint": row[4],
                }
                for row in cursor.fetchall()
            ]

    def get_all_projects(self) -> List[str]:
        """Get all unique project IDs in the index.

        Returns:
            List of project IDs.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT DISTINCT project_id FROM videos
                WHERE project_id IS NOT NULL
                ORDER BY project_id
            """)
            return [row[0] for row in cursor.fetchall()]

    def set_video_project(self, video_id: int, project_id: str) -> None:
        """Set the project ID for a video.

        Args:
            video_id: Video ID.
            project_id: Project ID to set.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE videos SET project_id = ? WHERE id = ?",
                (project_id, video_id)
            )
            conn.commit()

    def add_segment(
        self,
        video_id: int,
        timestamp_start: float,
        timestamp_end: float,
        frame_description: str,
        transcript: Optional[str] = None,
        combined_summary: Optional[str] = None,
        inferred_context: Optional[InferredContext] = None,
        sample_reason: Optional[str] = None
    ) -> int:
        """Add a segment to the index.

        Args:
            video_id: ID of the video this segment belongs to.
            timestamp_start: Start timestamp in seconds.
            timestamp_end: End timestamp in seconds.
            frame_description: Visual description from vision model.
            transcript: Transcript text for this segment.
            combined_summary: LLM-fused summary of visual + audio.
            inferred_context: Inferred context (people, location, etc.).
            sample_reason: Why this frame was sampled.

        Returns:
            The segment_id of the inserted segment.
        """
        context_json = json.dumps(inferred_context.to_dict()) if inferred_context else None

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO segments (
                    video_id, timestamp_start, timestamp_end,
                    frame_description, transcript, combined_summary,
                    inferred_context, sample_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                video_id, timestamp_start, timestamp_end,
                frame_description, transcript, combined_summary,
                context_json, sample_reason
            ))
            conn.commit()
            return cursor.lastrowid

    def get_segments(self, video_path: str) -> List[VideoSegment]:
        """Get all segments for a video by path.

        Args:
            video_path: Path to video file.

        Returns:
            List of VideoSegment objects.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT v.path, s.timestamp_start, s.timestamp_end,
                       s.frame_description, s.transcript, s.combined_summary,
                       s.inferred_context, s.sample_reason
                FROM segments s
                JOIN videos v ON v.id = s.video_id
                WHERE v.path = ?
                ORDER BY s.timestamp_start
            """, (video_path,))

            return self._rows_to_segments(cursor.fetchall())

    def get_segments_by_video_id(self, video_id: int) -> List[VideoSegment]:
        """Get all segments for a video by ID.

        Args:
            video_id: Video ID.

        Returns:
            List of VideoSegment objects.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT v.path, s.timestamp_start, s.timestamp_end,
                       s.frame_description, s.transcript, s.combined_summary,
                       s.inferred_context, s.sample_reason
                FROM segments s
                JOIN videos v ON v.id = s.video_id
                WHERE s.video_id = ?
                ORDER BY s.timestamp_start
            """, (video_id,))

            return self._rows_to_segments(cursor.fetchall())

    def _rows_to_segments(self, rows) -> List[VideoSegment]:
        """Convert database rows to VideoSegment objects."""
        segments = []
        for row in rows:
            context_data = json.loads(row[6]) if row[6] else None
            segments.append(VideoSegment(
                video_path=row[0],
                timestamp_start=row[1] or 0,
                timestamp_end=row[2] or 0,
                frame_description=row[3] or "",
                transcript=row[4],
                combined_summary=row[5],
                inferred_context=InferredContext.from_dict(context_data) if context_data else None,
                sample_reason=row[7]
            ))
        return segments

    def needs_indexing(self, fingerprint: str, current_checksum: str) -> bool:
        """Check if a video needs (re)indexing.

        Args:
            fingerprint: Video fingerprint.
            current_checksum: Current file checksum.

        Returns:
            True if indexing is needed.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT checksum FROM videos WHERE fingerprint = ?",
                (fingerprint,)
            )
            row = cursor.fetchone()

            if row is None:
                return True

            return row[0] != current_checksum

    def clear_segments(self, video_id: int) -> None:
        """Clear all segments for a video (for reindexing).

        Args:
            video_id: Video ID.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM segments WHERE video_id = ?", (video_id,))
            conn.execute("DELETE FROM clusters WHERE video_id = ?", (video_id,))
            conn.commit()

    def search(
        self,
        query: str,
        limit: int = 10,
        fields: Optional[List[str]] = None,
        project_id: Optional[str] = None
    ) -> List[VideoSegment]:
        """Search for segments matching a query.

        Args:
            query: Search query (keywords).
            limit: Maximum results to return.
            fields: Optional list of fields to search. If None, searches all fields.
                    Valid fields: frame_description, transcript, combined_summary,
                                  people, location, story_context, objects
            project_id: Optional project ID to filter by. If None, searches all projects.

        Returns:
            List of matching VideoSegment objects.
        """
        keywords = query.lower().split()
        search_all = fields is None or len(fields) == 0

        with sqlite3.connect(self.db_path) as conn:
            sql = """
                SELECT v.path, s.timestamp_start, s.timestamp_end,
                       s.frame_description, s.transcript, s.combined_summary,
                       s.inferred_context, s.sample_reason
                FROM segments s
                JOIN videos v ON v.id = s.video_id
            """
            params = []
            if project_id:
                sql += " WHERE v.project_id = ?"
                params.append(project_id)
            cursor = conn.execute(sql, params)

            results = []
            for row in cursor.fetchall():
                searchable_parts = []

                # Add fields based on selection
                if search_all or "frame_description" in fields:
                    searchable_parts.append(row[3] or "")
                if search_all or "transcript" in fields:
                    searchable_parts.append(row[4] or "")
                if search_all or "combined_summary" in fields:
                    searchable_parts.append(row[5] or "")

                # Add inferred context fields
                if row[6]:
                    try:
                        ctx = json.loads(row[6])
                        if search_all or "people" in fields:
                            searchable_parts.extend(ctx.get("people", []))
                        if search_all or "location" in fields:
                            if ctx.get("location"):
                                searchable_parts.append(ctx["location"])
                        if search_all or "story_context" in fields:
                            if ctx.get("story_context"):
                                searchable_parts.append(ctx["story_context"])
                        if search_all or "objects" in fields:
                            searchable_parts.extend(ctx.get("objects", []))
                    except json.JSONDecodeError:
                        pass

                searchable = " ".join(searchable_parts).lower()

                # Score by number of matching keywords
                score = sum(1 for kw in keywords if kw in searchable)
                if score > 0:
                    context_data = json.loads(row[6]) if row[6] else None
                    results.append((score, VideoSegment(
                        video_path=row[0],
                        timestamp_start=row[1] or 0,
                        timestamp_end=row[2] or 0,
                        frame_description=row[3] or "",
                        transcript=row[4],
                        combined_summary=row[5],
                        inferred_context=InferredContext.from_dict(context_data) if context_data else None,
                        sample_reason=row[7]
                    )))

            # Sort by score descending
            results.sort(key=lambda x: x[0], reverse=True)
            return [seg for _, seg in results[:limit]]

    # ==================== Cluster Methods ====================

    def add_cluster(
        self,
        video_id: int,
        cluster_index: int,
        timestamp_start: float,
        timestamp_end: float,
        cluster_summary: Optional[str] = None,
        people: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        segment_ids: Optional[List[int]] = None
    ) -> int:
        """Add a cluster to the index.

        Args:
            video_id: ID of the video this cluster belongs to.
            cluster_index: Order of the cluster within the video.
            timestamp_start: Start timestamp in seconds.
            timestamp_end: End timestamp in seconds.
            cluster_summary: LLM-generated summary of the cluster.
            people: List of people in this cluster.
            locations: List of locations in this cluster.
            segment_ids: List of segment IDs in this cluster.

        Returns:
            The cluster_id of the inserted cluster.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO clusters (
                    video_id, cluster_index, timestamp_start, timestamp_end,
                    cluster_summary, people, locations, segment_ids, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                video_id, cluster_index, timestamp_start, timestamp_end,
                cluster_summary,
                json.dumps(people) if people else None,
                json.dumps(locations) if locations else None,
                json.dumps(segment_ids) if segment_ids else None,
                datetime.now().isoformat()
            ))
            conn.commit()
            return cursor.lastrowid

    def get_clusters(self, video_path: str) -> List[Dict[str, Any]]:
        """Get all clusters for a video by path.

        Args:
            video_path: Path to video file.

        Returns:
            List of cluster dictionaries.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT c.id, c.cluster_index, c.timestamp_start, c.timestamp_end,
                       c.cluster_summary, c.people, c.locations, c.segment_ids,
                       v.path
                FROM clusters c
                JOIN videos v ON v.id = c.video_id
                WHERE v.path = ?
                ORDER BY c.cluster_index
            """, (video_path,))

            return self._rows_to_clusters(cursor.fetchall())

    def get_clusters_by_video_id(self, video_id: int) -> List[Dict[str, Any]]:
        """Get all clusters for a video by ID.

        Args:
            video_id: Video ID.

        Returns:
            List of cluster dictionaries.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT c.id, c.cluster_index, c.timestamp_start, c.timestamp_end,
                       c.cluster_summary, c.people, c.locations, c.segment_ids,
                       v.path
                FROM clusters c
                JOIN videos v ON v.id = c.video_id
                WHERE c.video_id = ?
                ORDER BY c.cluster_index
            """, (video_id,))

            return self._rows_to_clusters(cursor.fetchall())

    def _rows_to_clusters(self, rows) -> List[Dict[str, Any]]:
        """Convert database rows to cluster dictionaries."""
        clusters = []
        for row in rows:
            clusters.append({
                "id": row[0],
                "cluster_index": row[1],
                "timestamp_start": row[2],
                "timestamp_end": row[3],
                "cluster_summary": row[4],
                "people": json.loads(row[5]) if row[5] else [],
                "locations": json.loads(row[6]) if row[6] else [],
                "segment_ids": json.loads(row[7]) if row[7] else [],
                "video_path": row[8],
            })
        return clusters

    def search_clusters(
        self,
        query: str,
        limit: int = 10,
        fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search for clusters matching a query.

        Args:
            query: Search query (keywords).
            limit: Maximum results to return.
            fields: Optional list of fields to search. If None, searches all fields.
                    Valid fields: cluster_summary, people, locations

        Returns:
            List of matching cluster dictionaries.
        """
        keywords = query.lower().split()
        search_all = fields is None or len(fields) == 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT c.id, c.cluster_index, c.timestamp_start, c.timestamp_end,
                       c.cluster_summary, c.people, c.locations, c.segment_ids,
                       v.path
                FROM clusters c
                JOIN videos v ON v.id = c.video_id
            """)

            results = []
            for row in cursor.fetchall():
                searchable_parts = []

                if search_all or "cluster_summary" in fields:
                    searchable_parts.append(row[4] or "")
                if search_all or "people" in fields:
                    if row[5]:
                        try:
                            searchable_parts.extend(json.loads(row[5]))
                        except json.JSONDecodeError:
                            pass
                if search_all or "locations" in fields:
                    if row[6]:
                        try:
                            searchable_parts.extend(json.loads(row[6]))
                        except json.JSONDecodeError:
                            pass

                searchable = " ".join(searchable_parts).lower()

                # Score by number of matching keywords
                score = sum(1 for kw in keywords if kw in searchable)
                if score > 0:
                    results.append((score, {
                        "id": row[0],
                        "cluster_index": row[1],
                        "timestamp_start": row[2],
                        "timestamp_end": row[3],
                        "cluster_summary": row[4],
                        "people": json.loads(row[5]) if row[5] else [],
                        "locations": json.loads(row[6]) if row[6] else [],
                        "segment_ids": json.loads(row[7]) if row[7] else [],
                        "video_path": row[8],
                    }))

            # Sort by score descending
            results.sort(key=lambda x: x[0], reverse=True)
            return [cluster for _, cluster in results[:limit]]


def compute_checksum(path: Path, chunk_size: int = 8192) -> str:
    """Compute MD5 checksum of a file.

    Args:
        path: Path to file.
        chunk_size: Read chunk size.

    Returns:
        Hex digest of file checksum.
    """
    hasher = hashlib.md5()
    with open(path, 'rb') as f:
        # Only hash first and last chunks for speed
        hasher.update(f.read(chunk_size))
        f.seek(-min(chunk_size, path.stat().st_size), 2)
        hasher.update(f.read(chunk_size))
    return hasher.hexdigest()


def compute_video_fingerprint(path: Path) -> str:
    """Generate stable content-based ID for a video file.

    This fingerprint survives file moves/renames but changes if content changes.
    Combines file size, duration, and sampled content from start/middle/end.

    Args:
        path: Path to video file.

    Returns:
        16-character hex fingerprint.
    """
    import cv2

    file_size = path.stat().st_size

    # Get duration from video metadata (fast)
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps if fps > 0 else 0
    cap.release()

    # Build fingerprint from multiple signals
    hasher = hashlib.sha256()
    hasher.update(f"size:{file_size}".encode())
    hasher.update(f"duration:{duration:.3f}".encode())

    chunk_size = 65536  # 64KB chunks

    with open(path, 'rb') as f:
        # First chunk
        hasher.update(f.read(chunk_size))

        # Middle chunk
        if file_size > chunk_size * 3:
            f.seek(file_size // 2)
            hasher.update(f.read(chunk_size))

        # Last chunk
        f.seek(-min(chunk_size, file_size), 2)
        hasher.update(f.read(chunk_size))

    return hasher.hexdigest()[:16]


class HybridVideoIndexer:
    """Indexes video files using visual analysis with optional transcript fusion."""

    def __init__(
        self,
        vision_provider,
        index: VideoIndex,
        sampler=None,
        llm_client=None,
        whisper_transcriber=None,
        enable_transcript: bool = True,
        enable_inference: bool = True,
        project_id: Optional[str] = None
    ):
        """Initialize the hybrid indexer.

        Args:
            vision_provider: VisionProvider for frame analysis.
            index: VideoIndex for storage.
            sampler: FrameSampler for smart sampling (optional, uses hybrid by default).
            llm_client: LLM client for fusion/inference (optional, needed if enable_inference=True).
            whisper_transcriber: WhisperTranscriber for auto-generating transcripts.
            enable_transcript: Whether to look for and use transcripts.
            enable_inference: Whether to run LLM fusion and inference.
            project_id: Optional project ID to associate indexed videos with.
        """
        self.vision = vision_provider
        self.index = index
        self.sampler = sampler
        self.llm = llm_client
        self.whisper = whisper_transcriber
        self.enable_transcript = enable_transcript
        self.enable_inference = enable_inference
        self.project_id = project_id

        # Lazy import analyzer
        self._analyzer = None

    def _get_analyzer(self):
        """Get or create segment analyzer."""
        if self._analyzer is None and self.llm is not None:
            from nolan.analyzer import SegmentAnalyzer
            self._analyzer = SegmentAnalyzer(self.llm)
        return self._analyzer

    def _get_sampler(self):
        """Get or create default sampler."""
        if self.sampler is None:
            from nolan.sampler import HybridSampler
            self.sampler = HybridSampler()
        return self.sampler

    async def index_video(
        self,
        video_path: Path,
        progress_callback=None
    ) -> int:
        """Index a single video file with hybrid approach.

        Args:
            video_path: Path to video file.
            progress_callback: Optional callback(current, total, message).

        Returns:
            Number of segments indexed.
        """
        import cv2
        import tempfile

        # Compute fingerprint and checksum
        fingerprint = compute_video_fingerprint(video_path)
        checksum = compute_checksum(video_path)

        if not self.index.needs_indexing(fingerprint, checksum):
            return 0  # Already indexed

        # Get video duration
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        cap.release()

        # Add video to index (returns video_id)
        video_id = self.index.add_video(str(video_path), duration, checksum, fingerprint,
                                         project_id=self.project_id)

        # Clear old segments if reindexing
        self.index.clear_segments(video_id)

        # Load transcript if available
        transcript = None
        if self.enable_transcript:
            from nolan.transcript import find_transcript_for_video, TranscriptLoader
            transcript_path = find_transcript_for_video(video_path)

            # Try loading existing transcript
            if transcript_path:
                try:
                    transcript = TranscriptLoader.load(transcript_path)
                except Exception:
                    pass  # Continue without transcript

            # Generate transcript with Whisper if none found
            if transcript is None and self.whisper is not None:
                try:
                    generated_path = self.whisper.transcribe_video(video_path)
                    if generated_path:
                        transcript = TranscriptLoader.load(generated_path)
                except Exception:
                    pass  # Continue without transcript

        # Sample frames
        sampler = self._get_sampler()
        frames_data = []

        for sampled in sampler.sample(video_path):
            frames_data.append({
                "timestamp": sampled.timestamp,
                "frame": sampled.frame,
                "reason": sampled.reason
            })

        if not frames_data:
            return 0

        # Calculate end timestamps
        for i in range(len(frames_data)):
            if i + 1 < len(frames_data):
                frames_data[i]["end"] = frames_data[i + 1]["timestamp"]
            else:
                frames_data[i]["end"] = duration

        # Align transcript if available
        if transcript:
            timestamps = [f["timestamp"] for f in frames_data]
            aligned_texts = transcript.align_to_frames(timestamps)
            for i, text in enumerate(aligned_texts):
                frames_data[i]["transcript"] = text

        # Process each frame
        segments_added = 0
        total = len(frames_data)
        analyzer = self._get_analyzer()

        for i, frame_data in enumerate(frames_data):
            if progress_callback:
                progress_callback(i + 1, total, f"Frame at {frame_data['timestamp']:.1f}s")

            # Save frame temporarily
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                cv2.imwrite(tmp.name, frame_data["frame"])
                tmp_path = Path(tmp.name)

            try:
                # Get frame description from vision model
                frame_description = await self.vision.describe_image(
                    tmp_path,
                    "Describe this video frame in one sentence. Focus on the main subject, action, and setting."
                )
                frame_description = frame_description.strip()

                # Get transcript for this segment
                segment_transcript = frame_data.get("transcript")

                # Run fusion and inference if enabled
                combined_summary = None
                inferred_context = None

                if self.enable_inference and analyzer and segment_transcript:
                    from nolan.analyzer import AnalysisResult
                    result = await analyzer.analyze(
                        frame_description=frame_description,
                        transcript=segment_transcript,
                        timestamp=frame_data["timestamp"]
                    )
                    combined_summary = result.combined_summary
                    inferred_context = result.inferred_context

                # Add segment to index
                self.index.add_segment(
                    video_id=video_id,
                    timestamp_start=frame_data["timestamp"],
                    timestamp_end=frame_data["end"],
                    frame_description=frame_description,
                    transcript=segment_transcript,
                    combined_summary=combined_summary,
                    inferred_context=inferred_context,
                    sample_reason=frame_data["reason"]
                )
                segments_added += 1

            finally:
                tmp_path.unlink(missing_ok=True)

        return segments_added

    async def index_directory(
        self,
        directory: Path,
        recursive: bool = True,
        progress_callback=None
    ) -> dict:
        """Index all videos in a directory.

        Args:
            directory: Directory to scan.
            recursive: Whether to scan subdirectories.
            progress_callback: Optional callback(video_num, total_videos, video_path).

        Returns:
            Dict with indexing statistics.
        """
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}

        pattern = '**/*' if recursive else '*'
        videos = [
            p for p in directory.glob(pattern)
            if p.suffix.lower() in video_extensions
        ]

        stats = {'total': len(videos), 'indexed': 0, 'skipped': 0, 'segments': 0}

        for i, video_path in enumerate(videos):
            if progress_callback:
                progress_callback(i + 1, len(videos), str(video_path))

            segments = await self.index_video(video_path)
            if segments > 0:
                stats['indexed'] += 1
                stats['segments'] += segments
            else:
                stats['skipped'] += 1

        return stats


# Backward compatibility alias
class VideoIndexer(HybridVideoIndexer):
    """Legacy alias for HybridVideoIndexer."""

    def __init__(self, llm_client, index: VideoIndex, frame_interval: int = 5):
        """Initialize with legacy signature.

        Args:
            llm_client: LLM client (used as both vision and text).
            index: VideoIndex for storage.
            frame_interval: Seconds between sampled frames.
        """
        from nolan.sampler import FixedIntervalSampler
        super().__init__(
            vision_provider=llm_client,  # Assumes generate_with_image method
            index=index,
            sampler=FixedIntervalSampler(interval=frame_interval),
            llm_client=llm_client,
            enable_transcript=True,
            enable_inference=True
        )
