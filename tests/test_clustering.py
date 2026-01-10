"""Tests for scene clustering module."""

import pytest
from nolan.indexer import VideoSegment, InferredContext
from nolan.clustering import (
    SceneCluster,
    cluster_segments,
    should_cluster_together,
    _normalize_person,
    _people_overlap,
    _location_similar,
    ClusterAnalyzer,
    StoryBoundaryDetector,
)


def make_segment(
    start: float,
    end: float,
    description: str = "Test frame",
    transcript: str = None,
    people: list = None,
    location: str = None,
    story_context: str = None,
) -> VideoSegment:
    """Helper to create test segments."""
    context = None
    if people or location or story_context:
        context = InferredContext(
            people=people or [],
            location=location,
            story_context=story_context,
            objects=[],
            confidence="high"
        )
    return VideoSegment(
        video_path="test.mp4",
        timestamp_start=start,
        timestamp_end=end,
        frame_description=description,
        transcript=transcript,
        combined_summary=description,
        inferred_context=context,
        sample_reason="test"
    )


class TestSceneCluster:
    """Tests for SceneCluster dataclass."""

    def test_empty_cluster_properties(self):
        """Empty cluster has zero values."""
        cluster = SceneCluster(id=0, segments=[])
        assert cluster.timestamp_start == 0.0
        assert cluster.timestamp_end == 0.0
        assert cluster.duration == 0.0
        assert cluster.people == []
        assert cluster.locations == []
        assert cluster.combined_transcript == ""

    def test_single_segment_cluster(self):
        """Cluster with one segment."""
        seg = make_segment(10.0, 15.0, people=["Tony Stark"], location="Lab")
        cluster = SceneCluster(id=0, segments=[seg])

        assert cluster.timestamp_start == 10.0
        assert cluster.timestamp_end == 15.0
        assert cluster.duration == 5.0
        assert cluster.people == ["Tony Stark"]
        assert cluster.locations == ["Lab"]

    def test_multiple_segments_cluster(self):
        """Cluster with multiple segments."""
        seg1 = make_segment(0.0, 5.0, people=["Tony Stark"], location="Lab")
        seg2 = make_segment(5.0, 10.0, people=["Steve Rogers"], location="Lab")
        seg3 = make_segment(10.0, 15.0, people=["Tony Stark", "Steve Rogers"], location="Lab")

        cluster = SceneCluster(id=0, segments=[seg1, seg2, seg3])

        assert cluster.timestamp_start == 0.0
        assert cluster.timestamp_end == 15.0
        assert cluster.duration == 15.0
        assert set(cluster.people) == {"Tony Stark", "Steve Rogers"}
        assert cluster.locations == ["Lab"]

    def test_combined_transcript(self):
        """Cluster combines transcripts from segments."""
        seg1 = make_segment(0.0, 5.0, transcript="Hello there.")
        seg2 = make_segment(5.0, 10.0, transcript="General Kenobi!")

        cluster = SceneCluster(id=0, segments=[seg1, seg2])
        assert cluster.combined_transcript == "Hello there. General Kenobi!"

    def test_timestamp_formatted(self):
        """Timestamp formatting works correctly."""
        seg1 = make_segment(65.0, 125.0)  # 1:05 to 2:05
        cluster = SceneCluster(id=0, segments=[seg1])
        assert cluster.timestamp_formatted == "01:05 - 02:05"

    def test_to_dict(self):
        """Conversion to dict for JSON export."""
        seg = make_segment(0.0, 5.0, transcript="Test", people=["Person"])
        cluster = SceneCluster(id=1, segments=[seg], cluster_summary="Test summary")

        d = cluster.to_dict()
        assert d["id"] == 1
        assert d["timestamp_start"] == 0.0
        assert d["timestamp_end"] == 5.0
        assert d["segment_count"] == 1
        assert d["cluster_summary"] == "Test summary"
        assert d["people"] == ["Person"]
        assert len(d["segments"]) == 1


class TestPersonNormalization:
    """Tests for person name normalization."""

    def test_normalize_removes_prefixes(self):
        """Common prefixes are removed."""
        assert _normalize_person("male speaker") == "speaker"
        assert _normalize_person("female scientist") == "scientist"
        assert _normalize_person("The President") == "president"

    def test_normalize_lowercase(self):
        """Names are lowercased."""
        assert _normalize_person("TONY STARK") == "tony stark"

    def test_people_overlap_exact_match(self):
        """Exact match gives 1.0 overlap."""
        assert _people_overlap(["Tony"], ["Tony"]) == 1.0

    def test_people_overlap_partial(self):
        """Partial overlap calculated correctly."""
        # 1 common out of 3 total = 1/3
        overlap = _people_overlap(["Tony", "Steve"], ["Tony", "Bruce"])
        assert overlap == pytest.approx(1/3, rel=0.01)

    def test_people_overlap_empty(self):
        """Empty lists give 0 overlap."""
        assert _people_overlap([], ["Tony"]) == 0.0
        assert _people_overlap(["Tony"], []) == 0.0
        assert _people_overlap([], []) == 0.0


class TestLocationSimilarity:
    """Tests for location similarity detection."""

    def test_exact_match(self):
        """Exact match returns True."""
        assert _location_similar("Laboratory", "Laboratory") is True

    def test_case_insensitive(self):
        """Matching is case insensitive."""
        assert _location_similar("LABORATORY", "laboratory") is True

    def test_contains(self):
        """One location containing another matches."""
        assert _location_similar("high-tech laboratory", "laboratory") is True
        assert _location_similar("lab", "high-tech laboratory") is True

    def test_shared_words(self):
        """Locations sharing significant words match."""
        assert _location_similar("SHIELD command center", "command center") is True

    def test_no_match(self):
        """Unrelated locations don't match."""
        assert _location_similar("beach", "laboratory") is False

    def test_none_handling(self):
        """None values don't match."""
        assert _location_similar(None, "lab") is False
        assert _location_similar("lab", None) is False
        assert _location_similar(None, None) is False


class TestShouldClusterTogether:
    """Tests for clustering decision logic."""

    def test_time_gap_too_large(self):
        """Segments with large gap don't cluster."""
        seg1 = make_segment(0.0, 5.0)
        seg2 = make_segment(10.0, 15.0)  # 5s gap
        assert should_cluster_together(seg1, seg2, max_gap=2.0) is False

    def test_time_continuous(self):
        """Continuous segments cluster (no context)."""
        seg1 = make_segment(0.0, 5.0)
        seg2 = make_segment(5.0, 10.0)  # No gap
        assert should_cluster_together(seg1, seg2, max_gap=2.0) is True

    def test_same_people(self):
        """Segments with same people cluster."""
        seg1 = make_segment(0.0, 5.0, people=["Tony Stark", "Steve Rogers"])
        seg2 = make_segment(5.0, 10.0, people=["Tony Stark"])
        # 50% overlap (1/2)
        assert should_cluster_together(seg1, seg2, min_people_overlap=0.3) is True

    def test_same_location(self):
        """Segments at same location cluster."""
        seg1 = make_segment(0.0, 5.0, location="SHIELD Helicarrier")
        seg2 = make_segment(5.0, 10.0, location="Helicarrier bridge")
        assert should_cluster_together(seg1, seg2) is True

    def test_similar_story_context(self):
        """Segments with similar story context cluster."""
        seg1 = make_segment(0.0, 5.0, story_context="argument about heroism and sacrifice")
        seg2 = make_segment(5.0, 10.0, story_context="heated debate about sacrifice and duty")
        assert should_cluster_together(seg1, seg2) is True


class TestClusterSegments:
    """Tests for the main clustering function."""

    def test_empty_list(self):
        """Empty input returns empty list."""
        assert cluster_segments([]) == []

    def test_single_segment(self):
        """Single segment becomes one cluster."""
        seg = make_segment(0.0, 5.0)
        clusters = cluster_segments([seg])
        assert len(clusters) == 1
        assert clusters[0].segments == [seg]

    def test_continuous_segments_cluster(self):
        """Continuous segments with shared context cluster together."""
        seg1 = make_segment(0.0, 5.0, people=["Tony"], location="Lab")
        seg2 = make_segment(5.0, 10.0, people=["Tony"], location="Lab")
        seg3 = make_segment(10.0, 15.0, people=["Tony"], location="Lab")

        clusters = cluster_segments([seg1, seg2, seg3])
        assert len(clusters) == 1
        assert len(clusters[0].segments) == 3

    def test_different_contexts_split(self):
        """Segments with different contexts split into clusters."""
        seg1 = make_segment(0.0, 5.0, people=["Tony"], location="Lab")
        seg2 = make_segment(5.0, 10.0, people=["Steve"], location="Gym")  # Different
        seg3 = make_segment(10.0, 15.0, people=["Steve"], location="Gym")

        clusters = cluster_segments([seg1, seg2, seg3])
        assert len(clusters) == 2
        assert len(clusters[0].segments) == 1
        assert len(clusters[1].segments) == 2

    def test_time_gap_splits(self):
        """Large time gaps split clusters."""
        seg1 = make_segment(0.0, 5.0, people=["Tony"], location="Lab")
        seg2 = make_segment(15.0, 20.0, people=["Tony"], location="Lab")  # 10s gap

        clusters = cluster_segments([seg1, seg2], max_gap=2.0)
        assert len(clusters) == 2

    def test_unsorted_input(self):
        """Input is sorted by timestamp before clustering."""
        seg1 = make_segment(10.0, 15.0, people=["Tony"])
        seg2 = make_segment(0.0, 5.0, people=["Tony"])
        seg3 = make_segment(5.0, 10.0, people=["Tony"])

        clusters = cluster_segments([seg1, seg2, seg3])
        # Should all cluster together regardless of input order
        assert len(clusters) == 1
        # First segment in cluster should be earliest
        assert clusters[0].segments[0].timestamp_start == 0.0


class TestClusterAnalyzer:
    """Tests for cluster summary generation."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM client."""
        class MockLLM:
            async def generate(self, prompt):
                return "This is a test summary generated by LLM."
        return MockLLM()

    @pytest.mark.asyncio
    async def test_generate_summary(self, mock_llm):
        """Summary generation works."""
        analyzer = ClusterAnalyzer(mock_llm)
        seg = make_segment(0.0, 5.0, transcript="Hello world")
        cluster = SceneCluster(id=0, segments=[seg])

        summary = await analyzer.generate_cluster_summary(cluster)
        assert summary == "This is a test summary generated by LLM."

    @pytest.mark.asyncio
    async def test_analyze_clusters(self, mock_llm):
        """Batch analysis populates summaries."""
        analyzer = ClusterAnalyzer(mock_llm)
        seg = make_segment(0.0, 5.0)
        clusters = [SceneCluster(id=0, segments=[seg])]

        result = await analyzer.analyze_clusters(clusters)
        assert result[0].cluster_summary == "This is a test summary generated by LLM."


class TestStoryBoundaryDetector:
    """Tests for LLM-based story boundary detection."""

    @pytest.fixture
    def yes_llm(self):
        """LLM that always says YES."""
        class MockLLM:
            async def generate(self, prompt):
                return "YES"
        return MockLLM()

    @pytest.fixture
    def no_llm(self):
        """LLM that always says NO."""
        class MockLLM:
            async def generate(self, prompt):
                return "NO"
        return MockLLM()

    @pytest.mark.asyncio
    async def test_detect_boundary_yes(self, yes_llm):
        """Boundary detected when LLM says YES."""
        detector = StoryBoundaryDetector(yes_llm)
        seg1 = make_segment(0.0, 5.0)
        seg2 = make_segment(5.0, 10.0)

        result = await detector.detect_boundary(seg1, seg2)
        assert result is True

    @pytest.mark.asyncio
    async def test_detect_boundary_no(self, no_llm):
        """No boundary when LLM says NO."""
        detector = StoryBoundaryDetector(no_llm)
        seg1 = make_segment(0.0, 5.0)
        seg2 = make_segment(5.0, 10.0)

        result = await detector.detect_boundary(seg1, seg2)
        assert result is False

    @pytest.mark.asyncio
    async def test_refine_clusters_splits(self, yes_llm):
        """Clusters are split at detected boundaries."""
        detector = StoryBoundaryDetector(yes_llm)
        seg1 = make_segment(0.0, 5.0)
        seg2 = make_segment(5.0, 10.0)
        seg3 = make_segment(10.0, 15.0)

        cluster = SceneCluster(id=0, segments=[seg1, seg2, seg3])
        refined = await detector.refine_clusters([cluster])

        # Should split into 3 clusters (boundary between each)
        assert len(refined) == 3

    @pytest.mark.asyncio
    async def test_refine_clusters_no_split(self, no_llm):
        """Clusters remain intact when no boundaries detected."""
        detector = StoryBoundaryDetector(no_llm)
        seg1 = make_segment(0.0, 5.0)
        seg2 = make_segment(5.0, 10.0)

        cluster = SceneCluster(id=0, segments=[seg1, seg2])
        refined = await detector.refine_clusters([cluster])

        assert len(refined) == 1
        assert len(refined[0].segments) == 2
