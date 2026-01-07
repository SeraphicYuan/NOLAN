"""Tests for essay parsing."""

import pytest
from nolan.parser import parse_essay, Section


def test_parse_essay_extracts_sections():
    """Parser extracts markdown sections."""
    essay = """## Hook

This is the hook content.
It has multiple lines.

## Context

This is context content.
"""

    sections = parse_essay(essay)

    assert len(sections) == 2
    assert sections[0].title == "Hook"
    assert "hook content" in sections[0].content
    assert sections[1].title == "Context"


def test_parse_essay_calculates_word_count():
    """Parser calculates word count per section."""
    essay = """## Section One

One two three four five.

## Section Two

Six seven eight.
"""

    sections = parse_essay(essay)

    assert sections[0].word_count == 5
    assert sections[1].word_count == 3


def test_parse_real_essay(sample_essay):
    """Parser handles the Venezuela sample essay."""
    sections = parse_essay(sample_essay)

    assert len(sections) == 7
    assert sections[0].title == "Hook"
    assert sections[1].title == "Context"
    assert sections[2].title == "Thesis"
    assert sections[3].title == "Evidence 1"
    assert sections[6].title == "Conclusion"
