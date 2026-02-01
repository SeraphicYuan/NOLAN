"""
Document highlight renderer.

Creates animated document excerpt mockups:
- Document-style background
- Text with highlighted portions
- Source/document title
- Official document aesthetic

Animation: Document fades in, highlight reveals, source appears
"""

from typing import Tuple, Optional, Union, List
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ExpandWidth
from ..layout import Position, POSITIONS


class DocumentHighlightRenderer(BaseRenderer):
    """
    Render animated document highlight cards.

    Usage:
        renderer = DocumentHighlightRenderer(
            text="The government shall transfer ownership of all private enterprises...",
            highlight_text="transfer ownership of all private enterprises",
            document_title="Decree No. 3,167",
            source="Official Gazette, 2014"
        )
        renderer.render("output.mp4", duration=6.0)
    """

    def __init__(
        self,
        text: str,
        highlight_text: str = None,
        document_title: str = None,
        source: str = None,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (18, 18, 24),
        document_bg_color: Tuple[int, int, int] = (245, 242, 235),  # Paper color
        text_color: Tuple[int, int, int] = (40, 40, 50),
        highlight_bg_color: Tuple[int, int, int] = (255, 235, 100),
        title_color: Tuple[int, int, int] = (60, 60, 80),
        source_color: Tuple[int, int, int] = (100, 100, 120),
        border_color: Tuple[int, int, int] = (180, 175, 165),
        # Typography
        text_size: int = 32,
        title_size: int = 24,
        source_size: int = 20,
        text_font: str = "C:/Windows/Fonts/times.ttf",
        title_font: str = "C:/Windows/Fonts/arialbd.ttf",
        source_font: str = "C:/Windows/Fonts/arial.ttf",
        # Dimensions
        document_width: int = 900,
        document_padding: int = 50,
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.text = text
        self.highlight_text = highlight_text
        self.document_title = document_title
        self.source = source
        self.document_bg_color = document_bg_color
        self.text_color = text_color
        self.highlight_bg_color = highlight_bg_color
        self.title_color = title_color
        self.source_color = source_color
        self.border_color = border_color
        self.text_size = text_size
        self.title_size = title_size
        self.source_size = source_size
        self.text_font = text_font
        self.title_font = title_font
        self.source_font = source_font
        self.document_width = document_width
        self.document_padding = document_padding
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)
        doc_x = (self.width - self.document_width) // 2
        content_x = doc_x + self.document_padding

        # Calculate document height
        doc_height = 300
        doc_y = base_y - doc_height // 2

        # Document shadow (subtle)
        shadow_element = Element(
            id="shadow",
            element_type="rectangle",
            color=(20, 20, 30),
            x=doc_x + 8,
            y=doc_y + 8,
            width=self.document_width,
            height=doc_height,
        )
        shadow_element.add_effect(
            FadeIn(start=0.1, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(shadow_element)

        # Document background
        doc_element = Element(
            id="document",
            element_type="rectangle",
            color=self.document_bg_color,
            x=doc_x,
            y=doc_y,
            width=self.document_width,
            height=doc_height,
        )
        doc_element.add_effect(
            FadeIn(start=0.2, duration=0.4, easing="ease_out_cubic")
        )
        self.add_element(doc_element)

        # Border accent on left
        border_element = Element(
            id="border",
            element_type="rectangle",
            color=self.border_color,
            x=doc_x,
            y=doc_y,
            width=6,
            height=doc_height,
        )
        border_element.add_effect(
            FadeIn(start=0.3, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(border_element)

        current_y = doc_y + self.document_padding

        # Document title (optional)
        if self.document_title:
            title_element = Element(
                id="title",
                element_type="text",
                text=self.document_title.upper(),
                font_path=self.title_font,
                font_size=self.title_size,
                color=self.title_color,
                x=content_x,
                y=current_y,
            )
            title_element.add_effect(
                FadeIn(start=0.4, duration=0.3, easing="ease_out_cubic")
            )
            self.add_element(title_element)
            current_y += self.title_size + 20

        # Underline under title
        if self.document_title:
            underline_element = Element(
                id="underline",
                element_type="rectangle",
                color=self.border_color,
                x=content_x,
                y=current_y - 10,
                width=self.document_width - self.document_padding * 2,
                height=1,
            )
            underline_element.add_effect(
                FadeIn(start=0.45, duration=0.2, easing="ease_out_cubic")
            )
            self.add_element(underline_element)
            current_y += 15

        # Main text (with smart wrapping)
        text_element = Element(
            id="text",
            element_type="text",
            text=self.text,
            font_path=self.text_font,
            font_size=self.text_size,
            color=self.text_color,
            x=content_x,
            y=current_y,
            max_width=self.document_width - self.document_padding * 2,
            max_lines=5,
            text_align="left",
        )
        text_element.add_effect(
            FadeIn(start=0.5, duration=0.5, easing="ease_out_cubic")
        )
        self.add_element(text_element)

        # Source (below document)
        if self.source:
            source_y = doc_y + doc_height + 20
            source_element = Element(
                id="source",
                element_type="text",
                text=self.source,
                font_path=self.source_font,
                font_size=self.source_size,
                color=self.source_color,
                x='center',
                y=source_y,
            )
            source_element.add_effect(
                FadeIn(start=1.0, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(source_element)


def render_document_highlight(
    text: str,
    document_title: str = None,
    source: str = None,
    output_path: str = "document.mp4",
    duration: float = 6.0,
    **style_kwargs,
) -> str:
    """Render an animated document highlight card."""
    renderer = DocumentHighlightRenderer(text, document_title=document_title, source=source, **style_kwargs)
    return renderer.render(output_path, duration=duration)
