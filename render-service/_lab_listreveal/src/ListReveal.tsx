import React from "react";
import {
  AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig,
  interpolate, spring,
} from "remotion";

// A parameterized, step-aware block. Visuals use ONLY the skill's semantic theme
// tokens (--surface/--text/--accent/--rule/--font-*/--t-*/--space-*) — never
// hard-coded colors/fonts — so all 23 skill themes apply unchanged. Reveal timing
// comes from the narration's per-word timestamps (compute, don't capture).
type Item = { model: string; domain: string };
type Props = {
  title?: string;
  items: Item[];
  revealFrames: number[];
  audioSrc?: string;
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const ListReveal: React.FC<Props> = ({ title, items, revealFrames, audioSrc }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ backgroundColor: "var(--surface)", color: "var(--text)", fontFamily: "var(--font-body)" }}>
      {audioSrc ? <Audio src={staticFile(audioSrc)} /> : null}

      {/* surface pattern overlay — mirrors the skill's .stage-frame::after so each
          theme's decoration (bold-signal gradient / paper-press multiply texture)
          renders faithfully on top of the solid --surface. */}
      <AbsoluteFill style={{
        backgroundImage: "var(--surface-pattern, none)",
        backgroundSize: "var(--surface-pattern-size, auto)",
        mixBlendMode: "var(--surface-pattern-blend, normal)",
        opacity: "var(--surface-pattern-opacity, 1)",
      } as React.CSSProperties} />

      <AbsoluteFill style={{ padding: "var(--stage-pad-y) var(--stage-pad-x)", zIndex: 1 }}>
        {title ? (
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase",
            color: "var(--text-mute)",
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
                <span style={{
                  fontFamily: "var(--font-display-en)", fontWeight: 900,
                  fontSize: "var(--t-h1)", lineHeight: 1, letterSpacing: "var(--hero-num-track)",
                }}>{it.model}</span>
                <span style={{ flex: 1, height: "var(--rule-w)", background: "var(--rule)" }} />
                <span style={{
                  fontFamily: "var(--font-display-en)", fontWeight: 900,
                  fontSize: "var(--t-h2)", color: "var(--accent)",
                }}>{it.domain}</span>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
