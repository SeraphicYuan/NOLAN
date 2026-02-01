"""
Ranking list renderer.

Creates animated ranking/numbered lists:
- Numbered items with values
- Optional title
- Staggered fade-in animation
- Highlight for top item

Animation: Items fade in sequentially from top to bottom
"""

from typing import Tuple, Optional, Union, List
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp
from ..layout import Position, POSITIONS


class RankingRenderer(BaseRenderer):
    """
    Render animated ranking list cards.

    Usage:
        renderer = RankingRenderer(
            title="Worst Inflation Rates",
            items=[
                ("Venezuela", "1,000,000%"),
                ("Zimbabwe", "79,600,000,000%"),
                ("Hungary", "41,900,000,000%"),
            ]
        )
        renderer.render("output.mp4", duration=6.0)
    """

    def __init__(
        self,
        items: List[Tuple[str, str]],  # List of (name, value) tuples
        title: str = None,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (18, 18, 24),
        title_color: Tuple[int, int, int] = (255, 255, 255),
        rank_color: Tuple[int, int, int] = (255, 180, 100),
        name_color: Tuple[int, int, int] = (220, 220, 230),
        value_color: Tuple[int, int, int] = (140, 180, 255),
        top_highlight_color: Tuple[int, int, int] = (255, 220, 100),
        # Typography
        title_size: int = 36,
        rank_size: int = 28,
        name_size: int = 32,
        value_size: int = 28,
        title_font: str = "C:/Windows/Fonts/arialbd.ttf",
        item_font: str = "C:/Windows/Fonts/arial.ttf",
        value_font: str = "C:/Windows/Fonts/arialbd.ttf",
        # Layout
        item_spacing: int = 60,
        max_items: int = 5,
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.items = items[:max_items]
        self.title = title
        self.title_color = title_color
        self.rank_color = rank_color
        self.name_color = name_color
        self.value_color = value_color
        self.top_highlight_color = top_highlight_color
        self.title_size = title_size
        self.rank_size = rank_size
        self.name_size = name_size
        self.value_size = value_size
        self.title_font = title_font
        self.item_font = item_font
        self.value_font = value_font
        self.item_spacing = item_spacing
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)

        # Calculate starting position based on content height
        total_items_height = len(self.items) * self.item_spacing
        title_offset = self.title_size + 40 if self.title else 0
        start_y = base_y - (total_items_height + title_offset) // 2

        current_y = start_y
        left_x = self.width // 4
        right_x = 3 * self.width // 4

        # Title (optional)
        if self.title:
            title_element = Element(
                id="title",
                element_type="text",
                text=self.title.upper(),
                font_path=self.title_font,
                font_size=self.title_size,
                color=self.title_color,
                x='center',
                y=current_y,
            )
            title_element.add_effect(
                FadeIn(start=0.2, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(title_element)
            current_y += self.title_size + 40

        # Items
        for i, (name, value) in enumerate(self.items):
            delay = 0.4 + (i * 0.15)  # Stagger animation
            is_top = (i == 0)

            # Rank number
            rank_element = Element(
                id=f"rank_{i}",
                element_type="text",
                text=f"#{i + 1}",
                font_path=self.value_font,
                font_size=self.rank_size,
                color=self.top_highlight_color if is_top else self.rank_color,
                x=left_x - 100,
                y=current_y,
            )
            rank_element.add_effects([
                FadeIn(start=delay, duration=0.3, easing="ease_out_cubic"),
                SlideUp(start=delay, duration=0.3, distance=10, easing="ease_out_cubic"),
            ])
            self.add_element(rank_element)

            # Name
            name_element = Element(
                id=f"name_{i}",
                element_type="text",
                text=name,
                font_path=self.item_font if not is_top else self.title_font,
                font_size=self.name_size,
                color=self.top_highlight_color if is_top else self.name_color,
                x=left_x,
                y=current_y,
            )
            name_element.add_effects([
                FadeIn(start=delay + 0.05, duration=0.3, easing="ease_out_cubic"),
                SlideUp(start=delay + 0.05, duration=0.3, distance=10, easing="ease_out_cubic"),
            ])
            self.add_element(name_element)

            # Value
            value_element = Element(
                id=f"value_{i}",
                element_type="text",
                text=value,
                font_path=self.value_font,
                font_size=self.value_size,
                color=self.top_highlight_color if is_top else self.value_color,
                x=right_x,
                y=current_y,
            )
            value_element.add_effects([
                FadeIn(start=delay + 0.1, duration=0.3, easing="ease_out_cubic"),
                SlideUp(start=delay + 0.1, duration=0.3, distance=10, easing="ease_out_cubic"),
            ])
            self.add_element(value_element)

            current_y += self.item_spacing


def render_ranking(
    items: List[Tuple[str, str]],
    title: str = None,
    output_path: str = "ranking.mp4",
    duration: float = 6.0,
    **style_kwargs,
) -> str:
    """Render an animated ranking list card."""
    renderer = RankingRenderer(items, title=title, **style_kwargs)
    return renderer.render(output_path, duration=duration)
