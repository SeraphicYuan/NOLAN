"""
Definition card renderer.

Creates animated definition cards for explaining terms:
- Term in large, bold font
- Definition text below
- Optional category/context label
- Accent underline

Animation: Term fades in, underline expands, definition slides up
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ExpandWidth, ScaleIn
from ..layout import Position, POSITIONS


class DefinitionRenderer(BaseRenderer):
    """
    Render animated definition cards.

    Usage:
        renderer = DefinitionRenderer(
            term="Hyperinflation",
            definition="Extremely rapid or out of control inflation, typically over 50% per month.",
            category="Economics"
        )
        renderer.render("output.mp4", duration=6.0)
    """

    def __init__(
        self,
        term: str,
        definition: str,
        category: str = None,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (18, 18, 24),
        term_color: Tuple[int, int, int] = (255, 255, 255),
        definition_color: Tuple[int, int, int] = (180, 180, 190),
        category_color: Tuple[int, int, int] = (120, 120, 140),
        accent_color: Tuple[int, int, int] = (100, 140, 255),
        # Typography
        term_size: int = 72,
        definition_size: int = 36,
        category_size: int = 24,
        term_font: str = "C:/Windows/Fonts/arialbd.ttf",
        definition_font: str = "C:/Windows/Fonts/arial.ttf",
        category_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.term = term
        self.definition = definition
        self.category = category
        self.term_color = term_color
        self.definition_color = definition_color
        self.category_color = category_color
        self.accent_color = accent_color
        self.term_size = term_size
        self.definition_size = definition_size
        self.category_size = category_size
        self.term_font = term_font
        self.definition_font = definition_font
        self.category_font = category_font
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)

        # Category label (optional, above term)
        if self.category:
            category_y = base_y - 100
            category_element = Element(
                id="category",
                element_type="text",
                text=self.category.upper(),
                font_path=self.category_font,
                font_size=self.category_size,
                color=self.category_color,
                x='center',
                y=category_y,
            )
            category_element.add_effect(
                FadeIn(start=0.2, duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(category_element)

        # Term - main word being defined
        term_y = base_y - 30
        term_element = Element(
            id="term",
            element_type="text",
            text=self.term,
            font_path=self.term_font,
            font_size=self.term_size,
            color=self.term_color,
            x='center',
            y=term_y,
        )
        term_element.add_effects([
            FadeIn(start=0.3, duration=0.6, easing="ease_out_cubic"),
            ScaleIn(start=0.3, duration=0.6, from_scale=0.95, easing="ease_out_cubic"),
        ])
        self.add_element(term_element)

        # Accent underline
        underline_y = term_y + self.term_size + 15
        underline_element = Element(
            id="underline",
            element_type="rectangle",
            color=self.accent_color,
            x='center',
            y=underline_y,
            width=300,
            height=4,
        )
        underline_element.add_effect(
            ExpandWidth(start=0.6, duration=0.5, easing="ease_out_quart")
        )
        self.add_element(underline_element)

        # Definition text (with smart wrapping)
        definition_y = underline_y + 40
        definition_element = Element(
            id="definition",
            element_type="text",
            text=self.definition,
            font_path=self.definition_font,
            font_size=self.definition_size,
            color=self.definition_color,
            x='center',
            y=definition_y,
            max_width=self.get_text_max_width("default"),
            max_lines=4,
            text_align="center",
        )
        definition_element.add_effects([
            FadeIn(start=0.9, duration=0.6, easing="ease_out_cubic"),
            SlideUp(start=0.9, duration=0.6, distance=20, easing="ease_out_cubic"),
        ])
        self.add_element(definition_element)


def render_definition(
    term: str,
    definition: str,
    category: str = None,
    output_path: str = "definition.mp4",
    duration: float = 6.0,
    **style_kwargs,
) -> str:
    """Render an animated definition card."""
    renderer = DefinitionRenderer(term, definition, category=category, **style_kwargs)
    return renderer.render(output_path, duration=duration)
