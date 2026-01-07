"""Video library indexing for NOLAN."""

import sqlite3
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class VideoSegment:
    """A segment of indexed video."""
    video_path: str
    timestamp: float
    description: str

    @property
    def timestamp_formatted(self) -> str:
        """Format timestamp as MM:SS."""
        minutes = int(self.timestamp // 60)
        seconds = int(self.timestamp % 60)
        return f"{minutes:02d}:{seconds:02d}"


class VideoIndex:
    """SQLite-backed video index."""

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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    path TEXT PRIMARY KEY,
                    duration REAL,
                    checksum TEXT,
                    indexed_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_path TEXT,
                    timestamp REAL,
                    description TEXT,
                    FOREIGN KEY (video_path) REFERENCES videos(path)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_segments_video
                ON segments(video_path)
            """)
            conn.commit()

    def add_video(self, path: str, duration: float, checksum: str) -> None:
        """Add or update a video in the index.

        Args:
            path: Path to video file.
            duration: Video duration in seconds.
            checksum: File checksum for change detection.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO videos (path, duration, checksum, indexed_at)
                VALUES (?, ?, ?, ?)
            """, (path, duration, checksum, datetime.now().isoformat()))
            conn.commit()

    def add_segment(self, video_path: str, timestamp: float, description: str) -> None:
        """Add a segment to the index.

        Args:
            video_path: Path to source video.
            timestamp: Timestamp in seconds.
            description: Visual description of the segment.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO segments (video_path, timestamp, description)
                VALUES (?, ?, ?)
            """, (video_path, timestamp, description))
            conn.commit()

    def get_segments(self, video_path: str) -> List[VideoSegment]:
        """Get all segments for a video.

        Args:
            video_path: Path to video file.

        Returns:
            List of VideoSegment objects.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT video_path, timestamp, description
                FROM segments
                WHERE video_path = ?
                ORDER BY timestamp
            """, (video_path,))

            return [
                VideoSegment(
                    video_path=row[0],
                    timestamp=row[1],
                    description=row[2]
                )
                for row in cursor.fetchall()
            ]

    def needs_indexing(self, path: str, current_checksum: str) -> bool:
        """Check if a video needs (re)indexing.

        Args:
            path: Path to video file.
            current_checksum: Current file checksum.

        Returns:
            True if indexing is needed.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT checksum FROM videos WHERE path = ?",
                (path,)
            )
            row = cursor.fetchone()

            if row is None:
                return True

            return row[0] != current_checksum

    def clear_segments(self, video_path: str) -> None:
        """Clear all segments for a video (for reindexing).

        Args:
            video_path: Path to video file.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM segments WHERE video_path = ?",
                (video_path,)
            )
            conn.commit()

    def search(self, query: str, limit: int = 10) -> List[VideoSegment]:
        """Search for segments matching a query.

        Args:
            query: Search query (keywords).
            limit: Maximum results to return.

        Returns:
            List of matching VideoSegment objects.
        """
        # Simple keyword matching (can be improved with embeddings later)
        keywords = query.lower().split()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT video_path, timestamp, description
                FROM segments
            """)

            results = []
            for row in cursor.fetchall():
                description = row[2].lower()
                # Score by number of matching keywords
                score = sum(1 for kw in keywords if kw in description)
                if score > 0:
                    results.append((score, VideoSegment(
                        video_path=row[0],
                        timestamp=row[1],
                        description=row[2]
                    )))

            # Sort by score descending
            results.sort(key=lambda x: x[0], reverse=True)
            return [seg for _, seg in results[:limit]]


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


class VideoIndexer:
    """Indexes video files using visual analysis."""

    def __init__(self, llm_client, index: VideoIndex, frame_interval: int = 5):
        """Initialize the indexer.

        Args:
            llm_client: LLM client for visual analysis.
            index: VideoIndex for storage.
            frame_interval: Seconds between sampled frames.
        """
        self.llm = llm_client
        self.index = index
        self.frame_interval = frame_interval

    async def index_video(self, video_path: Path) -> int:
        """Index a single video file.

        Args:
            video_path: Path to video file.

        Returns:
            Number of segments indexed.
        """
        import cv2
        import tempfile

        checksum = compute_checksum(video_path)

        if not self.index.needs_indexing(str(video_path), checksum):
            return 0  # Already indexed

        # Clear old segments if reindexing
        self.index.clear_segments(str(video_path))

        # Open video
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        # Add video to index
        self.index.add_video(str(video_path), duration, checksum)

        # Sample frames
        frame_skip = int(fps * self.frame_interval)
        segments_added = 0

        frame_num = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_num % frame_skip == 0:
                timestamp = frame_num / fps

                # Save frame temporarily
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    cv2.imwrite(tmp.name, frame)
                    tmp_path = tmp.name

                try:
                    # Analyze with LLM
                    description = await self.llm.generate_with_image(
                        "Describe this video frame in one sentence. Focus on the main subject, action, and setting.",
                        tmp_path
                    )

                    self.index.add_segment(str(video_path), timestamp, description.strip())
                    segments_added += 1
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            frame_num += 1

        cap.release()
        return segments_added

    async def index_directory(self, directory: Path, recursive: bool = True) -> dict:
        """Index all videos in a directory.

        Args:
            directory: Directory to scan.
            recursive: Whether to scan subdirectories.

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

        for video_path in videos:
            segments = await self.index_video(video_path)
            if segments > 0:
                stats['indexed'] += 1
                stats['segments'] += segments
            else:
                stats['skipped'] += 1

        return stats
