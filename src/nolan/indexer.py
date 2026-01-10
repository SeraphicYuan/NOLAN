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
                    indexed_at TEXT,
                    has_transcript INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_path TEXT,
                    timestamp_start REAL,
                    timestamp_end REAL,
                    frame_description TEXT,
                    transcript TEXT,
                    combined_summary TEXT,
                    inferred_context TEXT,
                    sample_reason TEXT,
                    FOREIGN KEY (video_path) REFERENCES videos(path)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_segments_video
                ON segments(video_path)
            """)
            # Migration: add new columns if they don't exist (for existing DBs)
            self._migrate_schema(conn)
            conn.commit()

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        """Migrate schema for existing databases."""
        cursor = conn.execute("PRAGMA table_info(segments)")
        columns = {row[1] for row in cursor.fetchall()}

        migrations = [
            ("timestamp_start", "REAL"),
            ("timestamp_end", "REAL"),
            ("frame_description", "TEXT"),
            ("transcript", "TEXT"),
            ("combined_summary", "TEXT"),
            ("inferred_context", "TEXT"),
            ("sample_reason", "TEXT"),
        ]

        for col_name, col_type in migrations:
            if col_name not in columns:
                try:
                    conn.execute(f"ALTER TABLE segments ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass  # Column might already exist

        # Migrate old 'timestamp' to 'timestamp_start' if needed
        if "timestamp" in columns and "timestamp_start" not in columns:
            conn.execute("UPDATE segments SET timestamp_start = timestamp WHERE timestamp_start IS NULL")

        # Migrate old 'description' to 'frame_description' if needed
        if "description" in columns and "frame_description" not in columns:
            conn.execute("UPDATE segments SET frame_description = description WHERE frame_description IS NULL")

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

    def add_segment(
        self,
        video_path: str,
        timestamp_start: float,
        timestamp_end: float,
        frame_description: str,
        transcript: Optional[str] = None,
        combined_summary: Optional[str] = None,
        inferred_context: Optional[InferredContext] = None,
        sample_reason: Optional[str] = None
    ) -> None:
        """Add a segment to the index.

        Args:
            video_path: Path to source video.
            timestamp_start: Start timestamp in seconds.
            timestamp_end: End timestamp in seconds.
            frame_description: Visual description from vision model.
            transcript: Transcript text for this segment.
            combined_summary: LLM-fused summary of visual + audio.
            inferred_context: Inferred context (people, location, etc.).
            sample_reason: Why this frame was sampled.
        """
        context_json = json.dumps(inferred_context.to_dict()) if inferred_context else None

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO segments (
                    video_path, timestamp_start, timestamp_end,
                    frame_description, transcript, combined_summary,
                    inferred_context, sample_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                video_path, timestamp_start, timestamp_end,
                frame_description, transcript, combined_summary,
                context_json, sample_reason
            ))
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
                SELECT video_path, timestamp_start, timestamp_end,
                       frame_description, transcript, combined_summary,
                       inferred_context, sample_reason
                FROM segments
                WHERE video_path = ?
                ORDER BY timestamp_start
            """, (video_path,))

            segments = []
            for row in cursor.fetchall():
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

        Searches across frame descriptions, transcripts, combined summaries,
        and inferred context (people, location, objects, story).

        Args:
            query: Search query (keywords).
            limit: Maximum results to return.

        Returns:
            List of matching VideoSegment objects.
        """
        keywords = query.lower().split()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT video_path, timestamp_start, timestamp_end,
                       frame_description, transcript, combined_summary,
                       inferred_context, sample_reason
                FROM segments
            """)

            results = []
            for row in cursor.fetchall():
                # Build searchable text from all fields
                searchable_parts = [
                    row[3] or "",  # frame_description
                    row[4] or "",  # transcript
                    row[5] or "",  # combined_summary
                ]

                # Add inferred context fields
                if row[6]:
                    try:
                        ctx = json.loads(row[6])
                        searchable_parts.extend(ctx.get("people", []))
                        if ctx.get("location"):
                            searchable_parts.append(ctx["location"])
                        if ctx.get("story_context"):
                            searchable_parts.append(ctx["story_context"])
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
        enable_inference: bool = True
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
        """
        self.vision = vision_provider
        self.index = index
        self.sampler = sampler
        self.llm = llm_client
        self.whisper = whisper_transcriber
        self.enable_transcript = enable_transcript
        self.enable_inference = enable_inference

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

        checksum = compute_checksum(video_path)

        if not self.index.needs_indexing(str(video_path), checksum):
            return 0  # Already indexed

        # Clear old segments if reindexing
        self.index.clear_segments(str(video_path))

        # Get video duration
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        cap.release()

        # Add video to index
        self.index.add_video(str(video_path), duration, checksum)

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
                    video_path=str(video_path),
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
