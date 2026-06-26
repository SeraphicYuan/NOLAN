"""Animated loop / feedback-cycle diagram renderer.

Places labelled nodes evenly around a circle and draws curved arrows between them
forming a cycle, revealing node-by-node then arrow-by-arrow. Built for systemic
arguments ("X feeds Y feeds Z feeds back to X") that a side-by-side comparison
can't express.

Custom per-frame drawing (like LineChartRenderer / KenBurnsRenderer); supports the
transparent/compositing path via render_frame_rgba.
"""
import math
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

from ..base import BaseRenderer
from ..easing import Easing


class LoopDiagramRenderer(BaseRenderer):
    def __init__(
        self,
        nodes: Sequence[str],
        title: Optional[str] = None,
        center_label: Optional[str] = None,
        draw_duration: Optional[float] = None,
        node_fill: Tuple[int, int, int] = (28, 30, 38),
        node_border: Tuple[int, int, int] = (90, 160, 255),
        node_text: Tuple[int, int, int] = (240, 240, 245),
        arrow_color: Tuple[int, int, int] = (220, 60, 60),
        title_color: Tuple[int, int, int] = (235, 235, 242),
        center_color: Tuple[int, int, int] = (150, 150, 160),
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        bg_color: Tuple[int, int, int] = (12, 12, 16),
        title_font: str = "C:/Windows/Fonts/arialbd.ttf",
        node_font: str = "C:/Windows/Fonts/arialbd.ttf",
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)
        self.nodes = [str(n) for n in nodes]
        self.title = title
        self.center_label = center_label
        self.draw_duration = draw_duration
        self.node_fill = node_fill
        self.node_border = node_border
        self.node_text = node_text
        self.arrow_color = arrow_color
        self.title_color = title_color
        self.center_color = center_color
        self.title_font = title_font
        self.node_font = node_font
        self.node_w, self.node_h, self.node_r = 330, 110, 26

    def _geom(self):
        cx, cy = self.width / 2, self.height / 2 + 40
        radius = min(self.width, self.height) * 0.33
        n = len(self.nodes)
        angles = [-math.pi / 2 + i * 2 * math.pi / n for i in range(n)]
        centers = [(cx + radius * math.cos(a), cy + radius * math.sin(a)) for a in angles]
        return cx, cy, radius, angles, centers

    def _draw_node(self, d, center, label, alpha_scale):
        x, y = center
        x0, y0 = x - self.node_w / 2, y - self.node_h / 2
        x1, y1 = x + self.node_w / 2, y + self.node_h / 2
        a = int(255 * alpha_scale)
        d.rounded_rectangle([x0, y0, x1, y1], radius=self.node_r,
                            fill=self.node_fill + (a,), outline=self.node_border + (a,), width=4)
        size = self.fit_font_size(label, self.node_font, 38, int(self.node_w - 36), min_size=20)
        f = self.get_font(self.node_font, size)
        bb = d.textbbox((0, 0), label, font=f)
        d.text((x - (bb[2] - bb[0]) / 2, y - (bb[3] - bb[1]) / 2 - bb[1]), label,
               font=f, fill=self.node_text + (a,))

    def _draw_arrow(self, d, cx, cy, radius, a_from, a_to, frac):
        """Curved arrow along the circle from node a_from to a_to, revealed by frac (0..1)."""
        gap = 0.34  # radians of clearance near each node
        start, end = a_from + gap, a_to - gap
        if end < start:
            end += 2 * math.pi
        end = start + (end - start) * max(0.0, min(1.0, frac))
        steps = 26
        pts = []
        for k in range(steps + 1):
            a = start + (end - start) * k / steps
            pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
        if len(pts) >= 2:
            d.line(pts, fill=self.arrow_color + (255,), width=7, joint="curve")
            # arrowhead at the leading end, along the tangent (clockwise)
            tip = pts[-1]
            ta = end + math.pi / 2  # tangent direction
            size = 22
            left = (tip[0] - size * math.cos(ta - 0.4), tip[1] - size * math.sin(ta - 0.4))
            right = (tip[0] - size * math.cos(ta + 0.4), tip[1] - size * math.sin(ta + 0.4))
            d.polygon([tip, left, right], fill=self.arrow_color + (255,))

    def _draw(self, t: float, transparent: bool) -> Image.Image:
        content = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        d = ImageDraw.Draw(content)
        cx, cy, radius, angles, centers = self._geom()
        n = len(self.nodes)

        dur = self.timeline.duration
        draw_dur = self.draw_duration or max(1.0, dur * 0.75)
        p = Easing.ease_out_cubic(min(1.0, t / draw_dur)) if draw_dur > 0 else 1.0
        steps = 2 * n               # node, arrow, node, arrow, ...
        revealed = p * steps

        # arrows first (behind nodes)
        for i in range(n):
            arrow_step = 2 * i + 1
            if revealed > arrow_step:
                frac = min(1.0, revealed - arrow_step)
                self._draw_arrow(d, cx, cy, radius, angles[i], angles[(i + 1) % n], frac)
        # nodes
        for i in range(n):
            node_step = 2 * i
            if revealed > node_step:
                ascale = min(1.0, revealed - node_step)
                self._draw_node(d, centers[i], self.nodes[i], ascale)

        if self.center_label:
            f = self.get_font(self.title_font, 40)
            bb = d.textbbox((0, 0), self.center_label, font=f)
            d.text((cx - (bb[2] - bb[0]) / 2, cy - (bb[3] - bb[1]) / 2 - bb[1]),
                   self.center_label, font=f, fill=self.center_color + (255,))
        if self.title:
            tf = self.get_font(self.title_font, 56)
            tb = d.textbbox((0, 0), self.title, font=tf)
            d.text(((self.width - (tb[2] - tb[0])) / 2, 60), self.title,
                   font=tf, fill=self.title_color + (255,))

        ga = self.timeline.get_global_alpha(t)
        if ga < 0.999:
            content.putalpha(content.split()[3].point(lambda a: int(a * ga)))
        if transparent:
            return content
        base = Image.new("RGBA", (self.width, self.height), self.bg_color + (255,))
        base.alpha_composite(content)
        return base

    def render_frame(self, t: float) -> np.ndarray:
        return np.array(self._draw(t, transparent=False).convert("RGB"))

    def render_frame_rgba(self, t: float) -> np.ndarray:
        return np.array(self._draw(t, transparent=True))


def render_loop_diagram(nodes, output_path: str, title: Optional[str] = None,
                        duration: float = 7.0, **kwargs) -> str:
    return LoopDiagramRenderer(nodes, title=title, **kwargs).render(output_path, duration=duration)
