"""
Base renderer classes for animated scene rendering.

The rendering system is built around:
- Element: A visual component (text, shape, image)
- Timeline: Manages global timing (fade in/out)
- BaseRenderer: Orchestrates elements and produces video
- Position: Layout system for element positioning
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Union
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .effects import Effect, FadeIn, FadeOut
from .easing import lerp_color
from .layout import Position, POSITIONS, resolve_position as layout_resolve


@dataclass
class Element:
    """
    A visual element in the scene.

    Elements have properties that can be animated via effects:
    - position (x, y) or Position object
    - alpha (transparency)
    - scale
    - color

    Position can be specified as:
    - 'center' (default): auto-center element
    - Pixel values: x=100, y=200
    - Position object: position=Position.from_preset("lower-third")
    - Preset name: position="lower-third"
    """
    id: str
    element_type: str  # 'text', 'rectangle', 'image'

    # Position (can use 'center', pixel values, or Position object)
    x: Any = 'center'
    y: Any = 'center'
    position: Optional[Union[str, Position]] = None  # Named preset or Position object

    # Visual properties
    color: Tuple = (255, 255, 255)
    alpha: float = 1.0
    visible: bool = True

    # Text-specific
    text: str = ""
    font_path: str = None
    font_size: int = 48
    font_bold: bool = False

    # Rectangle-specific
    width: int = 0
    height: int = 0

    # Effects
    effects: List[Effect] = field(default_factory=list)

    def add_effect(self, effect: Effect) -> 'Element':
        """Add an animation effect to this element."""
        self.effects.append(effect)
        return self

    def add_effects(self, effects: List[Effect]) -> 'Element':
        """Add multiple effects."""
        self.effects.extend(effects)
        return self

    def get_props_at(self, t: float) -> Dict[str, Any]:
        """Get element properties at time t, with effects applied."""
        props = {
            'x': self.x,
            'y': self.y,
            'position': self.position,  # Position object or preset name
            'color': self.color,
            'alpha': self.alpha,
            'text': self.text,
            'font_size': self.font_size,
            'width': self.width,
            'height': self.height,
            'x_offset': 0,
            'y_offset': 0,
            'scale': 1.0,
            'width_scale': 1.0,
            'visible_text': self.text,
        }

        # Apply each effect
        for effect in self.effects:
            props = effect.apply(t, props)

        return props


@dataclass
class Timeline:
    """
    Global timeline for the scene.

    Manages overall timing like fade in/out from black.
    """
    duration: float = 7.0
    fade_in_duration: float = 0.8
    fade_out_duration: float = 1.0

    def get_global_alpha(self, t: float) -> float:
        """Get global fade alpha at time t."""
        # Fade in
        if t < self.fade_in_duration:
            from .easing import Easing
            progress = t / self.fade_in_duration
            return Easing.ease_out_cubic(progress)

        # Fade out
        fade_out_start = self.duration - self.fade_out_duration
        if t > fade_out_start:
            from .easing import Easing
            progress = (t - fade_out_start) / self.fade_out_duration
            return 1 - Easing.ease_in_out_cubic(progress)

        return 1.0


class BaseRenderer:
    """
    Base class for animated scene renderers.

    Subclasses define elements and their animations.
    The base class handles frame generation and video encoding.
    """

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        bg_color: Tuple[int, int, int] = (26, 26, 26),
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.bg_color = bg_color

        self.elements: List[Element] = []
        self.timeline = Timeline()

        # Font cache
        self._font_cache: Dict[str, ImageFont.FreeTypeFont] = {}

    def add_element(self, element: Element) -> Element:
        """Add an element to the scene."""
        self.elements.append(element)
        return element

    def get_font(self, path: str, size: int) -> ImageFont.FreeTypeFont:
        """Get font with caching."""
        key = f"{path}:{size}"
        if key not in self._font_cache:
            try:
                self._font_cache[key] = ImageFont.truetype(path, size)
            except OSError:
                # Fallback to default
                self._font_cache[key] = ImageFont.truetype(
                    "C:/Windows/Fonts/arial.ttf", size
                )
        return self._font_cache[key]

    def resolve_position(
        self,
        x: Any,
        y: Any,
        element_width: int,
        element_height: int,
        position: Optional[Union[str, Position, Dict]] = None,
    ) -> Tuple[int, int]:
        """
        Resolve position to pixel coordinates.

        Supports:
        - Position object or preset name (highest priority)
        - 'center' keyword for x or y
        - Direct pixel values

        Args:
            x: X position (pixel, 'center', or ignored if position is set)
            y: Y position (pixel, 'center', or ignored if position is set)
            element_width: Width of element for alignment
            element_height: Height of element for alignment
            position: Optional Position object, preset name, or dict

        Returns:
            Tuple of (x, y) pixel coordinates
        """
        # If position object/preset is provided, use layout system
        if position is not None:
            return layout_resolve(
                position,
                self.width,
                self.height,
                element_width,
                element_height
            )

        # Legacy: handle 'center' keyword
        if x == 'center':
            x = (self.width - element_width) // 2
        if y == 'center':
            y = (self.height - element_height) // 2

        return int(x), int(y)

    def render_element(
        self,
        draw: ImageDraw.ImageDraw,
        element: Element,
        props: Dict[str, Any],
        global_alpha: float,
    ):
        """Render a single element to the draw context."""
        if not element.visible:
            return

        alpha = props['alpha'] * global_alpha
        if alpha <= 0:
            return

        if element.element_type == 'text':
            self._render_text(draw, element, props, alpha)
        elif element.element_type == 'rectangle':
            self._render_rectangle(draw, element, props, alpha)

    def _render_text(
        self,
        draw: ImageDraw.ImageDraw,
        element: Element,
        props: Dict[str, Any],
        alpha: float,
    ):
        """Render text element."""
        text = props.get('visible_text', props['text'])
        if not text:
            return

        font_path = element.font_path or "C:/Windows/Fonts/arialbd.ttf"
        font_size = int(props['font_size'] * props.get('scale', 1.0))
        font = self.get_font(font_path, font_size)

        # Get text size
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Resolve position (supports Position objects)
        x, y = self.resolve_position(
            props['x'], props['y'],
            text_width, text_height,
            position=props.get('position')
        )

        # Apply offsets
        x += int(props.get('x_offset', 0))
        y += int(props.get('y_offset', 0))

        # Blend color with background for alpha effect
        base_color = props.get('color', element.color)
        blended_color = lerp_color(self.bg_color, base_color, alpha)

        draw.text((x, y), text, fill=blended_color, font=font)

    def _render_rectangle(
        self,
        draw: ImageDraw.ImageDraw,
        element: Element,
        props: Dict[str, Any],
        alpha: float,
    ):
        """Render rectangle element."""
        width = int(props['width'] * props.get('width_scale', 1.0))
        height = props['height']

        if width <= 0 or height <= 0:
            return

        # Resolve position (supports Position objects)
        full_width = props['width']
        x, y = self.resolve_position(
            props['x'], props['y'],
            full_width, height,
            position=props.get('position')
        )

        # Center the scaled rectangle
        x += (full_width - width) // 2
        x += int(props.get('x_offset', 0))
        y += int(props.get('y_offset', 0))

        # Blend color
        base_color = props.get('color', element.color)
        blended_color = lerp_color(self.bg_color, base_color, alpha)

        draw.rectangle([(x, y), (x + width, y + height)], fill=blended_color)

    def render_frame(self, t: float) -> np.ndarray:
        """Render a single frame at time t."""
        img = Image.new('RGB', (self.width, self.height), self.bg_color)
        draw = ImageDraw.Draw(img)

        global_alpha = self.timeline.get_global_alpha(t)

        for element in self.elements:
            props = element.get_props_at(t)
            self.render_element(draw, element, props, global_alpha)

        return np.array(img)

    def render(
        self,
        output_path: str,
        duration: float = None,
        with_qa: bool = True,
    ) -> str:
        """
        Render the animation to a video file.

        Args:
            output_path: Output video file path
            duration: Override timeline duration
            with_qa: Run quality protocol validation

        Returns:
            Path to rendered video
        """
        from moviepy import VideoClip

        if duration:
            self.timeline.duration = duration

        total_frames = int(self.timeline.duration * self.fps)
        print(f"Rendering {total_frames} frames at {self.fps}fps...")

        # Pre-render all frames
        frames = []
        for frame_idx in range(total_frames):
            t = frame_idx / self.fps
            frames.append(self.render_frame(t))

        # Create video
        def make_frame(t):
            frame_idx = min(int(t * self.fps), len(frames) - 1)
            return frames[frame_idx]

        clip = VideoClip(make_frame, duration=self.timeline.duration)

        print(f"Encoding video to {output_path}...")
        clip.write_videofile(
            output_path,
            fps=self.fps,
            codec="libx264",
            audio=False,
            preset="medium",
            threads=4,
        )

        # Quality check
        if with_qa:
            self._run_quality_check(output_path)

        print(f"Done! Video saved to: {output_path}")
        return output_path

    def _run_quality_check(self, video_path: str):
        """Run quality protocol validation."""
        try:
            from nolan.quality import QualityProtocol, QAConfig

            config = QAConfig(
                check_properties=True,
                check_visual=True,
                check_text=False,
            )
            qa = QualityProtocol(config)

            result = qa.validate(
                video_path=video_path,
                expected_duration=self.timeline.duration,
                expected_resolution=(self.width, self.height),
            )

            if result.passed:
                print("[QA] PASSED - All quality checks passed")
            else:
                print(f"[QA] WARNING - {len(result.issues)} issues found")
                for issue in result.issues:
                    print(f"  - {issue}")

        except ImportError:
            print("[QA] Skipped - quality module not available")
