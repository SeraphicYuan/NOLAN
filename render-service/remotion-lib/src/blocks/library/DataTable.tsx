import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// BESPOKE results-table block. One-off signature visual — NOT a reusable
// library block. Renders a clean comparison/results table that builds itself
// row-by-row, the way a paper's headline table lands a beat at a time:
//   - the header (column names) settles in first under a hairline rule,
//   - each data row reveals ONE BY ONE, staggered ~12 frames apart, sliding up
//     and fading in from revealFrames[0],
//   - one `highlightRow` is emphasized — its text in --accent over a soft
//     --accent-soft band, a left --accent accent bar, and a brief reveal glow.
//
// First column is a left-aligned label (--font-body); numeric columns are
// right-aligned tabular-nums (--font-mono). The whole table is ONE CSS grid and
// the header + every row are `grid-template-columns: subgrid`, so headers and
// data share the exact same column tracks and stay aligned even though the
// header font (--t-micro) differs from the data font (--t-body). Handles
// arbitrary column / row counts.
//
// Wraps content in <Surface>, uses ONLY semantic theme tokens, no <Audio>.
// `useCurrentFrame()` is step-relative (Remotion resets per Series.Sequence);
// if a spoken word in `words` matches the highlight row's label, that row's
// reveal snaps to the word so the emphasis lands on-beat.

type Word = { text: string; startFrame: number; endFrame: number };
export type DataTableProps = {
  // Column headers (mono / caps / muted). Defines the table's column count.
  columns: string[];
  // Row-major cells; ragged rows are tolerated (missing cells render empty).
  rows: string[][];
  // Index into `rows` to emphasize (accent text + band + bar + reveal glow).
  highlightRow?: number;
  // Small mono/caps label above the table (e.g. "WMT 2014 · BLEU").
  caption?: string;
  // Entrance cues (step-relative); revealFrames[0] starts the row stagger.
  revealFrames: number[];
  // Per-word timeline for THIS step (step-relative) — can snap the highlight.
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

// A cell "looks numeric" if it carries digits and only number-ish glyphs
// (separators, signs, units like % $ × :). Used to pick alignment + font.
const looksNumeric = (v: string) =>
  /\d/.test(v) && /^[\s\d.,%+\-$€£×x*:/()]+$/i.test(v.trim());

const STAGGER = 12; // frames between consecutive row reveals

export const DataTable: React.FC<DataTableProps> = ({
  columns,
  rows,
  highlightRow,
  caption,
  revealFrames,
  words,
  durationInFrames: _durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const r0 = revealFrames[0] ?? 0;
  const capStart = Math.max(0, r0 - 18);
  const headStart = Math.max(0, r0 - 9);
  const colCount = columns.length;

  // Per-column model: column 0 is the label; later columns that read numeric
  // become right-aligned mono. Grid `max-content` tracks size each column to its
  // widest cell (header or data), so no manual width math is needed.
  const cols = columns.map((_, c) => {
    const cells = rows.map((row) => row[c] ?? "");
    const numeric =
      c > 0 &&
      cells.length > 0 &&
      cells.filter((v) => v.trim() !== "").every((v) => looksNumeric(v));
    return { numeric };
  });
  // label column flexes (1fr), numeric columns size to content (right-aligned).
  const gridTemplate = `minmax(0, 1fr) ${cols.slice(1).map(() => "max-content").join(" ")}`;

  // If a spoken word matches the highlight row's label, snap its reveal to that
  // word so the emphasis lands exactly on-beat; otherwise use the stagger slot.
  const hi =
    typeof highlightRow === "number" && highlightRow >= 0 && highlightRow < rows.length
      ? highlightRow
      : -1;
  let hiSnap: number | null = null;
  if (hi >= 0) {
    const labelTokens = new Set(norm(rows[hi][0] ?? "").match(/[a-z0-9]+/g) ?? [norm(rows[hi][0] ?? "")]);
    const w = words.find((x) => labelTokens.size > 0 && labelTokens.has(norm(x.text)));
    if (w) hiSnap = w.startFrame;
  }

  const rowStart = (i: number) =>
    i === hi && hiSnap != null ? hiSnap : r0 + i * STAGGER;

  const headP = interpolate(frame, [headStart, headStart + 10], [0, 1], clamp);
  const capP = interpolate(frame, [capStart, capStart + 10], [0, 1], clamp);

  const headerCell = (text: string, ci: number): React.CSSProperties => ({
    textAlign: cols[ci]?.numeric ? "right" : "left",
    fontFamily: "var(--font-mono)",
    fontSize: "var(--t-micro)",
    letterSpacing: "var(--track-caps)",
    textTransform: "uppercase",
    color: "var(--text-mute)",
    whiteSpace: "nowrap",
  });

  const dataCell = (ci: number, isHi: boolean): React.CSSProperties => {
    const numeric = cols[ci]?.numeric;
    return {
      textAlign: numeric ? "right" : "left",
      fontFamily: numeric ? "var(--font-mono)" : "var(--font-body)",
      fontVariantNumeric: numeric ? "tabular-nums" : undefined,
      fontSize: "var(--t-body)",
      fontWeight: isHi ? 600 : ci === 0 ? 500 : 400,
      color: isHi ? "var(--accent)" : numeric ? "var(--text-2)" : "var(--text)",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis",
    };
  };

  return (
    <Surface>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          gap: "var(--space-5)",
        }}
      >
        {caption ? (
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--t-micro)",
              letterSpacing: "var(--track-caps)",
              textTransform: "uppercase",
              color: "var(--text-mute)",
              opacity: capP,
              transform: `translateY(${interpolate(capP, [0, 1], [8, 0])}px)`,
            }}
          >
            {caption}
          </div>
        ) : null}

        {/* table — one grid; header + every row are subgrids sharing its tracks */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: gridTemplate,
            columnGap: "var(--space-7)",
            minWidth: "min(72%, 880px)",
            maxWidth: "92%",
          }}
        >
          {/* header row */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "subgrid",
              gridColumn: "1 / -1",
              alignItems: "end",
              padding: "0 var(--space-4) var(--space-3)",
              borderBottom: "var(--rule-w) var(--rule-style, solid) var(--rule)",
              opacity: headP,
            }}
          >
            {columns.map((c, ci) => (
              <div key={ci} style={headerCell(c, ci)}>
                {c}
              </div>
            ))}
          </div>

          {/* data rows — revealed one by one */}
          {rows.map((row, i) => {
            const start = rowStart(i);
            const p = spring({
              frame: frame - start,
              fps,
              durationInFrames: 20,
              config: { damping: 200 },
            });
            const isHi = i === hi;
            // Highlight reveals with a touch more lift + a brief glow.
            const ty = interpolate(p, [0, 1], [isHi ? 22 : 16, 0]);
            const scale = isHi ? interpolate(p, [0, 1], [0.985, 1]) : 1;
            const glow = isHi
              ? interpolate(frame, [start, start + 12, start + 34], [0, 1, 0], clamp)
              : 0;

            return (
              <div
                key={i}
                style={{
                  position: "relative",
                  display: "grid",
                  gridTemplateColumns: "subgrid",
                  gridColumn: "1 / -1",
                  alignItems: "center",
                  padding: "var(--space-3) var(--space-4)",
                  borderRadius: "var(--r-sm, 4px)",
                  background: isHi ? "var(--accent-soft)" : "transparent",
                  boxShadow: isHi
                    ? `0 0 ${24 + glow * 26}px var(--accent-glow)`
                    : "none",
                  opacity: p,
                  transform: `translateY(${ty}px) scale(${scale})`,
                  transformOrigin: "center left",
                }}
              >
                {/* left accent bar on the highlighted row */}
                {isHi ? (
                  <div
                    style={{
                      position: "absolute",
                      left: 0,
                      top: "12%",
                      bottom: "12%",
                      width: 3,
                      borderRadius: 3,
                      background: "var(--accent)",
                    }}
                  />
                ) : null}
                {Array.from({ length: colCount }).map((_, ci) => (
                  <div key={ci} style={dataCell(ci, isHi)}>
                    {row[ci] ?? ""}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </Surface>
  );
};
