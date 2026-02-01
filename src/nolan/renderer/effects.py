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


@dataclass
class CountUp(Effect):
    """Animate a number from start to end value."""
    from_value: float = 0
    to_value: float = 100
    prefix: str = ""       # e.g., "$"
    suffix: str = ""       # e.g., "%", "M", "B"
    decimals: int = 0      # Decimal places
    use_commas: bool = True  # Thousand separators

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        current = self.from_value + (self.to_value - self.from_value) * progress

        # Format the number
        if self.decimals > 0:
            formatted = f"{current:,.{self.decimals}f}" if self.use_commas else f"{current:.{self.decimals}f}"
        else:
            formatted = f"{int(current):,}" if self.use_commas else str(int(current))

        props['visible_text'] = f"{self.prefix}{formatted}{self.suffix}"
        return props


@dataclass
class Shake(Effect):
    """Shake/wiggle effect for emphasis."""
    intensity: float = 10    # Max pixels of shake
    frequency: float = 20    # Shakes per second
    decay: bool = True       # Whether shake decreases over time

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        import math
        import random

        progress = self.get_progress(t)
        if progress <= 0 or progress >= 1:
            return props

        # Use time-based seed for consistent shake at same timestamp
        seed = int(t * 1000)
        random.seed(seed)

        # Calculate shake amount (decays if enabled)
        decay_factor = 1 - progress if self.decay else 1.0
        shake_amount = self.intensity * decay_factor

        # High-frequency oscillation
        phase = t * self.frequency * 2 * math.pi
        x_shake = math.sin(phase) * shake_amount * random.uniform(0.5, 1.0)
        y_shake = math.cos(phase * 1.3) * shake_amount * random.uniform(0.5, 1.0)

        props['x_offset'] = props.get('x_offset', 0) + x_shake
        props['y_offset'] = props.get('y_offset', 0) + y_shake
        return props


@dataclass
class Hold(Effect):
    """Hold element at full visibility (useful for sequencing)."""

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        # Hold just maintains current props - useful as explicit timing marker
        if t >= self.start and t <= self.end:
            props['alpha'] = props.get('alpha', 1.0)
        return props


@dataclass
class Flash(Effect):
    """Quick flash/blink effect."""
    flashes: int = 3

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        import math
        progress = self.get_progress(t)
        if progress <= 0 or progress >= 1:
            return props

        # Square wave for sharp on/off
        flash_progress = progress * self.flashes * 2
        is_on = int(flash_progress) % 2 == 0
        props['alpha'] = props.get('alpha', 1.0) if is_on else 0
        return props


@dataclass
class WipeIn(Effect):
    """Reveal element with directional wipe."""
    direction: str = "left"  # left, right, up, down

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['wipe_progress'] = progress
        props['wipe_direction'] = self.direction
        return props


@dataclass
class Bounce(Effect):
    """Bounce in effect (element overshoots then settles)."""
    overshoot: float = 1.2   # How much to overshoot (1.2 = 20% overshoot)
    bounces: int = 2

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        import math
        progress = self.get_progress(t)

        if progress <= 0:
            props['scale'] = props.get('scale', 1.0) * 0
            return props
        if progress >= 1:
            return props

        # Damped oscillation
        decay = math.exp(-progress * 4)
        oscillation = math.cos(progress * math.pi * self.bounces * 2)
        bounce_scale = 1 + (self.overshoot - 1) * oscillation * decay

        props['scale'] = props.get('scale', 1.0) * bounce_scale
        return props


@dataclass
class Glitch(Effect):
    """Digital glitch effect with random offset."""
    intensity: float = 20
    frequency: float = 10   # Glitches per second

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        import random
        import math

        progress = self.get_progress(t)
        if progress <= 0 or progress >= 1:
            return props

        # Random glitch at intervals
        glitch_phase = int(t * self.frequency)
        random.seed(glitch_phase)

        # Occasional strong glitch
        if random.random() < 0.3:
            x_glitch = random.uniform(-self.intensity, self.intensity)
            props['x_offset'] = props.get('x_offset', 0) + x_glitch

            # Sometimes also vertical
            if random.random() < 0.5:
                y_glitch = random.uniform(-self.intensity/2, self.intensity/2)
                props['y_offset'] = props.get('y_offset', 0) + y_glitch

        return props


@dataclass
class Reveal(Effect):
    """Reveal text word by word or character by character."""
    mode: str = "word"  # "word" or "char"

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        text = props.get('text', '')

        if self.mode == "word":
            words = text.split()
            visible_count = int(len(words) * progress)
            props['visible_text'] = ' '.join(words[:visible_count]) if visible_count > 0 else ''
        else:  # char mode (same as TypeWriter)
            visible_chars = int(len(text) * progress)
            props['visible_text'] = text[:visible_chars]

        return props


@dataclass
class StaggeredFadeIn(Effect):
    """Fade in with staggered delay per character/word."""
    mode: str = "char"      # "char" or "word"
    stagger_delay: float = 0.05  # Delay between each unit

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        # This effect sets up metadata for the renderer to handle
        # The actual staggering happens at render time
        progress = self.get_progress(t)
        props['stagger_mode'] = self.mode
        props['stagger_progress'] = progress
        props['stagger_delay'] = self.stagger_delay
        return props


@dataclass
class RotateIn(Effect):
    """Rotate element in from an angle."""
    from_angle: float = -90  # Starting angle in degrees

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        angle = self.from_angle * (1 - progress)
        props['rotation'] = props.get('rotation', 0) + angle
        return props


@dataclass
class RotateOut(Effect):
    """Rotate element out to an angle."""
    to_angle: float = 90  # Ending angle in degrees

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        angle = self.to_angle * progress
        props['rotation'] = props.get('rotation', 0) + angle
        return props


@dataclass
class Spin(Effect):
    """Continuous spinning effect."""
    rotations: float = 1  # Number of full rotations
    clockwise: bool = True

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        angle = 360 * self.rotations * progress
        if not self.clockwise:
            angle = -angle
        props['rotation'] = props.get('rotation', 0) + angle
        return props


@dataclass
class Wobble(Effect):
    """Oscillating rotation (like a pendulum)."""
    angle: float = 15      # Max angle of wobble
    oscillations: int = 3  # Number of back-and-forth movements

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        import math
        progress = self.get_progress(t)
        # Damped oscillation
        decay = 1 - progress
        wobble = math.sin(progress * math.pi * self.oscillations * 2) * self.angle * decay
        props['rotation'] = props.get('rotation', 0) + wobble
        return props


# ============================================================================
# BLUR EFFECTS
# ============================================================================

@dataclass
class BlurIn(Effect):
    """Element comes into focus from blurred state."""
    from_blur: float = 10  # Starting blur radius

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        blur = self.from_blur * (1 - progress)
        props['blur'] = props.get('blur', 0) + blur
        return props


@dataclass
class BlurOut(Effect):
    """Element goes out of focus to blurred state."""
    to_blur: float = 10  # Ending blur radius

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        blur = self.to_blur * progress
        props['blur'] = props.get('blur', 0) + blur
        return props


@dataclass
class FocusPull(Effect):
    """Rack focus effect - blur then sharp then optionally blur again."""
    max_blur: float = 8
    focus_point: float = 0.5  # When element is in perfect focus (0-1)

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        # Distance from focus point determines blur
        distance = abs(progress - self.focus_point)
        normalized_distance = distance / max(self.focus_point, 1 - self.focus_point)
        blur = self.max_blur * normalized_distance
        props['blur'] = props.get('blur', 0) + blur
        return props


@dataclass
class PulseBlur(Effect):
    """Pulsing blur effect."""
    max_blur: float = 5
    pulses: int = 2

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        import math
        progress = self.get_progress(t)
        pulse = abs(math.sin(progress * math.pi * self.pulses))
        blur = self.max_blur * pulse * (1 - progress)  # Decay over time
        props['blur'] = props.get('blur', 0) + blur
        return props


# ============================================================================
# SHADOW AND GLOW EFFECTS
# ============================================================================

@dataclass
class ShadowIn(Effect):
    """Fade in a drop shadow."""
    offset: tuple = (4, 4)  # x, y offset
    blur: float = 8
    color: tuple = (0, 0, 0)
    max_alpha: float = 0.5

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['shadow_offset'] = self.offset
        props['shadow_blur'] = self.blur
        props['shadow_color'] = self.color
        props['shadow_alpha'] = self.max_alpha * progress
        return props


@dataclass
class ShadowOut(Effect):
    """Fade out a drop shadow."""
    offset: tuple = (4, 4)
    blur: float = 8
    color: tuple = (0, 0, 0)
    max_alpha: float = 0.5

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['shadow_offset'] = self.offset
        props['shadow_blur'] = self.blur
        props['shadow_color'] = self.color
        props['shadow_alpha'] = self.max_alpha * (1 - progress)
        return props


@dataclass
class ShadowPulse(Effect):
    """Pulsing shadow for emphasis."""
    offset: tuple = (4, 4)
    min_blur: float = 4
    max_blur: float = 12
    color: tuple = (0, 0, 0)
    alpha: float = 0.5
    pulses: int = 2

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        import math
        progress = self.get_progress(t)
        pulse = abs(math.sin(progress * math.pi * self.pulses))
        blur = self.min_blur + (self.max_blur - self.min_blur) * pulse

        props['shadow_offset'] = self.offset
        props['shadow_blur'] = blur
        props['shadow_color'] = self.color
        props['shadow_alpha'] = self.alpha
        return props


@dataclass
class GlowIn(Effect):
    """Fade in a glow effect."""
    radius: float = 10
    color: tuple = (255, 255, 255)
    max_alpha: float = 0.6

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['glow_radius'] = self.radius
        props['glow_color'] = self.color
        props['glow_alpha'] = self.max_alpha * progress
        return props


@dataclass
class GlowOut(Effect):
    """Fade out a glow effect."""
    radius: float = 10
    color: tuple = (255, 255, 255)
    max_alpha: float = 0.6

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['glow_radius'] = self.radius
        props['glow_color'] = self.color
        props['glow_alpha'] = self.max_alpha * (1 - progress)
        return props


@dataclass
class GlowPulse(Effect):
    """Pulsing glow for emphasis (like neon sign)."""
    min_radius: float = 5
    max_radius: float = 15
    color: tuple = (255, 200, 100)
    min_alpha: float = 0.3
    max_alpha: float = 0.8
    pulses: int = 3

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        import math
        progress = self.get_progress(t)
        pulse = abs(math.sin(progress * math.pi * self.pulses))

        props['glow_radius'] = self.min_radius + (self.max_radius - self.min_radius) * pulse
        props['glow_color'] = self.color
        props['glow_alpha'] = self.min_alpha + (self.max_alpha - self.min_alpha) * pulse
        return props


@dataclass
class Highlight(Effect):
    """Quick highlight flash (glow that fades)."""
    radius: float = 15
    color: tuple = (255, 255, 200)
    peak_alpha: float = 0.8

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        # Quick rise, slow fall
        if progress < 0.2:
            alpha = (progress / 0.2) * self.peak_alpha
        else:
            alpha = self.peak_alpha * (1 - (progress - 0.2) / 0.8)

        props['glow_radius'] = self.radius
        props['glow_color'] = self.color
        props['glow_alpha'] = max(0, alpha)
        return props


# ============================================================================
# TEXT ANNOTATION EFFECTS
# ============================================================================

@dataclass
class Underline(Effect):
    """Animated underline/highlighter reveal under text."""
    color: tuple = (255, 220, 100)  # Highlighter yellow
    thickness: int = 8
    offset_y: int = 5  # Below text baseline
    style: str = "line"  # "line" or "highlight" (thicker, semi-transparent)

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['underline_progress'] = progress
        props['underline_color'] = self.color
        props['underline_thickness'] = self.thickness
        props['underline_offset'] = self.offset_y
        props['underline_style'] = self.style
        return props


@dataclass
class Strikethrough(Effect):
    """Animated strikethrough line crossing out text."""
    color: tuple = (255, 80, 80)  # Red strike
    thickness: int = 4

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['strikethrough_progress'] = progress
        props['strikethrough_color'] = self.color
        props['strikethrough_thickness'] = self.thickness
        return props


@dataclass
class CircleAnnotation(Effect):
    """Draw animated circle around an element."""
    color: tuple = (255, 100, 100)
    thickness: int = 4
    padding: int = 20  # Space around element
    style: str = "circle"  # "circle" or "ellipse"

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['circle_progress'] = progress
        props['circle_color'] = self.color
        props['circle_thickness'] = self.thickness
        props['circle_padding'] = self.padding
        props['circle_style'] = self.style
        return props


@dataclass
class ArrowPoint(Effect):
    """Animated arrow pointing to element."""
    color: tuple = (255, 200, 100)
    direction: str = "left"  # Which side arrow comes from: left, right, top, bottom
    size: int = 40  # Arrow head size
    offset: int = 50  # Distance from element

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['arrow_progress'] = progress
        props['arrow_color'] = self.color
        props['arrow_direction'] = self.direction
        props['arrow_size'] = self.size
        props['arrow_offset'] = self.offset
        return props


# ============================================================================
# CINEMATIC EFFECTS
# ============================================================================

@dataclass
class Letterbox(Effect):
    """Animate cinematic letterbox bars in/out."""
    bar_height: float = 0.12  # Percentage of screen height per bar
    color: tuple = (0, 0, 0)
    mode: str = "in"  # "in" (bars appear) or "out" (bars disappear)

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        if self.mode == "out":
            progress = 1 - progress
        props['letterbox_progress'] = progress
        props['letterbox_height'] = self.bar_height
        props['letterbox_color'] = self.color
        return props


@dataclass
class Scanlines(Effect):
    """CRT/VHS retro scanline effect."""
    line_spacing: int = 4  # Pixels between scanlines
    opacity: float = 0.3
    moving: bool = True  # Whether lines scroll
    speed: float = 50  # Pixels per second if moving

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['scanlines_active'] = True
        props['scanlines_spacing'] = self.line_spacing
        props['scanlines_opacity'] = self.opacity * progress
        props['scanlines_moving'] = self.moving
        props['scanlines_offset'] = (t * self.speed) % self.line_spacing if self.moving else 0
        return props


@dataclass
class ColorTint(Effect):
    """Apply color overlay/tint to element."""
    color: tuple = (255, 200, 150)  # Warm sepia-ish
    intensity: float = 0.3  # 0-1, how strong the tint
    mode: str = "in"  # "in", "out", or "hold"

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        if self.mode == "out":
            intensity = self.intensity * (1 - progress)
        elif self.mode == "in":
            intensity = self.intensity * progress
        else:
            intensity = self.intensity

        props['tint_color'] = self.color
        props['tint_intensity'] = intensity
        return props


@dataclass
class VHSEffect(Effect):
    """VHS tape distortion effect."""
    noise_intensity: float = 0.1
    color_bleed: float = 3  # RGB channel offset
    tracking_lines: bool = True

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        import random
        progress = self.get_progress(t)

        props['vhs_active'] = True
        props['vhs_noise'] = self.noise_intensity * progress
        props['vhs_color_bleed'] = int(self.color_bleed * progress)
        props['vhs_tracking'] = self.tracking_lines
        # Random tracking glitch
        if self.tracking_lines and random.random() < 0.1:
            props['vhs_tracking_offset'] = random.randint(-5, 5)
        return props


# ============================================================================
# DRAWING/PATH EFFECTS
# ============================================================================

@dataclass
class DrawLine(Effect):
    """Animate drawing a line from point A to point B."""
    start_point: tuple = (0, 0)  # (x, y) as pixels or percentages
    end_point: tuple = (100, 100)
    color: tuple = (255, 255, 255)
    thickness: int = 3
    use_percentage: bool = False  # If True, points are 0-1 percentages

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        props['draw_line_progress'] = progress
        props['draw_line_start'] = self.start_point
        props['draw_line_end'] = self.end_point
        props['draw_line_color'] = self.color
        props['draw_line_thickness'] = self.thickness
        props['draw_line_percentage'] = self.use_percentage
        return props


@dataclass
class DrawBox(Effect):
    """Animate drawing a box around an area."""
    color: tuple = (255, 200, 100)
    thickness: int = 3
    padding: int = 10

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.get_progress(t)
        # Box draws in 4 segments (top, right, bottom, left)
        props['draw_box_progress'] = progress
        props['draw_box_color'] = self.color
        props['draw_box_thickness'] = self.thickness
        props['draw_box_padding'] = self.padding
        return props


# ============================================================================
# SEQUENCING EFFECTS
# ============================================================================

@dataclass
class Loop(Effect):
    """Repeat an inner effect N times."""
    inner_effect: Effect = None
    iterations: int = 3

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        if self.inner_effect is None:
            return props

        # Calculate which iteration we're in and progress within it
        progress = self.get_progress(t)
        iteration_duration = self.duration / self.iterations
        current_iteration = int(progress * self.iterations)
        iteration_progress = (progress * self.iterations) % 1.0

        # Create a modified inner effect with adjusted timing
        inner_t = self.start + iteration_progress * iteration_duration
        return self.inner_effect.apply(inner_t, props)


@dataclass
class Sequence(Effect):
    """Chain multiple effects in sequence."""
    effects: list = None  # List of Effect objects

    def __post_init__(self):
        if self.effects is None:
            self.effects = []

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        if not self.effects:
            return props

        progress = self.get_progress(t)
        num_effects = len(self.effects)
        effect_duration = self.duration / num_effects

        # Find which effect is active
        effect_index = min(int(progress * num_effects), num_effects - 1)
        effect_progress = (progress * num_effects) % 1.0

        # Apply the active effect
        effect = self.effects[effect_index]
        # Temporarily adjust effect timing
        original_start = effect.start
        original_duration = effect.duration
        effect.start = 0
        effect.duration = 1.0

        # Calculate effective time within effect
        effect_t = effect_progress
        result = effect.apply(effect_t, props)

        # Restore original timing
        effect.start = original_start
        effect.duration = original_duration

        return result


@dataclass
class Delay(Effect):
    """Delay before an effect starts (useful in sequences)."""

    def apply(self, t: float, props: Dict[str, Any]) -> Dict[str, Any]:
        # Delay does nothing - it's just a timing placeholder
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

    @staticmethod
    def bounce_in(start: float = 0.0, duration: float = 0.8) -> list:
        """Bouncy entrance - playful reveal."""
        return [
            FadeIn(start=start, duration=duration * 0.5),
            Bounce(start=start, duration=duration, easing="linear"),
        ]

    @staticmethod
    def shake_attention(start: float = 0.0, duration: float = 0.5) -> list:
        """Shake for attention/warning."""
        return [
            Shake(start=start, duration=duration, intensity=8, frequency=25),
        ]

    @staticmethod
    def dramatic_number(start: float = 0.0, duration: float = 1.5,
                        from_val: float = 0, to_val: float = 100,
                        prefix: str = "", suffix: str = "") -> list:
        """Dramatic number count-up with scale."""
        return [
            FadeIn(start=start, duration=0.3),
            ScaleIn(start=start, duration=0.5, from_scale=0.8, easing="ease_out_back"),
            CountUp(start=start, duration=duration, from_value=from_val,
                   to_value=to_val, prefix=prefix, suffix=suffix, easing="ease_out_cubic"),
        ]

    @staticmethod
    def glitch_reveal(start: float = 0.0, duration: float = 0.8) -> list:
        """Glitchy digital reveal."""
        return [
            FadeIn(start=start, duration=duration * 0.3),
            Glitch(start=start, duration=duration, intensity=15),
        ]

    @staticmethod
    def typewriter(start: float = 0.0, duration: float = 2.0) -> list:
        """Classic typewriter text reveal."""
        return [
            TypeWriter(start=start, duration=duration, easing="linear"),
        ]

    @staticmethod
    def flash_emphasis(start: float = 0.0, duration: float = 0.4, flashes: int = 2) -> list:
        """Quick flash for emphasis."""
        return [
            Flash(start=start, duration=duration, flashes=flashes),
        ]
