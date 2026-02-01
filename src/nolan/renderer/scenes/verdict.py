"""
Verdict/Conclusion card renderer.

Creates conclusion/takeaway cards:
- Icon or symbol (checkmark, warning, etc.)
- Main verdict text
- Optional supporting text
- Color-coded by sentiment

Animation: Icon scales in, text fades in
"""

from typing import Tuple, Optional, Union, Literal
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp, ScaleIn
from ..layout import Position, POSITIONS


VerdictType = Literal["conclusion", "warning", "success", "info", "key_point"]


class VerdictRenderer(BaseRenderer):
    """
    Render animated verdict/conclusion cards.

    Usage:
        renderer = VerdictRenderer(
            verdict="The economy never recovered",
            supporting_text="Despite multiple attempts at reform",
            verdict_type="conclusion"
        )
        renderer.render("output.mp4", duration=5.0)
    """

    # Preset styles for different verdict types
    VERDICT_STYLES = {
        "conclusion": {
            "icon": "→",
            "accent_color": (100, 140, 255),
            "bg_tint": (15, 18, 28),
        },
        "warning": {
            "icon": "⚠",
            "accent_color": (255, 180, 80),
            "bg_tint": (28, 22, 15),
        },
        "success": {
            "icon": "✓",
            "accent_color": (80, 200, 120),
            "bg_tint": (15, 25, 18),
        },
        "info": {
            "icon": "ℹ",
            "accent_color": (100, 180, 255),
            "bg_tint": (15, 20, 28),
        },
        "key_point": {
            "icon": "★",
            "accent_color": (255, 200, 100),
            "bg_tint": (25, 22, 15),
        },
    }

    def __init__(
        self,
        verdict: str,
        supporting_text: str = None,
        verdict_type: VerdictType = "conclusion",
        label: str = None,  # e.g., "KEY TAKEAWAY", "CONCLUSION"
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = None,  # Auto from verdict_type
        verdict_color: Tuple[int, int, int] = (255, 255, 255),
        supporting_color: Tuple[int, int, int] = (160, 160, 170),
        accent_color: Tuple[int, int, int] = None,  # Auto from verdict_type
        # Typography
        verdict_size: int = 52,
        supporting_size: int = 28,
        label_size: int = 22,
        icon_size: int = 80,
        verdict_font: str = "C:/Windows/Fonts/arialbd.ttf",
        supporting_font: str = "C:/Windows/Fonts/arial.ttf",
        # Timing
        fps: int = 30,
    ):
        # Get style from verdict type
        style = self.VERDICT_STYLES.get(verdict_type, self.VERDICT_STYLES["conclusion"])

        # Apply defaults from style
        if bg_color is None:
            bg_color = style["bg_tint"]
        if accent_color is None:
            accent_color = style["accent_color"]

        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.verdict = verdict
        self.supporting_text = supporting_text
        self.verdict_type = verdict_type
        self.label = label or verdict_type.upper().replace("_", " ")
        self.icon = style["icon"]
        self.verdict_color = verdict_color
        self.supporting_color = supporting_color
        self.accent_color = accent_color
        self.verdict_size = verdict_size
        self.supporting_size = supporting_size
        self.label_size = label_size
        self.icon_size = icon_size
        self.verdict_font = verdict_font
        self.supporting_font = supporting_font
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)

        # Icon
        icon_y = base_y - 100
        icon_element = Element(
            id="icon",
            element_type="text",
            text=self.icon,
            font_path=self.verdict_font,
            font_size=self.icon_size,
            color=self.accent_color,
            x='center',
            y=icon_y,
        )
        icon_element.add_effects([
            FadeIn(start=0.2, duration=0.4, easing="ease_out_cubic"),
            ScaleIn(start=0.2, duration=0.4, from_scale=0.5, easing="ease_out_back"),
        ])
        self.add_element(icon_element)

        # Label
        label_y = icon_y + self.icon_size + 10
        label_element = Element(
            id="label",
            element_type="text",
            text=self.label,
            font_path=self.supporting_font,
            font_size=self.label_size,
            color=self.accent_color,
            x='center',
            y=label_y,
        )
        label_element.add_effect(
            FadeIn(start=0.4, duration=0.4, easing="ease_out_cubic")
        )
        self.add_element(label_element)

        # Main verdict text (with smart wrapping)
        # Pre-calculate text layout to know the height
        from ..text_layout import TextLayout
        verdict_max_width = self.get_text_max_width("default")
        verdict_layout = TextLayout(
            text=self.verdict,
            font_path=self.verdict_font,
            font_size=self.verdict_size,
            max_width=verdict_max_width,
            max_lines=3,
        )

        verdict_y = label_y + 50
        verdict_element = Element(
            id="verdict",
            element_type="text",
            text=self.verdict,
            font_path=self.verdict_font,
            font_size=self.verdict_size,
            color=self.verdict_color,
            x='center',
            y=verdict_y,
            max_width=verdict_max_width,
            max_lines=3,
            text_align="center",
        )
        verdict_element.add_effects([
            FadeIn(start=0.6, duration=0.6, easing="ease_out_cubic"),
            SlideUp(start=0.6, duration=0.6, distance=20, easing="ease_out_cubic"),
        ])
        self.add_element(verdict_element)

        # Supporting text (with smart wrapping)
        # Position below the verdict text block
        if self.supporting_text:
            supporting_y = verdict_y + verdict_layout.total_height + 30
            supporting_element = Element(
                id="supporting",
                element_type="text",
                text=self.supporting_text,
                font_path=self.supporting_font,
                font_size=self.supporting_size,
                color=self.supporting_color,
                x='center',
                y=supporting_y,
                max_width=self.get_text_max_width("default"),
                max_lines=2,
                text_align="center",
            )
            supporting_element.add_effect(
                FadeIn(start=1.0, duration=0.5, easing="ease_out_cubic")
            )
            self.add_element(supporting_element)


def render_verdict(
    verdict: str,
    supporting_text: str = None,
    verdict_type: VerdictType = "conclusion",
    output_path: str = "verdict.mp4",
    duration: float = 5.0,
    **style_kwargs,
) -> str:
    """Render an animated verdict/conclusion card."""
    renderer = VerdictRenderer(
        verdict, supporting_text=supporting_text, verdict_type=verdict_type, **style_kwargs
    )
    return renderer.render(output_path, duration=duration)
