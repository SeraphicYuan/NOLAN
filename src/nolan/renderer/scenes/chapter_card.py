"""
Chapter card renderer.

Creates animated chapter title cards:
- Chapter number (e.g., "CHAPTER 1", "PART II")
- Chapter title
- Optional subtitle/description

Animation: Number fades in, title slides up with underline
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ExpandWidth, ScaleIn
from ..layout import Position, POSITIONS


class ChapterCardRenderer(BaseRenderer):
    """
    Render animated chapter title cards.

    Usage:
        renderer = ChapterCardRenderer(
            chapter_number="CHAPTER 1",
            title="The Rise of a Revolution",
            subtitle="Venezuela 1998-2002"
        )
        renderer.render("output.mp4", duration=5.0)
    """

    def __init__(
        self,
        title: str,
        chapter_number: str = None,
        subtitle: str = None,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (12, 12, 18),
        title_color: Tuple[int, int, int] = (255, 255, 255),
        number_color: Tuple[int, int, int] = (140, 140, 160),
        subtitle_color: Tuple[int, int, int] = (160, 160, 180),
        accent_color: Tuple[int, int, int] = (255, 180, 100),
        # Typography
        title_size: int = 64,
        number_size: int = 24,
        subtitle_size: int = 28,
        title_font: str = "C:/Windows/Fonts/arialbd.ttf",
        number_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.title = title
        self.chapter_number = chapter_number
        self.subtitle = subtitle
        self.title_color = title_color
        self.number_color = number_color
        self.subtitle_color = subtitle_color
        self.accent_color = accent_color
        self.title_size = title_size
        self.number_size = number_size
        self.subtitle_size = subtitle_size
        self.title_font = title_font
        self.number_font = number_font
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)

        # Chapter number label (optional)
        current_y = base_y - 80
        if self.chapter_number:
            number_element = Element(
                id="chapter_number",
                element_type="text",
                text=self.chapter_number.upper(),
                font_path=self.number_font,
                font_size=self.number_size,
                color=self.number_color,
                x='center',
                y=current_y,
            )
            number_element.add_effect(
                FadeIn(start=0.2, duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(number_element)
            current_y = base_y - 20

        # Main title
        title_element = Element(
            id="title",
            element_type="text",
            text=self.title,
            font_path=self.title_font,
            font_size=self.title_size,
            color=self.title_color,
            x='center',
            y=current_y,
        )
        title_element.add_effects([
            FadeIn(start=0.4, duration=0.6, easing="ease_out_cubic"),
            SlideUp(start=0.4, duration=0.6, distance=25, easing="ease_out_cubic"),
        ])
        self.add_element(title_element)

        # Accent line below title
        line_y = current_y + self.title_size + 20
        line_element = Element(
            id="accent_line",
            element_type="rectangle",
            color=self.accent_color,
            x='center',
            y=line_y,
            width=300,
            height=4,
        )
        line_element.add_effect(
            ExpandWidth(start=0.7, duration=0.5, easing="ease_out_quart")
        )
        self.add_element(line_element)

        # Subtitle (optional)
        if self.subtitle:
            subtitle_y = line_y + 30
            subtitle_element = Element(
                id="subtitle",
                element_type="text",
                text=self.subtitle,
                font_path=self.number_font,
                font_size=self.subtitle_size,
                color=self.subtitle_color,
                x='center',
                y=subtitle_y,
            )
            subtitle_element.add_effect(
                FadeIn(start=1.0, duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(subtitle_element)


def render_chapter_card(
    title: str,
    chapter_number: str = None,
    subtitle: str = None,
    output_path: str = "chapter.mp4",
    duration: float = 5.0,
    **style_kwargs,
) -> str:
    """Render an animated chapter title card."""
    renderer = ChapterCardRenderer(
        title, chapter_number=chapter_number, subtitle=subtitle, **style_kwargs
    )
    return renderer.render(output_path, duration=duration)
