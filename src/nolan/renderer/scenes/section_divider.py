"""
Section divider renderer.

Creates animated section transition cards:
- Full-screen color transition
- Optional section number/label
- Section title
- Dramatic timing for pacing

Animation: Background wipes in, text fades dramatically
"""

from typing import Tuple, Optional, Union, Literal
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ScaleIn, ExpandWidth
from ..layout import Position, POSITIONS


DividerStyle = Literal["simple", "numbered", "dramatic", "minimal"]


class SectionDividerRenderer(BaseRenderer):
    """
    Render animated section divider transitions.

    Usage:
        renderer = SectionDividerRenderer(
            title="The Collapse",
            section_number="Part II",
            style="dramatic"
        )
        renderer.render("output.mp4", duration=4.0)
    """

    STYLE_PRESETS = {
        "simple": {
            "bg_color": (20, 20, 28),
            "accent_color": (100, 140, 255),
            "title_size": 72,
        },
        "numbered": {
            "bg_color": (18, 22, 30),
            "accent_color": (255, 180, 100),
            "title_size": 64,
        },
        "dramatic": {
            "bg_color": (10, 10, 15),
            "accent_color": (200, 60, 60),
            "title_size": 80,
        },
        "minimal": {
            "bg_color": (25, 25, 30),
            "accent_color": (150, 150, 160),
            "title_size": 56,
        },
    }

    def __init__(
        self,
        title: str,
        section_number: str = None,  # e.g., "Part II", "Chapter 3", "01"
        subtitle: str = None,
        style: DividerStyle = "simple",
        # Position
        position: Union[str, Position] = "center",
        # Visual style (overrides)
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = None,
        title_color: Tuple[int, int, int] = (255, 255, 255),
        number_color: Tuple[int, int, int] = None,
        subtitle_color: Tuple[int, int, int] = (160, 160, 180),
        accent_color: Tuple[int, int, int] = None,
        # Typography
        title_size: int = None,
        number_size: int = 28,
        subtitle_size: int = 28,
        title_font: str = "C:/Windows/Fonts/arialbd.ttf",
        number_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        # Get style preset
        preset = self.STYLE_PRESETS.get(style, self.STYLE_PRESETS["simple"])

        # Apply preset defaults
        if bg_color is None:
            bg_color = preset["bg_color"]
        if accent_color is None:
            accent_color = preset["accent_color"]
        if title_size is None:
            title_size = preset["title_size"]
        if number_color is None:
            number_color = accent_color

        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.title = title
        self.section_number = section_number
        self.subtitle = subtitle
        self.style = style
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

        current_y = base_y - 60

        # Section number (optional)
        if self.section_number:
            number_element = Element(
                id="section_number",
                element_type="text",
                text=self.section_number.upper(),
                font_path=self.number_font,
                font_size=self.number_size,
                color=self.number_color,
                x='center',
                y=current_y - 60,
            )
            number_element.add_effect(
                FadeIn(start=0.3, duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(number_element)

        # Accent line above title
        line_y = current_y - 20
        line_element = Element(
            id="accent_line",
            element_type="rectangle",
            color=self.accent_color,
            x='center',
            y=line_y,
            width=120,
            height=4,
        )
        line_element.add_effect(
            ExpandWidth(start=0.4, duration=0.5, easing="ease_out_quart")
        )
        self.add_element(line_element)

        # Main title
        title_element = Element(
            id="title",
            element_type="text",
            text=self.title,
            font_path=self.title_font,
            font_size=self.title_size,
            color=self.title_color,
            x='center',
            y=current_y + 20,
        )
        title_element.add_effects([
            FadeIn(start=0.6, duration=0.7, easing="ease_out_cubic"),
            ScaleIn(start=0.6, duration=0.7, from_scale=0.9, easing="ease_out_cubic"),
        ])
        self.add_element(title_element)

        # Subtitle (optional)
        if self.subtitle:
            subtitle_y = current_y + self.title_size + 40
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
                FadeIn(start=1.1, duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(subtitle_element)


def render_section_divider(
    title: str,
    section_number: str = None,
    style: DividerStyle = "simple",
    output_path: str = "divider.mp4",
    duration: float = 4.0,
    **style_kwargs,
) -> str:
    """Render an animated section divider transition."""
    renderer = SectionDividerRenderer(
        title, section_number=section_number, style=style, **style_kwargs
    )
    return renderer.render(output_path, duration=duration)
