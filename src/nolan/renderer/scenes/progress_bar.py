"""
Progress bar renderer.

Creates animated progress indicators:
- Section label
- Progress bar with fill animation
- Percentage or fraction display
- Optional milestone markers

Animation: Bar fills from left to right with label fades
"""

from typing import Tuple, Optional, Union, List
from ..base import BaseRenderer, Element
from ..effects import FadeIn, ExpandWidth
from ..layout import Position, POSITIONS


class ProgressBarRenderer(BaseRenderer):
    """
    Render animated progress bar cards.

    Usage:
        renderer = ProgressBarRenderer(
            label="Story Progress",
            progress=0.65,  # 65%
            show_percentage=True
        )
        renderer.render("output.mp4", duration=4.0)
    """

    def __init__(
        self,
        progress: float,  # 0.0 to 1.0
        label: str = None,
        show_percentage: bool = True,
        milestone_labels: List[str] = None,  # e.g., ["Start", "Middle", "End"]
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (18, 18, 24),
        label_color: Tuple[int, int, int] = (200, 200, 210),
        bar_bg_color: Tuple[int, int, int] = (50, 50, 60),
        bar_fill_color: Tuple[int, int, int] = (100, 180, 255),
        percentage_color: Tuple[int, int, int] = (255, 255, 255),
        # Dimensions
        bar_width: int = 800,
        bar_height: int = 12,
        # Typography
        label_size: int = 28,
        percentage_size: int = 48,
        label_font: str = "C:/Windows/Fonts/arial.ttf",
        percentage_font: str = "C:/Windows/Fonts/arialbd.ttf",
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.progress = max(0.0, min(1.0, progress))
        self.label = label
        self.show_percentage = show_percentage
        self.milestone_labels = milestone_labels
        self.label_color = label_color
        self.bar_bg_color = bar_bg_color
        self.bar_fill_color = bar_fill_color
        self.percentage_color = percentage_color
        self.bar_width = bar_width
        self.bar_height = bar_height
        self.label_size = label_size
        self.percentage_size = percentage_size
        self.label_font = label_font
        self.percentage_font = percentage_font
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)
        bar_x = (self.width - self.bar_width) // 2

        current_y = base_y - 60

        # Label (optional)
        if self.label:
            label_element = Element(
                id="label",
                element_type="text",
                text=self.label.upper(),
                font_path=self.label_font,
                font_size=self.label_size,
                color=self.label_color,
                x='center',
                y=current_y,
            )
            label_element.add_effect(
                FadeIn(start=0.2, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(label_element)
            current_y = base_y

        # Bar background (track)
        bg_element = Element(
            id="bar_bg",
            element_type="rectangle",
            color=self.bar_bg_color,
            x=bar_x,
            y=current_y,
            width=self.bar_width,
            height=self.bar_height,
        )
        bg_element.add_effect(
            FadeIn(start=0.3, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(bg_element)

        # Bar fill (progress)
        fill_width = int(self.bar_width * self.progress)
        if fill_width > 0:
            fill_element = Element(
                id="bar_fill",
                element_type="rectangle",
                color=self.bar_fill_color,
                x=bar_x,
                y=current_y,
                width=fill_width,
                height=self.bar_height,
            )
            fill_element.add_effect(
                ExpandWidth(start=0.5, duration=0.8, easing="ease_out_quart")
            )
            self.add_element(fill_element)

        # Percentage display
        if self.show_percentage:
            percentage_text = f"{int(self.progress * 100)}%"
            percentage_y = current_y + self.bar_height + 30
            percent_element = Element(
                id="percentage",
                element_type="text",
                text=percentage_text,
                font_path=self.percentage_font,
                font_size=self.percentage_size,
                color=self.percentage_color,
                x='center',
                y=percentage_y,
            )
            percent_element.add_effect(
                FadeIn(start=1.0, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(percent_element)


def render_progress_bar(
    progress: float,
    label: str = None,
    output_path: str = "progress.mp4",
    duration: float = 4.0,
    **style_kwargs,
) -> str:
    """Render an animated progress bar card."""
    renderer = ProgressBarRenderer(progress, label=label, **style_kwargs)
    return renderer.render(output_path, duration=duration)
