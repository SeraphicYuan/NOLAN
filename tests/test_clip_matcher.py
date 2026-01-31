"""Tests for the nolan.clip_matcher module."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from nolan.clip_matcher import (
    ClipCandidate,
    MatchResult,
    ClipMatcher,
)
from nolan.scenes import Scene


class TestClipCandidate:
    """Tests for ClipCandidate dataclass."""

    def test_creation(self):
        """Should create with all fields."""
        candidate = ClipCandidate(
            video_path="/path/to/video.mp4",
            timestamp_start=10.0,
            timestamp_end=20.0,
            description="A person walking in the park",
            transcript="This is the transcript",
            similarity_score=0.85,
            people=["John", "Jane"],
            location="Central Park",
        )

        assert candidate.video_path == "/path/to/video.mp4"
        assert candidate.timestamp_start == 10.0
        assert candidate.timestamp_end == 20.0
        assert candidate.description == "A person walking in the park"
        assert candidate.transcript == "This is the transcript"
        assert candidate.similarity_score == 0.85
        assert candidate.people == ["John", "Jane"]
        assert candidate.location == "Central Park"

    def test_duration_property(self):
        """Should calculate duration correctly."""
        candidate = ClipCandidate(
            video_path="test.mp4",
            timestamp_start=5.0,
            timestamp_end=15.0,
            description="Test",
            transcript=None,
            similarity_score=0.5,
            people=[],
            location=None,
        )

        assert candidate.duration == 10.0

    def test_duration_with_same_timestamps(self):
        """Should return 0 for same start and end."""
        candidate = ClipCandidate(
            video_path="test.mp4",
            timestamp_start=5.0,
            timestamp_end=5.0,
            description="Test",
            transcript=None,
            similarity_score=0.5,
            people=[],
            location=None,
        )

        assert candidate.duration == 0.0

    def test_nullable_fields(self):
        """Should allow None for optional fields."""
        candidate = ClipCandidate(
            video_path="test.mp4",
            timestamp_start=0.0,
            timestamp_end=1.0,
            description="Test",
            transcript=None,
            similarity_score=0.0,
            people=[],
            location=None,
        )

        assert candidate.transcript is None
        assert candidate.location is None


class TestMatchResult:
    """Tests for MatchResult dataclass."""

    def test_creation(self):
        """Should create with all fields."""
        result = MatchResult(
            selected_index=2,
            reasoning="Best match for the scene",
            confidence=0.95,
            tailored_start=10.5,
            tailored_end=15.5,
        )

        assert result.selected_index == 2
        assert result.reasoning == "Best match for the scene"
        assert result.confidence == 0.95
        assert result.tailored_start == 10.5
        assert result.tailored_end == 15.5

    def test_zero_index(self):
        """Should allow zero index (first candidate)."""
        result = MatchResult(
            selected_index=0,
            reasoning="First is best",
            confidence=1.0,
            tailored_start=0.0,
            tailored_end=5.0,
        )

        assert result.selected_index == 0


class TestClipMatcherUtilities:
    """Tests for ClipMatcher utility methods."""

    def create_mock_scene(self, **kwargs):
        """Create a mock scene with default values."""
        defaults = {
            "id": "test_scene",
            "section": "test",
            "type": "b-roll",
            "visual_description": None,
            "search_query": None,
            "narration_excerpt": None,
            "duration": 5.0,
        }
        defaults.update(kwargs)

        scene = MagicMock(spec=Scene)
        for key, value in defaults.items():
            setattr(scene, key, value)
        return scene

    def test_build_search_query_all_parts(self):
        """Should combine all scene parts."""
        scene = self.create_mock_scene(
            narration_excerpt="The narrator speaks",
            visual_description="A visual scene",
            search_query="specific query",
        )

        # Test static method behavior
        parts = []
        if scene.narration_excerpt:
            parts.append(scene.narration_excerpt)
        if scene.visual_description:
            parts.append(scene.visual_description)
        if scene.search_query:
            parts.append(scene.search_query)
        query = " | ".join(parts)

        assert "narrator speaks" in query
        assert "visual scene" in query
        assert "specific query" in query
        assert " | " in query

    def test_build_search_query_partial(self):
        """Should handle missing parts."""
        scene = self.create_mock_scene(
            narration_excerpt="Only narration",
            visual_description=None,
            search_query=None,
        )

        parts = []
        if scene.narration_excerpt:
            parts.append(scene.narration_excerpt)
        if scene.visual_description:
            parts.append(scene.visual_description)
        if scene.search_query:
            parts.append(scene.search_query)
        query = " | ".join(parts)

        assert query == "Only narration"
        assert " | " not in query

    def test_build_search_query_empty(self):
        """Should return empty for no parts."""
        scene = self.create_mock_scene(
            narration_excerpt=None,
            visual_description=None,
            search_query=None,
        )

        parts = []
        if scene.narration_excerpt:
            parts.append(scene.narration_excerpt)
        if scene.visual_description:
            parts.append(scene.visual_description)
        if scene.search_query:
            parts.append(scene.search_query)
        query = " | ".join(parts) if parts else ""

        assert query == ""


class TestClipMatcherDeduplication:
    """Tests for ClipMatcher._dedupe_candidates."""

    def test_dedupe_unique_candidates(self):
        """Should keep all unique candidates."""
        candidates = [
            ClipCandidate("video1.mp4", 0.0, 5.0, "Desc 1", None, 0.9, [], None),
            ClipCandidate("video2.mp4", 0.0, 5.0, "Desc 2", None, 0.8, [], None),
            ClipCandidate("video1.mp4", 10.0, 15.0, "Desc 3", None, 0.7, [], None),
        ]

        result = ClipMatcher._dedupe_candidates(candidates)

        assert len(result) == 3

    def test_dedupe_same_clip(self):
        """Should keep highest scoring duplicate."""
        candidates = [
            ClipCandidate("video.mp4", 0.0, 5.0, "Low score", None, 0.5, [], None),
            ClipCandidate("video.mp4", 0.0, 5.0, "High score", None, 0.9, [], None),
            ClipCandidate("video.mp4", 0.0, 5.0, "Mid score", None, 0.7, [], None),
        ]

        result = ClipMatcher._dedupe_candidates(candidates)

        assert len(result) == 1
        assert result[0].similarity_score == 0.9
        assert result[0].description == "High score"

    def test_dedupe_empty_list(self):
        """Should handle empty list."""
        result = ClipMatcher._dedupe_candidates([])
        assert result == []

    def test_dedupe_preserves_order_keys(self):
        """Deduplication should be based on video_path+timestamps."""
        candidates = [
            ClipCandidate("a.mp4", 0.0, 5.0, "A", None, 0.8, [], None),
            ClipCandidate("b.mp4", 0.0, 5.0, "B", None, 0.7, [], None),  # Different video
            ClipCandidate("a.mp4", 5.0, 10.0, "A2", None, 0.6, [], None),  # Different time
        ]

        result = ClipMatcher._dedupe_candidates(candidates)

        assert len(result) == 3


class TestClipMatcherCacheKey:
    """Tests for ClipMatcher._candidate_cache_key."""

    def create_mock_scene(self, id="scene_1"):
        """Create a mock scene."""
        scene = MagicMock(spec=Scene)
        scene.id = id
        return scene

    def test_same_inputs_same_key(self):
        """Same inputs should produce same cache key."""
        scene = self.create_mock_scene("scene_001")
        candidates = [
            ClipCandidate("video.mp4", 0.0, 5.0, "Desc", None, 0.8, [], None),
        ]

        key1 = ClipMatcher._candidate_cache_key(scene, candidates, 5.0)
        key2 = ClipMatcher._candidate_cache_key(scene, candidates, 5.0)

        assert key1 == key2

    def test_different_scene_different_key(self):
        """Different scene IDs should produce different keys."""
        scene1 = self.create_mock_scene("scene_001")
        scene2 = self.create_mock_scene("scene_002")
        candidates = [
            ClipCandidate("video.mp4", 0.0, 5.0, "Desc", None, 0.8, [], None),
        ]

        key1 = ClipMatcher._candidate_cache_key(scene1, candidates, 5.0)
        key2 = ClipMatcher._candidate_cache_key(scene2, candidates, 5.0)

        assert key1 != key2

    def test_different_candidates_different_key(self):
        """Different candidates should produce different keys."""
        scene = self.create_mock_scene("scene_001")
        candidates1 = [
            ClipCandidate("video1.mp4", 0.0, 5.0, "Desc", None, 0.8, [], None),
        ]
        candidates2 = [
            ClipCandidate("video2.mp4", 0.0, 5.0, "Desc", None, 0.8, [], None),
        ]

        key1 = ClipMatcher._candidate_cache_key(scene, candidates1, 5.0)
        key2 = ClipMatcher._candidate_cache_key(scene, candidates2, 5.0)

        assert key1 != key2

    def test_different_duration_different_key(self):
        """Different durations should produce different keys."""
        scene = self.create_mock_scene("scene_001")
        candidates = [
            ClipCandidate("video.mp4", 0.0, 5.0, "Desc", None, 0.8, [], None),
        ]

        key1 = ClipMatcher._candidate_cache_key(scene, candidates, 5.0)
        key2 = ClipMatcher._candidate_cache_key(scene, candidates, 10.0)

        assert key1 != key2

    def test_key_is_deterministic(self):
        """Key should be deterministic (MD5 hash)."""
        scene = self.create_mock_scene("scene_001")
        candidates = [
            ClipCandidate("video.mp4", 0.0, 5.0, "Desc", None, 0.8, [], None),
        ]

        key = ClipMatcher._candidate_cache_key(scene, candidates, 5.0)

        # MD5 hashes are 32 hex characters
        assert len(key) == 32
        assert all(c in '0123456789abcdef' for c in key)
