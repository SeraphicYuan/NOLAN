"""
Flashback/Historical effect renderer.

Creates vintage/flashback effects on images:
- Black & white with vignette
- Sepia tones
- Film grain overlay
- Aged/vintage look

Animation: Fade in with desaturation effect
"""

from typing import Tuple, Optional
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw

from ..base import BaseRenderer, Timeline
from ..easing import Easing


class FlashbackRenderer(BaseRenderer):
    """
    Render flashback/vintage effect on images.

    Usage:
        renderer = FlashbackRenderer(
            image_path="photo.jpg",
            style="sepia",  # "bw", "sepia", "vintage"
            vignette=True,
            grain=0.1
        )
        renderer.render("output.mp4", duration=5.0)
    """

    def __init__(
        self,
        image_path: str,
        # Effect settings
        style: str = "sepia",  # "bw", "sepia", "vintage"
        vignette: bool = True,
        vignette_strength: float = 0.6,
        grain: float = 0.05,  # 0-1, grain intensity
        contrast: float = 1.1,
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (0, 0, 0),
        # Optional text overlay
        year_text: str = None,
        year_color: Tuple[int, int, int] = (255, 255, 255),
        year_size: int = 120,
        # Timing
        fps: int = 30,
        easing: str = "ease_in_out_cubic",
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        self.image_path = image_path
        self.style = style
        self.vignette = vignette
        self.vignette_strength = vignette_strength
        self.grain = grain
        self.contrast = contrast
        self.year_text = year_text
        self.year_color = year_color
        self.year_size = year_size
        self.easing = easing

        # Load and process image
        self._load_image()
        self._create_vignette_mask()

    def _load_image(self):
        """Load and apply flashback effects to image."""
        img = Image.open(self.image_path).convert('RGB')

        # Resize to cover canvas
        img_aspect = img.width / img.height
        canvas_aspect = self.width / self.height

        if img_aspect > canvas_aspect:
            new_height = self.height
            new_width = int(self.height * img_aspect)
        else:
            new_width = self.width
            new_height = int(self.width / img_aspect)

        img = img.resize((new_width, new_height), Image.LANCZOS)

        # Center crop
        left = (new_width - self.width) // 2
        top = (new_height - self.height) // 2
        img = img.crop((left, top, left + self.width, top + self.height))

        # Apply style
        if self.style == "bw":
            img = img.convert('L').convert('RGB')
        elif self.style == "sepia":
            img = self._apply_sepia(img)
        elif self.style == "vintage":
            img = self._apply_vintage(img)

        # Adjust contrast
        if self.contrast != 1.0:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(self.contrast)

        self.processed_image = img

    def _apply_sepia(self, img: Image.Image) -> Image.Image:
        """Apply sepia tone effect."""
        # Convert to grayscale first
        gray = img.convert('L')
        # Apply sepia tint
        sepia_r = gray.point(lambda x: min(255, x * 1.1))
        sepia_g = gray.point(lambda x: min(255, x * 0.9))
        sepia_b = gray.point(lambda x: min(255, x * 0.7))
        return Image.merge('RGB', (sepia_r, sepia_g, sepia_b))

    def _apply_vintage(self, img: Image.Image) -> Image.Image:
        """Apply vintage color grading."""
        # Slight desaturation
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(0.7)
        # Warm tint
        r, g, b = img.split()
        r = r.point(lambda x: min(255, x * 1.05))
        b = b.point(lambda x: max(0, x * 0.9))
        return Image.merge('RGB', (r, g, b))

    def _create_vignette_mask(self):
        """Create vignette mask for overlay."""
        if not self.vignette:
            self.vignette_mask = None
            return

        # Create radial gradient mask
        mask = Image.new('L', (self.width, self.height), 255)
        draw = ImageDraw.Draw(mask)

        center_x, center_y = self.width // 2, self.height // 2
        max_radius = int(((self.width ** 2 + self.height ** 2) ** 0.5) / 2)

        for r in range(max_radius, 0, -1):
            # Calculate alpha based on distance from center
            progress = r / max_radius
            if progress > 0.5:
                alpha = int(255 * (1 - (progress - 0.5) * 2 * self.vignette_strength))
            else:
                alpha = 255

            draw.ellipse(
                [center_x - r, center_y - r, center_x + r, center_y + r],
                fill=alpha
            )

        self.vignette_mask = mask

    def _add_grain(self, img: Image.Image, intensity: float) -> Image.Image:
        """Add film grain effect."""
        if intensity <= 0:
            return img

        arr = np.array(img, dtype=np.float32)
        noise = np.random.normal(0, intensity * 50, arr.shape)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        return Image.fromarray(arr)

    def render_frame(self, t: float) -> np.ndarray:
        """Render a single frame with flashback effects."""
        frame = self.processed_image.copy()

        # Add grain (varies slightly per frame for realistic effect)
        if self.grain > 0:
            frame = self._add_grain(frame, self.grain)

        # Apply vignette
        if self.vignette_mask:
            black = Image.new('RGB', (self.width, self.height), (0, 0, 0))
            frame = Image.composite(frame, black, self.vignette_mask)

        # Add year text if specified
        if self.year_text:
            draw = ImageDraw.Draw(frame)
            font = self.get_font("C:/Windows/Fonts/arialbd.ttf", self.year_size)
            bbox = draw.textbbox((0, 0), self.year_text, font=font)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) // 2
            y = self.height // 2 - self.year_size // 2

            # Calculate fade for text
            global_alpha = self.timeline.get_global_alpha(t)
            if t < 1.0:
                text_alpha = min(1.0, t / 0.8)
            else:
                text_alpha = 1.0
            text_alpha *= global_alpha

            # Draw text with alpha
            color = tuple(int(c * text_alpha) for c in self.year_color)
            draw.text((x, y), self.year_text, fill=color, font=font)

        # Apply global fade
        global_alpha = self.timeline.get_global_alpha(t)
        if global_alpha < 1.0:
            bg = Image.new('RGB', (self.width, self.height), self.bg_color)
            frame = Image.blend(bg, frame, global_alpha)

        return np.array(frame)


def render_flashback(
    image_path: str,
    output_path: str = "flashback.mp4",
    duration: float = 5.0,
    style: str = "sepia",
    year_text: str = None,
    **style_kwargs,
) -> str:
    """Render flashback effect on an image."""
    renderer = FlashbackRenderer(
        image_path,
        style=style,
        year_text=year_text,
        **style_kwargs
    )
    return renderer.render(output_path, duration=duration)
