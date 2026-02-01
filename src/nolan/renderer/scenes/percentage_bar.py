"""
Percentage bar renderer.

Creates animated percentage visualizations:
- Category label
- Horizontal bar showing percentage
- Large percentage number display
- Optional context text

Animation: Bar fills up, percentage counts up
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, ExpandWidth
from ..layout import Position, POSITIONS


class PercentageBarRenderer(BaseRenderer):
    """
    Render animated percentage bar cards.

    Usage:
        renderer = PercentageBarRenderer(
            percentage=87,
            label="Population in Poverty",
            context="As of 2020"
        )
        renderer.render("output.mp4", duration=5.0)
    """

    def __init__(
        self,
        percentage: int,  # 0-100
        label: str,
        context: str = None,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (18, 18, 24),
        bar_bg_color: Tuple[int, int, int] = (50, 50, 60),
        bar_fill_color: Tuple[int, int, int] = (255, 100, 100),
        label_color: Tuple[int, int, int] = (255, 255, 255),
        percentage_color: Tuple[int, int, int] = (255, 255, 255),
        context_color: Tuple[int, int, int] = (140, 140, 160),
        # Dimensions
        bar_width: int = 700,
        bar_height: int = 20,
        # Typography
        label_size: int = 32,
        percentage_size: int = 96,
        context_size: int = 22,
        label_font: str = "C:/Windows/Fonts/arialbd.ttf",
        percentage_font: str = "C:/Windows/Fonts/arialbd.ttf",
        context_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.percentage = max(0, min(100, percentage))
        self.label = label
        self.context = context
        self.bar_bg_color = bar_bg_color
        self.bar_fill_color = bar_fill_color
        self.label_color = label_color
        self.percentage_color = percentage_color
        self.context_color = context_color
        self.bar_width = bar_width
        self.bar_height = bar_height
        self.label_size = label_size
        self.percentage_size = percentage_size
        self.context_size = context_size
        self.label_font = label_font
        self.percentage_font = percentage_font
        self.context_font = context_font
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)
        bar_x = (self.width - self.bar_width) // 2

        # Large percentage number at top
        percentage_y = base_y - 100
        percent_element = Element(
            id="percentage",
            element_type="text",
            text=f"{self.percentage}%",
            font_path=self.percentage_font,
            font_size=self.percentage_size,
            color=self.percentage_color,
            x='center',
            y=percentage_y,
        )
        percent_element.add_effect(
            FadeIn(start=0.3, duration=0.5, easing="ease_out_cubic")
        )
        self.add_element(percent_element)

        # Label below percentage
        label_y = percentage_y + self.percentage_size + 10
        label_element = Element(
            id="label",
            element_type="text",
            text=self.label,
            font_path=self.label_font,
            font_size=self.label_size,
            color=self.label_color,
            x='center',
            y=label_y,
        )
        label_element.add_effect(
            FadeIn(start=0.5, duration=0.4, easing="ease_out_cubic")
        )
        self.add_element(label_element)

        # Bar background
        bar_y = label_y + self.label_size + 30
        bg_element = Element(
            id="bar_bg",
            element_type="rectangle",
            color=self.bar_bg_color,
            x=bar_x,
            y=bar_y,
            width=self.bar_width,
            height=self.bar_height,
        )
        bg_element.add_effect(
            FadeIn(start=0.6, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(bg_element)

        # Bar fill
        fill_width = int(self.bar_width * self.percentage / 100)
        if fill_width > 0:
            fill_element = Element(
                id="bar_fill",
                element_type="rectangle",
                color=self.bar_fill_color,
                x=bar_x,
                y=bar_y,
                width=fill_width,
                height=self.bar_height,
            )
            fill_element.add_effect(
                ExpandWidth(start=0.7, duration=0.8, easing="ease_out_quart")
            )
            self.add_element(fill_element)

        # Context (optional)
        if self.context:
            context_y = bar_y + self.bar_height + 25
            context_element = Element(
                id="context",
                element_type="text",
                text=self.context,
                font_path=self.context_font,
                font_size=self.context_size,
                color=self.context_color,
                x='center',
                y=context_y,
            )
            context_element.add_effect(
                FadeIn(start=1.2, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(context_element)


def render_percentage_bar(
    percentage: int,
    label: str,
    context: str = None,
    output_path: str = "percentage.mp4",
    duration: float = 5.0,
    **style_kwargs,
) -> str:
    """Render an animated percentage bar card."""
    renderer = PercentageBarRenderer(percentage, label, context=context, **style_kwargs)
    return renderer.render(output_path, duration=duration)
