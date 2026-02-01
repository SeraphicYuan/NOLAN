"""
Quote scene renderer.

Creates animated quote cards with:
- Main quote text (fade + slide up)
- Attribution (fade in after quote)
- Accent bar (expand from center)
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element, Timeline
from ..effects import FadeIn, SlideUp, ExpandWidth, EffectPresets
from ..layout import Position, POSITIONS


class QuoteRenderer(BaseRenderer):
    """
    Render animated quote scenes.

    Usage:
        renderer = QuoteRenderer(
            quote="WE ARE TIRED",
            attribution="— Maria Rodriguez, Caracas Resident"
        )
        renderer.render("output.mp4", duration=7.0)

        # With position control
        renderer = QuoteRenderer(
            quote="WE ARE TIRED",
            attribution="— Maria Rodriguez",
            position="center-top"  # Move to upper portion
        )
    """

    def __init__(
        self,
        quote: str,
        attribution: str = None,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (26, 26, 26),
        quote_color: Tuple[int, int, int] = (255, 255, 255),
        attr_color: Tuple[int, int, int] = (136, 136, 136),
        accent_color: Tuple[int, int, int] = (220, 38, 38),
        # Typography
        quote_size: int = 72,
        attr_size: int = 36,
        quote_font: str = "C:/Windows/Fonts/arialbd.ttf",
        attr_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.quote = quote
        self.attribution = attribution
        self.quote_color = quote_color
        self.attr_color = attr_color
        self.accent_color = accent_color
        self.quote_size = quote_size
        self.attr_size = attr_size
        self.quote_font = quote_font
        self.attr_font = attr_font

        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        # Calculate base Y from position
        base_y = int(self.height * self.position.y)

        # Quote text - appears first with slide up
        quote_element = Element(
            id="quote",
            element_type="text",
            text=self.quote,
            font_path=self.quote_font,
            font_size=self.quote_size,
            color=self.quote_color,
            x='center',
            y=base_y - 40,  # Slightly above position center
        )
        quote_element.add_effects([
            FadeIn(start=0.3, duration=1.0, easing="ease_out_cubic"),
            SlideUp(start=0.3, duration=1.0, distance=40, easing="ease_out_cubic"),
        ])
        self.add_element(quote_element)

        # Accent bar - expands from center (below attribution area)
        bar_y = base_y + 120  # Below attribution
        bar_element = Element(
            id="accent_bar",
            element_type="rectangle",
            color=self.accent_color,
            x='center',
            y=bar_y,
            width=self.width,
            height=8,
        )
        bar_element.add_effect(
            ExpandWidth(start=0.8, duration=0.7, easing="ease_out_quart")
        )
        self.add_element(bar_element)

        # Attribution - fades in after quote
        if self.attribution:
            attr_element = Element(
                id="attribution",
                element_type="text",
                text=self.attribution,
                font_path=self.attr_font,
                font_size=self.attr_size,
                color=self.attr_color,
                x='center',
                y=base_y + 50,  # Below quote
            )
            attr_element.add_effect(
                FadeIn(start=1.0, duration=0.8, easing="ease_out_cubic")
            )
            self.add_element(attr_element)

    def with_timing(
        self,
        quote_start: float = 0.3,
        quote_duration: float = 1.0,
        attr_start: float = 1.0,
        attr_duration: float = 0.8,
        bar_start: float = 0.8,
        bar_duration: float = 0.7,
    ) -> 'QuoteRenderer':
        """
        Customize animation timing.

        Returns self for chaining.
        """
        # Clear existing effects and re-add with new timing
        for element in self.elements:
            element.effects.clear()

            if element.id == "quote":
                element.add_effects([
                    FadeIn(start=quote_start, duration=quote_duration),
                    SlideUp(start=quote_start, duration=quote_duration, distance=40),
                ])
            elif element.id == "accent_bar":
                element.add_effect(
                    ExpandWidth(start=bar_start, duration=bar_duration)
                )
            elif element.id == "attribution":
                element.add_effect(
                    FadeIn(start=attr_start, duration=attr_duration)
                )

        return self

    def with_style(
        self,
        bg_color: Tuple[int, int, int] = None,
        quote_color: Tuple[int, int, int] = None,
        attr_color: Tuple[int, int, int] = None,
        accent_color: Tuple[int, int, int] = None,
    ) -> 'QuoteRenderer':
        """
        Customize colors.

        Returns self for chaining.
        """
        if bg_color:
            self.bg_color = bg_color
        if quote_color:
            for el in self.elements:
                if el.id == "quote":
                    el.color = quote_color
        if attr_color:
            for el in self.elements:
                if el.id == "attribution":
                    el.color = attr_color
        if accent_color:
            for el in self.elements:
                if el.id == "accent_bar":
                    el.color = accent_color

        return self


# Convenience function
def render_quote(
    quote: str,
    attribution: str = None,
    output_path: str = "quote.mp4",
    duration: float = 7.0,
    **style_kwargs,
) -> str:
    """
    Quick function to render an animated quote.

    Args:
        quote: Main quote text
        attribution: Attribution line (optional)
        output_path: Output video file
        duration: Video duration in seconds
        **style_kwargs: Style options (bg_color, quote_color, etc.)

    Returns:
        Path to rendered video
    """
    renderer = QuoteRenderer(quote, attribution, **style_kwargs)
    return renderer.render(output_path, duration=duration)
