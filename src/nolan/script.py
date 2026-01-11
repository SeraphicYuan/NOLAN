"""Script conversion for NOLAN."""

import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any
from pathlib import Path

from nolan.parser import Section


PROMPT_TEMPLATE = """You are converting a written essay section into a YouTube video narration script.

SECTION TITLE: {title}

ORIGINAL CONTENT:
{content}

INSTRUCTIONS:
1. Adapt the text for spoken word - it should sound natural when read aloud
2. Shorten complex sentences - break them into digestible pieces
3. Add verbal transitions where appropriate ("Now, let's look at...", "Here's the key insight...")
4. Remove parentheticals and dense citations that don't work in speech
5. Maintain the original meaning and key points
6. Keep the same approximate length (don't significantly expand or shorten)

OUTPUT:
Return ONLY the converted narration text. Do not include the section title or any other formatting."""


def format_timestamp(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


@dataclass
class ScriptSection:
    """A section of the converted script."""
    title: str
    narration: str
    start_time: float
    end_time: float
    word_count: int

    @property
    def timestamp(self) -> str:
        """Format as 'M:SS - M:SS'."""
        return f"{format_timestamp(self.start_time)} - {format_timestamp(self.end_time)}"

    @property
    def duration(self) -> float:
        """Duration in seconds."""
        return self.end_time - self.start_time


@dataclass
class Script:
    """Complete converted script."""
    sections: List[ScriptSection] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        """Total duration in seconds."""
        if not self.sections:
            return 0.0
        return self.sections[-1].end_time

    def to_markdown(self) -> str:
        """Export script as markdown."""
        lines = ["# Video Script\n"]
        lines.append(f"**Total Duration:** {format_timestamp(self.total_duration)}\n")
        lines.append("---\n")

        for section in self.sections:
            lines.append(f"## {section.title} [{section.timestamp}]\n")
            lines.append(section.narration)
            lines.append("\n")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Export script as dictionary."""
        return {
            "total_duration": self.total_duration,
            "sections": [asdict(s) for s in self.sections]
        }

    def to_json(self, indent: int = 2) -> str:
        """Export script as JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save_json(self, path: str) -> None:
        """Save script to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Script":
        """Load script from dictionary."""
        script = cls()
        for section_data in data.get("sections", []):
            script.sections.append(ScriptSection(
                title=section_data["title"],
                narration=section_data["narration"],
                start_time=section_data["start_time"],
                end_time=section_data["end_time"],
                word_count=section_data["word_count"],
            ))
        return script

    @classmethod
    def load_json(cls, path: str) -> "Script":
        """Load script from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


class ScriptConverter:
    """Converts essay sections to video script narration."""

    def __init__(self, llm_client, words_per_minute: int = 150):
        """Initialize the converter.

        Args:
            llm_client: The LLM client to use for conversion.
            words_per_minute: Speaking rate for duration estimation.
        """
        self.llm = llm_client
        self.words_per_minute = words_per_minute

    async def convert_section(self, section: Section, start_time: float = 0.0) -> ScriptSection:
        """Convert a single section to script narration.

        Args:
            section: The essay section to convert.
            start_time: Start time in seconds.

        Returns:
            Converted ScriptSection.
        """
        prompt = PROMPT_TEMPLATE.format(
            title=section.title,
            content=section.content
        )

        narration = await self.llm.generate(prompt)
        narration = narration.strip()

        # Calculate timing based on output word count
        word_count = len(narration.split())
        duration = (word_count / self.words_per_minute) * 60

        return ScriptSection(
            title=section.title,
            narration=narration,
            start_time=start_time,
            end_time=start_time + duration,
            word_count=word_count
        )

    async def convert_essay(self, sections: List[Section]) -> Script:
        """Convert all sections to a complete script.

        Args:
            sections: List of essay sections.

        Returns:
            Complete Script object.
        """
        script = Script()
        current_time = 0.0

        for section in sections:
            script_section = await self.convert_section(section, start_time=current_time)
            script.sections.append(script_section)
            current_time = script_section.end_time

        return script
