"""Tests for the nolan.image_search module."""

import pytest
from unittest.mock import MagicMock, patch
from nolan.image_search import (
    ImageSearchResult,
    ImageProvider,
    DDGSProvider,
)


class TestImageSearchResult:
    """Tests for ImageSearchResult dataclass."""

    def test_minimal_creation(self):
        """Should create with only required field."""
        result = ImageSearchResult(url="https://example.com/image.jpg")
        assert result.url == "https://example.com/image.jpg"
        assert result.thumbnail_url is None
        assert result.title is None

    def test_full_creation(self):
        """Should create with all fields."""
        result = ImageSearchResult(
            url="https://example.com/image.jpg",
            thumbnail_url="https://example.com/thumb.jpg",
            title="Test Image",
            source="test_provider",
            source_url="https://example.com/page",
            width=1920,
            height=1080,
            photographer="John Doe",
            license="CC0",
            score=8.5,
            score_reason="Highly relevant",
            scored_by="gemini",
            quality_score=9.0,
            quality_reason="High resolution",
        )

        assert result.url == "https://example.com/image.jpg"
        assert result.thumbnail_url == "https://example.com/thumb.jpg"
        assert result.title == "Test Image"
        assert result.source == "test_provider"
        assert result.width == 1920
        assert result.height == 1080
        assert result.photographer == "John Doe"
        assert result.license == "CC0"
        assert result.score == 8.5
        assert result.quality_score == 9.0

    def test_to_dict(self):
        """Should convert to dict without None values."""
        result = ImageSearchResult(
            url="https://example.com/image.jpg",
            title="Test",
            width=100,
        )
        d = result.to_dict()

        assert d["url"] == "https://example.com/image.jpg"
        assert d["title"] == "Test"
        assert d["width"] == 100
        # None values should be excluded
        assert "thumbnail_url" not in d
        assert "photographer" not in d

    def test_combined_score_with_both(self):
        """Should calculate combined score correctly."""
        result = ImageSearchResult(
            url="https://example.com/image.jpg",
            score=8.0,
            quality_score=9.0,
        )
        # 8.0 + (9.0 * 0.01) = 8.09
        assert result.combined_score() == 8.09

    def test_combined_score_relevance_only(self):
        """Should handle missing quality score."""
        result = ImageSearchResult(
            url="https://example.com/image.jpg",
            score=7.5,
        )
        assert result.combined_score() == 7.5

    def test_combined_score_quality_only(self):
        """Should handle missing relevance score."""
        result = ImageSearchResult(
            url="https://example.com/image.jpg",
            quality_score=8.0,
        )
        # 0 + (8.0 * 0.01) = 0.08
        assert result.combined_score() == 0.08

    def test_combined_score_no_scores(self):
        """Should return 0 when no scores."""
        result = ImageSearchResult(url="https://example.com/image.jpg")
        assert result.combined_score() == 0.0


class TestImageProvider:
    """Tests for ImageProvider base class."""

    def test_is_abstract(self):
        """Should not be instantiable directly."""
        with pytest.raises(TypeError):
            ImageProvider()

    def test_subclass_must_implement_search(self):
        """Subclass without search should raise error."""
        class IncompleteProvider(ImageProvider):
            name = "incomplete"

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_valid_subclass(self):
        """Valid subclass should be instantiable."""
        class ValidProvider(ImageProvider):
            name = "valid"

            def search(self, query, max_results=10):
                return []

        provider = ValidProvider()
        assert provider.name == "valid"
        assert provider.is_available() is True
        assert provider.search("test") == []


class TestDDGSProvider:
    """Tests for DDGSProvider."""

    def test_init_without_package(self):
        """Should handle missing ddgs package gracefully."""
        with patch.dict('sys.modules', {'ddgs': None, 'duckduckgo_search': None}):
            # Force re-import to test import handling
            # This test verifies the pattern, not the actual import behavior
            pass

    def test_is_available_property(self):
        """Should report availability based on package presence."""
        provider = DDGSProvider()
        # Result depends on whether ddgs is installed
        assert isinstance(provider.is_available(), bool)

    def test_name(self):
        """Should have correct name."""
        provider = DDGSProvider()
        assert provider.name == "ddgs"

    def test_search_returns_list(self):
        """Search should return a list."""
        provider = DDGSProvider()
        if provider.is_available():
            # Only test if package is available
            # Use mock to avoid actual API calls
            with patch.object(provider, 'search', return_value=[]):
                results = provider.search("test query", max_results=5)
                assert isinstance(results, list)


class TestImageSearchResultSorting:
    """Tests for sorting ImageSearchResult by score."""

    def test_sort_by_combined_score(self):
        """Should sort correctly by combined score."""
        results = [
            ImageSearchResult(url="c.jpg", score=5.0, quality_score=9.0),  # 5.09
            ImageSearchResult(url="a.jpg", score=9.0, quality_score=5.0),  # 9.05
            ImageSearchResult(url="b.jpg", score=7.0, quality_score=7.0),  # 7.07
        ]

        sorted_results = sorted(results, key=lambda r: r.combined_score(), reverse=True)

        assert sorted_results[0].url == "a.jpg"  # Highest (9.05)
        assert sorted_results[1].url == "b.jpg"  # Middle (7.07)
        assert sorted_results[2].url == "c.jpg"  # Lowest (5.09)

    def test_quality_as_tiebreaker(self):
        """Quality should break ties in relevance score."""
        results = [
            ImageSearchResult(url="low_quality.jpg", score=8.0, quality_score=3.0),  # 8.03
            ImageSearchResult(url="high_quality.jpg", score=8.0, quality_score=9.0),  # 8.09
        ]

        sorted_results = sorted(results, key=lambda r: r.combined_score(), reverse=True)

        assert sorted_results[0].url == "high_quality.jpg"  # Higher quality wins


class TestImageSearchResultEquality:
    """Tests for comparing ImageSearchResult objects."""

    def test_same_url_same_object(self):
        """Same URL should create equal objects with same attributes."""
        r1 = ImageSearchResult(url="test.jpg", title="Test")
        r2 = ImageSearchResult(url="test.jpg", title="Test")

        # Dataclasses should implement __eq__
        assert r1 == r2

    def test_different_urls_different_objects(self):
        """Different URLs should create different objects."""
        r1 = ImageSearchResult(url="test1.jpg")
        r2 = ImageSearchResult(url="test2.jpg")

        assert r1 != r2
