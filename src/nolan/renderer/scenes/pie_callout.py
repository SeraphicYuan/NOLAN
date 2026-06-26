"""
Pie/donut callout renderer.

A 5-beat data-reveal motion built for highlighting a single proportion:

  1. A big donut chart fades/scales in, centered.
  2. It scales down and slides to its resting spot (left by default).
  3. The target slice (sized by ``percentage``) is drawn in an accent colour,
     sweeping into place.
  4. The coloured slice ejects outward along its own bisector (exploded slice).
  5. An info text block (title + body) slides in from the right.

The pie's resting location is controllable via ``pie_center``.

Usage:
    renderer = PieCalloutRenderer(
        percentage=0.0017,
        info_title="0.0017%",
        info_text="of every 30 million people are affected. A vanishingly small slice.",
        slice_label="Affected",
    )
    renderer.render("pie.mp4", duration=6.5)
"""

import math
from typing import Tuple, Optional

import numpy as np
from PIL import Image, ImageDraw

from ..base import BaseRenderer
from ..easing import Easing, lerp_color
from ..text_layout import TextLayout


def _fmt_pct(value: float) -> str:
    """Format a percentage compactly: 0.0017 -> '0.0017%', 23.0 -> '23%'."""
    return f"{value:g}%"


class PieCalloutRenderer(BaseRenderer):
    """Animated donut/pie callout for a single highlighted proportion."""

    def __init__(
        self,
        percentage: float,
        info_text: str = "",
        info_title: Optional[str] = None,
        slice_label: Optional[str] = None,
        # Layout
        width: int = 1920,
        height: int = 1080,
        pie_center: Tuple[float, float] = (0.30, 0.52),  # resting (small) centre, fractions
        big_center: Tuple[float, float] = (0.5, 0.5),    # intro (big) centre
        big_radius_frac: float = 0.34,   # of height
        small_radius_frac: float = 0.22,
        # Style
        donut: bool = True,
        hole_ratio: float = 0.58,
        bg_color: Tuple[int, int, int] = (244, 242, 237),
        track_color: Tuple[int, int, int] = (206, 206, 213),
        slice_color: Tuple[int, int, int] = (37, 99, 235),
        title_color: Optional[Tuple[int, int, int]] = None,  # defaults to slice_color
        text_color: Tuple[int, int, int] = (32, 32, 42),
        label_color: Tuple[int, int, int] = (120, 120, 132),
        # Geometry
        start_angle: float = -90.0,   # 12 o'clock; PIL: 0=3 o'clock, +=clockwise
        explode_frac: float = 0.16,   # eject distance as fraction of radius
        show_center_value: bool = True,
        # Typography
        title_font: str = "C:/Windows/Fonts/arialbd.ttf",
        body_font: str = "C:/Windows/Fonts/arial.ttf",
        label_font: str = "C:/Windows/Fonts/arial.ttf",
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        self.percentage = max(0.0, float(percentage))
        self.info_text = info_text
        self.info_title = info_title if info_title is not None else _fmt_pct(self.percentage)
        self.slice_label = slice_label

        self.pie_center = pie_center
        self.big_center = big_center
        self.big_radius_frac = big_radius_frac
        self.small_radius_frac = small_radius_frac

        self.donut = donut
        self.hole_ratio = hole_ratio if donut else 0.0
        self.track_color = track_color
        self.slice_color = slice_color
        self.title_color = title_color if title_color is not None else slice_color
        self.text_color = text_color
        self.label_color = label_color

        self.start_angle = start_angle
        self.explode_frac = explode_frac
        self.show_center_value = show_center_value

        self.title_font = title_font
        self.body_font = body_font
        self.label_font = label_font

        # Sweep angle of the highlighted slice (clamped to a full turn).
        self.slice_sweep = min(360.0, self.percentage / 100.0 * 360.0)

        # Quick entry fade and a short exit tail, so the settled composition
        # (slice + text) holds at full opacity before fading out.
        self.timeline.fade_in_duration = 0.5
        self.timeline.fade_out_duration = 0.6

    # -- timing helpers -------------------------------------------------------

    def _phase(self, t: float, t0: float, t1: float, easing: str = "ease_in_out_cubic") -> float:
        """Eased 0..1 progress of a phase spanning fractions [t0, t1] of duration."""
        dur = self.timeline.duration
        p = (t / dur - t0) / max(1e-6, (t1 - t0))
        p = min(1.0, max(0.0, p))
        return Easing.get(easing)(p)

    # -- drawing helpers ------------------------------------------------------

    def _annular_sector(self, size, center, R, r, a0, a1, color):
        """Return an RGBA layer with a filled annular sector (donut wedge)."""
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        cx, cy = center
        d.pieslice([cx - R, cy - R, cx + R, cy + R], a0, a1, fill=color + (255,))
        if r > 0:
            d.pieslice([cx - r, cy - r, cx + r, cy + r], a0, a1, fill=(0, 0, 0, 0))
        return layer

    # -- frame ---------------------------------------------------------------

    def render_frame(self, t: float) -> np.ndarray:
        ga = self.timeline.get_global_alpha(t)
        img = Image.new("RGB", (self.width, self.height), self.bg_color)
        draw = ImageDraw.Draw(img)

        # Phase progresses (fractions of duration). Beats finish by ~0.72 so the
        # settled slice + text hold before the global fade-out tail.
        intro = self._phase(t, 0.00, 0.12, "ease_out_cubic")     # fade/scale in
        shrink = self._phase(t, 0.16, 0.34)                       # big -> small + move
        reveal = self._phase(t, 0.34, 0.52, "ease_out_cubic")     # slice sweeps in
        explode = self._phase(t, 0.50, 0.64, "ease_out_back")     # slice ejects
        text_in = self._phase(t, 0.56, 0.72, "ease_out_cubic")    # text slides in

        # Donut geometry (interpolate centre + radius from big -> resting)
        bx = self.big_center[0] + (self.pie_center[0] - self.big_center[0]) * shrink
        by = self.big_center[1] + (self.pie_center[1] - self.big_center[1]) * shrink
        cx, cy = self.width * bx, self.height * by
        R = self.height * (self.big_radius_frac
                           + (self.small_radius_frac - self.big_radius_frac) * shrink)
        # Scale-in on intro
        R *= (0.6 + 0.4 * intro)
        r = R * self.hole_ratio

        track = lerp_color(self.bg_color, self.track_color, intro * ga)
        draw.ellipse([cx - R, cy - R, cx + R, cy + R], fill=track)
        if r > 0:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=self.bg_color)

        # Highlighted slice: sweep then explode along its bisector.
        if reveal > 0 and self.slice_sweep > 0:
            a0 = self.start_angle
            a1 = a0 + self.slice_sweep * reveal
            bis = math.radians(a0 + self.slice_sweep / 2.0)
            dist = R * self.explode_frac * explode
            ex, ey = math.cos(bis) * dist, math.sin(bis) * dist
            sl_color = lerp_color(self.bg_color, self.slice_color, ga)
            sector = self._annular_sector(
                img.size, (cx + ex, cy + ey), R, r, a0, a1, tuple(sl_color))
            img.paste(Image.alpha_composite(img.convert("RGBA"), sector).convert("RGB"), (0, 0))
            draw = ImageDraw.Draw(img)

        # Center value inside the donut hole.
        if self.show_center_value and self.donut and reveal > 0:
            cv = lerp_color(self.bg_color, self.slice_color, reveal * ga)
            fsize = int(r * 0.42)
            if fsize >= 8:
                font = self.get_font(self.title_font, fsize)
                txt = _fmt_pct(self.percentage)
                bb = draw.textbbox((0, 0), txt, font=font)
                draw.text((cx - (bb[2] - bb[0]) / 2, cy - (bb[3] - bb[1]) / 2 - bb[1]),
                          txt, fill=tuple(cv), font=font)

        # Info text block on the right, sliding in from further right.
        if text_in > 0:
            self._draw_text_block(draw, text_in, ga)

        return np.array(img)

    def _draw_text_block(self, draw, prog, ga):
        block_x = int(self.width * 0.52)
        block_w = int(self.width * 0.40)
        slide = int((1 - prog) * 70)  # ease in from the right
        x = block_x + slide
        y = int(self.height * 0.34)
        alpha = prog * ga

        if self.slice_label:
            lf = self.get_font(self.label_font, int(self.height * 0.026))
            lc = lerp_color(self.bg_color, self.label_color, alpha)
            draw.text((x, y), self.slice_label.upper(), fill=tuple(lc), font=lf)
            y += int(self.height * 0.05)

        tf = self.get_font(self.title_font, int(self.height * 0.072))
        tc = lerp_color(self.bg_color, self.title_color, alpha)
        draw.text((x, y), self.info_title, fill=tuple(tc), font=tf)
        tb = draw.textbbox((0, 0), self.info_title, font=tf)
        y += (tb[3] - tb[1]) + int(self.height * 0.04)

        if self.info_text:
            bsize = int(self.height * 0.032)
            layout = TextLayout(text=self.info_text, font_path=self.body_font,
                                font_size=bsize, max_width=block_w, max_lines=6)
            bf = self.get_font(self.body_font, layout.final_font_size)
            bc = lerp_color(self.bg_color, self.text_color, alpha)
            for i, line in enumerate(layout.lines):
                draw.text((x, y + i * layout.line_height), line, fill=tuple(bc), font=bf)


def render_pie_callout(percentage: float, info_text: str = "",
                       output_path: str = "pie_callout.mp4",
                       duration: float = 6.5, **kwargs) -> str:
    """Render an animated pie/donut callout for a single proportion."""
    renderer = PieCalloutRenderer(percentage, info_text=info_text, **kwargs)
    return renderer.render(output_path, duration=duration)
