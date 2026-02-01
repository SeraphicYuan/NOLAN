"""
Smart text layout system for Python renderer.

Handles:
- Automatic line wrapping based on max width
- Dynamic font sizing to fit content
- Multi-line text rendering with proper spacing
- Alignment within text boxes

Usage:
    from nolan.renderer.text_layout import TextLayout, fit_text

    layout = TextLayout(
        text="Very long sentence that needs wrapping",
        font_path="arial.ttf",
        font_size=48,
        max_width=800,
        max_lines=3
    )

    # Get wrapped lines and final font size
    lines = layout.lines
    final_size = layout.font_size
    total_height = layout.total_height
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
from PIL import ImageFont


@dataclass
class TextLayout:
    """
    Smart text layout with automatic wrapping and sizing.

    Attributes:
        text: Original text to layout
        font_path: Path to font file
        font_size: Initial/target font size
        max_width: Maximum width in pixels for text
        max_lines: Maximum number of lines allowed (0 = unlimited)
        min_font_size: Minimum font size to try before giving up
        line_spacing: Multiplier for line height (1.2 = 20% extra)
    """
    text: str
    font_path: str
    font_size: int
    max_width: int
    max_lines: int = 0  # 0 = unlimited
    min_font_size: int = 16
    line_spacing: float = 1.3

    def __post_init__(self):
        """Calculate layout after initialization."""
        self._calculate_layout()

    def _calculate_layout(self):
        """Calculate optimal font size and line wrapping."""
        self.lines: List[str] = []
        self.final_font_size: int = self.font_size
        self.line_height: int = 0
        self.total_height: int = 0

        if not self.text or not self.text.strip():
            return

        # Try progressively smaller font sizes
        current_size = self.font_size

        while current_size >= self.min_font_size:
            font = self._get_font(current_size)
            lines = self._wrap_text(self.text, font, self.max_width)

            # Check if we're within line limit
            if self.max_lines == 0 or len(lines) <= self.max_lines:
                self.lines = lines
                self.final_font_size = current_size
                self.line_height = int(current_size * self.line_spacing)
                self.total_height = self.line_height * len(lines)
                return

            # Reduce font size and try again
            current_size -= 2

        # Fallback: use min font size even if it exceeds max_lines
        font = self._get_font(self.min_font_size)
        self.lines = self._wrap_text(self.text, font, self.max_width)
        self.final_font_size = self.min_font_size
        self.line_height = int(self.min_font_size * self.line_spacing)
        self.total_height = self.line_height * len(self.lines)

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Load font at given size."""
        try:
            return ImageFont.truetype(self.font_path, size)
        except OSError:
            return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
        """
        Wrap text to fit within max_width.

        Uses word-based wrapping. If a single word is too long,
        it will be placed on its own line (may overflow).
        """
        if not text:
            return []

        words = text.split()
        if not words:
            return []

        lines = []
        current_line = []

        for word in words:
            # Try adding word to current line
            test_line = ' '.join(current_line + [word])
            bbox = font.getbbox(test_line)
            width = bbox[2] - bbox[0]

            if width <= max_width:
                current_line.append(word)
            else:
                # Word doesn't fit - start new line
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        # Don't forget the last line
        if current_line:
            lines.append(' '.join(current_line))

        return lines

    def get_line_positions(
        self,
        x: int,
        y: int,
        align: str = "left"
    ) -> List[Tuple[int, int, str]]:
        """
        Get (x, y, text) for each line, adjusted for alignment.

        Args:
            x: Base X position
            y: Base Y position (top of text block)
            align: "left", "center", or "right"

        Returns:
            List of (x, y, line_text) tuples
        """
        positions = []
        font = self._get_font(self.final_font_size)

        for i, line in enumerate(self.lines):
            line_y = y + (i * self.line_height)

            if align == "center":
                bbox = font.getbbox(line)
                line_width = bbox[2] - bbox[0]
                line_x = x - (line_width // 2)
            elif align == "right":
                bbox = font.getbbox(line)
                line_width = bbox[2] - bbox[0]
                line_x = x - line_width
            else:  # left
                line_x = x

            positions.append((line_x, line_y, line))

        return positions


def fit_text(
    text: str,
    font_path: str,
    font_size: int,
    max_width: int,
    max_lines: int = 3,
    min_font_size: int = 16,
) -> TextLayout:
    """
    Convenience function to create a TextLayout.

    Args:
        text: Text to layout
        font_path: Path to font
        font_size: Desired font size
        max_width: Maximum width in pixels
        max_lines: Maximum lines allowed (0 = unlimited)
        min_font_size: Minimum font size before giving up

    Returns:
        TextLayout with calculated lines and final font size
    """
    return TextLayout(
        text=text,
        font_path=font_path,
        font_size=font_size,
        max_width=max_width,
        max_lines=max_lines,
        min_font_size=min_font_size,
    )


def measure_text(
    text: str,
    font_path: str,
    font_size: int
) -> Tuple[int, int]:
    """
    Measure text dimensions without wrapping.

    Returns:
        (width, height) tuple
    """
    try:
        font = ImageFont.truetype(font_path, font_size)
    except OSError:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)

    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


# Default max widths as percentage of canvas
DEFAULT_MAX_WIDTH_PERCENT = 0.75  # 75% of canvas width
QUOTE_MAX_WIDTH_PERCENT = 0.70   # 70% for quotes (need room for quote marks)
NARROW_MAX_WIDTH_PERCENT = 0.60  # 60% for cards/documents


def calculate_max_width(canvas_width: int, style: str = "default") -> int:
    """
    Calculate appropriate max width based on canvas and style.

    Args:
        canvas_width: Canvas width in pixels
        style: "default", "quote", or "narrow"

    Returns:
        Max width in pixels
    """
    percentages = {
        "default": DEFAULT_MAX_WIDTH_PERCENT,
        "quote": QUOTE_MAX_WIDTH_PERCENT,
        "narrow": NARROW_MAX_WIDTH_PERCENT,
    }
    percent = percentages.get(style, DEFAULT_MAX_WIDTH_PERCENT)
    return int(canvas_width * percent)
