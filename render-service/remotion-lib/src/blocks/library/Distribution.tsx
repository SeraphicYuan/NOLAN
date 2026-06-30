import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { scaleLinear } from "@visx/scale";
import { Bar } from "@visx/shape";
import { bin as d3bin, max as d3max } from "d3-array";
import { Surface } from "../../Surface";
import { Axis, fmtNum } from "../../primitives/chart";

// Distribution — a histogram over a numeric axis: how a set of values is spread
// (return distributions, score / latency distributions, any "shape of the data"
// figure common in finance / ML papers). Geometry from visx/d3 scales; bars are
// pure per-frame geometry. The reveal is frame-driven: axes fade in first, then
// each bar GROWS up from the baseline, staggered left→right via spring, and an
// optional marker line (mean / median) draws in after the bars settle. Deterministic,
// SVG, fully token-themed. Use for raw values you HAVE (redraw tier) — pass
// pre-binned `bins` OR raw `values` we bin with d3-array.
type Word = { text: string; startFrame: number; endFrame: number };
type Binned = { x0: number; x1: number; count: number };
export type DistributionProps = {
  title?: string;
  caption?: string;
  // EITHER pre-binned bars OR raw values (binned with d3-array):
  bins?: Binned[];
  values?: number[];
  binCount?: number;            // thresholds when binning raw values (default ~12)
  markerX?: number;             // optional vertical reference line (mean / median)
  markerLabel?: string;
  xPrefix?: string; xSuffix?: string; xDecimals?: number;
  highlightRange?: [number, number]; // bars whose center falls here render in --accent, rest muted
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const W = 1180, H = 560;
const M = { top: 56, right: 64, bottom: 56, left: 96 };
const innerW = W - M.left - M.right;
const innerH = H - M.top - M.bottom;
const GAP = 3;          // px gutter between adjacent bars
const STAGGER = 3.5;    // frames between successive bars growing
const BAR_START = 10;   // frames after r0 the first bar begins

const resolveBins = (
  bins: Binned[] | undefined,
  values: number[] | undefined,
  binCount: number,
): Binned[] => {
  if (bins && bins.length) return bins;
  const vals = (values ?? []).filter((v) => Number.isFinite(v));
  if (!vals.length) return [];
  const out = d3bin<number, number>().thresholds(binCount)(vals);
  return out.map((b) => ({ x0: b.x0 ?? 0, x1: b.x1 ?? 0, count: b.length }));
};

export const Distribution: React.FC<DistributionProps> = ({
  title, caption, bins, values, binCount = 12,
  markerX, markerLabel, xPrefix, xSuffix, xDecimals = 0,
  highlightRange, revealFrames, words: _words, durationInFrames: _durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const r0 = revealFrames[0] ?? 0;

  const data = resolveBins(bins, values, binCount);
  const xMin = data.length ? Math.min(...data.map((b) => b.x0)) : 0;
  const xMax = data.length ? Math.max(...data.map((b) => b.x1)) : 1;
  const yMax = (d3max(data, (b) => b.count) ?? 1) || 1;

  const x = scaleLinear({ domain: [xMin, xMax], range: [0, innerW] });
  const y = scaleLinear({ domain: [0, yMax * 1.08], range: [innerH, 0] });

  const intro = spring({ frame: frame - r0, fps, durationInFrames: 20, config: { damping: 200 } });
  const titleOp = interpolate(frame - r0, [2, 16], [0, 1], clamp);
  const axisOp = interpolate(frame - r0, [8, 24], [0, 1], clamp);

  // marker fades in once the bars have finished growing
  const barsDone = BAR_START + (data.length - 1) * STAGGER + 18;
  const markerOp = interpolate(frame - r0, [barsDone, barsDone + 14], [0, 1], clamp);

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
          <g transform={`translate(${M.left}, ${M.top})`}>
            <Axis orientation="left" scale={y as never} length={innerW} opacity={axisOp}
              format={(v) => fmtNum(v, { decimals: 0 })} />
            <Axis orientation="bottom" scale={x as never} length={innerH} opacity={axisOp} grid={false}
              format={(v) => fmtNum(v, { prefix: xPrefix, suffix: xSuffix, decimals: xDecimals })} />

            {data.map((b, i) => {
              const grow = spring({ frame: frame - (r0 + BAR_START + i * STAGGER), fps,
                durationInFrames: 18, config: { damping: 200 } });
              const left = x(b.x0);
              const bw = Math.max(1, x(b.x1) - x(b.x0) - GAP);
              const fullH = innerH - y(b.count);
              const h = Math.max(0, fullH * grow);
              const center = (b.x0 + b.x1) / 2;
              const inRange = highlightRange
                ? center >= highlightRange[0] && center <= highlightRange[1]
                : true;
              return (
                <Bar key={i} x={left} y={innerH - h} width={bw} height={h} rx={3}
                  fill={inRange ? "var(--accent)" : "var(--text-2)"}
                  opacity={inRange ? 1 : 0.45}
                  style={inRange ? { filter: "drop-shadow(0 0 8px var(--accent-glow))" } : undefined} />
              );
            })}

            {/* optional mean / median reference line, drawn in after the bars settle */}
            {markerX != null && markerX >= xMin && markerX <= xMax ? (
              <g opacity={markerOp} transform={`translate(${x(markerX)}, 0)`}>
                <line y1={0} y2={innerH} stroke="var(--accent)" strokeWidth={2} strokeDasharray="6 7"
                  style={{ filter: "drop-shadow(0 0 6px var(--accent-glow))" }} />
                {markerLabel ? (
                  <text y={-12} textAnchor="middle" fontFamily="var(--font-mono)" fontSize={16} fontWeight={700}
                    letterSpacing="var(--track-caps)" fill="var(--accent)">{markerLabel}</text>
                ) : null}
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
