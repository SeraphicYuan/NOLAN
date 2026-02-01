"""
Comparison/Split Screen scene renderer.

Creates side-by-side comparisons:
- Before/After
- Vs. matchups (Maduro vs Guaidó)
- Rich vs Poor contrasts

Animation: Center line reveals both sides
"""

from typing import Tuple, Optional, Union, List
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ExpandWidth
from ..layout import Position


class ComparisonRenderer(BaseRenderer):
    """
    Render animated comparison/split screen.

    Usage:
        renderer = ComparisonRenderer(
            left_text="MADURO",
            right_text="GUAIDÓ",
            left_subtitle="Current President",
            right_subtitle="Opposition Leader"
        )
        renderer.render("output.mp4", duration=5.0)
    """

    def __init__(
        self,
        left_text: str,
        right_text: str,
        left_subtitle: str = None,
        right_subtitle: str = None,
        center_label: str = "VS",
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (15, 15, 20),
        left_color: Tuple[int, int, int] = (220, 60, 60),  # Red
        right_color: Tuple[int, int, int] = (60, 130, 220),  # Blue
        text_color: Tuple[int, int, int] = (255, 255, 255),
        subtitle_color: Tuple[int, int, int] = (160, 160, 170),
        divider_color: Tuple[int, int, int] = (80, 80, 90),
        # Typography
        main_size: int = 72,
        subtitle_size: int = 32,
        center_size: int = 48,
        main_font: str = "C:/Windows/Fonts/arialbd.ttf",
        subtitle_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        self.left_text = left_text
        self.right_text = right_text
        self.left_subtitle = left_subtitle
        self.right_subtitle = right_subtitle
        self.center_label = center_label
        self.left_color = left_color
        self.right_color = right_color
        self.text_color = text_color
        self.subtitle_color = subtitle_color
        self.divider_color = divider_color
        self.main_size = main_size
        self.subtitle_size = subtitle_size
        self.center_size = center_size
        self.main_font = main_font
        self.subtitle_font = subtitle_font

        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        center_x = self.width // 2
        center_y = self.height // 2

        # Left side text
        left_x = self.width // 4
        left_element = Element(
            id="left_text",
            element_type="text",
            text=self.left_text.upper(),
            font_path=self.main_font,
            font_size=self.main_size,
            color=self.left_color,
            x=left_x,
            y=center_y - 40,
        )
        left_element.add_effect(
            FadeIn(start=0.3, duration=0.6, easing="ease_out_cubic")
        )
        self.add_element(left_element)

        # Left subtitle
        if self.left_subtitle:
            left_sub = Element(
                id="left_subtitle",
                element_type="text",
                text=self.left_subtitle,
                font_path=self.subtitle_font,
                font_size=self.subtitle_size,
                color=self.subtitle_color,
                x=left_x,
                y=center_y + 50,
            )
            left_sub.add_effect(
                FadeIn(start=0.6, duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(left_sub)

        # Center divider line
        divider = Element(
            id="divider",
            element_type="rectangle",
            color=self.divider_color,
            x=center_x - 2,
            y=center_y - 150,
            width=4,
            height=300,
        )
        divider.add_effect(
            FadeIn(start=0.2, duration=0.4, easing="ease_out_cubic")
        )
        self.add_element(divider)

        # Center label (VS)
        if self.center_label:
            center_element = Element(
                id="center_label",
                element_type="text",
                text=self.center_label,
                font_path=self.main_font,
                font_size=self.center_size,
                color=self.text_color,
                x='center',
                y=center_y - 20,
            )
            center_element.add_effect(
                FadeIn(start=0.5, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(center_element)

        # Right side text
        right_x = (self.width // 4) * 3
        right_element = Element(
            id="right_text",
            element_type="text",
            text=self.right_text.upper(),
            font_path=self.main_font,
            font_size=self.main_size,
            color=self.right_color,
            x=right_x,
            y=center_y - 40,
        )
        right_element.add_effect(
            FadeIn(start=0.4, duration=0.6, easing="ease_out_cubic")
        )
        self.add_element(right_element)

        # Right subtitle
        if self.right_subtitle:
            right_sub = Element(
                id="right_subtitle",
                element_type="text",
                text=self.right_subtitle,
                font_path=self.subtitle_font,
                font_size=self.subtitle_size,
                color=self.subtitle_color,
                x=right_x,
                y=center_y + 50,
            )
            right_sub.add_effect(
                FadeIn(start=0.7, duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(right_sub)


def render_comparison(
    left_text: str,
    right_text: str,
    left_subtitle: str = None,
    right_subtitle: str = None,
    output_path: str = "comparison.mp4",
    duration: float = 5.0,
    **style_kwargs,
) -> str:
    """Render an animated comparison."""
    renderer = ComparisonRenderer(
        left_text, right_text,
        left_subtitle, right_subtitle,
        **style_kwargs
    )
    return renderer.render(output_path, duration=duration)
