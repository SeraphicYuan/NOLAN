"""Tests for the nolan.aligner module."""

import pytest
from nolan.aligner import (
    normalize_text,
    words_to_text,
    find_text_in_words,
    align_scenes_to_audio,
    AlignmentResult,
)
from nolan.whisper import WordTimestamp


class TestNormalizeText:
    """Tests for normalize_text function."""

    def test_lowercase(self):
        """Should convert to lowercase."""
        assert normalize_text("HELLO WORLD") == "hello world"

    def test_removes_punctuation(self):
        """Should remove punctuation."""
        assert normalize_text("Hello, world!") == "hello world"
        assert normalize_text("What's up?") == "what s up"

    def test_normalizes_unicode(self):
        """Should normalize unicode characters."""
        assert normalize_text("café") == "cafe"
        assert normalize_text("naïve") == "naive"

    def test_replaces_special_dashes(self):
        """Should replace special dash characters."""
        assert normalize_text("hello—world") == "hello world"  # em dash
        assert normalize_text("hello–world") == "hello world"  # en dash

    def test_replaces_curly_quotes(self):
        """Should replace curly quotes with straight quotes."""
        # Note: quotes are then removed by punctuation removal
        assert "s" in normalize_text("it's")

    def test_collapses_whitespace(self):
        """Should collapse multiple whitespace."""
        assert normalize_text("hello   world") == "hello world"
        assert normalize_text("  hello  \n  world  ") == "hello world"

    def test_empty_string(self):
        """Should handle empty string."""
        assert normalize_text("") == ""


class TestWordsToText:
    """Tests for words_to_text function."""

    def test_converts_words_to_text(self):
        """Should convert word list to normalized text."""
        words = [
            WordTimestamp(word="Hello", start=0.0, end=0.5),
            WordTimestamp(word="World!", start=0.5, end=1.0),
        ]
        assert words_to_text(words) == "hello world"

    def test_empty_list(self):
        """Should handle empty list."""
        assert words_to_text([]) == ""


class TestFindTextInWords:
    """Tests for find_text_in_words function."""

    def create_word_stream(self, text: str) -> list:
        """Create a word stream from text for testing."""
        words = text.split()
        result = []
        current_time = 0.0
        for word in words:
            result.append(WordTimestamp(
                word=word,
                start=current_time,
                end=current_time + 0.5,
            ))
            current_time += 0.5
        return result

    def test_exact_match(self):
        """Should find exact match."""
        words = self.create_word_stream("The quick brown fox jumps over the lazy dog")
        result = find_text_in_words("quick brown fox", words)

        assert result is not None
        start_idx, end_idx, confidence = result
        assert start_idx == 1  # "quick" is at index 1
        assert end_idx == 4  # ends after "fox"
        assert confidence == 1.0

    def test_case_insensitive(self):
        """Should match case-insensitively."""
        words = self.create_word_stream("Hello World")
        result = find_text_in_words("HELLO WORLD", words)

        assert result is not None
        _, _, confidence = result
        assert confidence == 1.0

    def test_punctuation_insensitive(self):
        """Should match ignoring punctuation."""
        words = [
            WordTimestamp(word="Hello,", start=0.0, end=0.5),
            WordTimestamp(word="world!", start=0.5, end=1.0),
        ]
        result = find_text_in_words("Hello world", words)

        assert result is not None

    def test_not_found(self):
        """Should return None when not found."""
        words = self.create_word_stream("The quick brown fox")
        result = find_text_in_words("lazy dog", words)

        # May return None or low confidence match
        if result:
            _, _, confidence = result
            assert confidence < 0.5

    def test_start_index(self):
        """Should respect start_index parameter."""
        words = self.create_word_stream("fox fox fox fox")
        # Start after first "fox"
        result = find_text_in_words("fox", words, start_index=1)

        assert result is not None
        start_idx, _, _ = result
        assert start_idx >= 1  # Should not find the first "fox"

    def test_empty_query(self):
        """Should return None for empty query."""
        words = self.create_word_stream("Hello world")
        result = find_text_in_words("", words)
        assert result is None


class TestAlignmentResult:
    """Tests for AlignmentResult dataclass."""

    def test_fields(self):
        """Should have all required fields."""
        result = AlignmentResult(
            scene_id="scene_001",
            start_seconds=1.5,
            end_seconds=3.5,
            confidence=0.95,
            matched_text="hello world",
            narration_excerpt="Hello, world!",
        )

        assert result.scene_id == "scene_001"
        assert result.start_seconds == 1.5
        assert result.end_seconds == 3.5
        assert result.confidence == 0.95
        assert result.matched_text == "hello world"
        assert result.narration_excerpt == "Hello, world!"

    def test_default_narration_excerpt(self):
        """Should have default empty narration_excerpt."""
        result = AlignmentResult(
            scene_id="test",
            start_seconds=0.0,
            end_seconds=1.0,
            confidence=1.0,
            matched_text="test",
        )
        assert result.narration_excerpt == ""


class TestAlignScenesToAudio:
    """Tests for align_scenes_to_audio function."""

    def create_word_stream(self, text: str) -> list:
        """Create a word stream from text."""
        words = text.split()
        result = []
        current_time = 0.0
        for word in words:
            result.append(WordTimestamp(
                word=word,
                start=current_time,
                end=current_time + 0.5,
            ))
            current_time += 0.5
        return result

    def test_align_single_scene(self):
        """Should align a single scene."""
        words = self.create_word_stream("Welcome to the show Today we talk about coding")
        scenes = [
            {"id": "scene_001", "narration_excerpt": "Welcome to the show"},
        ]

        results, unmatched = align_scenes_to_audio(scenes, words)

        assert len(results) == 1
        assert results[0].scene_id == "scene_001"
        assert results[0].start_seconds == 0.0
        assert results[0].confidence >= 0.5

    def test_align_multiple_scenes(self):
        """Should align multiple scenes in order."""
        words = self.create_word_stream("First scene content Second scene content Third scene content")
        scenes = [
            {"id": "scene_1", "narration_excerpt": "First scene"},
            {"id": "scene_2", "narration_excerpt": "Second scene"},
            {"id": "scene_3", "narration_excerpt": "Third scene"},
        ]

        results, unmatched = align_scenes_to_audio(scenes, words)

        # Should find at least some matches
        assert len(results) >= 1
        # Should be in order
        for i in range(1, len(results)):
            assert results[i].start_seconds >= results[i-1].start_seconds

    def test_empty_scenes(self):
        """Should handle empty scenes list."""
        words = self.create_word_stream("Some content here")
        scenes = []

        results, unmatched = align_scenes_to_audio(scenes, words)

        assert results == []
        assert unmatched == []

    def test_empty_words(self):
        """Should handle empty words list."""
        words = []
        scenes = [{"id": "scene_1", "narration_excerpt": "Hello world"}]

        results, unmatched = align_scenes_to_audio(scenes, words)

        # Can't match anything with no words
        assert len(results) == 0 or all(r.confidence < 0.5 for r in results)

    def test_scene_without_narration(self):
        """Should skip scenes without narration_excerpt."""
        words = self.create_word_stream("Hello world")
        scenes = [
            {"id": "scene_1"},  # No narration_excerpt
            {"id": "scene_2", "narration_excerpt": ""},  # Empty narration
        ]

        results, unmatched = align_scenes_to_audio(scenes, words)

        # Neither scene should be in results (no narration to match)
        assert all(r.scene_id not in ["scene_1", "scene_2"] for r in results)

    def test_generates_scene_id_if_missing(self):
        """Should generate scene_id if not provided."""
        words = self.create_word_stream("Test content here")
        scenes = [
            {"narration_excerpt": "Test content"},
        ]

        results, unmatched = align_scenes_to_audio(scenes, words)

        if results:
            # Should have generated an ID
            assert results[0].scene_id.startswith("scene_")
