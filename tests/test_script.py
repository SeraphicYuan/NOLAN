"""Tests for script conversion."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from nolan.script import ScriptConverter, ScriptSection, Script, format_timestamp
from nolan.parser import Section


@pytest.fixture
def mock_llm():
    """Create a mock LLM client."""
    client = Mock()
    client.generate = AsyncMock(return_value="""Venezuela. A land of stunning beauty.

Now, let's look at what makes this nation so complex. Every day, millions struggle just to get by.""")
    return client


def test_script_section_has_timestamp():
    """Script section includes calculated timestamp."""
    section = ScriptSection(
        title="Hook",
        narration="This is the narration text.",
        start_time=0.0,
        end_time=45.0,
        word_count=5
    )

    assert section.timestamp == "0:00 - 0:45"


def test_format_timestamp():
    """Timestamp formatting works correctly."""
    assert format_timestamp(0) == "0:00"
    assert format_timestamp(45) == "0:45"
    assert format_timestamp(60) == "1:00"
    assert format_timestamp(125) == "2:05"
    assert format_timestamp(3661) == "1:01:01"


@pytest.mark.asyncio
async def test_convert_section_calls_llm(mock_llm):
    """Converter uses LLM to transform section."""
    converter = ScriptConverter(llm_client=mock_llm)
    section = Section(title="Hook", content="Original content here.", word_count=3)

    result = await converter.convert_section(section, start_time=0.0)

    assert mock_llm.generate.called
    assert result.title == "Hook"
    assert len(result.narration) > 0


@pytest.mark.asyncio
async def test_convert_essay_produces_full_script(mock_llm):
    """Converter produces complete script with all sections."""
    converter = ScriptConverter(llm_client=mock_llm)
    sections = [
        Section(title="Hook", content="Hook content.", word_count=150),
        Section(title="Context", content="Context content.", word_count=300),
    ]

    script = await converter.convert_essay(sections)

    assert len(script.sections) == 2
    assert script.sections[0].start_time == 0.0
    assert script.sections[1].start_time > 0  # Continues from previous
    assert script.total_duration > 0


def test_script_to_markdown():
    """Script can be exported to markdown."""
    script = Script(sections=[
        ScriptSection(
            title="Hook",
            narration="This is the hook narration.",
            start_time=0.0,
            end_time=30.0,
            word_count=5
        ),
        ScriptSection(
            title="Context",
            narration="This is the context narration.",
            start_time=30.0,
            end_time=90.0,
            word_count=5
        ),
    ])

    markdown = script.to_markdown()

    assert "# Video Script" in markdown
    assert "## Hook [0:00 - 0:30]" in markdown
    assert "## Context [0:30 - 1:30]" in markdown
    assert "This is the hook narration." in markdown
