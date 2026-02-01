"""
Ken Burns effect renderer.

Creates zoom/pan animations on static images:
- Slow zoom in (documentary staple)
- Slow zoom out
- Pan across image

Animation: Gradual zoom with optional pan
"""

from typing import Tuple, Optional, Union
from pathlib import Path
import numpy as np
from PIL import Image
import math

from ..base import BaseRenderer, Timeline
from ..easing import Easing


class KenBurnsRenderer(BaseRenderer):
    """
    Render Ken Burns zoom/pan effect on images.

    Usage:
        renderer = KenBurnsRenderer(
            image_path="photo.jpg",
            zoom_start=1.0,
            zoom_end=1.2,
            pan_direction="right"
        )
        renderer.render("output.mp4", duration=6.0)
    """

    def __init__(
        self,
        image_path: str,
        # Zoom settings
        zoom_start: float = 1.0,
        zoom_end: float = 1.15,
        # Pan settings (optional)
        pan_direction: str = None,  # "left", "right", "up", "down"
        pan_amount: float = 0.1,  # Percentage of image to pan
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (0, 0, 0),
        # Timing
        fps: int = 30,
        easing: str = "ease_in_out_cubic",
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        self.image_path = image_path
        self.zoom_start = zoom_start
        self.zoom_end = zoom_end
        self.pan_direction = pan_direction
        self.pan_amount = pan_amount
        self.easing = easing

        # Load and prepare image
        self._load_image()

    def _load_image(self):
        """Load and prepare the source image."""
        img = Image.open(self.image_path).convert('RGB')

        # Calculate scaling to cover the canvas at max zoom
        max_zoom = max(self.zoom_start, self.zoom_end)
        img_aspect = img.width / img.height
        canvas_aspect = self.width / self.height

        if img_aspect > canvas_aspect:
            # Image is wider - scale by height
            scale = (self.height * max_zoom * 1.2) / img.height
        else:
            # Image is taller - scale by width
            scale = (self.width * max_zoom * 1.2) / img.width

        new_width = int(img.width * scale)
        new_height = int(img.height * scale)

        self.source_image = img.resize((new_width, new_height), Image.LANCZOS)

    def render_frame(self, t: float) -> np.ndarray:
        """Render a single frame with Ken Burns effect."""
        # Calculate progress with easing
        progress = t / self.timeline.duration
        easing_func = Easing.get(self.easing)
        eased_progress = easing_func(progress)

        # Calculate current zoom level
        current_zoom = self.zoom_start + (self.zoom_end - self.zoom_start) * eased_progress

        # Calculate crop size based on zoom
        crop_width = int(self.width / current_zoom)
        crop_height = int(self.height / current_zoom)

        # Calculate center position (with optional pan)
        center_x = self.source_image.width // 2
        center_y = self.source_image.height // 2

        # Apply pan if specified
        if self.pan_direction:
            pan_offset = self.pan_amount * eased_progress

            if self.pan_direction == "left":
                center_x += int(self.source_image.width * pan_offset / 2)
            elif self.pan_direction == "right":
                center_x -= int(self.source_image.width * pan_offset / 2)
            elif self.pan_direction == "up":
                center_y += int(self.source_image.height * pan_offset / 2)
            elif self.pan_direction == "down":
                center_y -= int(self.source_image.height * pan_offset / 2)

        # Calculate crop box
        left = max(0, center_x - crop_width // 2)
        top = max(0, center_y - crop_height // 2)
        right = min(self.source_image.width, left + crop_width)
        bottom = min(self.source_image.height, top + crop_height)

        # Adjust if we hit edges
        if right - left < crop_width:
            left = max(0, right - crop_width)
        if bottom - top < crop_height:
            top = max(0, bottom - crop_height)

        # Crop and resize to canvas
        cropped = self.source_image.crop((left, top, right, bottom))
        frame = cropped.resize((self.width, self.height), Image.LANCZOS)

        # Apply global fade
        global_alpha = self.timeline.get_global_alpha(t)
        if global_alpha < 1.0:
            # Blend with background
            bg = Image.new('RGB', (self.width, self.height), self.bg_color)
            frame = Image.blend(bg, frame, global_alpha)

        return np.array(frame)


def render_ken_burns(
    image_path: str,
    output_path: str = "ken_burns.mp4",
    duration: float = 6.0,
    zoom_start: float = 1.0,
    zoom_end: float = 1.15,
    pan_direction: str = None,
    **style_kwargs,
) -> str:
    """Render Ken Burns effect on an image."""
    renderer = KenBurnsRenderer(
        image_path,
        zoom_start=zoom_start,
        zoom_end=zoom_end,
        pan_direction=pan_direction,
        **style_kwargs
    )
    return renderer.render(output_path, duration=duration)
