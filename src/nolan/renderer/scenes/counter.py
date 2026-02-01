"""
Counter/Number Roll scene renderer.

Creates animated counting numbers:
- Count up from 0 to target value
- Count down
- Animated percentage reveals

Animation: Numbers roll/count with easing
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, ScaleIn, Effect
from ..layout import Position
from ..easing import Easing
from dataclasses import dataclass


@dataclass
class CountUp(Effect):
    """Animate number counting up from 0 to target."""
    target: int = 100
    prefix: str = ""
    suffix: str = ""

    def apply(self, t: float, props: dict) -> dict:
        progress = self.get_progress(t)
        current_value = int(self.target * progress)
        props['visible_text'] = f"{self.prefix}{current_value:,}{self.suffix}"
        return props


class CounterRenderer(BaseRenderer):
    """
    Render animated counter/number roll.

    Usage:
        renderer = CounterRenderer(
            value=300,
            label="BILLION BARRELS",
            prefix="$",
            suffix="B"
        )
        renderer.render("output.mp4", duration=4.0)
    """

    def __init__(
        self,
        value: int,
        label: str = None,
        prefix: str = "",
        suffix: str = "",
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (15, 15, 20),
        value_color: Tuple[int, int, int] = (70, 130, 220),
        label_color: Tuple[int, int, int] = (180, 180, 190),
        # Typography
        value_size: int = 160,
        label_size: int = 42,
        value_font: str = "C:/Windows/Fonts/arialbd.ttf",
        label_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
        count_start: float = 0.3,
        count_duration: float = 2.0,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        self.value = value
        self.label = label
        self.prefix = prefix
        self.suffix = suffix
        self.position = position if isinstance(position, Position) else Position.from_spec(position)
        self.value_color = value_color
        self.label_color = label_color
        self.value_size = value_size
        self.label_size = label_size
        self.value_font = value_font
        self.label_font = label_font
        self.count_start = count_start
        self.count_duration = count_duration

        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        # Calculate vertical positions
        value_y = self.height // 2 - (30 if self.label else 0)
        label_y = value_y + self.value_size + 20

        # Value with count-up animation
        value_element = Element(
            id="value",
            element_type="text",
            text=f"{self.prefix}0{self.suffix}",  # Start at 0
            font_path=self.value_font,
            font_size=self.value_size,
            color=self.value_color,
            x='center',
            y=value_y,
        )
        value_element.add_effects([
            FadeIn(start=0.2, duration=0.5, easing="ease_out_cubic"),
            ScaleIn(start=0.2, duration=0.8, from_scale=0.9, easing="ease_out_back"),
            CountUp(
                start=self.count_start,
                duration=self.count_duration,
                target=self.value,
                prefix=self.prefix,
                suffix=self.suffix,
                easing="ease_out_cubic"
            ),
        ])
        self.add_element(value_element)

        # Label below value
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
                FadeIn(start=self.count_start + self.count_duration - 0.3,
                       duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(label_element)

    def with_danger_style(self) -> 'CounterRenderer':
        """Apply danger/warning colors (for negative stats)."""
        self.bg_color = (25, 15, 15)
        for el in self.elements:
            if el.id == "value":
                el.color = (255, 80, 80)
            elif el.id == "label":
                el.color = (180, 150, 150)
        return self

    def with_success_style(self) -> 'CounterRenderer':
        """Apply success/positive colors."""
        self.bg_color = (15, 25, 20)
        for el in self.elements:
            if el.id == "value":
                el.color = (80, 220, 120)
            elif el.id == "label":
                el.color = (150, 180, 160)
        return self


def render_counter(
    value: int,
    label: str = None,
    output_path: str = "counter.mp4",
    duration: float = 4.0,
    prefix: str = "",
    suffix: str = "",
    **style_kwargs,
) -> str:
    """Render an animated counter."""
    renderer = CounterRenderer(value, label, prefix=prefix, suffix=suffix, **style_kwargs)
    return renderer.render(output_path, duration=duration)
