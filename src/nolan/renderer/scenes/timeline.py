"""
Timeline scene renderer.

Creates animated historical timelines:
- Sequential date reveals
- Event markers
- Progress through time

Animation: Points appear sequentially along a line
"""

from typing import Tuple, List, Union
from dataclasses import dataclass
from ..base import BaseRenderer, Element
from ..effects import FadeIn, ScaleIn, ExpandWidth
from ..layout import Position


@dataclass
class TimelineEvent:
    """A single event on the timeline."""
    year: str
    label: str
    color: Tuple[int, int, int] = None  # Optional override color


class TimelineRenderer(BaseRenderer):
    """
    Render animated timeline.

    Usage:
        renderer = TimelineRenderer(
            events=[
                TimelineEvent("1821", "Independence"),
                TimelineEvent("1976", "Oil Nationalization"),
                TimelineEvent("1998", "Chávez Elected"),
                TimelineEvent("2014", "Economic Crisis"),
            ]
        )
        renderer.render("output.mp4", duration=8.0)
    """

    def __init__(
        self,
        events: List[TimelineEvent],
        title: str = None,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (15, 15, 20),
        line_color: Tuple[int, int, int] = (60, 60, 70),
        year_color: Tuple[int, int, int] = (255, 255, 255),
        label_color: Tuple[int, int, int] = (160, 160, 170),
        dot_color: Tuple[int, int, int] = (220, 38, 38),
        # Typography
        title_size: int = 48,
        year_size: int = 36,
        label_size: int = 24,
        title_font: str = "C:/Windows/Fonts/arialbd.ttf",
        year_font: str = "C:/Windows/Fonts/arialbd.ttf",
        label_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
        event_stagger: float = 0.8,  # Delay between events
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        self.events = events
        self.title = title
        self.line_color = line_color
        self.year_color = year_color
        self.label_color = label_color
        self.dot_color = dot_color
        self.title_size = title_size
        self.year_size = year_size
        self.label_size = label_size
        self.title_font = title_font
        self.year_font = year_font
        self.label_font = label_font
        self.event_stagger = event_stagger

        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        # Calculate layout
        n_events = len(self.events)
        line_y = self.height // 2 + 20
        line_start_x = int(self.width * 0.1)
        line_end_x = int(self.width * 0.9)
        line_width = line_end_x - line_start_x

        # Title (optional)
        if self.title:
            title_element = Element(
                id="title",
                element_type="text",
                text=self.title.upper(),
                font_path=self.title_font,
                font_size=self.title_size,
                color=self.year_color,
                x='center',
                y=self.height // 2 - 120,
            )
            title_element.add_effect(
                FadeIn(start=0.2, duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(title_element)

        # Horizontal timeline line
        line_element = Element(
            id="timeline_line",
            element_type="rectangle",
            color=self.line_color,
            x=line_start_x,
            y=line_y,
            width=line_width,
            height=3,
        )
        line_element.add_effect(
            ExpandWidth(start=0.3, duration=0.8, easing="ease_out_quart")
        )
        self.add_element(line_element)

        # Events
        for i, event in enumerate(self.events):
            event_start = 0.8 + (i * self.event_stagger)

            # Calculate x position for this event
            if n_events > 1:
                event_x = line_start_x + int(line_width * i / (n_events - 1))
            else:
                event_x = self.width // 2

            # Dot marker
            dot_color = event.color or self.dot_color
            dot = Element(
                id=f"dot_{i}",
                element_type="rectangle",
                color=dot_color,
                x=event_x - 6,
                y=line_y - 4,
                width=12,
                height=12,
            )
            dot.add_effect(
                ScaleIn(start=event_start, duration=0.3, from_scale=0.0, easing="ease_out_back")
            )
            self.add_element(dot)

            # Year above line
            year_element = Element(
                id=f"year_{i}",
                element_type="text",
                text=event.year,
                font_path=self.year_font,
                font_size=self.year_size,
                color=self.year_color,
                x=event_x,
                y=line_y - 50,
            )
            year_element.add_effect(
                FadeIn(start=event_start + 0.1, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(year_element)

            # Label below line
            label_element = Element(
                id=f"label_{i}",
                element_type="text",
                text=event.label,
                font_path=self.label_font,
                font_size=self.label_size,
                color=self.label_color,
                x=event_x,
                y=line_y + 25,
            )
            label_element.add_effect(
                FadeIn(start=event_start + 0.2, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(label_element)


def render_timeline(
    events: List[dict],
    title: str = None,
    output_path: str = "timeline.mp4",
    duration: float = 8.0,
    **style_kwargs,
) -> str:
    """
    Render an animated timeline.

    Args:
        events: List of dicts with 'year' and 'label' keys
        title: Optional title above timeline
        output_path: Output file path
        duration: Video duration
    """
    timeline_events = [
        TimelineEvent(year=e['year'], label=e['label'])
        for e in events
    ]
    renderer = TimelineRenderer(timeline_events, title=title, **style_kwargs)
    return renderer.render(output_path, duration=duration)
