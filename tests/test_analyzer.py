"""Tests for segment analyzer module."""

import pytest
import json
from unittest.mock import Mock, AsyncMock

from nolan.analyzer import (
    AnalysisResult,
    SegmentAnalyzer,
    BatchAnalyzer,
)
from nolan.indexer import InferredContext


class TestAnalysisResult:
    """Tests for AnalysisResult dataclass."""

    def test_creation(self):
        """Test creating an analysis result."""
        context = InferredContext(
            people=["John"],
            location="Office",
            confidence="high"
        )
        result = AnalysisResult(
            combined_summary="A man in an office",
            inferred_context=context
        )

        assert result.combined_summary == "A man in an office"
        assert result.inferred_context.people == ["John"]
        assert result.inferred_context.location == "Office"

    def test_creation_without_context(self):
        """Test creating result without inferred context."""
        result = AnalysisResult(
            combined_summary="Simple description",
            inferred_context=None
        )
        assert result.combined_summary == "Simple description"
        assert result.inferred_context is None


class TestSegmentAnalyzer:
    """Tests for SegmentAnalyzer."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM client."""
        client = Mock()
        client.generate = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_analyze_without_transcript(self, mock_llm):
        """Test analysis without transcript returns frame description."""
        analyzer = SegmentAnalyzer(mock_llm)

        result = await analyzer.analyze(
            frame_description="A person sitting at a desk",
            transcript=None
        )

        assert result.combined_summary == "A person sitting at a desk"
        assert result.inferred_context is None
        mock_llm.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_analyze_with_transcript(self, mock_llm):
        """Test analysis with transcript."""
        mock_llm.generate.return_value = json.dumps({
            "combined_summary": "John discusses the project at his desk",
            "inferred_context": {
                "people": ["John"],
                "location": "office",
                "story_context": "project discussion",
                "confidence": "high"
            }
        })

        analyzer = SegmentAnalyzer(mock_llm)

        result = await analyzer.analyze(
            frame_description="A person sitting at a desk with a laptop",
            transcript="John said, let's discuss the project status."
        )

        assert "John" in result.combined_summary
        assert result.inferred_context is not None
        assert "John" in result.inferred_context.people
        assert result.inferred_context.location == "office"

    @pytest.mark.asyncio
    async def test_analyze_with_markdown_json(self, mock_llm):
        """Test parsing JSON wrapped in markdown code block."""
        mock_llm.generate.return_value = """```json
{
    "combined_summary": "Test summary",
    "inferred_context": {
        "people": ["Alice"],
        "confidence": "medium"
    }
}
```"""

        analyzer = SegmentAnalyzer(mock_llm)

        result = await analyzer.analyze(
            frame_description="Person talking",
            transcript="Alice explains the concept"
        )

        assert result.combined_summary == "Test summary"
        assert "Alice" in result.inferred_context.people

    @pytest.mark.asyncio
    async def test_analyze_with_invalid_json(self, mock_llm):
        """Test fallback on invalid JSON response."""
        mock_llm.generate.return_value = "Not valid JSON at all"

        analyzer = SegmentAnalyzer(mock_llm)

        result = await analyzer.analyze(
            frame_description="Original description",
            transcript="Some transcript"
        )

        # Should fall back to frame description
        assert result.combined_summary == "Original description"
        assert result.inferred_context is None

    @pytest.mark.asyncio
    async def test_analyze_with_llm_error(self, mock_llm):
        """Test fallback on LLM error."""
        mock_llm.generate.side_effect = Exception("API Error")

        analyzer = SegmentAnalyzer(mock_llm)

        result = await analyzer.analyze(
            frame_description="Frame description",
            transcript="Transcript text"
        )

        # Should return fallback with partial info
        assert "Frame description" in result.combined_summary
        assert result.inferred_context is None

    @pytest.mark.asyncio
    async def test_analyze_empty_transcript(self, mock_llm):
        """Test empty transcript treated as no transcript."""
        analyzer = SegmentAnalyzer(mock_llm)

        result = await analyzer.analyze(
            frame_description="Scene description",
            transcript="   "  # Whitespace only
        )

        assert result.combined_summary == "Scene description"
        mock_llm.generate.assert_not_called()


class TestBatchAnalyzer:
    """Tests for BatchAnalyzer."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create mock segment analyzer."""
        analyzer = Mock(spec=SegmentAnalyzer)
        analyzer.analyze = AsyncMock()
        return analyzer

    @pytest.mark.asyncio
    async def test_analyze_segments(self, mock_analyzer):
        """Test batch analysis of segments."""
        mock_analyzer.analyze.return_value = AnalysisResult(
            combined_summary="Test summary",
            inferred_context=None
        )

        batch_analyzer = BatchAnalyzer(mock_analyzer, batch_size=2)

        segments = [
            {"frame_description": "Desc 1", "transcript": "Trans 1", "timestamp": 0},
            {"frame_description": "Desc 2", "transcript": "Trans 2", "timestamp": 5},
            {"frame_description": "Desc 3", "transcript": "Trans 3", "timestamp": 10},
        ]

        results = await batch_analyzer.analyze_segments(segments)

        assert len(results) == 3
        assert mock_analyzer.analyze.call_count == 3

    @pytest.mark.asyncio
    async def test_analyze_with_exception(self, mock_analyzer):
        """Test handling exceptions in batch."""
        mock_analyzer.analyze.side_effect = [
            AnalysisResult("Summary 1", None),
            Exception("Error"),
            AnalysisResult("Summary 3", None),
        ]

        batch_analyzer = BatchAnalyzer(mock_analyzer, batch_size=5)

        segments = [
            {"frame_description": "Desc 1"},
            {"frame_description": "Desc 2"},
            {"frame_description": "Desc 3"},
        ]

        results = await batch_analyzer.analyze_segments(segments)

        assert len(results) == 3
        assert results[0].combined_summary == "Summary 1"
        assert results[1].combined_summary == "Desc 2"  # Fallback
        assert results[2].combined_summary == "Summary 3"
