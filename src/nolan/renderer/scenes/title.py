"""
Title card scene renderer.

Creates animated title cards with:
- Main title (zoom + fade)
- Subtitle (fade in)
- Accent line (expand from center)
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ScaleIn, ExpandWidth
from ..layout import Position, POSITIONS


class TitleRenderer(BaseRenderer):
    """
    Render animated title card scenes.

    Usage:
        renderer = TitleRenderer(
            title="VENEZUELA: THE PRICE OF OIL",
            subtitle="How a nation with incredible wealth became so fractured"
        )
        renderer.render("output.mp4", duration=6.0)

        # With position control
        renderer = TitleRenderer(
            title="CHAPTER ONE",
            subtitle="The Beginning",
            position="upper-third"  # Position in upper area
        )
    """

    def __init__(
        self,
        title: str,
        subtitle: str = None,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (15, 15, 20),
        title_color: Tuple[int, int, int] = (255, 255, 255),
        subtitle_color: Tuple[int, int, int] = (180, 180, 180),
        accent_color: Tuple[int, int, int] = (220, 38, 38),
        # Typography
        title_size: int = 90,
        subtitle_size: int = 32,
        title_font: str = "C:/Windows/Fonts/arialbd.ttf",
        subtitle_font: str = "C:/Windows/Fonts/arial.ttf",
        # Layout
        show_accent_line: bool = True,
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
        self.subtitle = subtitle
        self.title_color = title_color
        self.subtitle_color = subtitle_color
        self.accent_color = accent_color
        self.title_size = title_size
        self.subtitle_size = subtitle_size
        self.title_font = title_font
        self.subtitle_font = subtitle_font
        self.show_accent_line = show_accent_line

        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        # Calculate base Y from position
        base_y = int(self.height * self.position.y)

        # Calculate vertical positions relative to base
        title_y = base_y - 60
        line_y = title_y + self.title_size + 20
        subtitle_y = line_y + 40

        # Title - zoom + fade in
        title_element = Element(
            id="title",
            element_type="text",
            text=self.title,
            font_path=self.title_font,
            font_size=self.title_size,
            color=self.title_color,
            x='center',
            y=title_y,
        )
        title_element.add_effects([
            FadeIn(start=0.2, duration=0.8, easing="ease_out_cubic"),
            ScaleIn(start=0.2, duration=0.8, from_scale=0.95, easing="ease_out_cubic"),
        ])
        self.add_element(title_element)

        # Accent line - expands from center
        if self.show_accent_line:
            line_element = Element(
                id="accent_line",
                element_type="rectangle",
                color=self.accent_color,
                x='center',
                y=line_y,
                width=min(self.width - 200, 1200),  # Max width with margins
                height=4,
            )
            line_element.add_effect(
                ExpandWidth(start=0.6, duration=0.6, easing="ease_out_quart")
            )
            self.add_element(line_element)

        # Subtitle - fade in after title
        if self.subtitle:
            subtitle_element = Element(
                id="subtitle",
                element_type="text",
                text=self.subtitle,
                font_path=self.subtitle_font,
                font_size=self.subtitle_size,
                color=self.subtitle_color,
                x='center',
                y=subtitle_y,
            )
            subtitle_element.add_effect(
                FadeIn(start=1.0, duration=0.7, easing="ease_out_cubic")
            )
            self.add_element(subtitle_element)


# Convenience function
def render_title(
    title: str,
    subtitle: str = None,
    output_path: str = "title.mp4",
    duration: float = 6.0,
    **style_kwargs,
) -> str:
    """
    Quick function to render an animated title card.

    Args:
        title: Main title text
        subtitle: Subtitle text (optional)
        output_path: Output video file
        duration: Video duration in seconds
        **style_kwargs: Style options

    Returns:
        Path to rendered video
    """
    renderer = TitleRenderer(title, subtitle, **style_kwargs)
    return renderer.render(output_path, duration=duration)
