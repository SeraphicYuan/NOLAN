"""Tests for transcript handling module."""

import pytest
import json
from pathlib import Path

from nolan.transcript import (
    TranscriptChunk,
    Transcript,
    TranscriptLoader,
    find_transcript_for_video,
)


class TestTranscriptChunk:
    """Tests for TranscriptChunk dataclass."""

    def test_creation(self):
        """Test creating a transcript chunk."""
        chunk = TranscriptChunk(start=1.0, end=3.5, text="Hello world")
        assert chunk.start == 1.0
        assert chunk.end == 3.5
        assert chunk.text == "Hello world"
        assert chunk.duration == 2.5


class TestTranscript:
    """Tests for Transcript class."""

    def test_full_text(self):
        """Test getting full transcript text."""
        chunks = [
            TranscriptChunk(start=0, end=2, text="Hello"),
            TranscriptChunk(start=2, end=4, text="world"),
        ]
        transcript = Transcript(chunks=chunks, source="test")
        assert transcript.full_text == "Hello world"

    def test_duration(self):
        """Test transcript duration."""
        chunks = [
            TranscriptChunk(start=0, end=2, text="Hello"),
            TranscriptChunk(start=2, end=5, text="world"),
        ]
        transcript = Transcript(chunks=chunks, source="test")
        assert transcript.duration == 5

    def test_get_text_in_range(self):
        """Test getting text within a time range."""
        chunks = [
            TranscriptChunk(start=0, end=2, text="First"),
            TranscriptChunk(start=2, end=4, text="Second"),
            TranscriptChunk(start=4, end=6, text="Third"),
            TranscriptChunk(start=6, end=8, text="Fourth"),
        ]
        transcript = Transcript(chunks=chunks, source="test")

        # Get text from 1.5 to 5.5 (should include Second and Third)
        text = transcript.get_text_in_range(1.5, 5.5)
        assert "First" in text  # Overlaps with 1.5-5.5
        assert "Second" in text
        assert "Third" in text
        assert "Fourth" not in text

    def test_align_to_frames(self):
        """Test aligning transcript to frame timestamps."""
        chunks = [
            TranscriptChunk(start=0, end=3, text="First chunk"),
            TranscriptChunk(start=3, end=6, text="Second chunk"),
            TranscriptChunk(start=6, end=9, text="Third chunk"),
        ]
        transcript = Transcript(chunks=chunks, source="test")

        frame_timestamps = [0.0, 5.0, 10.0]
        aligned = transcript.align_to_frames(frame_timestamps)

        assert len(aligned) == 3
        assert "First chunk" in aligned[0]
        assert "Second chunk" in aligned[0]  # Falls in 0-5 window
        assert "Third chunk" in aligned[1]   # Falls in 5-10 window
        assert aligned[2] is None  # No transcript after 10s


class TestTranscriptLoader:
    """Tests for TranscriptLoader."""

    def test_load_srt(self, tmp_path):
        """Test loading SRT file."""
        srt_content = """1
00:00:01,000 --> 00:00:04,000
Hello, this is the first subtitle.

2
00:00:05,500 --> 00:00:08,000
And this is the second one.
"""
        srt_path = tmp_path / "test.srt"
        srt_path.write_text(srt_content)

        transcript = TranscriptLoader.load(srt_path)

        assert transcript.source == "srt"
        assert len(transcript.chunks) == 2
        assert transcript.chunks[0].start == 1.0
        assert transcript.chunks[0].end == 4.0
        assert transcript.chunks[0].text == "Hello, this is the first subtitle."
        assert transcript.chunks[1].start == 5.5
        assert transcript.chunks[1].end == 8.0

    def test_load_vtt(self, tmp_path):
        """Test loading WebVTT file."""
        vtt_content = """WEBVTT

00:00:01.000 --> 00:00:04.000
Hello from VTT.

00:00:05.000 --> 00:00:08.000
Second line here.
"""
        vtt_path = tmp_path / "test.vtt"
        vtt_path.write_text(vtt_content)

        transcript = TranscriptLoader.load(vtt_path)

        assert transcript.source == "vtt"
        assert len(transcript.chunks) == 2
        assert transcript.chunks[0].text == "Hello from VTT."

    def test_load_whisper_json(self, tmp_path):
        """Test loading Whisper JSON output."""
        whisper_data = {
            "segments": [
                {"start": 0.0, "end": 2.5, "text": " First segment"},
                {"start": 2.5, "end": 5.0, "text": " Second segment"},
            ]
        }
        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(whisper_data))

        transcript = TranscriptLoader.load(json_path)

        assert transcript.source == "whisper"
        assert len(transcript.chunks) == 2
        assert transcript.chunks[0].text == "First segment"
        assert transcript.chunks[0].start == 0.0
        assert transcript.chunks[0].end == 2.5

    def test_unsupported_format(self, tmp_path):
        """Test loading unsupported format raises error."""
        txt_path = tmp_path / "test.txt"
        txt_path.write_text("Some text")

        with pytest.raises(ValueError, match="Unsupported transcript format"):
            TranscriptLoader.load(txt_path)

    def test_srt_with_html_tags(self, tmp_path):
        """Test SRT with HTML tags are stripped."""
        srt_content = """1
00:00:01,000 --> 00:00:04,000
<i>Italic text</i> and <b>bold text</b>
"""
        srt_path = tmp_path / "test.srt"
        srt_path.write_text(srt_content)

        transcript = TranscriptLoader.load(srt_path)
        assert transcript.chunks[0].text == "Italic text and bold text"


class TestFindTranscriptForVideo:
    """Tests for find_transcript_for_video."""

    def test_find_srt(self, tmp_path):
        """Test finding SRT file."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()

        srt_path = tmp_path / "video.srt"
        srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest")

        found = find_transcript_for_video(video_path)
        assert found == srt_path

    def test_find_vtt(self, tmp_path):
        """Test finding VTT file."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()

        vtt_path = tmp_path / "video.vtt"
        vtt_path.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nTest")

        found = find_transcript_for_video(video_path)
        assert found == vtt_path

    def test_find_whisper_json(self, tmp_path):
        """Test finding Whisper JSON file."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()

        whisper_path = tmp_path / "video.whisper.json"
        whisper_path.write_text('{"segments": []}')

        found = find_transcript_for_video(video_path)
        assert found == whisper_path

    def test_no_transcript_found(self, tmp_path):
        """Test when no transcript exists."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()

        found = find_transcript_for_video(video_path)
        assert found is None

    def test_priority_srt_over_vtt(self, tmp_path):
        """Test SRT is preferred over VTT."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()

        srt_path = tmp_path / "video.srt"
        srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest")

        vtt_path = tmp_path / "video.vtt"
        vtt_path.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nTest")

        found = find_transcript_for_video(video_path)
        assert found == srt_path  # SRT should be found first
