"""Animated line-chart scene renderer.

Progressively draws a line through a series of (label, value) points, with
segments coloured green where the line rises and red where it falls, a leading
dot, a value readout that follows the dot, and x-axis labels that appear as the
line passes them. Built for the classic finance beat: a market index rising,
crashing, then rallying.

Like KenBurnsRenderer, this overrides frame composition directly (the chart is
custom per-frame drawing rather than discrete Elements), and supports the
transparent/compositing path via `render_frame_rgba`.
"""
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

from ..base import BaseRenderer
from ..easing import Easing


class LineChartRenderer(BaseRenderer):
    """Render an animated line chart from a list of (label, value) points."""

    def __init__(
        self,
        points: Sequence[Tuple[str, float]],
        title: Optional[str] = None,
        value_prefix: str = "",
        value_suffix: str = "",
        draw_duration: Optional[float] = None,
        up_color: Tuple[int, int, int] = (80, 220, 120),
        down_color: Tuple[int, int, int] = (255, 80, 80),
        axis_color: Tuple[int, int, int] = (70, 70, 82),
        label_color: Tuple[int, int, int] = (175, 175, 188),
        title_color: Tuple[int, int, int] = (235, 235, 242),
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        bg_color: Tuple[int, int, int] = (15, 15, 20),
        title_font: str = "C:/Windows/Fonts/arialbd.ttf",
        label_font: str = "C:/Windows/Fonts/arial.ttf",
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)
        self.points = list(points)
        self.labels = [str(p[0]) for p in self.points]
        self.values = [float(p[1]) for p in self.points]
        self.title = title
        self.value_prefix = value_prefix
        self.value_suffix = value_suffix
        self.draw_duration = draw_duration
        self.up_color = up_color
        self.down_color = down_color
        self.axis_color = axis_color
        self.label_color = label_color
        self.title_color = title_color
        self.title_font = title_font
        self.label_font = label_font

        # Plot area margins
        self.m_left = 190
        self.m_right = 150
        self.m_top = 230 if title else 150
        self.m_bottom = 150

    # --- coordinate helpers ---
    def _plot_box(self):
        return (self.m_left, self.m_top,
                self.width - self.m_right, self.height - self.m_bottom)

    def _coords(self) -> List[Tuple[float, float]]:
        x0, y0, x1, y1 = self._plot_box()
        n = len(self.values)
        vmin, vmax = min(self.values), max(self.values)
        span = (vmax - vmin) or 1.0
        pad = span * 0.12
        vmin -= pad
        vmax += pad
        span = vmax - vmin
        pts = []
        for i, v in enumerate(self.values):
            x = x0 + (i / max(1, n - 1)) * (x1 - x0)
            y = y1 - ((v - vmin) / span) * (y1 - y0)
            pts.append((x, y))
        return pts

    def _fmt(self, v: float) -> str:
        return f"{self.value_prefix}{int(round(v)):,}{self.value_suffix}"

    @staticmethod
    def _seg_color(v_from, v_to, up, down):
        return up if v_to >= v_from else down

    def _draw(self, t: float, transparent: bool) -> Image.Image:
        w, h = self.width, self.height
        content = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(content)
        coords = self._coords()
        n = len(coords)
        x0, y0, x1, y1 = self._plot_box()

        dur = self.timeline.duration
        draw_dur = self.draw_duration or max(1.0, dur * 0.7)
        p = Easing.ease_out_cubic(min(1.0, t / draw_dur)) if draw_dur > 0 else 1.0
        pos = p * (n - 1)
        last = int(np.floor(pos))
        frac = pos - last
        last = min(last, n - 1)

        # baseline axis
        d.line([(x0, y1), (x1, y1)], fill=self.axis_color + (255,), width=3)

        # x-axis labels revealed as the line passes
        lf = self.get_font(self.label_font, 34)
        for i, (cx, _) in enumerate(coords):
            if i <= pos + 1e-6:
                txt = self.labels[i]
                bb = d.textbbox((0, 0), txt, font=lf)
                d.text((cx - (bb[2] - bb[0]) / 2, y1 + 22), txt,
                       font=lf, fill=self.label_color + (255,))

        # full segments
        def thick_line(a, b, color, width=8):
            d.line([a, b], fill=color + (255,), width=width)
            r = width / 2
            for c in (a, b):
                d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=color + (255,))

        for i in range(min(last, n - 1)):
            col = self._seg_color(self.values[i], self.values[i + 1], self.up_color, self.down_color)
            thick_line(coords[i], coords[i + 1], col)

        # partial trailing segment + leading point
        if last < n - 1:
            a = coords[last]
            b = coords[last + 1]
            cur = (a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac)
            col = self._seg_color(self.values[last], self.values[last + 1], self.up_color, self.down_color)
            thick_line(a, cur, col)
            cur_val = self.values[last] + (self.values[last + 1] - self.values[last]) * frac
            cur_col = col
        else:
            cur = coords[-1]
            cur_val = self.values[-1]
            cur_col = self._seg_color(self.values[-2], self.values[-1], self.up_color, self.down_color) if n >= 2 else self.up_color

        # leading dot
        r = 13
        d.ellipse([cur[0] - r, cur[1] - r, cur[0] + r, cur[1] + r], fill=(255, 255, 255, 255))
        d.ellipse([cur[0] - r + 4, cur[1] - r + 4, cur[0] + r - 4, cur[1] + r - 4], fill=cur_col + (255,))

        # value readout following the dot
        vf = self.get_font(self.title_font, 64)
        vtxt = self._fmt(cur_val)
        vb = d.textbbox((0, 0), vtxt, font=vf)
        vw, vh = vb[2] - vb[0], vb[3] - vb[1]
        vx = min(max(cur[0] - vw / 2, x0), x1 - vw)
        vy = cur[1] - vh - 38
        if vy < y0:
            vy = cur[1] + 24
        d.text((vx, vy), vtxt, font=vf, fill=cur_col + (255,))

        # title
        if self.title:
            tf = self.get_font(self.title_font, 56)
            tb = d.textbbox((0, 0), self.title, font=tf)
            d.text(((w - (tb[2] - tb[0])) / 2, 70), self.title,
                   font=tf, fill=self.title_color + (255,))

        # global fade in/out
        ga = self.timeline.get_global_alpha(t)
        if ga < 0.999:
            alpha = content.split()[3].point(lambda a: int(a * ga))
            content.putalpha(alpha)

        if transparent:
            return content
        base = Image.new("RGBA", (w, h), self.bg_color + (255,))
        base.alpha_composite(content)
        return base

    def render_frame(self, t: float) -> np.ndarray:
        return np.array(self._draw(t, transparent=False).convert("RGB"))

    def render_frame_rgba(self, t: float) -> np.ndarray:
        return np.array(self._draw(t, transparent=True))


def render_line_chart(points, output_path: str, title: Optional[str] = None,
                      duration: float = 6.0, **kwargs) -> str:
    """Render an animated line chart to a video file."""
    return LineChartRenderer(points, title=title, **kwargs).render(output_path, duration=duration)
