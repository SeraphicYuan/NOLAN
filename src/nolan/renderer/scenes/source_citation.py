"""
Source citation card renderer.

Creates animated citation cards for credibility:
- Source name/title
- Publication/organization
- Date
- Optional URL

Animation: Elements fade in sequentially with slide
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp
from ..layout import Position, POSITIONS


class SourceCitationRenderer(BaseRenderer):
    """
    Render animated source citation cards.

    Usage:
        renderer = SourceCitationRenderer(
            source_name="The Economic Collapse of Venezuela",
            publication="Reuters",
            date="March 15, 2019",
            url="reuters.com/article/..."
        )
        renderer.render("output.mp4", duration=5.0)
    """

    def __init__(
        self,
        source_name: str,
        publication: str = None,
        date: str = None,
        url: str = None,
        author: str = None,
        # Position
        position: Union[str, Position] = "lower-third",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (18, 18, 24),
        source_color: Tuple[int, int, int] = (255, 255, 255),
        publication_color: Tuple[int, int, int] = (100, 180, 255),
        meta_color: Tuple[int, int, int] = (140, 140, 150),
        accent_color: Tuple[int, int, int] = (100, 180, 255),
        # Typography
        source_size: int = 36,
        publication_size: int = 28,
        meta_size: int = 22,
        source_font: str = "C:/Windows/Fonts/arialbd.ttf",
        publication_font: str = "C:/Windows/Fonts/arial.ttf",
        meta_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.source_name = source_name
        self.publication = publication
        self.date = date
        self.url = url
        self.author = author
        self.source_color = source_color
        self.publication_color = publication_color
        self.meta_color = meta_color
        self.accent_color = accent_color
        self.source_size = source_size
        self.publication_size = publication_size
        self.meta_size = meta_size
        self.source_font = source_font
        self.publication_font = publication_font
        self.meta_font = meta_font

        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)

        # "SOURCE" label
        label_y = base_y - 80
        label_element = Element(
            id="label",
            element_type="text",
            text="SOURCE",
            font_path=self.meta_font,
            font_size=18,
            color=self.meta_color,
            x='center',
            y=label_y,
        )
        label_element.add_effect(
            FadeIn(start=0.2, duration=0.4, easing="ease_out_cubic")
        )
        self.add_element(label_element)

        # Accent line
        line_y = label_y + 25
        line_element = Element(
            id="accent_line",
            element_type="rectangle",
            color=self.accent_color,
            x='center',
            y=line_y,
            width=60,
            height=2,
        )
        line_element.add_effect(
            FadeIn(start=0.3, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(line_element)

        # Source name (main title)
        source_y = line_y + 25
        source_element = Element(
            id="source_name",
            element_type="text",
            text=f'"{self.source_name}"',
            font_path=self.source_font,
            font_size=self.source_size,
            color=self.source_color,
            x='center',
            y=source_y,
        )
        source_element.add_effects([
            FadeIn(start=0.4, duration=0.5, easing="ease_out_cubic"),
            SlideUp(start=0.4, duration=0.5, distance=15, easing="ease_out_cubic"),
        ])
        self.add_element(source_element)

        # Publication name
        pub_y = source_y + self.source_size + 15
        if self.publication:
            pub_element = Element(
                id="publication",
                element_type="text",
                text=self.publication,
                font_path=self.publication_font,
                font_size=self.publication_size,
                color=self.publication_color,
                x='center',
                y=pub_y,
            )
            pub_element.add_effect(
                FadeIn(start=0.7, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(pub_element)
            pub_y += self.publication_size + 8

        # Meta info (date, author, url)
        meta_parts = []
        if self.author:
            meta_parts.append(self.author)
        if self.date:
            meta_parts.append(self.date)

        if meta_parts:
            meta_text = " · ".join(meta_parts)
            meta_element = Element(
                id="meta",
                element_type="text",
                text=meta_text,
                font_path=self.meta_font,
                font_size=self.meta_size,
                color=self.meta_color,
                x='center',
                y=pub_y,
            )
            meta_element.add_effect(
                FadeIn(start=0.9, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(meta_element)


def render_source_citation(
    source_name: str,
    publication: str = None,
    date: str = None,
    output_path: str = "source.mp4",
    duration: float = 5.0,
    **style_kwargs,
) -> str:
    """Render an animated source citation card."""
    renderer = SourceCitationRenderer(
        source_name, publication=publication, date=date, **style_kwargs
    )
    return renderer.render(output_path, duration=duration)
