"""
News headline renderer.

Creates animated breaking news style cards:
- "BREAKING" or custom label
- Main headline
- Source attribution
- Optional ticker-style banner

Animation: Label flashes, headline slides in, source fades
"""

from typing import Tuple, Optional, Union, Literal
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ExpandWidth
from ..layout import Position, POSITIONS


NewsType = Literal["breaking", "alert", "update", "exclusive", "developing"]


class NewsHeadlineRenderer(BaseRenderer):
    """
    Render animated news headline cards.

    Usage:
        renderer = NewsHeadlineRenderer(
            headline="Venezuela declares state of emergency",
            source="Reuters",
            news_type="breaking"
        )
        renderer.render("output.mp4", duration=5.0)
    """

    NEWS_STYLES = {
        "breaking": {
            "label": "BREAKING NEWS",
            "label_color": (255, 255, 255),
            "label_bg": (200, 40, 40),
        },
        "alert": {
            "label": "NEWS ALERT",
            "label_color": (255, 255, 255),
            "label_bg": (220, 120, 40),
        },
        "update": {
            "label": "UPDATE",
            "label_color": (255, 255, 255),
            "label_bg": (60, 120, 200),
        },
        "exclusive": {
            "label": "EXCLUSIVE",
            "label_color": (255, 255, 255),
            "label_bg": (180, 50, 180),
        },
        "developing": {
            "label": "DEVELOPING",
            "label_color": (255, 255, 255),
            "label_bg": (200, 160, 40),
        },
    }

    def __init__(
        self,
        headline: str,
        source: str = None,
        news_type: NewsType = "breaking",
        custom_label: str = None,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (18, 18, 24),
        headline_color: Tuple[int, int, int] = (255, 255, 255),
        source_color: Tuple[int, int, int] = (160, 160, 180),
        banner_color: Tuple[int, int, int] = (30, 30, 40),
        # Typography
        label_size: int = 24,
        headline_size: int = 48,
        source_size: int = 22,
        label_font: str = "C:/Windows/Fonts/arialbd.ttf",
        headline_font: str = "C:/Windows/Fonts/arialbd.ttf",
        source_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        # Get style
        style = self.NEWS_STYLES.get(news_type, self.NEWS_STYLES["breaking"])

        self.headline = headline
        self.source = source
        self.label_text = custom_label or style["label"]
        self.label_color = style["label_color"]
        self.label_bg = style["label_bg"]
        self.headline_color = headline_color
        self.source_color = source_color
        self.banner_color = banner_color
        self.label_size = label_size
        self.headline_size = headline_size
        self.source_size = source_size
        self.label_font = label_font
        self.headline_font = headline_font
        self.source_font = source_font
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)

        # Banner background
        banner_height = 180
        banner_y = base_y - banner_height // 2
        banner_element = Element(
            id="banner",
            element_type="rectangle",
            color=self.banner_color,
            x=0,
            y=banner_y,
            width=self.width,
            height=banner_height,
        )
        banner_element.add_effect(
            FadeIn(start=0.1, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(banner_element)

        # Label background (red box for "BREAKING NEWS")
        label_padding = 15
        label_width = len(self.label_text) * (self.label_size * 0.6) + label_padding * 2
        label_height = self.label_size + label_padding
        label_x = 100
        label_y = banner_y + 20

        label_bg_element = Element(
            id="label_bg",
            element_type="rectangle",
            color=self.label_bg,
            x=label_x,
            y=label_y,
            width=int(label_width),
            height=int(label_height),
        )
        label_bg_element.add_effect(
            FadeIn(start=0.2, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(label_bg_element)

        # Label text
        label_element = Element(
            id="label",
            element_type="text",
            text=self.label_text,
            font_path=self.label_font,
            font_size=self.label_size,
            color=self.label_color,
            x=label_x + label_padding,
            y=label_y + (label_height - self.label_size) // 2,
        )
        label_element.add_effect(
            FadeIn(start=0.3, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(label_element)

        # Headline (with smart wrapping)
        headline_y = label_y + label_height + 15
        headline_element = Element(
            id="headline",
            element_type="text",
            text=self.headline,
            font_path=self.headline_font,
            font_size=self.headline_size,
            color=self.headline_color,
            x=label_x,
            y=headline_y,
            max_width=self.width - label_x * 2,  # Leave margin on both sides
            max_lines=2,
            text_align="left",
        )
        headline_element.add_effects([
            FadeIn(start=0.5, duration=0.5, easing="ease_out_cubic"),
            SlideUp(start=0.5, duration=0.5, distance=15, easing="ease_out_cubic"),
        ])
        self.add_element(headline_element)

        # Source
        if self.source:
            source_y = headline_y + self.headline_size + 10
            source_element = Element(
                id="source",
                element_type="text",
                text=self.source,
                font_path=self.source_font,
                font_size=self.source_size,
                color=self.source_color,
                x=label_x,
                y=source_y,
            )
            source_element.add_effect(
                FadeIn(start=0.9, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(source_element)


def render_news_headline(
    headline: str,
    source: str = None,
    news_type: NewsType = "breaking",
    output_path: str = "headline.mp4",
    duration: float = 5.0,
    **style_kwargs,
) -> str:
    """Render an animated news headline card."""
    renderer = NewsHeadlineRenderer(headline, source=source, news_type=news_type, **style_kwargs)
    return renderer.render(output_path, duration=duration)
