"""Tests for video indexing."""

import pytest
import sqlite3
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from nolan.indexer import VideoIndexer, VideoIndex, VideoSegment


@pytest.fixture
def mock_llm():
    """Mock LLM for frame analysis."""
    client = Mock()
    client.generate_with_image = AsyncMock(return_value="City skyline at sunset with tall buildings and orange sky")
    return client


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database path."""
    return tmp_path / "test_library.db"


def test_video_index_creates_database(temp_db):
    """Index creates SQLite database on init."""
    index = VideoIndex(temp_db)

    assert temp_db.exists()


def test_video_index_stores_and_retrieves_segments(temp_db):
    """Index can store and retrieve video segments."""
    index = VideoIndex(temp_db)

    index.add_video(
        path="/videos/test.mp4",
        duration=120.0,
        checksum="abc123"
    )

    index.add_segment(
        video_path="/videos/test.mp4",
        timestamp_start=5.0,
        timestamp_end=10.0,
        frame_description="A person walking in a park"
    )

    segments = index.get_segments("/videos/test.mp4")

    assert len(segments) == 1
    assert segments[0].description == "A person walking in a park"
    assert segments[0].frame_description == "A person walking in a park"
    assert segments[0].timestamp_start == 5.0
    assert segments[0].timestamp_end == 10.0


def test_video_index_search_returns_matches(temp_db):
    """Index search returns matching segments."""
    index = VideoIndex(temp_db)

    index.add_video("/videos/city.mp4", 60.0, "def456")
    index.add_segment("/videos/city.mp4", 10.0, 15.0, "Aerial view of city skyline at dusk")
    index.add_segment("/videos/city.mp4", 20.0, 25.0, "Close-up of traffic lights")

    index.add_video("/videos/nature.mp4", 60.0, "ghi789")
    index.add_segment("/videos/nature.mp4", 5.0, 10.0, "Forest with tall trees")

    results = index.search("city skyline aerial")

    assert len(results) >= 1
    assert "city" in results[0].description.lower()


def test_video_index_skips_unchanged_files(temp_db):
    """Index skips files that haven't changed."""
    index = VideoIndex(temp_db)

    index.add_video("/videos/test.mp4", 60.0, "checksum123")

    needs_index = index.needs_indexing("/videos/test.mp4", "checksum123")

    assert needs_index is False


def test_video_index_reindexes_changed_files(temp_db):
    """Index flags changed files for reindexing."""
    index = VideoIndex(temp_db)

    index.add_video("/videos/test.mp4", 60.0, "old_checksum")

    needs_index = index.needs_indexing("/videos/test.mp4", "new_checksum")

    assert needs_index is True
