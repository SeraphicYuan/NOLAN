import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// REFERENCE BLOCK for the chapter library. A block is a per-step full-screen
// scene that (a) wraps its content in <Surface> (theme-faithful), (b) uses ONLY
// semantic theme tokens, (c) reveals sub-items at frames given in `revealFrames`
// (computed upstream from the narration's per-word timestamps). No <Audio> — the
// Chapter driver adds the step's narration. `useCurrentFrame()` is relative to
// this step's start (Remotion resets it per Series.Sequence).
type Item = { label: string; tag: string };
export type ListRevealProps = {
  title?: string;
  items: Item[];
  revealFrames: number[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const ListReveal: React.FC<ListRevealProps> = ({ title, items, revealFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <Surface>
      {title ? (
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
          letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)",
        }}>{title}</div>
      ) : null}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-7)", marginTop: "var(--space-9)" }}>
        {items.map((it, i) => {
          const rf = revealFrames[i] ?? 0;
          const s = spring({ frame: frame - rf, fps, durationInFrames: 16, config: { damping: 200 } });
          const appear = interpolate(frame, [rf, rf + 5], [0, 1], clamp);
          const x = interpolate(s, [0, 1], [-70, 0]);
          const nextRf = revealFrames[i + 1];
          const dim = nextRf != null && frame >= nextRf;
          return (
            <div key={i} style={{
              display: "flex", alignItems: "baseline", gap: "var(--space-7)",
              transform: `translateX(${x}px)`, opacity: appear * (dim ? 0.4 : 1),
            }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--t-body)", color: "var(--text-faint)" }}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <span style={{ fontFamily: "var(--font-display-en)", fontWeight: 900, fontSize: "var(--t-h1)", lineHeight: 1, letterSpacing: "var(--hero-num-track)" }}>
                {it.label}
              </span>
              <span style={{ flex: 1, height: "var(--rule-w)", background: "var(--rule)" }} />
              <span style={{ fontFamily: "var(--font-display-en)", fontWeight: 900, fontSize: "var(--t-h2)", color: "var(--accent)" }}>
                {it.tag}
              </span>
            </div>
          );
        })}
      </div>
    </Surface>
  );
};
