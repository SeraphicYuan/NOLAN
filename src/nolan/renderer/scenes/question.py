"""
Question card renderer.

Creates rhetorical question cards to engage viewers:
- Large question text
- Optional context/subtitle
- Question mark accent

Animation: Question fades in with dramatic timing
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ScaleIn
from ..layout import Position, POSITIONS


class QuestionRenderer(BaseRenderer):
    """
    Render animated question cards.

    Usage:
        renderer = QuestionRenderer(
            question="What happens when a nation's wealth disappears overnight?",
            context="The Venezuelan Crisis"
        )
        renderer.render("output.mp4", duration=5.0)
    """

    def __init__(
        self,
        question: str,
        context: str = None,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (12, 12, 18),
        question_color: Tuple[int, int, int] = (255, 255, 255),
        context_color: Tuple[int, int, int] = (120, 120, 140),
        accent_color: Tuple[int, int, int] = (255, 180, 100),
        # Typography
        question_size: int = 64,
        context_size: int = 28,
        accent_size: int = 200,
        question_font: str = "C:/Windows/Fonts/arialbd.ttf",
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

        self.question = question
        self.context = context
        self.question_color = question_color
        self.context_color = context_color
        self.accent_color = accent_color
        self.question_size = question_size
        self.context_size = context_size
        self.accent_size = accent_size
        self.question_font = question_font
        self.context_font = context_font
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)

        # Context label (optional, above question)
        if self.context:
            context_y = base_y - 100
            context_element = Element(
                id="context",
                element_type="text",
                text=self.context.upper(),
                font_path=self.context_font,
                font_size=self.context_size,
                color=self.context_color,
                x='center',
                y=context_y,
            )
            context_element.add_effect(
                FadeIn(start=0.2, duration=0.4, easing="ease_out_cubic")
            )
            self.add_element(context_element)

        # Large decorative question mark (background)
        qmark_element = Element(
            id="question_mark",
            element_type="text",
            text="?",
            font_path=self.question_font,
            font_size=self.accent_size,
            color=tuple(max(0, c - 200) for c in self.accent_color),  # Dimmed version
            x=self.width - 300,
            y=base_y - 100,
        )
        qmark_element.add_effects([
            FadeIn(start=0.1, duration=0.6, easing="ease_out_cubic"),
            ScaleIn(start=0.1, duration=0.6, from_scale=0.5, easing="ease_out_back"),
        ])
        self.add_element(qmark_element)

        # Main question text (with smart wrapping)
        question_element = Element(
            id="question",
            element_type="text",
            text=self.question,
            font_path=self.question_font,
            font_size=self.question_size,
            color=self.question_color,
            x='center',
            y=base_y,
            max_width=self.get_text_max_width("default"),
            max_lines=3,
            text_align="center",
        )
        question_element.add_effects([
            FadeIn(start=0.4, duration=0.8, easing="ease_out_cubic"),
            SlideUp(start=0.4, duration=0.8, distance=30, easing="ease_out_cubic"),
        ])
        self.add_element(question_element)

        # Accent underline
        underline_y = base_y + 80
        underline_element = Element(
            id="underline",
            element_type="rectangle",
            color=self.accent_color,
            x='center',
            y=underline_y,
            width=200,
            height=4,
        )
        underline_element.add_effect(
            FadeIn(start=1.0, duration=0.4, easing="ease_out_cubic")
        )
        self.add_element(underline_element)


def render_question(
    question: str,
    context: str = None,
    output_path: str = "question.mp4",
    duration: float = 5.0,
    **style_kwargs,
) -> str:
    """Render an animated question card."""
    renderer = QuestionRenderer(question, context=context, **style_kwargs)
    return renderer.render(output_path, duration=duration)
