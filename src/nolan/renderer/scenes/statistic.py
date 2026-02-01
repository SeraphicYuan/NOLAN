"""
Statistic/Year reveal scene renderer.

Creates animated stat cards for:
- Year reveals (1821, 1976, etc.)
- Statistics (300 BILLION BARRELS)
- Key numbers with labels
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ScaleIn, ExpandWidth
from ..layout import Position, POSITIONS


class StatisticRenderer(BaseRenderer):
    """
    Render animated statistic/year reveal scenes.

    Usage:
        # Year reveal
        renderer = StatisticRenderer(
            value="1821",
            label="INDEPENDENCIA"
        )
        renderer.render("output.mp4", duration=5.0)

        # Statistic with position
        renderer = StatisticRenderer(
            value="300 BILLION",
            label="BARRELS OF OIL RESERVES",
            position="center-bottom"  # Position in lower area
        )
    """

    def __init__(
        self,
        value: str,
        label: str = None,
        prefix: str = "",
        suffix: str = "",
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (20, 18, 15),
        value_color: Tuple[int, int, int] = (255, 255, 255),
        label_color: Tuple[int, int, int] = (200, 180, 140),
        accent_color: Tuple[int, int, int] = (180, 140, 80),
        # Typography
        value_size: int = 180,
        label_size: int = 48,
        value_font: str = "C:/Windows/Fonts/arialbd.ttf",
        label_font: str = "C:/Windows/Fonts/arial.ttf",
        # Layout
        show_accent_lines: bool = True,
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.value = value
        self.full_value = f"{prefix}{value}{suffix}"
        self.label = label
        self.value_color = value_color
        self.label_color = label_color
        self.accent_color = accent_color
        self.value_size = value_size
        self.label_size = label_size
        self.value_font = value_font
        self.label_font = label_font
        self.show_accent_lines = show_accent_lines

        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        # Calculate base Y from position
        base_y = int(self.height * self.position.y)

        # Calculate vertical positions relative to base
        value_y = base_y - (40 if self.label else 0)
        label_y = value_y + self.value_size + 20

        # Main value - dramatic scale + fade
        value_element = Element(
            id="value",
            element_type="text",
            text=self.full_value,
            font_path=self.value_font,
            font_size=self.value_size,
            color=self.value_color,
            x='center',
            y=value_y,
        )
        value_element.add_effects([
            FadeIn(start=0.2, duration=0.9, easing="ease_out_cubic"),
            ScaleIn(start=0.2, duration=0.9, from_scale=0.85, easing="ease_out_back"),
        ])
        self.add_element(value_element)

        # Accent lines on sides
        if self.show_accent_lines:
            line_y = value_y + self.value_size // 2 - 2

            # Left line
            left_line = Element(
                id="left_line",
                element_type="rectangle",
                color=self.accent_color,
                x=100,
                y=line_y,
                width=150,
                height=4,
            )
            left_line.add_effect(
                ExpandWidth(start=0.5, duration=0.5, easing="ease_out_quart")
            )
            self.add_element(left_line)

            # Right line
            right_line = Element(
                id="right_line",
                element_type="rectangle",
                color=self.accent_color,
                x=self.width - 250,
                y=line_y,
                width=150,
                height=4,
            )
            right_line.add_effect(
                ExpandWidth(start=0.5, duration=0.5, easing="ease_out_quart")
            )
            self.add_element(right_line)

        # Label - fade in below value
        if self.label:
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
                FadeIn(start=0.8, duration=0.6, easing="ease_out_cubic")
            )
            self.add_element(label_element)

    def with_historical_style(self) -> 'StatisticRenderer':
        """Apply sepia/historical color scheme."""
        self.bg_color = (20, 18, 15)
        for el in self.elements:
            if el.id == "value":
                el.color = (255, 255, 255)
            elif el.id == "label":
                el.color = (200, 180, 140)
            elif el.id in ("left_line", "right_line"):
                el.color = (180, 140, 80)
        return self

    def with_modern_style(self) -> 'StatisticRenderer':
        """Apply modern/clean color scheme."""
        self.bg_color = (15, 15, 20)
        for el in self.elements:
            if el.id == "value":
                el.color = (255, 255, 255)
            elif el.id == "label":
                el.color = (150, 150, 160)
            elif el.id in ("left_line", "right_line"):
                el.color = (70, 130, 220)
        return self

    def with_danger_style(self) -> 'StatisticRenderer':
        """Apply danger/warning color scheme (for negative stats)."""
        self.bg_color = (25, 15, 15)
        for el in self.elements:
            if el.id == "value":
                el.color = (255, 80, 80)
            elif el.id == "label":
                el.color = (180, 150, 150)
            elif el.id in ("left_line", "right_line"):
                el.color = (200, 60, 60)
        return self


# Convenience functions
def render_year(
    year: str,
    label: str = None,
    output_path: str = "year.mp4",
    duration: float = 5.0,
    **style_kwargs,
) -> str:
    """Render an animated year reveal."""
    renderer = StatisticRenderer(year, label, **style_kwargs)
    renderer.with_historical_style()
    return renderer.render(output_path, duration=duration)


def render_statistic(
    value: str,
    label: str = None,
    output_path: str = "stat.mp4",
    duration: float = 5.0,
    prefix: str = "",
    suffix: str = "",
    **style_kwargs,
) -> str:
    """Render an animated statistic reveal."""
    renderer = StatisticRenderer(value, label, prefix=prefix, suffix=suffix, **style_kwargs)
    return renderer.render(output_path, duration=duration)
