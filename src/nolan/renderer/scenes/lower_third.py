"""
Lower Third scene renderer.

Creates animated lower-third overlays for:
- Speaker identification
- Location labels
- Source citations

Animation: Slide in from left + fade, with accent bar
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ExpandWidth
from ..layout import Position, POSITIONS


class LowerThirdRenderer(BaseRenderer):
    """
    Render animated lower-third overlays.

    Usage:
        renderer = LowerThirdRenderer(
            name="Maria Rodriguez",
            title="Caracas Resident"
        )
        renderer.render("output.mp4", duration=4.0)

        # With position control
        renderer = LowerThirdRenderer(
            name="Dr. Smith",
            title="Economist",
            position="lower-third-left"
        )
    """

    def __init__(
        self,
        name: str,
        title: str = None,
        # Position
        position: Union[str, Position] = "lower-third-left",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (0, 0, 0, 0),  # Transparent default
        name_color: Tuple[int, int, int] = (255, 255, 255),
        title_color: Tuple[int, int, int] = (180, 180, 180),
        accent_color: Tuple[int, int, int] = (220, 38, 38),
        bar_color: Tuple[int, int, int] = (30, 30, 35),
        # Typography
        name_size: int = 42,
        title_size: int = 28,
        name_font: str = "C:/Windows/Fonts/arialbd.ttf",
        title_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        # Use dark background for now (transparency requires RGBA handling)
        super().__init__(width=width, height=height, fps=fps, bg_color=(15, 15, 20))

        self.name = name
        self.title = title
        self.position = position if isinstance(position, Position) else Position.from_preset(position)
        self.name_color = name_color
        self.title_color = title_color
        self.accent_color = accent_color
        self.bar_color = bar_color
        self.name_size = name_size
        self.title_size = title_size
        self.name_font = name_font
        self.title_font = title_font

        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        # Calculate positions based on preset
        # Lower third typically at bottom left
        base_x = int(self.width * 0.05)  # 5% from left
        base_y = int(self.height * 0.82)  # 82% from top

        # Accent bar (vertical)
        accent_bar = Element(
            id="accent_bar",
            element_type="rectangle",
            color=self.accent_color,
            x=base_x,
            y=base_y,
            width=4,
            height=60 if self.title else 40,
        )
        accent_bar.add_effect(
            FadeIn(start=0.1, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(accent_bar)

        # Name text
        name_element = Element(
            id="name",
            element_type="text",
            text=self.name.upper(),
            font_path=self.name_font,
            font_size=self.name_size,
            color=self.name_color,
            x=base_x + 20,
            y=base_y,
        )
        name_element.add_effect(
            FadeIn(start=0.2, duration=0.5, easing="ease_out_cubic")
        )
        self.add_element(name_element)

        # Title text (below name)
        if self.title:
            title_element = Element(
                id="title",
                element_type="text",
                text=self.title,
                font_path=self.title_font,
                font_size=self.title_size,
                color=self.title_color,
                x=base_x + 20,
                y=base_y + self.name_size + 8,
            )
            title_element.add_effect(
                FadeIn(start=0.4, duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(title_element)


def render_lower_third(
    name: str,
    title: str = None,
    output_path: str = "lower_third.mp4",
    duration: float = 4.0,
    position: str = "lower-third-left",
    **style_kwargs,
) -> str:
    """Render an animated lower third."""
    renderer = LowerThirdRenderer(name, title, position=position, **style_kwargs)
    return renderer.render(output_path, duration=duration)
