import React from "react";
import { useCurrentFrame, interpolate } from "remotion";
import { Surface } from "../../Surface";
import { useCountToWord, type Word } from "../../primitives/RollingNumber";

// Rebuild of NOLAN's PIL PercentageBarRenderer as a single-stat block: one big
// --accent percentage number sits above a horizontal track (--surface-2) holding
// an --accent fill bar. Both the number and the fill animate 0 -> `percentage`
// in lockstep, keyed to the spoken `word` (or revealFrames[0] fallback) via the
// shared useCountToWord mechanic. A mono-caps `label` rides above, a body-text
// `context` line below. ONLY semantic theme tokens; <Surface>-wrapped, no random/
// date/timers/CSS-transitions. `useCurrentFrame()` is step-relative.
export type PercentBarProps = {
  percentage: number; // 0–100
  label?: string;
  context?: string;
  word?: string; // spoken word to count-up on (optional)
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const PercentBar: React.FC<PercentBarProps> = ({
  percentage,
  label,
  context,
  word,
  revealFrames,
  words,
}) => {
  const frame = useCurrentFrame();
  const pct = Math.max(0, Math.min(100, percentage));
  const fallback = revealFrames[0] ?? 0;

  // Single source of truth: count 0 -> pct keyed to the spoken word (or reveal
  // fallback). `live` drives the printed number; the same progress drives the
  // fill width so the bar and number stay perfectly in sync.
  const { live, start, rolling } = useCountToWord(words, word ?? "", pct, { fallback });
  const fillPct = pct <= 0 ? 0 : (live / pct) * 100;

  // Gentle whole-card fade-in on the reveal.
  const appear = interpolate(frame, [fallback, fallback + 8], [0, 1], clamp);
  // Number entrance lands with its word.
  const rise = interpolate(frame, [start, start + 8], [16, 0], clamp);

  return (
    <Surface>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
          justifyContent: "center",
          alignItems: "stretch",
          gap: "var(--space-7)",
          opacity: appear,
        }}
      >
        {label ? (
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--t-micro)",
              letterSpacing: "var(--track-caps)",
              textTransform: "uppercase",
              color: "var(--text-mute)",
            }}
          >
            {label}
          </div>
        ) : null}

        {/* big accent percentage number, glowing while it ticks */}
        <div
          style={{
            fontFamily: "var(--font-display-en)",
            fontSize: "var(--t-display-1)",
            letterSpacing: "var(--hero-num-track)",
            lineHeight: 1,
            fontWeight: 900,
            color: "var(--accent)",
            fontVariantNumeric: "tabular-nums",
            transform: `translateY(${rise}px)`,
            textShadow: `0 0 ${interpolate(rolling, [0, 1], [10, 46], clamp)}px var(--accent-glow)`,
          }}
        >
          {Math.round(live)}
          <span style={{ fontSize: "0.5em", marginLeft: "var(--space-2)", color: "var(--accent)" }}>%</span>
        </div>

        {/* track + growing fill */}
        <div
          style={{
            position: "relative",
            width: "100%",
            height: "var(--space-7)",
            background: "var(--surface-2)",
            borderRadius: "var(--space-2)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: `${fillPct}%`,
              background: "var(--accent-fill, var(--accent))",
              borderRadius: "var(--space-2)",
              boxShadow: `0 0 var(--space-5) var(--accent-glow)`,
            }}
          />
        </div>

        {context ? (
          <div
            style={{
              fontFamily: "var(--font-body)",
              fontSize: "var(--t-body)",
              color: "var(--text-2)",
            }}
          >
            {context}
          </div>
        ) : null}
      </div>
    </Surface>
  );
};
