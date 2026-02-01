"""
Location stamp renderer.

Creates animated location cards for establishing shots:
- Location name (city, country)
- Optional date/time
- Optional coordinates
- Subtle underline accent

Animation: Text slides in, underline expands
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ExpandWidth
from ..layout import Position, POSITIONS


class LocationStampRenderer(BaseRenderer):
    """
    Render animated location stamp cards.

    Usage:
        renderer = LocationStampRenderer(
            location="Caracas, Venezuela",
            date="March 15, 2014",
            sublocation="Presidential Palace"
        )
        renderer.render("output.mp4", duration=5.0)
    """

    def __init__(
        self,
        location: str,
        date: str = None,
        sublocation: str = None,
        coordinates: str = None,
        # Position
        position: Union[str, Position] = "lower-third-left",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (18, 18, 24),
        location_color: Tuple[int, int, int] = (255, 255, 255),
        date_color: Tuple[int, int, int] = (140, 140, 160),
        sublocation_color: Tuple[int, int, int] = (180, 180, 190),
        accent_color: Tuple[int, int, int] = (255, 180, 100),
        # Typography
        location_size: int = 42,
        date_size: int = 22,
        sublocation_size: int = 28,
        location_font: str = "C:/Windows/Fonts/arialbd.ttf",
        date_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["lower-third-left"])
        else:
            self.position = position

        self.location = location
        self.date = date
        self.sublocation = sublocation
        self.coordinates = coordinates
        self.location_color = location_color
        self.date_color = date_color
        self.sublocation_color = sublocation_color
        self.accent_color = accent_color
        self.location_size = location_size
        self.date_size = date_size
        self.sublocation_size = sublocation_size
        self.location_font = location_font
        self.date_font = date_font
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_x = int(self.width * self.position.x)
        base_y = int(self.height * self.position.y)

        # Main location text
        location_element = Element(
            id="location",
            element_type="text",
            text=self.location.upper(),
            font_path=self.location_font,
            font_size=self.location_size,
            color=self.location_color,
            x=base_x,
            y=base_y - 50,
        )
        location_element.add_effects([
            FadeIn(start=0.2, duration=0.5, easing="ease_out_cubic"),
            SlideUp(start=0.2, duration=0.5, distance=20, easing="ease_out_cubic"),
        ])
        self.add_element(location_element)

        # Accent underline
        underline_y = base_y + 5
        underline_element = Element(
            id="underline",
            element_type="rectangle",
            color=self.accent_color,
            x=base_x,
            y=underline_y,
            width=200,
            height=3,
        )
        underline_element.add_effect(
            ExpandWidth(start=0.4, duration=0.4, easing="ease_out_quart")
        )
        self.add_element(underline_element)

        # Sublocation (optional)
        info_y = underline_y + 15
        if self.sublocation:
            sub_element = Element(
                id="sublocation",
                element_type="text",
                text=self.sublocation,
                font_path=self.date_font,
                font_size=self.sublocation_size,
                color=self.sublocation_color,
                x=base_x,
                y=info_y,
            )
            sub_element.add_effect(
                FadeIn(start=0.6, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(sub_element)
            info_y += self.sublocation_size + 5

        # Date (optional)
        if self.date:
            date_element = Element(
                id="date",
                element_type="text",
                text=self.date,
                font_path=self.date_font,
                font_size=self.date_size,
                color=self.date_color,
                x=base_x,
                y=info_y,
            )
            date_element.add_effect(
                FadeIn(start=0.7, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(date_element)

        # Coordinates (optional, styled differently)
        if self.coordinates:
            coord_element = Element(
                id="coordinates",
                element_type="text",
                text=self.coordinates,
                font_path=self.date_font,
                font_size=18,
                color=self.date_color,
                x=base_x,
                y=info_y + 30,
            )
            coord_element.add_effect(
                FadeIn(start=0.9, duration=0.3, easing="ease_out_cubic")
            )
            self.add_element(coord_element)


def render_location_stamp(
    location: str,
    date: str = None,
    sublocation: str = None,
    output_path: str = "location.mp4",
    duration: float = 5.0,
    **style_kwargs,
) -> str:
    """Render an animated location stamp card."""
    renderer = LocationStampRenderer(
        location, date=date, sublocation=sublocation, **style_kwargs
    )
    return renderer.render(output_path, duration=duration)
