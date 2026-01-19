"""Transcript handling and alignment for hybrid indexing."""

import re
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Iterator


@dataclass
class TranscriptChunk:
    """A chunk of transcript with timing."""
    start: float  # seconds
    end: float    # seconds
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Transcript:
    """A full transcript with chunks."""
    chunks: List[TranscriptChunk]
    source: str  # e.g., "whisper", "srt", "vtt"

    @property
    def full_text(self) -> str:
        """Get full transcript text."""
        return " ".join(c.text for c in self.chunks)

    @property
    def duration(self) -> float:
        """Total duration covered by transcript."""
        if not self.chunks:
            return 0
        return self.chunks[-1].end

    def get_text_in_range(self, start: float, end: float) -> str:
        """Get transcript text within a time range.

        Args:
            start: Start time in seconds.
            end: End time in seconds.

        Returns:
            Concatenated text of chunks that fall within the range.
        """
        texts = []
        for chunk in self.chunks:
            # Include chunk if it overlaps with the range
            if chunk.end > start and chunk.start < end:
                texts.append(chunk.text)
        return " ".join(texts)

    def align_to_frames(
        self,
        frame_timestamps: List[float],
        default_window: float = 10.0
    ) -> List[Optional[str]]:
        """Align transcript to frame sampling timestamps.

        Args:
            frame_timestamps: List of frame timestamps in seconds.
            default_window: Default window size for last frame.

        Returns:
            List of transcript texts for each frame window.
        """
        aligned = []
        for i, start in enumerate(frame_timestamps):
            if i + 1 < len(frame_timestamps):
                end = frame_timestamps[i + 1]
            else:
                end = start + default_window

            text = self.get_text_in_range(start, end)
            aligned.append(text if text else None)

        return aligned


class TranscriptLoader:
    """Load transcripts from various formats."""

    @staticmethod
    def load(path: Path) -> Transcript:
        """Load transcript from file, auto-detecting format.

        Args:
            path: Path to transcript file.

        Returns:
            Transcript object.

        Raises:
            ValueError: If format is not supported.
        """
        suffix = path.suffix.lower()

        loaders = {
            ".srt": TranscriptLoader._load_srt,
            ".vtt": TranscriptLoader._load_vtt,
            ".json": TranscriptLoader._load_whisper_json,
        }

        loader = loaders.get(suffix)
        if loader is None:
            raise ValueError(f"Unsupported transcript format: {suffix}. "
                           f"Supported: {list(loaders.keys())}")

        return loader(path)

    @staticmethod
    def _parse_srt_time(time_str: str) -> float:
        """Parse SRT timestamp to seconds."""
        # Format: HH:MM:SS,mmm or HH:MM:SS.mmm
        time_str = time_str.replace(",", ".")
        parts = time_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def _load_srt(path: Path) -> Transcript:
        """Load SRT subtitle file."""
        content = path.read_text(encoding="utf-8-sig")  # Handle BOM
        chunks = []

        # SRT format:
        # 1
        # 00:00:01,000 --> 00:00:04,000
        # Text here
        #
        # 2
        # ...

        blocks = re.split(r"\n\n+", content.strip())

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue

            # Skip index line, parse timing line
            timing_match = re.match(
                r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
                lines[1]
            )
            if not timing_match:
                continue

            start = TranscriptLoader._parse_srt_time(timing_match.group(1))
            end = TranscriptLoader._parse_srt_time(timing_match.group(2))
            text = " ".join(lines[2:]).strip()

            # Remove HTML-like tags
            text = re.sub(r"<[^>]+>", "", text)

            if text:
                chunks.append(TranscriptChunk(start=start, end=end, text=text))

        return Transcript(chunks=chunks, source="srt")

    @staticmethod
    def _parse_vtt_time(time_str: str) -> float:
        """Parse VTT timestamp to seconds."""
        # Format: HH:MM:SS.mmm or MM:SS.mmm
        parts = time_str.split(":")
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
        else:
            hours = 0
            minutes = int(parts[0])
            seconds = float(parts[1])
        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def _load_vtt(path: Path) -> Transcript:
        """Load WebVTT subtitle file."""
        content = path.read_text(encoding="utf-8-sig")
        chunks = []

        # Skip WEBVTT header
        lines = content.strip().split("\n")
        i = 0
        while i < len(lines) and not lines[i].startswith("WEBVTT"):
            i += 1
        i += 1  # Skip WEBVTT line

        # Parse cues
        while i < len(lines):
            # Skip empty lines and cue identifiers
            while i < len(lines) and (not lines[i].strip() or
                                       not re.match(r"\d", lines[i])):
                i += 1
            if i >= len(lines):
                break

            # Check if this is a timing line
            timing_match = re.match(
                r"(\d{1,2}:?\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{1,2}:?\d{2}:\d{2}\.\d{3})",
                lines[i]
            )
            if not timing_match:
                i += 1
                continue

            start = TranscriptLoader._parse_vtt_time(timing_match.group(1))
            end = TranscriptLoader._parse_vtt_time(timing_match.group(2))
            i += 1

            # Collect text lines until empty line or next timing
            text_lines = []
            while i < len(lines) and lines[i].strip():
                if re.match(r"\d{1,2}:?\d{2}:\d{2}\.\d{3}", lines[i]):
                    break
                text_lines.append(lines[i].strip())
                i += 1

            text = " ".join(text_lines)
            # Remove VTT formatting tags
            text = re.sub(r"<[^>]+>", "", text)

            if text:
                chunks.append(TranscriptChunk(start=start, end=end, text=text))

        return Transcript(chunks=chunks, source="vtt")

    @staticmethod
    def _load_whisper_json(path: Path) -> Transcript:
        """Load Whisper JSON output."""
        data = json.loads(path.read_text(encoding="utf-8"))
        chunks = []

        # Whisper JSON format varies, handle common structures
        segments = data.get("segments", data.get("results", []))

        for seg in segments:
            start = seg.get("start", seg.get("start_time", 0))
            end = seg.get("end", seg.get("end_time", start + 1))
            text = seg.get("text", seg.get("transcript", "")).strip()

            if text:
                chunks.append(TranscriptChunk(start=start, end=end, text=text))

        return Transcript(chunks=chunks, source="whisper")


def find_transcript_for_video(video_path: Path) -> Optional[Path]:
    """Find transcript file for a video (same name, different extension).

    Handles:
    - Direct extension: video.srt, video.vtt, video.json
    - Language-coded: video.en.srt, video.es.vtt (from yt-dlp)
    - Whisper output: video.whisper.json

    Args:
        video_path: Path to video file.

    Returns:
        Path to transcript file if found, None otherwise.
    """
    transcript_extensions = [".srt", ".vtt", ".json"]
    video_stem = video_path.stem
    video_dir = video_path.parent

    # Check direct extensions: video.srt, video.vtt, video.json
    for ext in transcript_extensions:
        transcript_path = video_path.with_suffix(ext)
        if transcript_path.exists():
            return transcript_path

    # Check whisper output: video.whisper.json
    whisper_path = video_path.with_suffix(".whisper.json")
    if whisper_path.exists():
        return whisper_path

    # Check language-coded subtitles: video.en.srt, video.es.vtt, etc.
    # Pattern: {video_stem}.{lang_code}.{ext}
    # Use glob.escape() to handle special characters like & in filenames
    import glob as glob_module
    escaped_stem = glob_module.escape(video_stem)
    for ext in [".srt", ".vtt"]:
        # Look for files matching pattern
        pattern = f"{escaped_stem}.*{ext}"
        matches = list(video_dir.glob(pattern))
        if matches:
            # Prefer English if available
            for match in matches:
                if ".en." in match.name or ".eng." in match.name:
                    return match
            # Otherwise return first match
            return matches[0]

    return None
