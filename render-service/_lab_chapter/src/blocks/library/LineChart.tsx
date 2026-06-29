import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { scaleLinear } from "@visx/scale";
import { LinePath, AreaClosed } from "@visx/shape";
import { curveMonotoneX } from "@visx/curve";
import { Surface } from "../../Surface";
import { Axis, SweepClip, sweepProgress, fmtNum } from "../../primitives/chart";

// LineChart — line / area over a numeric axis (PnL curves, trends, time series).
// Geometry from visx/d3 scales; the reveal is a frame-driven left→right sweep we
// drive ourselves (axes fade in first, then the line draws across), with a
// leading-edge dot + live value readout. Deterministic, SVG, fully token-themed.
// Use for data we HAVE (redraw tier) — vs PaperFigure for un-redrawable figures.
type Word = { text: string; startFrame: number; endFrame: number };
type Pt = { x: number; y: number };
export type LineChartProps = {
  title?: string;
  caption?: string;
  series: { name?: string; points: Pt[]; color?: string }[];
  area?: boolean;                 // fill under the first series
  xPrefix?: string; xSuffix?: string; xDecimals?: number; xGroup?: boolean;
  yPrefix?: string; ySuffix?: string; yDecimals?: number;
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const W = 1180, H = 560;
const M = { top: 56, right: 64, bottom: 56, left: 96 };
const innerW = W - M.left - M.right;
const innerH = H - M.top - M.bottom;

const yAt = (pts: Pt[], xv: number): number => {
  if (xv <= pts[0].x) return pts[0].y;
  if (xv >= pts[pts.length - 1].x) return pts[pts.length - 1].y;
  for (let i = 1; i < pts.length; i++) {
    if (xv <= pts[i].x) {
      const a = pts[i - 1], b = pts[i];
      const t = (xv - a.x) / (b.x - a.x || 1);
      return a.y + t * (b.y - a.y);
    }
  }
  return pts[pts.length - 1].y;
};

export const LineChart: React.FC<LineChartProps> = ({
  title, caption, series, area = false,
  xPrefix, xSuffix, xDecimals = 0, xGroup = false, yPrefix, ySuffix, yDecimals = 0,
  revealFrames, words: _words, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const r0 = revealFrames[0] ?? 0;

  const allX = series.flatMap((s) => s.points.map((p) => p.x));
  const allY = series.flatMap((s) => s.points.map((p) => p.y));
  const xMin = Math.min(...allX), xMax = Math.max(...allX);
  const yMin = Math.min(...allY, 0), yMax = Math.max(...allY);
  const yPad = (yMax - yMin) * 0.08 || 1;
  const x = scaleLinear({ domain: [xMin, xMax], range: [0, innerW] });
  const y = scaleLinear({ domain: [yMin - yPad * 0.2, yMax + yPad], range: [innerH, 0] });

  const intro = spring({ frame: frame - r0, fps, durationInFrames: 20, config: { damping: 200 } });
  const titleOp = interpolate(frame - r0, [2, 16], [0, 1], clamp);
  const axisOp = interpolate(frame - r0, [8, 24], [0, 1], clamp);
  const prog = sweepProgress(frame, r0 + 10, Math.round(durationInFrames * 0.62));

  const primary = series[0];
  const edgeX = xMin + (xMax - xMin) * prog;
  const edgeY = yAt(primary.points, edgeX);

  return (
    <Surface>
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", gap: "var(--space-4)",
        opacity: interpolate(intro, [0, 1], [0, 1]), transform: `translateY(${interpolate(intro, [0, 1], [22, 0])}px)` }}>
        {title ? (
          <div style={{ opacity: titleOp, fontFamily: "var(--font-mono)", color: "var(--text-mute)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase", fontSize: "var(--t-micro)" }}>{title}</div>
        ) : null}

        <svg viewBox={`0 0 ${W} ${H}`} width="min(72%, 1180px)" style={{ overflow: "visible" }}>
          <SweepClip id={`sweep-${r0}`} width={innerW} height={innerH} progress={prog} />
          <g transform={`translate(${M.left}, ${M.top})`}>
            <Axis orientation="left" scale={y as never} length={innerW} opacity={axisOp}
              format={(v) => fmtNum(v, { prefix: yPrefix, suffix: ySuffix, decimals: yDecimals })} />
            <Axis orientation="bottom" scale={x as never} length={innerH} opacity={axisOp} grid={false}
              format={(v) => fmtNum(v, { prefix: xPrefix, suffix: xSuffix, decimals: xDecimals, group: xGroup })} />

            <g clipPath={`url(#sweep-${r0})`}>
              {series.map((s, i) => {
                const color = s.color ?? (i === 0 ? "var(--accent)" : "var(--text-2)");
                return (
                  <g key={i}>
                    {area && i === 0 ? (
                      <AreaClosed data={s.points} x={(d) => x(d.x)} y={(d) => y(d.y)} yScale={y}
                        curve={curveMonotoneX} fill="var(--accent-fill)" />
                    ) : null}
                    <LinePath data={s.points} x={(d) => x(d.x)} y={(d) => y(d.y)} curve={curveMonotoneX}
                      stroke={color} strokeWidth={i === 0 ? 3.5 : 2.5} />
                  </g>
                );
              })}
            </g>

            {/* leading-edge dot + live readout on the primary series */}
            {prog > 0.001 && prog < 0.999 ? (
              <g transform={`translate(${x(edgeX)}, ${y(edgeY)})`}>
                <circle r={7} fill="var(--accent)" style={{ filter: "drop-shadow(0 0 8px var(--accent-glow))" }} />
                <text x={12} y={-12} fontFamily="var(--font-mono)" fontSize={22} fontWeight={700}
                  fill="var(--accent)">{fmtNum(edgeY, { prefix: yPrefix, suffix: ySuffix, decimals: yDecimals })}</text>
              </g>
            ) : null}
          </g>
        </svg>

        {caption ? (
          <div style={{ opacity: interpolate(frame - r0, [20, 36], [0, 1], clamp), fontFamily: "var(--font-body)",
            color: "var(--text-2)", fontSize: "var(--t-body)" }}>{caption}</div>
        ) : null}
      </div>
    </Surface>
  );
};
