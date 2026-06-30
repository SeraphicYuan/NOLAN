import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

// PhotoGrid — a "full view of the whole series" block: a cols×rows wall of image tiles
// that builds up one column (or row) at a time, then settles into the complete grid, then
// pulses a couple of named tiles — each fading IN, holding, and fading back OUT — while the
// rest of the wall dims to push them forward. Everything is a pure function of the frame and
// the grid shape, so 40 tiles is just data. Sibling of PhotoMontage (scatter) and UnlockGrid
// (abstract tiles); this one shows the actual images.
//
// Contract (supplied by the chapter driver):
//   revealFrames[0]      — when the column-by-column fill begins
//   revealFrames[1..]    — one cue per `highlight` index: when that tile pulses
type Word = { text: string; startFrame: number; endFrame: number };
type Card = { src: string; caption?: string };
export type PhotoGridProps = {
  cards: Card[];
  cols?: number;
  rows?: number;
  order?: "col" | "row" | "one-by-one"; // fill sequencing (default col-by-col)
  highlight?: number[];                  // flat tile indices to pulse (paired with revealFrames[1..])
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// trapezoid pulse: fade in (10f) → hold (34f) → fade out (16f). 0 before/after.
const pulse = (frame: number, cue: number) =>
  interpolate(frame, [cue, cue + 10, cue + 44, cue + 60], [0, 1, 1, 0], clamp);

export const PhotoGrid: React.FC<PhotoGridProps> = ({
  cards = [],
  cols = 8,
  rows = 5,
  order = "col",
  highlight = [],
  revealFrames,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const n = Math.min(cards.length, cols * rows);
  const fillStart = revealFrames?.[0] ?? 6;
  const hiCues = (revealFrames ?? []).slice(1);
  const firstHi = hiCues.length ? Math.min(...hiCues) : Math.round(durationInFrames * 0.62);

  // Column-by-column fill: a snappy cadence (~1.2s/unit, capped) that finishes well before
  // the first highlight, so the complete wall holds on screen before any tile is lit.
  const units = order === "row" ? rows : order === "col" ? cols : n;
  const room = (firstHi - 18 - fillStart) / Math.max(1, units);
  const stagger = Math.max(10, Math.min(36, room));
  const flyDur = Math.min(26, stagger * 1.6 + 8);

  // Highlight amount per tile (max across the cues that target it) + a global dim driver.
  const hiAmtFor = (i: number) =>
    highlight.reduce((m, idx, k) => (idx === i ? Math.max(m, pulse(frame, hiCues[k] ?? firstHi)) : m), 0);
  const globalHi = highlight.reduce((m, _idx, k) => Math.max(m, pulse(frame, hiCues[k] ?? firstHi)), 0);

  return (
    <AbsoluteFill style={{ background: "var(--surface)", color: "var(--text)", fontFamily: "var(--font-body)" }}>
      <div
        style={{
          position: "absolute",
          inset: "3.5% 2.5%",
          display: "grid",
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gridTemplateRows: `repeat(${rows}, 1fr)`,
          gap: "0.7%",
        }}
      >
        {cards.slice(0, n).map((card, i) => {
          const r = Math.floor(i / cols);
          const c = i % cols;
          const u = order === "row" ? r : order === "col" ? c : i;

          // phase 1: fly/fade in at this unit's cue
          const tileStart = fillStart + u * stagger;
          const s = spring({ frame: frame - tileStart, fps, durationInFrames: flyDur, config: { damping: 200 } });
          const appear = interpolate(s, [0, 1], [0, 1], clamp);

          // phase 3: pulse highlight
          const hi = hiAmtFor(i);
          const baseOp = appear * (1 - 0.55 * globalHi * (hi < 0.01 ? 1 : 0)); // others dim while a tile is lit
          const scale = interpolate(appear, [0, 1], [0.86, 1], clamp) + 0.55 * hi;
          const lift = interpolate(appear, [0, 1], [10, 0], clamp);

          return (
            <div
              key={i}
              style={{
                position: "relative",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                minWidth: 0,
                minHeight: 0,
                opacity: baseOp,
                zIndex: hi > 0.01 ? 100 : 1,
                transform: `translateY(${lift}px) scale(${scale})`,
                transformOrigin: "center center",
              }}
            >
              <div
                style={{
                  position: "relative",
                  maxWidth: "100%",
                  maxHeight: "100%",
                  border: `${hi > 0.5 ? 2 : 1}px solid ${hi > 0.2 ? "var(--accent)" : "rgba(0,0,0,0.18)"}`,
                  background: "#f4f2ea",
                  boxShadow: hi > 0.01
                    ? `0 10px 28px rgba(0,0,0,${0.18 + 0.32 * hi}), 0 0 ${Math.round(18 * hi)}px var(--accent-glow, rgba(212,160,80,0.5))`
                    : "0 2px 6px rgba(0,0,0,0.22)",
                  lineHeight: 0,
                }}
              >
                <Img
                  src={staticFile(card.src)}
                  style={{ display: "block", maxWidth: "100%", maxHeight: "100%", width: "auto", height: "auto", objectFit: "contain" }}
                />
                {card.caption && hi > 0.05 ? (
                  <div
                    style={{
                      position: "absolute",
                      left: 0,
                      right: 0,
                      bottom: 0,
                      padding: "6px 4px 5px",
                      textAlign: "center",
                      background: "linear-gradient(transparent, rgba(20,12,8,0.82))",
                      opacity: hi,
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--font-display-cn, var(--font-body))",
                        fontStyle: "italic",
                        fontWeight: 600,
                        fontSize: 18,
                        lineHeight: 1.05,
                        color: "#f6f1e6",
                      }}
                    >
                      {card.caption}
                    </span>
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
