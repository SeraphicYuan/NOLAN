import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";
import { fmtNum } from "../../primitives/chart";

// Heatmap — a grid of cells colored by value on a sequential scale (correlation
// matrices, confusion matrices, attention grids, month×year tables). Common in
// ML/finance papers. Each cell's fill is computed per frame as a token-faithful
// `color-mix` from the value's normalized intensity t (0..1) — accent at t=1,
// surface at t=0 — so it stays correct across all 23 themes with NO new color
// dependency. The reveal: title + labels fade in first, then cells fade/scale in
// on a DIAGONAL sweep (delay ∝ row+col) driven by spring/interpolate. A
// highlightCell gets an --accent ring + a brief --accent-glow pulse; if a spoken
// word names that cell's row/col label, the emphasis snaps to the word's start.
// Deterministic: pure function of useCurrentFrame() — no random/date/timers.
type Word = { text: string; startFrame: number; endFrame: number };
export type HeatmapProps = {
  title?: string;
  caption?: string;
  values: number[][];           // row-major matrix
  rowLabels?: string[];
  colLabels?: string[];
  showValues?: boolean;         // print the number in each cell (default true)
  valueDecimals?: number;
  domain?: [number, number];    // min/max for color normalization (else derive from data)
  highlightCell?: [number, number]; // [row,col] to emphasize (ring + --accent border)
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

// Does a spoken word name this label? Normalized exact / containment match,
// the same heuristic PaperFigure + DataTable use to land emphasis on-beat.
const wordMatches = (label: string, w: Word): boolean => {
  const a = norm(label), b = norm(w.text);
  if (!a || !b) return false;
  return a === b || (a.length >= 3 && b.length >= 3 && (a.includes(b) || b.includes(a)));
};

const DIAG = 2.5;   // frames of delay per diagonal (row+col) step
const CELLS_AT = 14; // frames after r0 before the first cell starts revealing

export const Heatmap: React.FC<HeatmapProps> = ({
  title, caption, values, rowLabels, colLabels,
  showValues = true, valueDecimals = 2, domain, highlightCell,
  revealFrames, words, durationInFrames: _durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const r0 = revealFrames[0] ?? 0;

  const nRows = values.length;
  const nCols = values.reduce((m, row) => Math.max(m, row.length), 0);

  // Color normalization domain — explicit or derived from the data.
  const flat = values.flat();
  const dMin = domain ? domain[0] : Math.min(...flat);
  const dMax = domain ? domain[1] : Math.max(...flat);
  const span = dMax - dMin || 1;
  const intensity = (v: number) =>
    Math.max(0, Math.min(1, (v - dMin) / span)); // 0..1

  // Container intro (matches LineChart): whole stage fades + lifts in.
  const intro = spring({ frame: frame - r0, fps, durationInFrames: 20, config: { damping: 200 } });
  const titleOp = interpolate(frame - r0, [2, 16], [0, 1], clamp);
  const labelOp = interpolate(frame - r0, [8, 22], [0, 1], clamp);
  const capOp = interpolate(frame - r0, [20, 36], [0, 1], clamp);

  // Highlight cell — clamp to bounds, then resolve its emphasis start: if a
  // spoken word names its row/col label, snap to that word; else the cell's own
  // diagonal reveal slot.
  const hr = highlightCell && highlightCell[0] >= 0 && highlightCell[0] < nRows ? highlightCell[0] : -1;
  const hc = highlightCell && highlightCell[1] >= 0 && highlightCell[1] < nCols ? highlightCell[1] : -1;
  const hasHighlight = hr >= 0 && hc >= 0;
  const cellStart = (r: number, c: number) => r0 + CELLS_AT + (r + c) * DIAG;
  let emphasisStart = hasHighlight ? cellStart(hr, hc) : 0;
  if (hasHighlight) {
    const labels = [rowLabels?.[hr], colLabels?.[hc]].filter(Boolean) as string[];
    const w = words.find((x) => labels.some((l) => wordMatches(l, x)));
    if (w) emphasisStart = w.startFrame;
  }

  // Size: square-ish grid that fits min(70%, 1100px); cell font scales with the
  // implied cell pixel width so numbers stay legible whatever the matrix size.
  const GRID_PX = 1100;
  const cellPx = GRID_PX / Math.max(nCols, 1);
  const valueFont = Math.max(11, Math.min(34, Math.round(cellPx * 0.24)));

  return (
    <Surface>
      <div style={{
        width: "100%", height: "100%", display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", gap: "var(--space-4)",
        opacity: interpolate(intro, [0, 1], [0, 1]),
        transform: `translateY(${interpolate(intro, [0, 1], [22, 0])}px)`,
      }}>
        {title ? (
          <div style={{
            opacity: titleOp, fontFamily: "var(--font-mono)", color: "var(--text-mute)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase", fontSize: "var(--t-micro)",
          }}>{title}</div>
        ) : null}

        {/* grid: optional row-label column + matrix; column labels sit above. */}
        <div style={{
          display: "grid",
          gridTemplateColumns: `${rowLabels ? "auto " : ""}repeat(${nCols}, 1fr)`,
          gap: "var(--space-2)",
          width: "min(70%, 1100px)",
          alignItems: "center",
        }}>
          {/* column-label header row */}
          {colLabels ? (
            <>
              {rowLabels ? <div /> : null}
              {Array.from({ length: nCols }).map((_, c) => (
                <div key={`col-${c}`} style={{
                  opacity: labelOp, textAlign: "center", fontFamily: "var(--font-mono)",
                  fontSize: "var(--t-micro)", color: "var(--text-mute)",
                  letterSpacing: "var(--track-caps)", overflow: "hidden", textOverflow: "ellipsis",
                  whiteSpace: "nowrap", paddingBottom: "var(--space-2)",
                }}>{colLabels[c] ?? ""}</div>
              ))}
            </>
          ) : null}

          {/* matrix rows */}
          {Array.from({ length: nRows }).map((_, r) => (
            <React.Fragment key={`row-${r}`}>
              {rowLabels ? (
                <div style={{
                  opacity: labelOp, textAlign: "right", fontFamily: "var(--font-mono)",
                  fontSize: "var(--t-micro)", color: "var(--text-mute)",
                  letterSpacing: "var(--track-caps)", whiteSpace: "nowrap",
                  paddingRight: "var(--space-3)", overflow: "hidden", textOverflow: "ellipsis",
                }}>{rowLabels[r] ?? ""}</div>
              ) : null}

              {Array.from({ length: nCols }).map((_, c) => {
                const v = values[r]?.[c];
                const has = typeof v === "number" && Number.isFinite(v);
                const t = has ? intensity(v as number) : 0;
                const start = cellStart(r, c);
                const p = spring({ frame: frame - start, fps, durationInFrames: 16, config: { damping: 200 } });
                const isHi = hasHighlight && r === hr && c === hc;

                // Sequential token color-mix: accent ramps over surface by intensity.
                const fill = has
                  ? `color-mix(in srgb, var(--accent) ${Math.round(t * 100)}%, var(--surface))`
                  : "var(--surface-2)";
                // High-intensity cells flip to --surface text for contrast.
                const textColor = t > 0.58 ? "var(--surface)" : "var(--text)";

                // Highlight: persistent --accent ring + a brief --accent-glow pulse
                // that lands on emphasisStart (word-snapped when matched).
                const glow = isHi
                  ? interpolate(frame, [emphasisStart, emphasisStart + 12, emphasisStart + 34], [0, 1, 0], clamp)
                  : 0;

                return (
                  <div key={`cell-${r}-${c}`} style={{
                    position: "relative",
                    aspectRatio: "1 / 1",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    background: fill,
                    borderRadius: "var(--r-sm, 4px)",
                    border: isHi ? "2px solid var(--accent)" : "var(--rule-w, 1px) var(--rule-style, solid) var(--rule)",
                    boxShadow: isHi ? `0 0 ${10 + glow * 30}px var(--accent-glow)` : "none",
                    zIndex: isHi ? 2 : 1,
                    opacity: interpolate(p, [0, 1], [0, 1]),
                    transform: `scale(${interpolate(p, [0, 1], [isHi ? 0.55 : 0.6, 1])})`,
                  }}>
                    {/* ring overlay so the accent ring reads on any fill */}
                    {isHi ? (
                      <div style={{
                        position: "absolute", inset: -4, borderRadius: "var(--r-sm, 4px)",
                        border: "2px solid var(--accent)", opacity: 0.5 + glow * 0.5, pointerEvents: "none",
                      }} />
                    ) : null}
                    {showValues && has ? (
                      <span style={{
                        fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums",
                        fontSize: valueFont, fontWeight: isHi ? 700 : 500,
                        color: isHi ? "var(--surface)" : textColor,
                        lineHeight: 1,
                      }}>{fmtNum(v as number, { decimals: valueDecimals })}</span>
                    ) : null}
                  </div>
                );
              })}
            </React.Fragment>
          ))}
        </div>

        {caption ? (
          <div style={{
            opacity: capOp, fontFamily: "var(--font-body)", color: "var(--text-2)",
            fontSize: "var(--t-body)",
          }}>{caption}</div>
        ) : null}
      </div>
    </Surface>
  );
};
