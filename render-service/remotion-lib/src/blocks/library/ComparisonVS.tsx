import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// Chapter-library block: a two-sided "VS" comparison — two mirrored columns
// split by a vertical rule with a circular "VS" badge at center. The LEFT side
// is the neutral / baseline option (--text-2); the RIGHT is the favored option
// (--accent, on a faint --accent-fill panel with --elev-3). Each side has a
// title, an optional mono-caps tag, and a few bullet points that stagger in.
// An optional `verdict` line fades up under the divider last. Token-only
// styling; wraps in <Surface>; no <Audio>. useCurrentFrame() is relative to
// this step's start (Remotion resets it per Series.Sequence).
type Side = { title: string; points?: string[]; tag?: string };
type Word = { text: string; startFrame: number; endFrame: number };
export type ComparisonVSProps = {
  kicker?: string;
  left: Side;
  right: Side;
  verdict?: string; // a closing line under the divider
  revealFrames: number[]; // [leftCue, rightCue, verdictCue]
  // Per-word timeline for THIS step (step-relative frames). Used to pop the
  // center badge exactly when "vs"/"versus" is spoken, if present.
  words?: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
// Cadence between sibling bullet reveals, mirroring the --stagger-step token
// (~70ms) translated to whole frames for deterministic, font-safe timing.
const STAGGER = 8;

export const ComparisonVS: React.FC<ComparisonVSProps> = ({
  kicker,
  left,
  right,
  verdict,
  revealFrames,
  words = [],
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const leftCue = revealFrames[0] ?? 0;
  const rightCue = revealFrames[1] ?? leftCue + 12;
  const verdictCue = revealFrames[2] ?? rightCue + 24;

  // Kicker rides in just before the left column.
  const kickerRf = leftCue - 6;
  const kickerS = spring({ frame: frame - kickerRf, fps, durationInFrames: 16, config: { damping: 200 } });

  // Column entrances: left slides in from the left, right from the right.
  const leftS = spring({ frame: frame - leftCue, fps, durationInFrames: 18, config: { damping: 200 } });
  const rightS = spring({ frame: frame - rightCue, fps, durationInFrames: 18, config: { damping: 200 } });
  const leftX = interpolate(leftS, [0, 1], [-90, 0]);
  const rightX = interpolate(rightS, [0, 1], [90, 0]);

  // Center "VS" badge pops at the midpoint of the two column cues — or, if the
  // narration actually says "vs"/"versus", snap the pop onto that spoken word.
  const spokenVs = words.find((w) => norm(w.text) === "vs" || norm(w.text) === "versus");
  const badgeCue = spokenVs ? spokenVs.startFrame : Math.round((leftCue + rightCue) / 2);
  const badgeS = spring({ frame: frame - badgeCue, fps, durationInFrames: 14, config: { damping: 12, stiffness: 180 } });

  // Verdict fades up under the divider.
  const verdictS = spring({ frame: frame - verdictCue, fps, durationInFrames: 18, config: { damping: 200 } });

  // Sparse mode (bench audit): with title-only sides the h2 titles float in
  // acres of empty Surface. Scale the type to display size when there are no
  // real bullet lists to carry the layout.
  const sparse = (left.points?.length ?? 0) + (right.points?.length ?? 0) <= 2;

  const renderSide = (side: Side, cue: number, s: number, x: number, favored: boolean) => {
    const appear = interpolate(frame, [cue, cue + 5], [0, 1], clamp);
    const points = side.points ?? [];
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-5)",
          padding: favored ? "var(--space-7)" : "var(--space-7) var(--space-6)",
          borderRadius: 12,
          background: favored ? "var(--accent-fill)" : "transparent",
          boxShadow: favored ? "var(--elev-3)" : "none",
          transform: `translateX(${x}px)`,
          opacity: appear,
        }}
      >
        {side.tag ? (
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--t-micro)",
              letterSpacing: "var(--track-caps)",
              textTransform: "uppercase",
              color: favored ? "var(--accent)" : "var(--text-mute)",
            }}
          >
            {side.tag}
          </div>
        ) : null}

        <div
          style={{
            fontFamily: "var(--font-display, var(--font-display-cn))",
            fontWeight: 900,
            fontSize: sparse ? "var(--t-h1)" : "var(--t-h2)",
            lineHeight: 1.05,
            color: favored ? "var(--accent)" : "var(--text-2)",
            textAlign: sparse ? "center" : undefined,
          }}
        >
          {side.title}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          {points.map((p, i) => {
            const prf = cue + 8 + i * STAGGER;
            const ps = spring({ frame: frame - prf, fps, durationInFrames: 14, config: { damping: 200 } });
            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: "var(--space-4)",
                  fontFamily: "var(--font-body)",
                  fontSize: "var(--t-body)",
                  color: "var(--text)",
                  transform: `translateY(${interpolate(ps, [0, 1], [14, 0])}px)`,
                  opacity: interpolate(frame, [prf, prf + 5], [0, 1], clamp),
                }}
              >
                <span
                  style={{
                    flex: "none",
                    width: "0.5em",
                    height: "0.5em",
                    marginTop: "0.1em",
                    borderRadius: "50%",
                    background: favored ? "var(--accent)" : "var(--text-mute)",
                  }}
                />
                <span>{p}</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
        {kicker ? (
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--t-micro)",
              letterSpacing: "var(--track-caps)",
              textTransform: "uppercase",
              color: "var(--text-mute)",
              marginBottom: "var(--space-7)",
              opacity: interpolate(frame, [kickerRf, kickerRf + 5], [0, 1], clamp),
              transform: `translateX(${interpolate(kickerS, [0, 1], [-24, 0])}px)`,
            }}
          >
            {kicker}
          </div>
        ) : null}

        {/* The two mirrored columns + center divider with the VS badge. */}
        <div style={{ position: "relative", display: "flex",
          alignItems: sparse ? "center" : "stretch",
          minHeight: sparse ? "40%" : undefined,
          gap: "var(--space-9)" }}>
          {renderSide(left, leftCue, leftS, leftX, false)}

          {/* Vertical rule + circular "VS" badge centered on it. */}
          <div
            style={{
              position: "relative",
              flex: "none",
              width: "var(--rule-w)",
              alignSelf: "stretch",
              background: "var(--rule)",
            }}
          >
            <div
              style={{
                position: "absolute",
                left: "50%",
                top: "50%",
                transform: `translate(-50%, -50%) scale(${interpolate(badgeS, [0, 1], [0.4, 1])})`,
                opacity: interpolate(frame, [badgeCue, badgeCue + 4], [0, 1], clamp),
                width: "var(--space-9)",
                height: "var(--space-9)",
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "var(--surface-2)",
                border: "var(--rule-w) solid var(--accent)",
                boxShadow: "0 0 var(--space-5) var(--accent-glow)",
                fontFamily: "var(--font-mono)",
                fontSize: "var(--t-micro)",
                letterSpacing: "var(--track-caps)",
                textTransform: "uppercase",
                color: "var(--accent)",
              }}
            >
              VS
            </div>
          </div>

          {renderSide(right, rightCue, rightS, rightX, true)}
        </div>

        {verdict ? (
          <div
            style={{
              marginTop: "var(--space-9)",
              textAlign: "center",
              fontFamily: "var(--font-body)",
              fontSize: "var(--t-body)",
              color: "var(--text-2)",
              opacity: interpolate(frame, [verdictCue, verdictCue + 6], [0, 1], clamp),
              transform: `translateY(${interpolate(verdictS, [0, 1], [16, 0])}px)`,
            }}
          >
            {verdict}
          </div>
        ) : null}
      </div>
    </Surface>
  );
};
