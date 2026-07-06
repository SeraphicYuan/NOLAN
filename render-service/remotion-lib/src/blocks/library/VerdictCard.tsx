import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// VerdictCard — a Remotion rebuild of NOLAN's PIL VerdictRenderer. A calm,
// conclusive takeaway card: a round icon badge (accent ring + accent-fill on an
// accent-glow), a mono-caps type label, the verdict line, and supporting text.
// Pure function of useCurrentFrame() — no random/date/timers/CSS-transitions —
// wraps content in <Surface> and uses ONLY semantic theme tokens, so every
// theme applies unchanged. `useCurrentFrame()` is step-relative (Remotion resets
// it per Series.Sequence); `revealFrames` are computed upstream from the
// narration's per-word timestamps. No <Audio> — the driver supplies narration.

type Word = { text: string; startFrame: number; endFrame: number };

export type VerdictCardProps = {
  verdict: string;
  supportingText?: string;
  verdictType?: "conclusion" | "warning" | "success" | "info" | "key_point"; // default "conclusion"
  label?: string;              // overrides the type word
  revealFrames: number[];      // [icon/label cue, verdict cue]
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
// Cadence between sibling reveals, mirroring the --stagger-step token (~70ms)
// translated to whole frames for deterministic, font-safe timing.
const STAGGER = 8;

// One glyph + default word per verdict type. A single accent carries them all;
// the type only changes the symbol and the label, never the colour.
const PRESETS: Record<
  NonNullable<VerdictCardProps["verdictType"]>,
  { glyph: string; word: string }
> = {
  conclusion: { glyph: "→", word: "Conclusion" }, // →
  warning: { glyph: "!", word: "Warning" },
  success: { glyph: "✓", word: "Success" }, // ✓
  info: { glyph: "i", word: "Info" },
  key_point: { glyph: "★", word: "Key Point" }, // ★
};

export const VerdictCard: React.FC<VerdictCardProps> = ({
  verdict,
  supportingText,
  verdictType = "conclusion",
  label,
  revealFrames,
  words = [],
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const preset = PRESETS[verdictType] ?? PRESETS.conclusion;
  const typeWord = (label ?? preset.word).toUpperCase();

  // Cues fall back to the first spoken word so the card still lands if the
  // upstream reveal schedule is short.
  const firstWord = words[0]?.startFrame ?? 0;
  const badgeRf = revealFrames[0] ?? firstWord;
  const verdictRf = revealFrames[1] ?? badgeRf + STAGGER * 2;
  const labelRf = badgeRf + STAGGER; // label fades in just after the badge pops
  const supportRf = verdictRf + STAGGER; // supporting text trails the verdict

  // Badge scales in with a settling overshoot; its glow blooms then eases back.
  const badgeS = spring({ frame: frame - badgeRf, fps, durationInFrames: 22, config: { damping: 200 } });
  const badgeScale = interpolate(badgeS, [0, 1], [0.4, 1]);
  const badgeAppear = interpolate(frame, [badgeRf, badgeRf + 6], [0, 1], clamp);
  const badgeGlow = interpolate(badgeS, [0, 1], [4, 30]);
  // Glyph draws in a beat behind the ring so the symbol "lands" inside.
  const glyphAppear = interpolate(frame, [badgeRf + 3, badgeRf + 10], [0, 1], clamp);

  // Type label fades up beside the badge.
  const labelS = spring({ frame: frame - labelRf, fps, durationInFrames: 16, config: { damping: 200 } });
  const labelX = interpolate(labelS, [0, 1], [-24, 0]);
  const labelAppear = interpolate(frame, [labelRf, labelRf + 6], [0, 1], clamp);

  // Verdict fades + slides up.
  const verdictS = spring({ frame: frame - verdictRf, fps, durationInFrames: 18, config: { damping: 200 } });
  const verdictY = interpolate(verdictS, [0, 1], [70, 0]);
  const verdictAppear = interpolate(frame, [verdictRf, verdictRf + 6], [0, 1], clamp);

  // Supporting text fades in below.
  const supportAppear = interpolate(frame, [supportRf, supportRf + 8], [0, 1], clamp);

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
        {/* Badge + type label row */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-5)",
          marginBottom: "var(--space-8)",
        }}>
          <div style={{
            flex: "none",
            width: "var(--space-12)",
            height: "var(--space-12)",
            borderRadius: "50%",
            border: "var(--rule) solid var(--accent)",
            background: "var(--accent-fill)",
            boxShadow: `0 0 ${badgeGlow}px var(--accent-glow)`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transform: `scale(${badgeScale})`,
            opacity: badgeAppear,
          }}>
            <span style={{
              fontFamily: "var(--font-display, var(--font-display-cn))",
              fontWeight: 900,
              fontSize: "var(--t-h2)",
              lineHeight: 1,
              color: "var(--accent)",
              opacity: glyphAppear,
            }}>{preset.glyph}</span>
          </div>

          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)",
            textTransform: "uppercase",
            color: "var(--accent)",
            transform: `translateX(${labelX}px)`,
            opacity: labelAppear,
          }}>{typeWord}</div>
        </div>

        {/* Verdict line */}
        <div style={{ overflow: "hidden", paddingBottom: "0.08em" }}>
          <div style={{
            fontFamily: "var(--font-display, var(--font-display-cn))",
            fontWeight: 900,
            fontSize: "var(--t-h1)",
            lineHeight: 1.08,
            color: "var(--text)",
            transform: `translateY(${verdictY}%)`,
            opacity: verdictAppear,
          }}>{verdict}</div>
        </div>

        {/* Supporting text */}
        {supportingText ? (
          <div style={{
            marginTop: "var(--space-6)",
            maxWidth: "82%",
            fontFamily: "var(--font-display, var(--font-display-cn))",
            fontWeight: 400,
            fontSize: "var(--t-body)",
            lineHeight: 1.5,
            color: "var(--text-2)",
            opacity: supportAppear,
          }}>{supportingText}</div>
        ) : null}
      </div>
    </Surface>
  );
};
