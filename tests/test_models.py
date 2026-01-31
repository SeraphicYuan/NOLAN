"""Tests for the nolan.models package."""

import pytest
from nolan.models import InferredContext, VideoSegment, SceneCluster


class TestInferredContext:
    """Tests for InferredContext dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        ctx = InferredContext()
        assert ctx.people == []
        assert ctx.location is None
        assert ctx.story_context is None
        assert ctx.objects == []
        assert ctx.confidence == "low"

    def test_to_dict(self):
        """Should convert to dictionary."""
        ctx = InferredContext(
            people=["Alice", "Bob"],
            location="New York",
            story_context="Meeting scene",
            objects=["laptop", "coffee"],
            confidence="high"
        )
        d = ctx.to_dict()

        assert d["people"] == ["Alice", "Bob"]
        assert d["location"] == "New York"
        assert d["story_context"] == "Meeting scene"
        assert d["objects"] == ["laptop", "coffee"]
        assert d["confidence"] == "high"

    def test_from_dict(self):
        """Should create from dictionary."""
        data = {
            "people": ["Alice"],
            "location": "Paris",
            "story_context": "Travel scene",
            "objects": ["camera"],
            "confidence": "medium"
        }
        ctx = InferredContext.from_dict(data)

        assert ctx.people == ["Alice"]
        assert ctx.location == "Paris"
        assert ctx.confidence == "medium"

    def test_from_dict_none(self):
        """Should handle None input."""
        ctx = InferredContext.from_dict(None)
        assert ctx.people == []
        assert ctx.location is None


class TestVideoSegment:
    """Tests for VideoSegment dataclass."""

    def test_required_fields(self):
        """Should require essential fields."""
        seg = VideoSegment(
            video_path="test.mp4",
            timestamp_start=0.0,
            timestamp_end=5.0,
            frame_description="A test frame"
        )
        assert seg.video_path == "test.mp4"
        assert seg.timestamp_start == 0.0
        assert seg.timestamp_end == 5.0

    def test_optional_fields_default(self):
        """Should have optional field defaults."""
        seg = VideoSegment(
            video_path="test.mp4",
            timestamp_start=0.0,
            timestamp_end=5.0,
            frame_description="Test"
        )
        assert seg.transcript is None
        assert seg.combined_summary is None
        assert seg.inferred_context is None

    def test_timestamp_legacy_property(self):
        """Should provide legacy timestamp property."""
        seg = VideoSegment(
            video_path="test.mp4",
            timestamp_start=10.5,
            timestamp_end=15.0,
            frame_description="Test"
        )
        assert seg.timestamp == 10.5

    def test_description_legacy_property(self):
        """Should provide legacy description property."""
        seg = VideoSegment(
            video_path="test.mp4",
            timestamp_start=0.0,
            timestamp_end=5.0,
            frame_description="Frame desc",
            combined_summary="Combined desc"
        )
        # Should prefer combined_summary
        assert seg.description == "Combined desc"

    def test_description_fallback(self):
        """Should fallback to frame_description."""
        seg = VideoSegment(
            video_path="test.mp4",
            timestamp_start=0.0,
            timestamp_end=5.0,
            frame_description="Frame desc"
        )
        assert seg.description == "Frame desc"

    def test_timestamp_formatted(self):
        """Should format timestamp as MM:SS."""
        seg = VideoSegment(
            video_path="test.mp4",
            timestamp_start=65.0,  # 1:05
            timestamp_end=70.0,
            frame_description="Test"
        )
        assert seg.timestamp_formatted == "01:05"

    def test_duration(self):
        """Should calculate segment duration."""
        seg = VideoSegment(
            video_path="test.mp4",
            timestamp_start=10.0,
            timestamp_end=25.0,
            frame_description="Test"
        )
        assert seg.duration == 15.0


class TestSceneCluster:
    """Tests for SceneCluster dataclass."""

    def test_empty_cluster(self):
        """Should handle empty cluster."""
        cluster = SceneCluster(id=0, segments=[])
        assert cluster.timestamp_start == 0.0
        assert cluster.timestamp_end == 0.0
        assert cluster.duration == 0.0
        assert cluster.people == []
        assert cluster.locations == []
        assert cluster.combined_transcript == ""

    def test_single_segment(self):
        """Should work with single segment."""
        seg = VideoSegment(
            video_path="test.mp4",
            timestamp_start=0.0,
            timestamp_end=5.0,
            frame_description="Test",
            transcript="Hello world"
        )
        cluster = SceneCluster(id=1, segments=[seg])

        assert cluster.timestamp_start == 0.0
        assert cluster.timestamp_end == 5.0
        assert cluster.duration == 5.0
        assert cluster.combined_transcript == "Hello world"

    def test_multiple_segments(self):
        """Should combine multiple segments."""
        seg1 = VideoSegment(
            video_path="test.mp4",
            timestamp_start=0.0,
            timestamp_end=5.0,
            frame_description="Test 1",
            transcript="Part one."
        )
        seg2 = VideoSegment(
            video_path="test.mp4",
            timestamp_start=5.0,
            timestamp_end=10.0,
            frame_description="Test 2",
            transcript="Part two."
        )
        cluster = SceneCluster(id=2, segments=[seg1, seg2])

        assert cluster.timestamp_start == 0.0
        assert cluster.timestamp_end == 10.0
        assert cluster.duration == 10.0
        assert "Part one." in cluster.combined_transcript
        assert "Part two." in cluster.combined_transcript

    def test_people_extraction(self):
        """Should extract unique people from segments."""
        ctx1 = InferredContext(people=["Alice", "Bob"])
        ctx2 = InferredContext(people=["Bob", "Charlie"])

        seg1 = VideoSegment(
            video_path="test.mp4",
            timestamp_start=0.0,
            timestamp_end=5.0,
            frame_description="Test",
            inferred_context=ctx1
        )
        seg2 = VideoSegment(
            video_path="test.mp4",
            timestamp_start=5.0,
            timestamp_end=10.0,
            frame_description="Test",
            inferred_context=ctx2
        )
        cluster = SceneCluster(id=3, segments=[seg1, seg2])

        people = cluster.people
        assert "Alice" in people
        assert "Bob" in people
        assert "Charlie" in people
        assert len(people) == 3

    def test_locations_extraction(self):
        """Should extract unique locations from segments."""
        ctx1 = InferredContext(location="Office")
        ctx2 = InferredContext(location="Office")  # Duplicate
        ctx3 = InferredContext(location="Street")

        segs = [
            VideoSegment("test.mp4", 0.0, 5.0, "T", inferred_context=ctx1),
            VideoSegment("test.mp4", 5.0, 10.0, "T", inferred_context=ctx2),
            VideoSegment("test.mp4", 10.0, 15.0, "T", inferred_context=ctx3),
        ]
        cluster = SceneCluster(id=4, segments=segs)

        locations = cluster.locations
        assert "Office" in locations
        assert "Street" in locations
        assert len(locations) == 2

    def test_timestamp_formatted(self):
        """Should format timestamp range."""
        seg1 = VideoSegment("test.mp4", 65.0, 70.0, "Test")  # 1:05
        seg2 = VideoSegment("test.mp4", 125.0, 130.0, "Test")  # 2:05

        cluster = SceneCluster(id=5, segments=[seg1, seg2])
        formatted = cluster.timestamp_formatted

        assert "01:05" in formatted
        assert "02:10" in formatted

    def test_to_dict(self):
        """Should convert to dictionary."""
        seg = VideoSegment(
            video_path="test.mp4",
            timestamp_start=0.0,
            timestamp_end=5.0,
            frame_description="Test frame",
            transcript="Hello"
        )
        cluster = SceneCluster(id=10, segments=[seg], cluster_summary="Test summary")

        d = cluster.to_dict()

        assert d["id"] == 10
        assert d["cluster_summary"] == "Test summary"
        assert d["segment_count"] == 1
        assert d["duration"] == 5.0
        assert len(d["segments"]) == 1


class TestBackwardsCompatibility:
    """Tests for backwards compatibility imports."""

    def test_import_from_indexer(self):
        """Should import from indexer for backwards compat."""
        from nolan.indexer import VideoSegment, InferredContext
        assert VideoSegment is not None
        assert InferredContext is not None

    def test_import_from_clustering(self):
        """Should import from clustering for backwards compat."""
        from nolan.clustering import SceneCluster
        assert SceneCluster is not None

    def test_same_class_references(self):
        """Imports from different modules should be same class."""
        from nolan.models import VideoSegment as VS1
        from nolan.indexer import VideoSegment as VS2
        assert VS1 is VS2

        from nolan.models import SceneCluster as SC1
        from nolan.clustering import SceneCluster as SC2
        assert SC1 is SC2
