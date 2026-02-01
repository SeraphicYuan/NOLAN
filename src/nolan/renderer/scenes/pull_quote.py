"""
Pull quote renderer.

Creates emphasized quote excerpts:
- Large quotation marks
- Bold, centered text
- Optional highlight on key words
- Attribution below

Animation: Quote marks appear, text fades in with emphasis
"""

from typing import Tuple, Optional, Union, List
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ScaleIn
from ..layout import Position, POSITIONS


class PullQuoteRenderer(BaseRenderer):
    """
    Render animated pull quote cards.

    Usage:
        renderer = PullQuoteRenderer(
            quote="This is the biggest economic collapse in modern history.",
            attribution="Dr. Ricardo Hausmann, Harvard",
            highlight_words=["biggest", "collapse"]
        )
        renderer.render("output.mp4", duration=6.0)
    """

    def __init__(
        self,
        quote: str,
        attribution: str = None,
        highlight_words: List[str] = None,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (15, 15, 20),
        quote_color: Tuple[int, int, int] = (255, 255, 255),
        highlight_color: Tuple[int, int, int] = (255, 220, 100),
        quotemark_color: Tuple[int, int, int] = (80, 80, 100),
        attribution_color: Tuple[int, int, int] = (140, 140, 160),
        # Typography
        quote_size: int = 56,
        quotemark_size: int = 180,
        attribution_size: int = 28,
        quote_font: str = "C:/Windows/Fonts/arialbd.ttf",
        attribution_font: str = "C:/Windows/Fonts/arial.ttf",
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
        self.highlight_words = highlight_words or []
        self.quote_color = quote_color
        self.highlight_color = highlight_color
        self.quotemark_color = quotemark_color
        self.attribution_color = attribution_color
        self.quote_size = quote_size
        self.quotemark_size = quotemark_size
        self.attribution_size = attribution_size
        self.quote_font = quote_font
        self.attribution_font = attribution_font
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)

        # Opening quotation mark
        open_quote_element = Element(
            id="open_quote",
            element_type="text",
            text="\u201c",
            font_path=self.quote_font,
            font_size=self.quotemark_size,
            color=self.quotemark_color,
            x=self.width // 2 - 500,
            y=base_y - 120,
        )
        open_quote_element.add_effects([
            FadeIn(start=0.2, duration=0.4, easing="ease_out_cubic"),
            ScaleIn(start=0.2, duration=0.4, from_scale=0.8, easing="ease_out_back"),
        ])
        self.add_element(open_quote_element)

        # Main quote text (with smart wrapping)
        quote_element = Element(
            id="quote",
            element_type="text",
            text=self.quote,
            font_path=self.quote_font,
            font_size=self.quote_size,
            color=self.quote_color,
            x='center',
            y=base_y - 20,
            max_width=self.get_text_max_width("quote"),
            max_lines=4,
            text_align="center",
        )
        quote_element.add_effects([
            FadeIn(start=0.5, duration=0.7, easing="ease_out_cubic"),
            SlideUp(start=0.5, duration=0.7, distance=25, easing="ease_out_cubic"),
        ])
        self.add_element(quote_element)

        # Closing quotation mark - using unicode escape to avoid encoding issues
        closing_quote = Element(
            id="close_quote",
            element_type="text",
            text="\u201d",
            font_path=self.quote_font,
            font_size=self.quotemark_size,
            color=self.quotemark_color,
            x=self.width // 2 + 450,
            y=base_y + 60,
        )
        closing_quote.add_effects([
            FadeIn(start=0.8, duration=0.4, easing="ease_out_cubic"),
            ScaleIn(start=0.8, duration=0.4, from_scale=0.8, easing="ease_out_back"),
        ])
        self.add_element(closing_quote)

        # Attribution
        if self.attribution:
            attr_y = base_y + 140
            attr_element = Element(
                id="attribution",
                element_type="text",
                text=f"— {self.attribution}",
                font_path=self.attribution_font,
                font_size=self.attribution_size,
                color=self.attribution_color,
                x='center',
                y=attr_y,
            )
            attr_element.add_effect(
                FadeIn(start=1.1, duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(attr_element)


def render_pull_quote(
    quote: str,
    attribution: str = None,
    output_path: str = "pull_quote.mp4",
    duration: float = 6.0,
    **style_kwargs,
) -> str:
    """Render an animated pull quote card."""
    renderer = PullQuoteRenderer(quote, attribution=attribution, **style_kwargs)
    return renderer.render(output_path, duration=duration)
