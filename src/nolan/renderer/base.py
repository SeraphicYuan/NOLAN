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
from PIL import Image, ImageDraw, ImageFont, ImageFilter

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
    max_width: int = 0  # 0 = no limit, auto-wrap if set
    max_lines: int = 0  # 0 = unlimited lines
    text_align: str = "center"  # "left", "center", "right"

    # Rectangle-specific
    width: int = 0
    height: int = 0

    # Transform properties
    rotation: float = 0  # Degrees, clockwise
    anchor: str = "center"  # Anchor point for transforms: center, top-left, etc.

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
            'rotation': self.rotation,
            'anchor': self.anchor,
            'blur': 0,  # Blur radius in pixels
            'shadow_offset': (0, 0),  # Shadow x, y offset
            'shadow_blur': 0,  # Shadow blur radius
            'shadow_color': (0, 0, 0),  # Shadow color
            'shadow_alpha': 0,  # Shadow opacity (0 = no shadow)
            'glow_radius': 0,  # Glow blur radius
            'glow_color': (255, 255, 255),  # Glow color
            'glow_alpha': 0,  # Glow opacity (0 = no glow)
            'visible_text': self.text,
            'max_width': self.max_width,
            'max_lines': self.max_lines,
            'text_align': self.text_align,
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

    def get_text_max_width(self, style: str = "default") -> int:
        """
        Get appropriate max width for text based on canvas size.

        Args:
            style: "default" (75%), "wide" (85%), "narrow" (60%), "quote" (70%)

        Returns:
            Max width in pixels
        """
        percentages = {
            "default": 0.75,
            "wide": 0.85,
            "narrow": 0.60,
            "quote": 0.70,
        }
        percent = percentages.get(style, 0.75)
        return int(self.width * percent)

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
        """Render text element with smart layout."""
        text = props.get('visible_text', props['text'])
        if not text:
            return

        font_path = element.font_path or "C:/Windows/Fonts/arialbd.ttf"
        base_font_size = int(props['font_size'] * props.get('scale', 1.0))
        max_width = props.get('max_width', 0)
        max_lines = props.get('max_lines', 0)
        text_align = props.get('text_align', 'center')

        # Blend color with background for alpha effect
        base_color = props.get('color', element.color)
        blended_color = lerp_color(self.bg_color, base_color, alpha)

        # If max_width is set, use smart text layout
        if max_width > 0:
            from .text_layout import TextLayout

            layout = TextLayout(
                text=text,
                font_path=font_path,
                font_size=base_font_size,
                max_width=max_width,
                max_lines=max_lines if max_lines > 0 else 0,
            )

            # Get font at final size
            font = self.get_font(font_path, layout.final_font_size)

            # Calculate base position for text block
            # Use first line width for rough centering
            if layout.lines:
                first_bbox = draw.textbbox((0, 0), layout.lines[0], font=font)
                block_width = max_width
                block_height = layout.total_height
            else:
                return

            # Resolve position for the text block
            x, y = self.resolve_position(
                props['x'], props['y'],
                block_width, block_height,
                position=props.get('position')
            )

            # Apply offsets
            x += int(props.get('x_offset', 0))
            y += int(props.get('y_offset', 0))

            # Adjust x for text alignment within block
            if text_align == 'center':
                block_center_x = x + block_width // 2
            elif text_align == 'right':
                block_center_x = x + block_width
            else:
                block_center_x = x

            # Render each line
            for i, line in enumerate(layout.lines):
                line_y = y + (i * layout.line_height)

                # Calculate line x based on alignment
                line_bbox = draw.textbbox((0, 0), line, font=font)
                line_width = line_bbox[2] - line_bbox[0]

                if text_align == 'center':
                    line_x = block_center_x - line_width // 2
                elif text_align == 'right':
                    line_x = block_center_x - line_width
                else:
                    line_x = block_center_x

                draw.text((line_x, line_y), line, fill=blended_color, font=font)
        else:
            # Original single-line rendering
            font = self.get_font(font_path, base_font_size)

            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            x, y = self.resolve_position(
                props['x'], props['y'],
                text_width, text_height,
                position=props.get('position')
            )

            x += int(props.get('x_offset', 0))
            y += int(props.get('y_offset', 0))

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

    def _render_element_transformed(
        self,
        main_img: Image.Image,
        element: Element,
        props: Dict[str, Any],
        global_alpha: float,
    ):
        """Render element with rotation/blur to a temp image and composite."""
        alpha = props['alpha'] * global_alpha
        if alpha <= 0:
            return

        rotation = props.get('rotation', 0)
        blur = props.get('blur', 0)

        # Estimate element size for temp canvas
        if element.element_type == 'text':
            text = props.get('visible_text', props['text'])
            if not text:
                return
            font_path = element.font_path or "C:/Windows/Fonts/arialbd.ttf"
            font_size = int(props['font_size'] * props.get('scale', 1.0))
            font = self.get_font(font_path, font_size)

            # Measure text
            temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            bbox = temp_draw.textbbox((0, 0), text, font=font)
            elem_width = bbox[2] - bbox[0] + 20
            elem_height = bbox[3] - bbox[1] + 20
        elif element.element_type == 'rectangle':
            elem_width = int(props['width'] * props.get('width_scale', 1.0)) + 20
            elem_height = props['height'] + 20
        else:
            return

        # Create temp canvas large enough for rotation + blur padding
        import math
        blur_padding = int(blur * 3) if blur > 0 else 0
        diagonal = int(math.sqrt(elem_width**2 + elem_height**2)) + 10 + blur_padding * 2
        temp_size = (diagonal, diagonal)
        temp_img = Image.new('RGBA', temp_size, (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_img)

        # Calculate center offset for drawing in temp image
        cx = diagonal // 2
        cy = diagonal // 2

        # Render element centered in temp image
        if element.element_type == 'text':
            text = props.get('visible_text', props['text'])
            font_path = element.font_path or "C:/Windows/Fonts/arialbd.ttf"
            font_size = int(props['font_size'] * props.get('scale', 1.0))
            font = self.get_font(font_path, font_size)
            bbox = temp_draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # Apply alpha to color
            base_color = props.get('color', element.color)
            color_with_alpha = base_color + (int(255 * alpha),)

            temp_draw.text(
                (cx - text_width // 2, cy - text_height // 2),
                text,
                fill=color_with_alpha,
                font=font
            )

        elif element.element_type == 'rectangle':
            width = int(props['width'] * props.get('width_scale', 1.0))
            height = props['height']
            base_color = props.get('color', element.color)
            color_with_alpha = base_color + (int(255 * alpha),)

            temp_draw.rectangle(
                [(cx - width // 2, cy - height // 2),
                 (cx + width // 2, cy + height // 2)],
                fill=color_with_alpha
            )

        # Apply blur if specified
        if blur > 0.1:
            temp_img = temp_img.filter(ImageFilter.GaussianBlur(radius=blur))

        # Rotate the temp image if specified
        if abs(rotation) > 0.1:
            temp_img = temp_img.rotate(-rotation, resample=Image.BICUBIC, expand=False)

        # Calculate final position on main canvas
        if element.element_type == 'text':
            elem_w, elem_h = text_width, text_height
        else:
            elem_w, elem_h = width, height

        x, y = self.resolve_position(
            props['x'], props['y'],
            elem_w, elem_h,
            position=props.get('position')
        )
        x += int(props.get('x_offset', 0))
        y += int(props.get('y_offset', 0))

        # Paste position (accounting for rotation/blur expansion)
        paste_x = x + elem_w // 2 - diagonal // 2
        paste_y = y + elem_h // 2 - diagonal // 2

        # Composite onto main image
        main_img.paste(temp_img, (int(paste_x), int(paste_y)), temp_img)

    def _render_shadow(
        self,
        main_img: Image.Image,
        element: Element,
        props: Dict[str, Any],
        global_alpha: float,
    ):
        """Render shadow layer for an element."""
        shadow_offset = props.get('shadow_offset', (0, 0))
        shadow_blur = props.get('shadow_blur', 0)
        shadow_color = props.get('shadow_color', (0, 0, 0))
        shadow_alpha = props.get('shadow_alpha', 0) * global_alpha

        if shadow_alpha <= 0:
            return

        # Create shadow props (shadow version of element)
        shadow_props = props.copy()
        shadow_props['color'] = shadow_color
        shadow_props['alpha'] = shadow_alpha
        shadow_props['blur'] = shadow_blur
        shadow_props['x_offset'] = props.get('x_offset', 0) + shadow_offset[0]
        shadow_props['y_offset'] = props.get('y_offset', 0) + shadow_offset[1]
        # Remove shadow from shadow to avoid recursion
        shadow_props['shadow_alpha'] = 0
        shadow_props['glow_alpha'] = 0

        # Render shadow using transformed method (handles blur)
        self._render_element_transformed(main_img, element, shadow_props, 1.0)

    def _render_glow(
        self,
        main_img: Image.Image,
        element: Element,
        props: Dict[str, Any],
        global_alpha: float,
    ):
        """Render glow layer for an element."""
        glow_radius = props.get('glow_radius', 0)
        glow_color = props.get('glow_color', (255, 255, 255))
        glow_alpha = props.get('glow_alpha', 0) * global_alpha

        if glow_alpha <= 0 or glow_radius <= 0:
            return

        # Create glow props (glow version of element)
        glow_props = props.copy()
        glow_props['color'] = glow_color
        glow_props['alpha'] = glow_alpha
        glow_props['blur'] = glow_radius
        # Remove glow/shadow from glow to avoid recursion
        glow_props['shadow_alpha'] = 0
        glow_props['glow_alpha'] = 0

        # Render glow using transformed method (handles blur)
        self._render_element_transformed(main_img, element, glow_props, 1.0)

    def _render_text_annotations(
        self,
        draw: ImageDraw.ImageDraw,
        element: Element,
        props: Dict[str, Any],
        global_alpha: float,
    ):
        """Render text annotations like underline, strikethrough, circle."""
        text = props.get('visible_text', props.get('text', ''))
        if not text:
            return

        # Get text dimensions for positioning
        font_path = element.font_path or "C:/Windows/Fonts/arialbd.ttf"
        font_size = int(props['font_size'] * props.get('scale', 1.0))
        font = self.get_font(font_path, font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Get text position
        x, y = self.resolve_position(
            props['x'], props['y'],
            text_width, text_height,
            position=props.get('position')
        )
        x += int(props.get('x_offset', 0))
        y += int(props.get('y_offset', 0))

        alpha = props.get('alpha', 1.0) * global_alpha

        # Underline effect
        underline_progress = props.get('underline_progress', 0)
        if underline_progress > 0:
            ul_color = props.get('underline_color', (255, 220, 100))
            ul_thickness = props.get('underline_thickness', 8)
            ul_offset = props.get('underline_offset', 5)
            ul_style = props.get('underline_style', 'line')

            line_y = y + text_height + ul_offset
            line_width = int(text_width * underline_progress)

            if ul_style == 'highlight':
                # Semi-transparent highlight bar
                highlight_color = ul_color + (int(150 * alpha),)
                highlight_img = Image.new('RGBA', (line_width, ul_thickness), highlight_color)
                # Note: Would need to composite onto main image
            else:
                # Simple line
                blended = tuple(int(c * alpha) for c in ul_color)
                draw.line([(x, line_y), (x + line_width, line_y)],
                         fill=blended, width=ul_thickness)

        # Strikethrough effect
        strike_progress = props.get('strikethrough_progress', 0)
        if strike_progress > 0:
            strike_color = props.get('strikethrough_color', (255, 80, 80))
            strike_thickness = props.get('strikethrough_thickness', 4)

            line_y = y + text_height // 2
            line_width = int(text_width * strike_progress)
            blended = tuple(int(c * alpha) for c in strike_color)
            draw.line([(x, line_y), (x + line_width, line_y)],
                     fill=blended, width=strike_thickness)

        # Circle annotation
        circle_progress = props.get('circle_progress', 0)
        if circle_progress > 0:
            circle_color = props.get('circle_color', (255, 100, 100))
            circle_thickness = props.get('circle_thickness', 4)
            circle_padding = props.get('circle_padding', 20)

            cx = x + text_width // 2
            cy = y + text_height // 2
            rx = text_width // 2 + circle_padding
            ry = text_height // 2 + circle_padding

            # Draw arc based on progress (0 to 360 degrees)
            end_angle = int(360 * circle_progress)
            blended = tuple(int(c * alpha) for c in circle_color)
            draw.arc(
                [(cx - rx, cy - ry), (cx + rx, cy + ry)],
                start=0, end=end_angle,
                fill=blended, width=circle_thickness
            )

        # Arrow annotation
        arrow_progress = props.get('arrow_progress', 0)
        if arrow_progress > 0:
            arrow_color = props.get('arrow_color', (255, 200, 100))
            arrow_direction = props.get('arrow_direction', 'left')
            arrow_size = props.get('arrow_size', 40)
            arrow_offset = props.get('arrow_offset', 50)

            # Arrow points TO the element from the specified direction
            # 'left' means arrow comes from the left, pointing right toward element
            text_center_y = y + text_height // 2
            text_center_x = x + text_width // 2
            gap = 15  # Gap between arrow tip and element

            if arrow_direction == 'left':
                # Arrow starts from left, points right toward element
                start_x = x - arrow_offset
                start_y = text_center_y
                end_x = x - gap
                end_y = text_center_y
            elif arrow_direction == 'right':
                # Arrow starts from right, points left toward element
                start_x = x + text_width + arrow_offset
                start_y = text_center_y
                end_x = x + text_width + gap
                end_y = text_center_y
            elif arrow_direction == 'top':
                # Arrow starts from top, points down toward element
                start_x = text_center_x
                start_y = y - arrow_offset
                end_x = text_center_x
                end_y = y - gap
            else:  # bottom
                # Arrow starts from bottom, points up toward element
                start_x = text_center_x
                start_y = y + text_height + arrow_offset
                end_x = text_center_x
                end_y = y + text_height + gap

            # Interpolate line based on progress
            current_end_x = start_x + (end_x - start_x) * arrow_progress
            current_end_y = start_y + (end_y - start_y) * arrow_progress

            blended = tuple(int(c * alpha) for c in arrow_color)

            # Draw the line
            draw.line([(int(start_x), int(start_y)), (int(current_end_x), int(current_end_y))],
                     fill=blended, width=4)

            # Draw arrowhead at the current end point
            if arrow_progress > 0.3:
                head_size = int(arrow_size * 0.5)
                head_width = int(head_size * 0.6)

                # Calculate arrowhead points based on direction
                if arrow_direction == 'left':
                    # Pointing right
                    draw.polygon([
                        (int(current_end_x), int(current_end_y)),
                        (int(current_end_x) - head_size, int(current_end_y) - head_width),
                        (int(current_end_x) - head_size, int(current_end_y) + head_width),
                    ], fill=blended)
                elif arrow_direction == 'right':
                    # Pointing left
                    draw.polygon([
                        (int(current_end_x), int(current_end_y)),
                        (int(current_end_x) + head_size, int(current_end_y) - head_width),
                        (int(current_end_x) + head_size, int(current_end_y) + head_width),
                    ], fill=blended)
                elif arrow_direction == 'top':
                    # Pointing down
                    draw.polygon([
                        (int(current_end_x), int(current_end_y)),
                        (int(current_end_x) - head_width, int(current_end_y) - head_size),
                        (int(current_end_x) + head_width, int(current_end_y) - head_size),
                    ], fill=blended)
                else:  # bottom
                    # Pointing up
                    draw.polygon([
                        (int(current_end_x), int(current_end_y)),
                        (int(current_end_x) - head_width, int(current_end_y) + head_size),
                        (int(current_end_x) + head_width, int(current_end_y) + head_size),
                    ], fill=blended)

    def _render_frame_effects(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        t: float,
        global_alpha: float,
    ):
        """Render frame-level effects like letterbox and scanlines."""
        # Check for any active frame effects from timeline or stored props
        # For now, these need to be set on a special frame_effects element
        for element in self.elements:
            if element.id == '_frame_effects':
                props = element.get_props_at(t)

                # Letterbox bars
                letterbox_progress = props.get('letterbox_progress', 0)
                if letterbox_progress > 0:
                    bar_height = props.get('letterbox_height', 0.12)
                    bar_color = props.get('letterbox_color', (0, 0, 0))
                    bar_px = int(self.height * bar_height * letterbox_progress)

                    # Top bar
                    draw.rectangle([(0, 0), (self.width, bar_px)], fill=bar_color)
                    # Bottom bar
                    draw.rectangle([(0, self.height - bar_px), (self.width, self.height)],
                                  fill=bar_color)

                # Scanlines
                if props.get('scanlines_active', False):
                    spacing = props.get('scanlines_spacing', 4)
                    opacity = props.get('scanlines_opacity', 0.3)
                    offset = int(props.get('scanlines_offset', 0))

                    scanline_color = (0, 0, 0, int(255 * opacity))
                    for y in range(offset, self.height, spacing):
                        # Draw semi-transparent black line
                        draw.line([(0, y), (self.width, y)], fill=(0, 0, 0), width=1)

    def render_frame(self, t: float) -> np.ndarray:
        """Render a single frame at time t."""
        img = Image.new('RGBA', (self.width, self.height), self.bg_color + (255,))
        draw = ImageDraw.Draw(img)

        global_alpha = self.timeline.get_global_alpha(t)

        for element in self.elements:
            props = element.get_props_at(t)
            rotation = props.get('rotation', 0)
            blur = props.get('blur', 0)
            shadow_alpha = props.get('shadow_alpha', 0)
            glow_alpha = props.get('glow_alpha', 0)

            # Render glow layer first (behind everything)
            if glow_alpha > 0.01:
                self._render_glow(img, element, props, global_alpha)

            # Render shadow layer (behind element)
            if shadow_alpha > 0.01:
                self._render_shadow(img, element, props, global_alpha)

            # Use special rendering for rotation or blur
            if abs(rotation) > 0.1 or blur > 0.1:
                self._render_element_transformed(img, element, props, global_alpha)
            else:
                self.render_element(draw, element, props, global_alpha)

            # Render text annotations (underline, strikethrough, etc.)
            if element.element_type == 'text':
                self._render_text_annotations(draw, element, props, global_alpha)

        # Render frame-level effects (letterbox, scanlines)
        self._render_frame_effects(img, draw, t, global_alpha)

        # Convert back to RGB for video encoding
        return np.array(img.convert('RGB'))

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
