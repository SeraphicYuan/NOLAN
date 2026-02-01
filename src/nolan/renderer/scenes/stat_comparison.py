"""
Stat comparison renderer.

Creates animated side-by-side statistic comparisons:
- Two values with labels
- Optional "vs" divider
- Color-coded for positive/negative context
- Works for before/after, this/that comparisons

Animation: Both stats fade in simultaneously, then highlight winner
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ScaleIn
from ..layout import Position, POSITIONS


class StatComparisonRenderer(BaseRenderer):
    """
    Render animated stat comparison cards.

    Usage:
        renderer = StatComparisonRenderer(
            left_value="$100B",
            left_label="GDP 2012",
            right_value="$12B",
            right_label="GDP 2020",
            title="Economic Collapse"
        )
        renderer.render("output.mp4", duration=6.0)
    """

    def __init__(
        self,
        left_value: str,
        left_label: str,
        right_value: str,
        right_label: str,
        title: str = None,
        divider_text: str = "vs",
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (18, 18, 24),
        left_color: Tuple[int, int, int] = (100, 200, 120),  # Green
        right_color: Tuple[int, int, int] = (255, 100, 100),  # Red
        title_color: Tuple[int, int, int] = (200, 200, 210),
        label_color: Tuple[int, int, int] = (140, 140, 160),
        divider_color: Tuple[int, int, int] = (100, 100, 120),
        # Typography
        value_size: int = 72,
        label_size: int = 24,
        title_size: int = 32,
        divider_size: int = 36,
        value_font: str = "C:/Windows/Fonts/arialbd.ttf",
        label_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.left_value = left_value
        self.left_label = left_label
        self.right_value = right_value
        self.right_label = right_label
        self.title = title
        self.divider_text = divider_text
        self.left_color = left_color
        self.right_color = right_color
        self.title_color = title_color
        self.label_color = label_color
        self.divider_color = divider_color
        self.value_size = value_size
        self.label_size = label_size
        self.title_size = title_size
        self.divider_size = divider_size
        self.value_font = value_font
        self.label_font = label_font
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)
        current_y = base_y - 40

        # Title (optional)
        if self.title:
            title_element = Element(
                id="title",
                element_type="text",
                text=self.title.upper(),
                font_path=self.label_font,
                font_size=self.title_size,
                color=self.title_color,
                x='center',
                y=current_y - 100,
            )
            title_element.add_effect(
                FadeIn(start=0.2, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(title_element)

        # Width available for each side (half of screen minus margins)
        side_width = self.width // 2 - 100

        # Left value - centered at 25% of width
        left_value_element = Element(
            id="left_value",
            element_type="text",
            text=self.left_value,
            font_path=self.value_font,
            font_size=self.value_size,
            color=self.left_color,
            x=50,  # Left margin
            y=current_y,
            max_width=side_width,
            max_lines=1,
            text_align="center",
        )
        left_value_element.add_effects([
            FadeIn(start=0.4, duration=0.5, easing="ease_out_cubic"),
            ScaleIn(start=0.4, duration=0.5, from_scale=0.8, easing="ease_out_back"),
        ])
        self.add_element(left_value_element)

        # Left label - below the value
        label_y = current_y + self.value_size + 20
        left_label_element = Element(
            id="left_label",
            element_type="text",
            text=self.left_label.upper(),
            font_path=self.label_font,
            font_size=self.label_size,
            color=self.label_color,
            x=50,
            y=label_y,
            max_width=side_width,
            max_lines=1,
            text_align="center",
        )
        left_label_element.add_effect(
            FadeIn(start=0.6, duration=0.4, easing="ease_out_cubic")
        )
        self.add_element(left_label_element)

        # Divider in center
        divider_element = Element(
            id="divider",
            element_type="text",
            text=self.divider_text,
            font_path=self.label_font,
            font_size=self.divider_size,
            color=self.divider_color,
            x='center',
            y=current_y + 15,
        )
        divider_element.add_effect(
            FadeIn(start=0.5, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(divider_element)

        # Right value - centered at 75% of width
        right_x = self.width // 2 + 50  # Right half starts at center + margin
        right_value_element = Element(
            id="right_value",
            element_type="text",
            text=self.right_value,
            font_path=self.value_font,
            font_size=self.value_size,
            color=self.right_color,
            x=right_x,
            y=current_y,
            max_width=side_width,
            max_lines=1,
            text_align="center",
        )
        right_value_element.add_effects([
            FadeIn(start=0.4, duration=0.5, easing="ease_out_cubic"),
            ScaleIn(start=0.4, duration=0.5, from_scale=0.8, easing="ease_out_back"),
        ])
        self.add_element(right_value_element)

        # Right label - below the value
        right_label_element = Element(
            id="right_label",
            element_type="text",
            text=self.right_label.upper(),
            font_path=self.label_font,
            font_size=self.label_size,
            color=self.label_color,
            x=right_x,
            y=label_y,
            max_width=side_width,
            max_lines=1,
            text_align="center",
        )
        right_label_element.add_effect(
            FadeIn(start=0.6, duration=0.4, easing="ease_out_cubic")
        )
        self.add_element(right_label_element)


def render_stat_comparison(
    left_value: str,
    left_label: str,
    right_value: str,
    right_label: str,
    title: str = None,
    output_path: str = "comparison.mp4",
    duration: float = 6.0,
    **style_kwargs,
) -> str:
    """Render an animated stat comparison card."""
    renderer = StatComparisonRenderer(
        left_value, left_label, right_value, right_label,
        title=title, **style_kwargs
    )
    return renderer.render(output_path, duration=duration)
