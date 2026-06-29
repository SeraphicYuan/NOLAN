import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// BESPOKE cold-open block for the HUMAN 3.0 hook chapter. One-off signature
// visual — NOT a reusable library block. Narration:
//   "I never wanted to be an NPC. You know the type — running on a script
//    someone else wrote. Same loop, every day, until it's over."
//
// Signature motion: a strike-through line draws across the word "NPC" exactly
// when "NPC" is spoken — synced to that word's [startFrame, endFrame] inside the
// step-relative `words` timeline. Behind it, a faint someone-else's-script
// daily-loop terminal drifts slowly upward (the NPC's repeating program).
//
// Wraps content in <Surface>, uses ONLY semantic theme tokens, no <Audio>.
// `useCurrentFrame()` is relative to this step's start.

type Word = { text: string; startFrame: number; endFrame: number };
export type NpcStrikeProps = {
  // Per-word timeline for THIS step (step-relative frames) — drives the strike.
  words: Word[];
  // Entrance cues (step-relative); revealFrames[0] kicks off the statement.
  revealFrames: number[];
  durationInFrames: number;
  // Bespoke copy — defaults hard-coded since this is a one-off scene.
  statement?: string;
  strikeWord?: string;
  backdrop?: string[];
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

const DEFAULT_BACKDROP = [
  "06:30  alarm() // not yours",
  "08:00  commute → cubicle",
  "12:00  same loop",
  "18:00  commute → couch",
  "23:00  scroll · sleep",
  "goto: tomorrow",
];

export const NpcStrike: React.FC<NpcStrikeProps> = ({
  words,
  revealFrames,
  durationInFrames,
  statement = "I never wanted to be an NPC.",
  strikeWord = "NPC",
  backdrop = DEFAULT_BACKDROP,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Split the statement so the strike-word renders as its own boxed token.
  const target = norm(strikeWord);
  const tokens = statement.split(/(\s+)/); // keep whitespace tokens
  const hitIndex = tokens.findIndex((t) => norm(t) === target);

  // Entrance: the whole statement masks up into view at the first cue.
  const startRf = revealFrames[0] ?? 0;
  const enter = spring({ frame: frame - startRf, fps, durationInFrames: 18, config: { damping: 200 } });
  const enterY = interpolate(enter, [0, 1], [120, 0]);
  const enterOpacity = interpolate(frame, [startRf, startRf + 5], [0, 1], clamp);

  // Signature motion: strike draws across "NPC" across that word's spoken span.
  const spoken = words.find((w) => norm(w.text) === target);
  const strikeW = spoken
    ? interpolate(frame, [spoken.startFrame, spoken.endFrame], [0, 100], clamp)
    : // Fallback if the timeline lacks the word: draw once the statement settles.
      interpolate(enter, [0.55, 1], [0, 100], clamp);

  // Backdrop drifts slowly upward over the whole step. Lines are tiled twice so
  // the loop never runs dry; kept faint so the statement dominates.
  const drift = interpolate(frame, [0, durationInFrames], [0, -220], clamp);
  const tiled = [...backdrop, ...backdrop];

  return (
    <Surface>
      {/* someone-else's-script terminal, drifting up behind the statement */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-start",
          gap: "var(--space-4)",
          padding: "var(--space-7)",
          fontFamily: "var(--font-mono)",
          fontSize: "var(--t-body)",
          lineHeight: 1.6,
          color: "var(--text-faint)",
          opacity: 0.28,
          transform: `translateY(${drift}px)`,
          pointerEvents: "none",
          maskImage: "linear-gradient(to bottom, transparent, black 18%, black 82%, transparent)",
          WebkitMaskImage: "linear-gradient(to bottom, transparent, black 18%, black 82%, transparent)",
        }}
      >
        {tiled.map((line, i) => (
          <div key={i} style={{ letterSpacing: "var(--track-caps)" }}>{line}</div>
        ))}
      </div>

      {/* the statement — dominant foreground */}
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%", position: "relative" }}>
        <div style={{ overflow: "hidden", paddingBottom: "0.12em" }}>
          <div
            style={{
              display: "inline-block",
              fontFamily: "var(--font-display-en)",
              fontWeight: 900,
              fontSize: "var(--t-display-2)",
              lineHeight: 1.04,
              letterSpacing: "var(--hero-num-track)",
              color: "var(--text)",
              transform: `translateY(${enterY}%)`,
              opacity: enterOpacity,
            }}
          >
            {tokens.map((tok, i) => {
              if (i !== hitIndex) return <span key={i}>{tok}</span>;
              // The strike-word: boxed + accent, with the signature line over it.
              return (
                <span
                  key={i}
                  style={{
                    position: "relative",
                    display: "inline-block",
                    color: "var(--accent)",
                    padding: "0 0.12em",
                    border: "var(--rule-w) solid var(--accent-soft)",
                    boxShadow: "0 0 var(--space-5) var(--accent-glow)",
                  }}
                >
                  {tok}
                  <span
                    style={{
                      position: "absolute",
                      left: 0,
                      top: "50%",
                      height: "calc(var(--rule-w) * 3)",
                      width: `${strikeW}%`,
                      background: "var(--accent)",
                      transform: "translateY(-50%)",
                    }}
                  />
                </span>
              );
            })}
          </div>
        </div>
      </div>
    </Surface>
  );
};
