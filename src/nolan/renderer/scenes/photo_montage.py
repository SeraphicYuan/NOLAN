"""
Photo-montage scene renderer ("photos on a table").

Reproduces the documentary scrapbook effect: several historical stills laid out as
Polaroid-bordered cards (white frame + drop shadow, slight rotations) on a textured
dark surface, viewed through a slow Ken Burns camera glide, while one "hero" card
slides into frame and a handwritten caption writes in beneath it.

Composed from existing NOLAN building blocks:
- the Ken Burns camera math (crop+zoom+pan) from `ken_burns.py`,
- per-element drop-shadow / rotation compositing like `base.py`,
- a type-on caption reveal in a handwriting font.

Usage:
    PhotoMontageRenderer(
        hero={"image_path": "ieyasu.jpg", "caption": "Tokugawa Ieyasu"},
        cards=[{"image_path": "scroll.jpg", "x": 0.30, "y": 0.46, "rotation": -6}],
    ).render("out.mp4", duration=10.0)
"""

from typing import Tuple, Optional, List, Dict, Any
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..base import BaseRenderer
from ..easing import Easing


def _clamp01(v: float) -> float:
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


class PhotoMontageRenderer(BaseRenderer):
    """Render a 'photos on a table' montage with a sliding, captioned hero card."""

    def __init__(
        self,
        hero: Dict[str, Any],
        cards: Optional[List[Dict[str, Any]]] = None,
        background: Optional[str] = None,
        bg_color: Tuple[int, int, int] = (58, 18, 22),
        # camera (Ken Burns over the whole composite)
        zoom_start: float = 1.06,
        zoom_end: float = 1.18,
        pan_direction: str = "left",     # left|right|up|down
        pan_amount: float = 0.12,
        # hero animation
        slide_from: str = "right",       # left|right|up|down
        slide_duration: float = 0.45,    # fraction of total duration
        caption_delay: float = 0.45,     # fraction of total duration before caption writes
        caption_duration: float = 0.40,  # fraction of total duration to finish writing
        caption_font: str = "C:/Windows/Fonts/segoesc.ttf",  # handwriting; falls back to arial
        # look
        vignette: float = 0.5,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=tuple(bg_color))

        self.hero = dict(hero or {})
        self.cards = [dict(c) for c in (cards or [])]
        self.background = background
        self.zoom_start = float(zoom_start)
        self.zoom_end = float(zoom_end)
        self.pan_direction = pan_direction
        self.pan_amount = float(pan_amount)
        self.slide_from = self.hero.get("slide_from", slide_from)
        self.slide_duration = float(slide_duration)
        self.caption_delay = float(caption_delay)
        self.caption_duration = float(caption_duration)
        self.caption_font = caption_font
        self.vignette = float(vignette)

        # Build the static plate (table + settled cards) once; hero animates per frame.
        self._base = self._build_base()
        # Pre-resize the hero card core (constant size) so per-frame work stays cheap.
        hs = float(self.hero.get("scale", 0.46))
        self._hero_core = self._load_core(self.hero.get("image_path"), hs)

    # ---- image helpers -----------------------------------------------------
    def _load_core(self, image_path: Optional[str], scale: float) -> Image.Image:
        """Load an image and size its 'core' to `scale` * canvas-height (aspect kept).

        Alpha is preserved, so a pre-cut PNG (irregular subject cutout) composites with
        its true silhouette in `frame:"cutout"` mode.
        """
        core_h = max(40, int(self.height * scale))
        try:
            img = Image.open(image_path).convert("RGBA")
            aspect = img.width / img.height
        except Exception:  # noqa: BLE001 - missing/unreadable -> neutral placeholder
            aspect = 0.78
            img = Image.new("RGBA", (int(core_h * aspect), core_h), (120, 120, 125, 255))
        core_w = max(40, int(core_h * aspect))
        return img.resize((core_w, core_h), Image.LANCZOS)

    def _build_polaroid(self, core: Image.Image, caption: Optional[str],
                        reveal: float, frame: str = "polaroid") -> Image.Image:
        """Wrap `core` for display.

        frame="polaroid": white border + type-on caption in the bottom border.
        frame="cutout"/"none": the image as-is (keeps an irregular alpha silhouette) —
        the drop shadow in `_framed` then follows that silhouette automatically.
        """
        if frame in ("cutout", "none"):
            return core
        cw, ch = core.size
        side = max(14, int(cw * 0.07))
        top = side
        bottom = int(side * (2.7 if caption else 1.4))
        card = Image.new("RGBA", (cw + 2 * side, ch + top + bottom), (250, 249, 244, 255))
        card.paste(core, (side, top), core)

        if caption and reveal > 0:
            shown = caption[: max(0, int(round(len(caption) * _clamp01(reveal))))]
            if shown:
                font = self.get_font(self.caption_font, max(18, int(cw * 0.085)))
                draw = ImageDraw.Draw(card)
                bbox = draw.textbbox((0, 0), shown, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                tx = (card.width - tw) // 2 - bbox[0]
                ty = ch + top + (bottom - th) // 2 - bbox[1]
                draw.text((tx, ty), shown, fill=(46, 42, 48, 255), font=font)
        return card

    def _framed(self, card: Image.Image, rotation: float) -> Image.Image:
        """Add a soft drop shadow and rotate; card stays centred in the returned image."""
        blur, off = 16, (10, 14)
        pad = blur * 3 + max(off)
        canvas = Image.new("RGBA", (card.width + 2 * pad, card.height + 2 * pad), (0, 0, 0, 0))
        shadow = Image.new("RGBA", card.size, (0, 0, 0, 120))
        canvas.paste(shadow, (pad + off[0], pad + off[1]), card.split()[3])
        canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
        canvas.paste(card, (pad, pad), card.split()[3])
        if abs(rotation) > 0.1:
            canvas = canvas.rotate(-rotation, resample=Image.BICUBIC, expand=True)
        return canvas

    @staticmethod
    def _paste_centered(dst: Image.Image, src: Image.Image, cx: float, cy: float,
                        alpha: float = 1.0):
        """Alpha-composite `src` centred at (cx, cy); clips at canvas edges."""
        mask = src.split()[3]
        if alpha < 1.0:
            mask = mask.point(lambda p: int(p * _clamp01(alpha)))
        dst.paste(src, (int(cx - src.width / 2), int(cy - src.height / 2)), mask)

    def _build_base(self) -> Image.Image:
        """Background plate + settled cards, rendered once."""
        if self.background:
            try:
                bg = Image.open(self.background).convert("RGB").resize(
                    (self.width, self.height), Image.LANCZOS)
            except Exception:  # noqa: BLE001
                bg = Image.new("RGB", (self.width, self.height), self.bg_color)
        else:
            bg = Image.new("RGB", (self.width, self.height), self.bg_color)
        base = bg.convert("RGBA")

        # Radial vignette for a velvet-table feel.
        if self.vignette > 0:
            yy, xx = np.mgrid[0:self.height, 0:self.width]
            nx = (xx - self.width / 2) / (self.width / 2)
            ny = (yy - self.height / 2) / (self.height / 2)
            d = np.sqrt(nx * nx + ny * ny)
            v = np.clip((d - 0.5) / 0.7, 0, 1) ** 1.6 * self.vignette
            overlay = Image.fromarray((v * 255).astype(np.uint8), "L")
            shade = Image.new("RGBA", base.size, (0, 0, 0, 0))
            shade.putalpha(overlay)
            base.alpha_composite(shade)

        for c in self.cards:
            core = self._load_core(c.get("image_path"), float(c.get("scale", 0.42)))
            card = self._build_polaroid(core, c.get("caption"), 1.0,
                                        frame=c.get("frame", "polaroid"))
            framed = self._framed(card, float(c.get("rotation", 0)))
            self._paste_centered(base, framed,
                                 float(c.get("x", 0.5)) * self.width,
                                 float(c.get("y", 0.5)) * self.height)
        return base

    # ---- per-frame ---------------------------------------------------------
    def _composite_hero(self, frame: Image.Image, t: float):
        dur = self.timeline.duration
        ease_out = Easing.get("ease_out_cubic")
        slide_t = max(0.001, self.slide_duration * dur)
        p_in = ease_out(_clamp01(t / slide_t))

        hx = float(self.hero.get("x", 0.58)) * self.width
        hy = float(self.hero.get("y", 0.52)) * self.height
        reach = 0.30 * self.width
        dx = dy = 0.0
        if self.slide_from == "right":
            dx = reach * (1 - p_in)
        elif self.slide_from == "left":
            dx = -reach * (1 - p_in)
        elif self.slide_from == "up":
            dy = -reach * (1 - p_in)
        elif self.slide_from == "down":
            dy = reach * (1 - p_in)

        cap_start = self.caption_delay * dur
        cap_span = max(0.001, self.caption_duration * dur)
        reveal = _clamp01((t - cap_start) / cap_span)

        card = self._build_polaroid(self._hero_core, self.hero.get("caption"), reveal,
                                    frame=self.hero.get("frame", "polaroid"))
        framed = self._framed(card, float(self.hero.get("rotation", 0)))
        self._paste_centered(frame, framed, hx + dx, hy + dy, alpha=p_in)

    def render_frame(self, t: float) -> np.ndarray:
        frame = self._base.copy()
        self._composite_hero(frame, t)

        # Ken Burns camera: crop base/zoom, pan, resize back to full frame.
        eased = Easing.get("ease_in_out_cubic")(_clamp01(t / self.timeline.duration))
        zoom = self.zoom_start + (self.zoom_end - self.zoom_start) * eased
        cw, ch = int(self.width / zoom), int(self.height / zoom)
        cx, cy = self.width / 2, self.height / 2
        po = self.pan_amount * eased
        if self.pan_direction == "left":
            cx += self.width * po / 2
        elif self.pan_direction == "right":
            cx -= self.width * po / 2
        elif self.pan_direction == "up":
            cy += self.height * po / 2
        elif self.pan_direction == "down":
            cy -= self.height * po / 2
        left = int(min(max(0, cx - cw / 2), self.width - cw))
        top = int(min(max(0, cy - ch / 2), self.height - ch))
        view = frame.crop((left, top, left + cw, top + ch)).resize(
            (self.width, self.height), Image.LANCZOS).convert("RGB")

        # Global fade in/out (mirrors KenBurnsRenderer).
        ga = self.timeline.get_global_alpha(t)
        if ga < 1.0:
            view = Image.blend(Image.new("RGB", view.size, self.bg_color), view, ga)
        return np.array(view)


def render_photo_montage(
    hero: Dict[str, Any],
    output_path: str = "photo_montage.mp4",
    duration: float = 10.0,
    cards: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> str:
    """Render a photo-montage scene. Thin functional wrapper around the renderer."""
    return PhotoMontageRenderer(hero=hero, cards=cards, **kwargs).render(
        output_path, duration=duration)
