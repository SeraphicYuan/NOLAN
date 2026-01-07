"""Essay parsing for NOLAN."""

import re
from dataclasses import dataclass
from typing import List


@dataclass
class Section:
    """A section of the essay."""
    title: str
    content: str
    word_count: int

    @property
    def estimated_duration_seconds(self) -> float:
        """Estimate duration at 150 words per minute."""
        return (self.word_count / 150) * 60


def parse_essay(text: str) -> List[Section]:
    """Parse a markdown essay into sections.

    Args:
        text: The essay text in markdown format.

    Returns:
        List of Section objects.
    """
    # Split on ## headers (level 2)
    pattern = r'^##\s+(.+?)$'

    sections = []
    current_title = None
    current_content = []

    for line in text.split('\n'):
        header_match = re.match(pattern, line)

        if header_match:
            # Save previous section if exists
            if current_title is not None:
                content = '\n'.join(current_content).strip()
                word_count = len(content.split())
                sections.append(Section(
                    title=current_title,
                    content=content,
                    word_count=word_count
                ))

            # Start new section
            current_title = header_match.group(1).strip()
            current_content = []
        else:
            current_content.append(line)

    # Don't forget the last section
    if current_title is not None:
        content = '\n'.join(current_content).strip()
        word_count = len(content.split())
        sections.append(Section(
            title=current_title,
            content=content,
            word_count=word_count
        ))

    return sections
