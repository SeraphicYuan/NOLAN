import React, { useMemo } from "react";
import { interpolate, spring } from "remotion";
import rough from "roughjs";

// Annotation primitives for the lift-and-place tier (PaperFigure et al). All
// frame-driven and deterministic — no time-based libs. Three reusable mechanics:
//   • useKenBurns  — zoom/pan a held graphic toward a focus region (guided read)
//   • SketchBox    — a SEEDED hand-drawn rough.js box that draws on (stroke-dash)
//   • Spotlight    — an SVG mask that dims everything except the focus region
// Coordinates are fractions (0..1) of the container box.

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export type Region = { x: number; y: number; w: number; h: number };

/** Zoom-to-region: returns transform + origin that pushes in toward `region`
 *  while `active`, easing back to 1 when not. `prog` is a 0..1 entrance ramp. */
export function useKenBurns(active: boolean, region: Region | null, prog: number, maxScale = 1.25) {
  if (!region) return { transform: "scale(1)", transformOrigin: "50% 50%" } as const;
  const cx = (region.x + region.w / 2) * 100;
  const cy = (region.y + region.h / 2) * 100;
  // scale so the region roughly fills ~70% of the frame, capped at maxScale.
  const fit = Math.min(maxScale, 0.7 / Math.max(region.w, region.h, 0.001));
  const s = interpolate(active ? prog : 0, [0, 1], [1, fit], clamp);
  return { transform: `scale(${s})`, transformOrigin: `${cx}% ${cy}%` } as const;
}

/** Deterministic hand-drawn rectangle as SVG path-d strings (fixed seed). */
const gen = rough.generator();
function roughRectPaths(w: number, h: number, seed: number, roughness = 1.3): string[] {
  const d = gen.rectangle(3, 3, Math.max(1, w - 6), Math.max(1, h - 6), {
    seed, roughness, strokeWidth: 2.4, bowing: 1.4,
  });
  return gen.toPaths(d).map((p) => p.d);
}

/** A seeded sketch box that draws on as `draw` goes 0→1 (stroke-dashoffset). */
export const SketchBox: React.FC<{
  w: number; h: number; draw: number; seed?: number; color?: string;
}> = ({ w, h, draw, seed = 7, color = "var(--accent)" }) => {
  const paths = useMemo(() => roughRectPaths(w, h, seed), [w, h, seed]);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
      {paths.map((d, i) => (
        <path
          key={i} d={d} fill="none" stroke={color} strokeWidth={2.4} strokeLinecap="round"
          pathLength={1} strokeDasharray={1}
          strokeDashoffset={interpolate(draw, [0, 1], [1, 0], clamp)}
          style={{ filter: "drop-shadow(0 0 6px var(--accent-glow))" }}
        />
      ))}
    </svg>
  );
};

/** Dim-the-rest: a full-cover scrim with a soft rectangular hole over `region`.
 *  `amount` (0..1) ramps the dim; null region → no dim. SVG mask, deterministic. */
export const Spotlight: React.FC<{ region: Region | null; amount: number; id: string }> = ({ region, amount, id }) => {
  if (!region || amount <= 0.001) return null;
  // percentages within the 0..100 viewBox
  const pad = 1.5;
  const rx = Math.max(0, region.x * 100 - pad), ry = Math.max(0, region.y * 100 - pad);
  const rw = Math.min(100, region.w * 100 + pad * 2), rh = Math.min(100, region.h * 100 + pad * 2);
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
      <defs>
        <mask id={`spot-${id}`}>
          <rect x="0" y="0" width="100" height="100" fill="white" />
          <rect x={rx} y={ry} width={rw} height={rh} rx="2" fill="black" />
        </mask>
        <filter id={`soft-${id}`}><feGaussianBlur stdDeviation="0.6" /></filter>
      </defs>
      <rect x="0" y="0" width="100" height="100" fill="#15171c"
        opacity={interpolate(amount, [0, 1], [0, 0.5], clamp)}
        mask={`url(#spot-${id})`} filter={`url(#soft-${id})`} />
    </svg>
  );
};
