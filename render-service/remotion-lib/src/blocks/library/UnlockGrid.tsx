import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// LIBRARY block: a big stamped value beside a grid that fills/unlocks tile-by-tile
// on a diagonal sweep, with supporting mono captions. A general coverage /
// completion / adoption / "every area unlocked" visual.
// Wraps content in <Surface>, theme tokens only, no <Audio>. `useCurrentFrame()`
// is relative to this step's start.
type Word = { text: string; startFrame: number; endFrame: number };
export type UnlockGridProps = {
  // Contract (supplied by the chapter driver)
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
  // Own props (all optional — neutral defaults)
  value?: string;
  kicker?: string;
  popWord?: string;
  captions?: string[];
  gridCols?: number;
  gridRows?: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const UnlockGrid: React.FC<UnlockGridProps> = ({
  revealFrames,
  words,
  durationInFrames,
  value = "100",
  kicker = "",
  popWord,
  captions = [],
  gridCols = 8,
  gridRows = 4,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Pop the hero number on `popWord` if supplied & spoken, else first reveal.
  const numWord = popWord
    ? words.find((w) => new RegExp(`\\b${popWord}\\b`, "i").test(w.text))
    : undefined;
  const popFrame = numWord ? numWord.startFrame : revealFrames[0] ?? 0;
  const stampS = spring({ frame: frame - popFrame, fps, durationInFrames: 18, config: { damping: 13, mass: 0.8 } });
  const stampScale = interpolate(stampS, [0, 1], [1.7, 1], clamp); // slams down like a stamp
  const stampOpacity = interpolate(frame, [popFrame, popFrame + 4], [0, 1], clamp);

  // --- Signature motion: diagonal tile-by-tile unlock of the grid. ---
  const total = gridCols * gridRows;
  const maxDiag = gridCols - 1 + (gridRows - 1);
  // Sweep window: starts just after the stamp, ends with a tail before step end.
  const sweepStart = popFrame + 8;
  const sweepEnd = Math.max(sweepStart + 18, durationInFrames - 14);

  const captionStart = revealFrames[1] ?? Math.round(durationInFrames * 0.6);

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%", gap: "var(--space-8)" }}>
        {/* Top zone: hero number (left) + grid (right) */}
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-9)" }}>
          {/* Hero number with kicker */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", flex: "0 0 auto" }}>
            {kicker ? (
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
                letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)",
                opacity: stampOpacity,
              }}>{kicker}</div>
            ) : null}
            <div style={{
              fontFamily: "var(--font-display-en)", fontWeight: 900,
              fontSize: "var(--t-display-1)", lineHeight: 0.9,
              letterSpacing: "var(--hero-num-track)", color: "var(--accent)",
              transform: `scale(${stampScale})`, transformOrigin: "left center",
              opacity: stampOpacity,
            }}>{value}</div>
          </div>

          {/* THE GRID — unlocks tile-by-tile on a diagonal sweep */}
          <div style={{
            flex: 1,
            display: "grid",
            gridTemplateColumns: `repeat(${gridCols}, 1fr)`,
            gridTemplateRows: `repeat(${gridRows}, 1fr)`,
            gap: "var(--space-2)",
            aspectRatio: `${gridCols} / ${gridRows}`,
          }}>
            {Array.from({ length: total }).map((_, idx) => {
              const r = Math.floor(idx / gridCols);
              const c = idx % gridCols;
              const t = maxDiag > 0 ? (c + r) / maxDiag : 0; // diagonal position 0..1
              const tileFrame = sweepStart + t * (sweepEnd - sweepStart);
              const u = spring({ frame: frame - tileFrame, fps, durationInFrames: 12, config: { damping: 200 } });
              return (
                <div key={idx} style={{
                  position: "relative",
                  border: "var(--rule-w) solid var(--rule)",
                  background: "var(--surface-3)",
                  borderRadius: 2,
                }}>
                  {/* Unlocked layer crossfades in over the dim outline */}
                  <div style={{
                    position: "absolute", inset: 0,
                    border: "var(--rule-w) solid var(--accent)",
                    background: "var(--accent-soft)",
                    boxShadow: "0 0 var(--space-4) var(--accent-glow)",
                    borderRadius: 2,
                    opacity: u,
                    transform: `scale(${interpolate(u, [0, 1], [0.82, 1], clamp)})`,
                  }} />
                </div>
              );
            })}
          </div>
        </div>

        {/* Mono captions for the supporting beats */}
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          {captions.map((cap, i) => {
            const rf = captionStart + i * 10;
            const s = spring({ frame: frame - rf, fps, durationInFrames: 14, config: { damping: 200 } });
            return (
              <div key={i} style={{
                fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
                letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)",
                opacity: interpolate(frame, [rf, rf + 5], [0, 1], clamp),
                transform: `translateX(${interpolate(s, [0, 1], [-24, 0])}px)`,
              }}>{cap}</div>
            );
          })}
        </div>
      </div>
    </Surface>
  );
};
