"""
List/bullet point scene renderer.

Creates animated list cards for:
- Topic introductions ("We'll cover: 1. History, 2. Economy, 3. Politics")
- Key points summaries
- Agenda/outline displays

Animation sequence:
1. Title fades in with slight zoom
2. Accent line expands from center
3. Each item fades in sequentially with staggered timing
"""

from typing import Tuple, List as ListType, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ScaleIn, ExpandWidth
from ..layout import Position, POSITIONS


class ListRenderer(BaseRenderer):
    """
    Render animated list/bullet point scenes.

    Usage:
        renderer = ListRenderer(
            title="THE VENEZUELAN PARADOX",
            items=["History", "Economy", "Politics"]
        )
        renderer.render("output.mp4", duration=6.0)

        # With position control
        renderer = ListRenderer(
            title="KEY TOPICS",
            items=["Topic 1", "Topic 2"],
            position="center-top"  # Position in upper area
        )
    """

    def __init__(
        self,
        title: str,
        items: ListType[str],
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (15, 15, 20),
        title_color: Tuple[int, int, int] = (255, 255, 255),
        item_color: Tuple[int, int, int] = (220, 220, 220),
        number_color: Tuple[int, int, int] = (100, 100, 120),
        accent_color: Tuple[int, int, int] = (220, 38, 38),
        # Typography
        title_size: int = 72,
        item_size: int = 48,
        title_font: str = "C:/Windows/Fonts/arialbd.ttf",
        item_font: str = "C:/Windows/Fonts/arial.ttf",
        # Layout
        show_numbers: bool = True,
        show_accent_line: bool = True,
        item_spacing: int = 70,
        # Timing
        fps: int = 30,
        item_stagger: float = 0.3,  # Delay between each item
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.title = title
        self.items = items
        self.title_color = title_color
        self.item_color = item_color
        self.number_color = number_color
        self.accent_color = accent_color
        self.title_size = title_size
        self.item_size = item_size
        self.title_font = title_font
        self.item_font = item_font
        self.show_numbers = show_numbers
        self.show_accent_line = show_accent_line
        self.item_spacing = item_spacing
        self.item_stagger = item_stagger

        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        # Calculate base Y from position
        base_y = int(self.height * self.position.y)

        # Calculate vertical positions relative to position
        total_items_height = len(self.items) * self.item_spacing
        content_height = self.title_size + 60 + total_items_height  # title + gap + items

        # Center content around the position's y coordinate
        start_y = base_y - (content_height // 2)
        title_y = start_y
        line_y = title_y + self.title_size + 25
        first_item_y = line_y + 35

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
            FadeIn(start=0.2, duration=0.7, easing="ease_out_cubic"),
            ScaleIn(start=0.2, duration=0.7, from_scale=0.95, easing="ease_out_cubic"),
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
                width=400,
                height=3,
            )
            line_element.add_effect(
                ExpandWidth(start=0.6, duration=0.5, easing="ease_out_quart")
            )
            self.add_element(line_element)

        # Items - fade in sequentially with stagger
        base_item_start = 0.9  # Start time for first item

        for i, item_text in enumerate(self.items):
            item_y = first_item_y + (i * self.item_spacing)
            item_start = base_item_start + (i * self.item_stagger)

            # Format item text with number if enabled
            if self.show_numbers:
                display_text = f"{i + 1}.  {item_text}"
            else:
                display_text = f"•  {item_text}"

            item_element = Element(
                id=f"item_{i}",
                element_type="text",
                text=display_text,
                font_path=self.item_font,
                font_size=self.item_size,
                color=self.item_color,
                x='center',
                y=item_y,
            )
            item_element.add_effects([
                FadeIn(start=item_start, duration=0.5, easing="ease_out_cubic"),
                SlideUp(start=item_start, duration=0.5, distance=20, easing="ease_out_cubic"),
            ])
            self.add_element(item_element)

    def with_documentary_style(self) -> 'ListRenderer':
        """Apply documentary color scheme."""
        self.bg_color = (26, 26, 26)
        for el in self.elements:
            if el.id == "title":
                el.color = (255, 255, 255)
            elif el.id.startswith("item_"):
                el.color = (200, 200, 200)
            elif el.id == "accent_line":
                el.color = (220, 38, 38)
        return self

    def with_modern_style(self) -> 'ListRenderer':
        """Apply modern/clean color scheme."""
        self.bg_color = (250, 250, 252)
        for el in self.elements:
            if el.id == "title":
                el.color = (30, 30, 40)
            elif el.id.startswith("item_"):
                el.color = (60, 60, 70)
            elif el.id == "accent_line":
                el.color = (70, 130, 220)
        return self

    def with_academic_style(self) -> 'ListRenderer':
        """Apply academic/formal color scheme."""
        self.bg_color = (20, 25, 35)
        for el in self.elements:
            if el.id == "title":
                el.color = (255, 255, 255)
            elif el.id.startswith("item_"):
                el.color = (180, 190, 200)
            elif el.id == "accent_line":
                el.color = (100, 140, 180)
        return self


# Convenience functions
def render_list(
    title: str,
    items: ListType[str],
    output_path: str = "list.mp4",
    duration: float = 6.0,
    show_numbers: bool = True,
    **style_kwargs,
) -> str:
    """Render an animated list/bullet points."""
    renderer = ListRenderer(title, items, show_numbers=show_numbers, **style_kwargs)
    return renderer.render(output_path, duration=duration)


def render_agenda(
    title: str,
    topics: ListType[str],
    output_path: str = "agenda.mp4",
    duration: float = 6.0,
) -> str:
    """Render an agenda/outline with numbered topics."""
    renderer = ListRenderer(
        title=title,
        items=topics,
        show_numbers=True,
        accent_color=(70, 130, 220),
    )
    return renderer.render(output_path, duration=duration)
