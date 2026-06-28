// SHARED procedural path generators used by multiple effects.
// All randomness is seeded via Remotion's `random()` so paths are stable across
// frames (Math.random would flicker).
import {random} from 'remotion';

// Line from (x0,y0)->(x1,y1) with a small seeded perpendicular wobble that tapers
// to 0 at both ends. jitter=0 yields a clean straight line.
export const jaggedPath = (
  x0: number, y0: number, x1: number, y1: number,
  segments: number, jitter: number, seed: string,
): string => {
  const dx = x1 - x0, dy = y1 - y0;
  const len = Math.hypot(dx, dy) || 1;
  const px = -dy / len, py = dx / len;
  let d = `M ${x0} ${y0}`;
  for (let i = 1; i <= segments; i++) {
    const t = i / segments;
    const bx = x0 + dx * t, by = y0 + dy * t;
    const taper = Math.sin(Math.PI * t);
    const r = (random(`${seed}-${i}`) - 0.5) * 2 * jitter * taper;
    d += ` L ${(bx + px * r).toFixed(1)} ${(by + py * r).toFixed(1)}`;
  }
  return d;
};

// Closed, hand-drawn ("scribble") ellipse — a seeded radial wobble around an
// ellipse, optionally rotated. Used by the annotation effects' shapeStyle.
export const scribbleEllipse = (
  cx: number, cy: number, rx: number, ry: number,
  seed: string, jitter = 12, points = 44, rotDeg = 0,
): string => {
  const rad = (rotDeg * Math.PI) / 180;
  const cos = Math.cos(rad), sin = Math.sin(rad);
  const j = jitter / Math.max(rx, ry);
  let d = '';
  for (let i = 0; i <= points; i++) {
    const a = (i / points) * 2 * Math.PI;
    const k = 1 + (random(`${seed}-${i}`) - 0.5) * 2 * j;
    const x = Math.cos(a) * rx * k, y = Math.sin(a) * ry * k;
    const xr = x * cos - y * sin, yr = x * sin + y * cos;
    d += (i === 0 ? 'M' : ' L') + ` ${(cx + xr).toFixed(1)} ${(cy + yr).toFixed(1)}`;
  }
  return d;
};
