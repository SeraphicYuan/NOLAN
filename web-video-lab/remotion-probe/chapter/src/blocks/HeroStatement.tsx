import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../Surface";

// Chapter-library block: one big punchy statement scene for transition / claim
// steps. Wraps content in <Surface>, uses ONLY semantic theme tokens, reveals
// each line at the frame given in `revealFrames` (computed upstream from the
// narration). No <Audio> — the Chapter driver supplies the step narration.
// `useCurrentFrame()` is relative to this step's start.
type Line = { text: string; accent?: boolean; strike?: boolean };
export type HeroStatementProps = {
  kicker?: string;
  lines: Line[];
  revealFrames: number[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const HeroStatement: React.FC<HeroStatementProps> = ({ kicker, lines, revealFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Kicker rides in just before the first line.
  const kickerRf = (revealFrames[0] ?? 0) - 6;
  const kickerS = spring({ frame: frame - kickerRf, fps, durationInFrames: 16, config: { damping: 200 } });

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
        {kicker ? (
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)",
            marginBottom: "var(--space-6)",
            opacity: interpolate(frame, [kickerRf, kickerRf + 5], [0, 1], clamp),
            transform: `translateX(${interpolate(kickerS, [0, 1], [-24, 0])}px)`,
          }}>{kicker}</div>
        ) : null}

        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          {lines.map((ln, i) => {
            const rf = revealFrames[i] ?? 0;
            const s = spring({ frame: frame - rf, fps, durationInFrames: 16, config: { damping: 200 } });
            // Mask-up reveal: the line sits in an overflow-clipped row and slides
            // up into view from below — deliberate, not a plain fade.
            const y = interpolate(s, [0, 1], [110, 0]);
            const appear = interpolate(frame, [rf, rf + 4], [0, 1], clamp);
            // Strike draws across after the line has settled.
            const strikeW = ln.strike
              ? interpolate(s, [0.45, 1], [0, 100], clamp)
              : 0;
            return (
              <div key={i} style={{ overflow: "hidden", paddingBottom: "0.08em" }}>
                <div style={{
                  position: "relative",
                  display: "inline-block",
                  fontFamily: "var(--font-display-en)", fontWeight: 900,
                  fontSize: "var(--t-display-2)", lineHeight: 1.02,
                  letterSpacing: "var(--hero-num-track)",
                  color: ln.accent ? "var(--accent)" : "var(--text)",
                  transform: `translateY(${y}%)`,
                  opacity: appear,
                }}>
                  {ln.text}
                  {ln.strike ? (
                    <span style={{
                      position: "absolute", left: 0, top: "50%",
                      height: "var(--rule-w)", width: `${strikeW}%`,
                      background: ln.accent ? "var(--accent)" : "var(--text)",
                      transform: "translateY(-50%)",
                    }} />
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Surface>
  );
};
