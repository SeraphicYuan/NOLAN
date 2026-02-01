"""
Composable animation effects.

Effects modify element properties over time. They can be combined
to create complex animations.

Usage:
    element.add_effect(FadeIn(start=0.0, duration=0.5))
    element.add_effect(SlideUp(start=0.0, duration=0.8, distance=50))
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from .easing import Easing, EasingFunc


@dataclass
class Effect:
    """Base class for animation effects."""
    start: float = 0.0           # Start time in seconds
    duration: float = 0.5        # Duration in seconds
    easing: str = "ease_out_cubic"  # Easing function name

    @property
    def end(self) -> float:
        return self.start + self.duration

    def get_progress(self, t: float) -> float:
        """Get animation progress at time t, with easing applied."""
        if t < self.start:
            return 0.0
        if t >= self.end:
            return 1.0

        linear_progress = (t - self.start) / self.duration
        easing_func = Easing.get(self.easing)
        return easing_func(linear_progress)

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply effect to element properties at time t.
        Override in subclasses.
        """
        return props


@dataclass
class FadeIn(Effect):
    """Fade element in from transparent."""

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['alpha'] = props.get('alpha', 1.0) * progress
        return props


@dataclass
class FadeOut(Effect):
    """Fade element out to transparent."""

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['alpha'] = props.get('alpha', 1.0) * (1 - progress)
        return props


@dataclass
class SlideUp(Effect):
    """Slide element up from below."""
    distance: float = 50  # Pixels to slide

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        offset = self.distance * (1 - progress)
        props['y_offset'] = props.get('y_offset', 0) + offset
        return props


@dataclass
class SlideDown(Effect):
    """Slide element down from above."""
    distance: float = 50

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        offset = -self.distance * (1 - progress)
        props['y_offset'] = props.get('y_offset', 0) + offset
        return props


@dataclass
class SlideLeft(Effect):
    """Slide element in from the right."""
    distance: float = 100

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        offset = self.distance * (1 - progress)
        props['x_offset'] = props.get('x_offset', 0) + offset
        return props


@dataclass
class SlideRight(Effect):
    """Slide element in from the left."""
    distance: float = 100

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        offset = -self.distance * (1 - progress)
        props['x_offset'] = props.get('x_offset', 0) + offset
        return props


@dataclass
class ScaleIn(Effect):
    """Scale element in from smaller size."""
    from_scale: float = 0.8

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        scale = self.from_scale + (1.0 - self.from_scale) * progress
        props['scale'] = props.get('scale', 1.0) * scale
        return props


@dataclass
class ScaleOut(Effect):
    """Scale element out to smaller size."""
    to_scale: float = 0.8

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        scale = 1.0 - (1.0 - self.to_scale) * progress
        props['scale'] = props.get('scale', 1.0) * scale
        return props


@dataclass
class ExpandWidth(Effect):
    """Expand element width from center."""

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['width_scale'] = progress
        return props


@dataclass
class TypeWriter(Effect):
    """Reveal text character by character."""

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        text = props.get('text', '')
        visible_chars = int(len(text) * progress)
        props['visible_text'] = text[:visible_chars]
        return props


@dataclass
class ColorShift(Effect):
    """Animate color from one value to another."""
    from_color: tuple = (255, 255, 255)
    to_color: tuple = (255, 255, 255)

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        color = tuple(
            int(self.from_color[i] + (self.to_color[i] - self.from_color[i]) * progress)
            for i in range(min(len(self.from_color), len(self.to_color)))
        )
        props['color'] = color
        return props


@dataclass
class Pulse(Effect):
    """Pulsing scale effect (for emphasis)."""
    scale_amount: float = 1.1
    pulses: int = 2

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        import math
        progress = self.get_progress(t)
        # Create sine wave for pulsing
        pulse = math.sin(progress * math.pi * self.pulses * 2)
        scale = 1.0 + (self.scale_amount - 1.0) * abs(pulse) * (1 - progress)
        props['scale'] = props.get('scale', 1.0) * scale
        return props


# Effect presets for common animations
class EffectPresets:
    """Pre-configured effect combinations."""

    @staticmethod
    def fade_slide_up(start: float = 0.0, duration: float = 0.8) -> list:
        """Fade in while sliding up - classic reveal."""
        return [
            FadeIn(start=start, duration=duration),
            SlideUp(start=start, duration=duration, distance=40),
        ]

    @staticmethod
    def fade_slide_down(start: float = 0.0, duration: float = 0.8) -> list:
        """Fade in while sliding down."""
        return [
            FadeIn(start=start, duration=duration),
            SlideDown(start=start, duration=duration, distance=40),
        ]

    @staticmethod
    def zoom_fade_in(start: float = 0.0, duration: float = 0.6) -> list:
        """Zoom in while fading - dramatic reveal."""
        return [
            FadeIn(start=start, duration=duration),
            ScaleIn(start=start, duration=duration, from_scale=0.9),
        ]

    @staticmethod
    def fade_only(start: float = 0.0, duration: float = 0.5) -> list:
        """Simple fade in."""
        return [FadeIn(start=start, duration=duration)]

    @staticmethod
    def expand_from_center(start: float = 0.0, duration: float = 0.6) -> list:
        """Expand width from center - for bars/lines."""
        return [ExpandWidth(start=start, duration=duration, easing="ease_out_quart")]
