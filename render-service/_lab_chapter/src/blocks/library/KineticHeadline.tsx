import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// KineticHeadline — kinetic typography: each WORD of a headline punches in exactly
// as it's spoken, using the per-word timeline. We already own word timestamps, so
// this is the cheapest premium motion we can add — each word rises + scales + un-
// blurs on its spoken frame with an overshoot spring. Accent words land in --accent.
// Deterministic, token-themed. (HeroStatement reveals whole LINES; this is per-word.)
type Word = { text: string; startFrame: number; endFrame: number };
export type KineticHeadlineProps = {
  text: string;                 // the headline; wraps naturally
  accentWords?: string[];       // words rendered in --accent
  align?: "left" | "center";
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

export const KineticHeadline: React.FC<KineticHeadlineProps> = ({
  text, accentWords = [], align = "center", revealFrames, words, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const r0 = revealFrames[0] ?? 0;
  const accentSet = new Set(accentWords.map(norm));

  const tokens = text.split(/\s+/).filter(Boolean);
  // Map each display token to a spoken-word start frame by walking the timeline
  // in order (Nth content word → next matching spoken word), with even-spacing
  // fallback so it always animates.
  let cursor = 0;
  const span = Math.max(1, Math.round(durationInFrames * 0.7));
  const starts = tokens.map((tok, i) => {
    const t = norm(tok);
    for (let j = cursor; j < words.length; j++) {
      if (norm(words[j].text) === t && t.length > 0) {
        cursor = j + 1;
        return words[j].startFrame;
      }
    }
    return r0 + Math.round((i / Math.max(1, tokens.length)) * span);
  });

  return (
    <Surface>
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center",
        justifyContent: align === "center" ? "center" : "flex-start",
        padding: "0 var(--space-9)" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.28em 0.32em",
          justifyContent: align === "center" ? "center" : "flex-start",
          fontFamily: "var(--font-display-cn)", fontWeight: 800,
          fontSize: "var(--t-h1)", lineHeight: "var(--lh-head, 1.08)",
          letterSpacing: "var(--track-tight)", maxWidth: "82%" }}>
          {tokens.map((tok, i) => {
            const local = frame - starts[i];
            const s = spring({ frame: local, fps, durationInFrames: 18, config: { damping: 12, stiffness: 140, mass: 0.8 } });
            const op = interpolate(local, [0, 6], [0, 1], clamp);
            const y = interpolate(s, [0, 1], [42, 0]);
            const blur = interpolate(local, [0, 9], [10, 0], clamp);
            const isAccent = accentSet.has(norm(tok));
            return (
              <span key={i} style={{ display: "inline-block", opacity: op,
                transform: `translateY(${y}px) scale(${interpolate(s, [0, 1], [0.8, 1])})`,
                filter: local < 9 ? `blur(${blur}px)` : "none",
                color: isAccent ? "var(--accent)" : "var(--text)",
                textShadow: isAccent ? "0 0 24px var(--accent-glow)" : "var(--text-shadow, none)" }}>
                {tok}
              </span>
            );
          })}
        </div>
      </div>
    </Surface>
  );
};
