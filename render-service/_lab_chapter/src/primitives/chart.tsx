import React from "react";
import { interpolate } from "remotion";

// Shared chart primitives. The architecture (per the library-boost research):
// charts are GEOMETRY computed per frame, never self-animating components. We
// use d3/visx scale + shape generators for the math and drive every reveal from
// the Remotion frame ourselves (a left→right sweep clip, axes fading in first).
// Deterministic, SVG-native (crisp + clip-revealable), fully token-themeable.

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Format a number with optional grouping / decimals / prefix / suffix. */
export const fmtNum = (
  n: number,
  o: { prefix?: string; suffix?: string; decimals?: number; group?: boolean } = {},
): string =>
  `${o.prefix ?? ""}${n.toLocaleString("en-US", {
    minimumFractionDigits: o.decimals ?? 0,
    maximumFractionDigits: o.decimals ?? 0,
    useGrouping: o.group ?? true,
  })}${o.suffix ?? ""}`;

/** A left→right sweep clip — wrap data marks in `clipPath={url(#id)}` and they
 *  reveal as `progress` 0→1. Pad lets the leading edge clear stroke width. */
export const SweepClip: React.FC<{ id: string; width: number; height: number; progress: number }> = ({
  id, width, height, progress,
}) => (
  <defs>
    <clipPath id={id}>
      <rect x={0} y={-20} width={Math.max(0, width * progress)} height={height + 40} />
    </clipPath>
  </defs>
);

/** Themed Y/X axis ticks (lines + labels) from a scale's `.ticks()`. Drawn in
 *  data space; pass formatted tick labels. Axes fade in before the data sweeps. */
export const Axis: React.FC<{
  orientation: "left" | "bottom";
  scale: { ticks: (n?: number) => number[]; (v: number): number };
  length: number;              // pixel length of the OTHER dimension (grid line)
  tickCount?: number;
  format?: (v: number) => string;
  opacity?: number;
  grid?: boolean;
}> = ({ orientation, scale, length, tickCount = 5, format, opacity = 1, grid = true }) => {
  const ticks = scale.ticks(tickCount);
  return (
    <g opacity={opacity}>
      {ticks.map((t, i) => {
        const p = scale(t);
        const label = format ? format(t) : String(t);
        if (orientation === "left") {
          return (
            <g key={i} transform={`translate(0, ${p})`}>
              {grid ? <line x1={0} x2={length} stroke="var(--rule)" strokeWidth={1} opacity={0.5} /> : null}
              <text x={-12} y={4} textAnchor="end" fontFamily="var(--font-mono)" fontSize={15}
                fill="var(--text-mute)">{label}</text>
            </g>
          );
        }
        return (
          <g key={i} transform={`translate(${p}, 0)`}>
            <text y={length + 26} textAnchor="middle" fontFamily="var(--font-mono)" fontSize={15}
              fill="var(--text-mute)">{label}</text>
          </g>
        );
      })}
    </g>
  );
};

/** Reveal progress 0→1 for a chart that sweeps from `start` over `spanFrames`. */
export const sweepProgress = (frame: number, start: number, spanFrames: number): number =>
  interpolate(frame, [start, start + spanFrames], [0, 1], clamp);
