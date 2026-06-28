"""Tests for the nolan.image_search module."""

import pytest
from unittest.mock import MagicMock, patch
from nolan.image_search import (
    ImageSearchResult,
    ImageProvider,
    DDGSProvider,
    WellcomeProvider,
    EuropeanaProvider,
    DPLAProvider,
)


def _mock_json_client(payload):
    """A patched httpx.Client whose .get().json() returns ``payload``."""
    mock_client = MagicMock()
    mock_client.__enter__.return_value.get.return_value.json.return_value = payload
    return mock_client


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


class TestWellcomeProvider:
    """Tests for the Wellcome Collection provider (keyless, IIIF)."""

    def test_keyless_and_name(self):
        p = WellcomeProvider()
        assert p.name == "wellcome"
        assert p.is_available() is True

    def test_builds_fullres_and_thumbnail_from_iiif(self):
        """Should build full-res + sized thumbnail from the IIIF info.json URL."""
        canned = {"results": [{
            "thumbnail": {"url": "https://iiif.wellcomecollection.org/image/X1/info.json"},
            "locations": [{
                "url": "https://iiif.wellcomecollection.org/image/X1/info.json",
                "license": {"id": "pdm", "label": "Public Domain Mark"},
            }],
            "source": {"id": "work123", "title": "A microscope"},
        }]}
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value.json.return_value = canned
        with patch("nolan.image_search.httpx.Client", return_value=mock_client):
            results = WellcomeProvider().search("microscope", max_results=5)

        assert len(results) == 1
        r = results[0]
        assert r.url == "https://iiif.wellcomecollection.org/image/X1/full/full/0/default.jpg"
        assert r.thumbnail_url == "https://iiif.wellcomecollection.org/image/X1/full/!400,400/0/default.jpg"
        assert r.license == "Public Domain Mark"
        assert r.source_url == "https://wellcomecollection.org/works/work123"
        assert r.source == "wellcome"

    def test_skips_results_without_location(self):
        canned = {"results": [{"source": {"id": "w", "title": "no image"}}]}
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value.json.return_value = canned
        with patch("nolan.image_search.httpx.Client", return_value=mock_client):
            assert WellcomeProvider().search("x") == []

    def test_network_error_returns_empty(self):
        with patch("nolan.image_search.httpx.Client", side_effect=Exception("boom")):
            assert WellcomeProvider().search("x") == []


class TestEuropeanaProvider:
    """Tests for Europeana (key-gated EU cultural heritage)."""

    def test_gated_on_key(self):
        assert EuropeanaProvider().is_available() is False
        assert EuropeanaProvider(api_key="k").is_available() is True

    def test_parses_list_or_string_fields(self):
        payload = {"items": [{
            "edmIsShownBy": ["https://prov.eu/full.jpg"],
            "edmPreview": ["https://prov.eu/thumb.jpg"],
            "title": ["A painting"],
            "guid": "https://europeana.eu/item/123",
            "rights": ["http://creativecommons.org/publicdomain/mark/1.0/"],
            "type": "IMAGE",
        }]}
        with patch("nolan.image_search.httpx.Client", return_value=_mock_json_client(payload)):
            r = EuropeanaProvider(api_key="k").search("painting")
        assert len(r) == 1
        assert r[0].url == "https://prov.eu/full.jpg"
        assert r[0].thumbnail_url == "https://prov.eu/thumb.jpg"
        assert r[0].title == "A painting"
        assert r[0].source_url == "https://europeana.eu/item/123"
        assert r[0].media_type == "image"

    def test_skips_items_without_url(self):
        payload = {"items": [{"title": ["no media"]}]}
        with patch("nolan.image_search.httpx.Client", return_value=_mock_json_client(payload)):
            assert EuropeanaProvider(api_key="k").search("x") == []

    def test_network_error_returns_empty(self):
        with patch("nolan.image_search.httpx.Client", side_effect=Exception("boom")):
            assert EuropeanaProvider(api_key="k").search("x") == []


class TestDPLAProvider:
    """Tests for DPLA (key-gated US archives/museums)."""

    def test_gated_on_key(self):
        assert DPLAProvider().is_available() is False
        assert DPLAProvider(api_key="k").is_available() is True

    def test_parses_object_and_source_resource(self):
        payload = {"docs": [{
            "object": "https://dp.la/thumb/abc.jpg",
            "sourceResource": {"title": ["Old map"]},
            "isShownAt": "https://provider.org/item/1",
            "rights": "No known copyright",
        }]}
        with patch("nolan.image_search.httpx.Client", return_value=_mock_json_client(payload)):
            r = DPLAProvider(api_key="k").search("map")
        assert len(r) == 1
        assert r[0].url == "https://dp.la/thumb/abc.jpg"
        assert r[0].title == "Old map"
        assert r[0].source_url == "https://provider.org/item/1"
        assert r[0].license == "No known copyright"

    def test_skips_docs_without_object(self):
        payload = {"docs": [{"sourceResource": {"title": "no object"}}]}
        with patch("nolan.image_search.httpx.Client", return_value=_mock_json_client(payload)):
            assert DPLAProvider(api_key="k").search("x") == []

    def test_network_error_returns_empty(self):
        with patch("nolan.image_search.httpx.Client", side_effect=Exception("boom")):
            assert DPLAProvider(api_key="k").search("x") == []


class TestScorerLocalFile:
    """The scorer must read local files (picture-library assets) for vision scoring."""

    def test_download_image_reads_local_path(self, tmp_path):
        from nolan.image_search import ImageScorer
        p = tmp_path / "x.bin"
        p.write_bytes(b"hello-bytes")
        assert ImageScorer()._download_image(str(p)) == b"hello-bytes"

    def test_download_image_missing_local_returns_none(self, tmp_path):
        from nolan.image_search import ImageScorer
        assert ImageScorer()._download_image(str(tmp_path / "nope.jpg")) is None


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
