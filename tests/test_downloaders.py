"""Tests for the downloaders package utilities."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from nolan.downloaders import (
    sanitize_filename,
    extract_lottie_metadata,
    save_lottie_json,
    RateLimiter,
    CatalogBuilder,
    BaseLottieTemplate,
)


class TestSanitizeFilename:
    """Tests for sanitize_filename utility."""

    def test_removes_filesystem_invalid_chars(self):
        """Should remove filesystem-invalid characters."""
        assert 'testfilename' in sanitize_filename('Test/File:Name')
        assert sanitize_filename('a<b>c:d"e/f\\g|h?i*j') == 'abcdefghij'

    def test_replaces_spaces_with_hyphens(self):
        """Should replace spaces with hyphens."""
        result = sanitize_filename('Hello World')
        assert ' ' not in result
        assert '-' in result

    def test_collapses_multiple_hyphens(self):
        """Should collapse multiple consecutive hyphens."""
        result = sanitize_filename('Test---Name')
        assert '---' not in result

    def test_lowercases_output(self):
        """Should return lowercase output."""
        result = sanitize_filename('UPPERCASE')
        assert result == result.lower()

    def test_truncates_to_max_length(self):
        """Should truncate to max_length."""
        result = sanitize_filename('a' * 100, max_length=20)
        assert len(result) <= 20

    def test_handles_empty_string(self):
        """Should handle empty strings."""
        result = sanitize_filename('')
        assert result == ''


class TestExtractLottieMetadata:
    """Tests for extract_lottie_metadata utility."""

    def test_extracts_basic_fields(self):
        """Should extract basic Lottie fields."""
        data = {
            'w': 1920,
            'h': 1080,
            'fr': 30,
            'ip': 0,
            'op': 90,
            'layers': [1, 2, 3]
        }
        meta = extract_lottie_metadata(data)

        assert meta['width'] == 1920
        assert meta['height'] == 1080
        assert meta['fps'] == 30
        assert meta['frames'] == 90
        assert meta['layer_count'] == 3

    def test_calculates_duration(self):
        """Should calculate duration from frames and fps."""
        data = {'w': 100, 'h': 100, 'fr': 30, 'ip': 0, 'op': 60, 'layers': []}
        meta = extract_lottie_metadata(data)
        assert meta['duration_seconds'] == 2.0

    def test_handles_non_zero_in_point(self):
        """Should handle non-zero in-point correctly."""
        data = {'w': 100, 'h': 100, 'fr': 30, 'ip': 30, 'op': 90, 'layers': []}
        meta = extract_lottie_metadata(data)
        assert meta['frames'] == 60
        assert meta['duration_seconds'] == 2.0

    def test_handles_missing_fields(self):
        """Should handle missing fields gracefully."""
        meta = extract_lottie_metadata({})
        assert meta['width'] == 0
        assert meta['fps'] == 0

    def test_zero_fps_no_division_error(self):
        """Should not raise division error when fps is 0."""
        data = {'w': 100, 'h': 100, 'fr': 0, 'ip': 0, 'op': 60, 'layers': []}
        meta = extract_lottie_metadata(data)
        assert meta['duration_seconds'] == 0


class TestSaveLottieJson:
    """Tests for save_lottie_json utility."""

    def test_creates_parent_directories(self, tmp_path):
        """Should create parent directories if they don't exist."""
        output_path = tmp_path / 'nested' / 'dir' / 'file.json'
        data = {'w': 100, 'h': 100}

        save_lottie_json(data, output_path)

        assert output_path.exists()
        assert output_path.parent.exists()

    def test_returns_file_size(self, tmp_path):
        """Should return the file size in bytes."""
        output_path = tmp_path / 'test.json'
        data = {'w': 100, 'h': 100}

        size = save_lottie_json(data, output_path)

        assert size > 0
        assert size == output_path.stat().st_size

    def test_minified_by_default(self, tmp_path):
        """Should save minified JSON by default."""
        output_path = tmp_path / 'test.json'
        data = {'key': 'value', 'nested': {'a': 1}}

        save_lottie_json(data, output_path, minify=True)
        content = output_path.read_text()

        assert '\n' not in content
        assert '  ' not in content

    def test_pretty_print_option(self, tmp_path):
        """Should support pretty-printed output."""
        output_path = tmp_path / 'test.json'
        data = {'key': 'value'}

        save_lottie_json(data, output_path, minify=False)
        content = output_path.read_text()

        # Pretty printed should have newlines or indentation
        assert '  ' in content or '\n' in content


class TestRateLimiter:
    """Tests for RateLimiter utility."""

    def test_first_request_no_wait(self):
        """First request should not wait."""
        import time
        limiter = RateLimiter(requests_per_minute=60)

        start = time.time()
        limiter.wait()
        elapsed = time.time() - start

        # First call should be nearly instant
        assert elapsed < 0.1

    def test_subsequent_requests_wait(self):
        """Subsequent requests should wait for rate limit."""
        import time
        limiter = RateLimiter(requests_per_minute=600)  # 0.1s interval

        limiter.wait()  # First call
        start = time.time()
        limiter.wait()  # Should wait
        elapsed = time.time() - start

        # Should wait approximately the interval
        assert elapsed >= 0.08


class TestCatalogBuilder:
    """Tests for CatalogBuilder utility."""

    def test_builds_catalog_structure(self, tmp_path):
        """Should build catalog with correct structure."""
        builder = CatalogBuilder('test-source', tmp_path)

        templates = [
            BaseLottieTemplate(
                id='1', name='Test 1', category='cat1',
                width=100, height=100, fps=30
            ),
            BaseLottieTemplate(
                id='2', name='Test 2', category='cat2',
                width=200, height=200, fps=60
            ),
        ]

        catalog = builder.build(templates, 'test-catalog.json')

        assert catalog['source'] == 'test-source'
        assert catalog['total_count'] == 2
        assert 'cat1' in catalog['categories']
        assert 'cat2' in catalog['categories']

    def test_saves_catalog_file(self, tmp_path):
        """Should save catalog JSON file."""
        builder = CatalogBuilder('test', tmp_path)
        templates = [BaseLottieTemplate(id='1', name='Test', category='cat')]

        builder.build(templates, 'catalog.json')

        catalog_path = tmp_path / 'catalog.json'
        assert catalog_path.exists()

        with open(catalog_path) as f:
            saved = json.load(f)
        assert saved['total_count'] == 1


class TestBaseLottieTemplate:
    """Tests for BaseLottieTemplate model."""

    def test_to_catalog_entry(self):
        """Should convert to catalog entry dict."""
        template = BaseLottieTemplate(
            id='test-id',
            name='Test Name',
            category='test-cat',
            source_url='https://example.com',
            width=1920,
            height=1080,
            fps=30,
            duration_seconds=2.5,
        )

        entry = template.to_catalog_entry()

        assert entry['id'] == 'test-id'
        assert entry['name'] == 'Test Name'
        assert entry['width'] == 1920
        assert entry['fps'] == 30
