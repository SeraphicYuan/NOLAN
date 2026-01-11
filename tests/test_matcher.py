"""Tests for asset matching."""

import pytest
from pathlib import Path

from nolan.matcher import AssetMatcher
from nolan.indexer import VideoIndex, VideoSegment
from nolan.scenes import Scene


@pytest.fixture
def populated_index(tmp_path):
    """Create an index with test data."""
    index = VideoIndex(tmp_path / "test.db")

    city_id = index.add_video("/videos/city.mp4", 120.0, "abc", "fp-city")
    index.add_segment(city_id, 10.0, 20.0, "Aerial view of city skyline at sunset")
    index.add_segment(city_id, 30.0, 40.0, "Busy street with cars and pedestrians")

    nature_id = index.add_video("/videos/nature.mp4", 60.0, "def", "fp-nature")
    index.add_segment(nature_id, 5.0, 10.0, "Waterfall in tropical rainforest")
    index.add_segment(nature_id, 15.0, 20.0, "Birds flying over mountains")

    return index


def test_matcher_finds_relevant_clips(populated_index):
    """Matcher returns clips matching scene description."""
    matcher = AssetMatcher(populated_index)

    scene = Scene(
        id="scene_001",
        start="0:00",
        duration="10s",
        narration_excerpt="The city awakens",
        visual_type="b-roll",
        visual_description="City skyline view from above",
        search_query="city skyline aerial",
        comfyui_prompt="",
        library_match=True
    )

    matches = matcher.find_matches(scene, limit=3)

    assert len(matches) >= 1
    assert "city" in matches[0].description.lower()


def test_matcher_returns_empty_when_no_match(populated_index):
    """Matcher returns empty list when no matches."""
    matcher = AssetMatcher(populated_index)

    scene = Scene(
        id="scene_001",
        start="0:00",
        duration="10s",
        narration_excerpt="Space exploration",
        visual_type="b-roll",
        visual_description="Rocket launching into space",
        search_query="rocket space launch",
        comfyui_prompt="",
        library_match=True
    )

    matches = matcher.find_matches(scene, limit=3)

    # No space-related footage in our test index
    assert len(matches) == 0


def test_matcher_skips_when_library_match_false(populated_index):
    """Matcher skips library search when library_match is False."""
    matcher = AssetMatcher(populated_index)

    scene = Scene(
        id="scene_001",
        start="0:00",
        duration="10s",
        narration_excerpt="Test",
        visual_type="generated-image",
        visual_description="Abstract art",
        search_query="abstract colors",
        comfyui_prompt="abstract art",
        library_match=False  # Don't search library
    )

    matches = matcher.find_matches(scene, limit=3)

    assert len(matches) == 0
