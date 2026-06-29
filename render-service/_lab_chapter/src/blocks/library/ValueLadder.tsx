import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";
import { useCountToWord } from "../../primitives/RollingNumber";

// LIBRARY block: "a value growing across a time/sequence axis with milestone
// markers." Generalized from the bespoke CompoundLadder (doubling-money beat). The
// milestones (`rungs`) are laid on a horizontal AXIS at x ∝ `year`, so the GAPS
// WIDEN when growth accelerates. The HERO is one big value that ROLLS from the
// previous milestone to the active one — and, mirroring the count-up primitive, it
// settles EXACTLY as the active milestone's `word` is spoken (driven by the per-word
// `words` timeline). Formatting (`$`, units…) and the axis unit are now props, so
// the same mechanic serves money, users, distance, etc. Wraps content in <Surface>,
// semantic tokens only, no <Audio>. `useCurrentFrame()` is step-relative.
type WordFrame = { text: string; startFrame: number; endFrame: number };
type Rung = { year: number; amount: number; word: string };
export type ValueLadderProps = {
  kicker?: string;
  rungs?: Rung[];
  // JSON-serializable formatting (spec-settable). `format` overrides if given.
  prefix?: string;
  suffix?: string;
  format?: (n: number) => string;
  axisUnit?: string;
  revealFrames: number[];
  words: WordFrame[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const DEFAULT_RUNGS: Rung[] = [
  { year: 0, amount: 1000, word: "thousand" }, // seed
  { year: 9, amount: 2000, word: "two" },
  { year: 18, amount: 4000, word: "four" },
  { year: 30, amount: 10000, word: "ten" },
];

// Axis padding (%) — rungs are placed at x ∝ year between these bounds.
const AXIS_LEFT = 9;
const AXIS_RIGHT = 91;

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

// startFrame of the first word matching `word` (normalized), else fallback.
const wordStart = (words: WordFrame[], word: string, fallback: number) => {
  const w = words.find((x) => norm(x.text) === norm(word));
  return w ? w.startFrame : fallback;
};

export const ValueLadder: React.FC<ValueLadderProps> = ({
  kicker,
  rungs = DEFAULT_RUNGS,
  prefix = "",
  suffix = "",
  format = (n: number) => `${prefix}${n.toLocaleString("en-US")}${suffix}`,
  axisUnit = "yr",
  revealFrames,
  words,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const kickerText = kicker ?? format(rungs[0].amount);
  const maxYear = Math.max(...rungs.map((r) => r.year), 1);
  const xForYear = (year: number) =>
    AXIS_LEFT + (year / maxYear) * (AXIS_RIGHT - AXIS_LEFT);

  // Per-rung roll trigger: when its value-word is spoken (fallback to reveal).
  const rollStart = (i: number) =>
    wordStart(words, rungs[i].word, revealFrames[i] ?? 0);

  // The axis draws in with the first reveal and sweeps left -> right.
  const axisRf = revealFrames[0] ?? 0;
  const axisS = spring({ frame: frame - axisRf, fps, durationInFrames: 28, config: { damping: 200 } });

  // Active rung = the latest one whose word/roll has begun. The HERO mirrors it.
  let activeIdx = 0;
  for (let i = 0; i < rungs.length; i++) if (frame >= rollStart(i)) activeIdx = i;

  // SIGNATURE: hero value rolls prev -> target across the word window so the digits
  // land precisely as the value is said — via the shared count-to-word primitive.
  const prev = activeIdx > 0 ? rungs[activeIdx - 1].amount : 0;
  const target = rungs[activeIdx].amount;
  const { live, rolling } = useCountToWord(words, rungs[activeIdx].word, target, {
    from: prev,
    fallback: revealFrames[activeIdx] ?? 0,
  });
  const heroAppear = interpolate(frame, [rollStart(0), rollStart(0) + 5], [0, 1], clamp);

  const kickerRf = axisRf - 8;
  const kickerS = spring({ frame: frame - kickerRf, fps, durationInFrames: 16, config: { damping: 200 } });

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%", gap: "var(--space-9)" }}>
        {/* Kicker — context label for the ladder. */}
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
          letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)",
          textAlign: "center",
          opacity: interpolate(frame, [kickerRf, kickerRf + 5], [0, 1], clamp),
          transform: `translateY(${interpolate(kickerS, [0, 1], [-16, 0])}px)`,
        }}>{kickerText}</div>

        {/* ---- HERO ROLLING NUMBER -------------------------------------- */}
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          opacity: heroAppear,
        }}>
          <div style={{
            fontFamily: "var(--font-display-en)", fontWeight: 900,
            fontSize: "var(--t-display-1)", lineHeight: 0.9,
            letterSpacing: "var(--hero-num-track)", color: "var(--accent)",
            fontVariantNumeric: "tabular-nums",
            textShadow: `0 0 ${interpolate(rolling, [0, 1], [14, 44], clamp)}px var(--accent-glow)`,
          }}>{format(live)}</div>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase",
            color: "var(--text-mute)", marginTop: "var(--space-5)",
          }}>{rungs[activeIdx].year === 0 ? "start" : `after ${rungs[activeIdx].year} ${axisUnit}`}</div>
        </div>

        {/* ---- TIME / SEQUENCE AXIS + MILESTONE RUNGS ------------------- */}
        <div style={{ position: "relative", height: "var(--space-9)", marginTop: "var(--space-7)" }}>
          {/* Axis line draws itself left-to-right. */}
          <div style={{
            position: "absolute", left: `${AXIS_LEFT}%`, right: `${100 - AXIS_RIGHT}%`, top: "50%",
            height: "var(--rule-w)", background: "var(--rule)",
            transform: `translateY(-50%) scaleX(${axisS})`, transformOrigin: "left center",
          }} />

          {rungs.map((r, i) => {
            const rf = revealFrames[i] ?? rollStart(i);
            const s = spring({ frame: frame - rf, fps, durationInFrames: 18, config: { damping: 200 } });
            const appear = interpolate(frame, [rf, rf + 5], [0, 1], clamp);
            const isActive = i === activeIdx;
            return (
              <div key={i} style={{ position: "absolute", left: `${xForYear(r.year)}%`, top: "50%", width: 0, opacity: appear }}>
                {/* Amount above the tick — active rung in --accent, settled ones muted. */}
                <div style={{
                  position: "absolute", left: "50%", bottom: "var(--space-6)", transform: "translateX(-50%)",
                  whiteSpace: "nowrap", textAlign: "center",
                  fontFamily: "var(--font-display-en)", fontWeight: 900,
                  fontSize: "var(--t-h2)", lineHeight: 1,
                  fontVariantNumeric: "tabular-nums",
                  color: isActive ? "var(--accent)" : "var(--text-2)",
                }}>{format(r.amount)}</div>
                {/* Tick dot on the axis. */}
                <span style={{
                  position: "absolute", left: "50%", top: "50%",
                  width: "var(--space-4)", height: "var(--space-4)", borderRadius: "50%",
                  background: isActive ? "var(--accent)" : "var(--text)",
                  boxShadow: isActive ? "0 0 0 var(--space-2) var(--accent-glow)" : "none",
                  transform: `translate(-50%, -50%) scale(${s})`,
                }} />
                {/* Axis tick below the line — --font-mono. */}
                <div style={{
                  position: "absolute", left: "50%", top: "var(--space-6)", transform: "translateX(-50%)",
                  whiteSpace: "nowrap", textAlign: "center",
                  fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
                  letterSpacing: "var(--track-caps)", textTransform: "uppercase",
                  color: isActive ? "var(--text)" : "var(--text-faint)",
                }}>{`${axisUnit} ${r.year}`}</div>
              </div>
            );
          })}
        </div>
      </div>
    </Surface>
  );
};
