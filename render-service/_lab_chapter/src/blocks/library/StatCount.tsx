import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";
import { useCountToWord, type Word } from "../../primitives/RollingNumber";

// Chapter-library block: N big numbers (1–4) that count up, each landing exactly
// on its spoken word, with labels. Generalized from the bespoke YearsStat hook
// block — the per-word count-up mechanic now lives in the RollingNumber
// primitive (`useCountToWord`), and the layout flexes to any stat count instead
// of hard-coding a 2-up grid. Wraps content in <Surface>, uses ONLY semantic
// theme tokens, no <Audio>. `useCurrentFrame()` is step-relative.
type Stat = { value: number; word: string; label: string; sub?: string;
  prefix?: string; suffix?: string; decimals?: number };

// Display the live count with grouping + optional decimals/prefix/suffix, so a
// spec can show "1,000+" or "1.95σ" while still driving a numeric count-up.
// (Spec props must be JSON-serializable — strings, not a format callback.)
const fmtStat = (live: number, st: Stat) =>
  `${st.prefix ?? ""}${live.toLocaleString("en-US", {
    minimumFractionDigits: st.decimals ?? 0, maximumFractionDigits: st.decimals ?? 0,
  })}${st.suffix ?? ""}`;
export type StatCountProps = {
  stats?: Stat[];
  closer?: string;
  accentPhrase?: string;
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const DEFAULT_STATS: Stat[] = [
  {
    value: 15,
    word: "fifteen",
    label: "YEARS RESEARCHING",
    sub: "psychology · philosophy · money · religion · startups · internet",
  },
  { value: 5, word: "five", label: "YEARS WRITING IN PUBLIC" },
];

const DEFAULT_CLOSER = "the same patterns kept showing up";
const DEFAULT_ACCENT = "same patterns";

export const StatCount: React.FC<StatCountProps> = ({
  stats = DEFAULT_STATS,
  closer = DEFAULT_CLOSER,
  accentPhrase = DEFAULT_ACCENT,
  revealFrames,
  words,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Closer line lands at the last reveal, or the final ~20% if none provided.
  const closerRf = revealFrames.length
    ? revealFrames[revealFrames.length - 1]
    : Math.round(durationInFrames * 0.8);
  const closerS = spring({ frame: frame - closerRf, fps, durationInFrames: 18, config: { damping: 200 } });

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%", gap: "var(--space-9)" }}>
        {/* Hero numbers in an even flex row, each counting up to its spoken word. */}
        <div style={{ display: "flex", alignItems: "stretch", justifyContent: "center", gap: "var(--space-9)" }}>
          {stats.map((st, i) => {
            // SIGNATURE: anchor the count-up to when this number's word is spoken.
            const { live, start, rolling } = useCountToWord(words, st.word, st.value, {
              fallback: revealFrames[i] ?? 0, decimals: st.decimals ?? 0,
            });
            // SKELETON: the label + a dim number placeholder appear EARLY (a short
            // entrance from the beat's start, independent of the spoken word), so the
            // stage is never empty while a long narration builds up to the number.
            // The NUMBER then counts up + brightens on its word (`active`).
            const scaffoldAt = 6 + i * 4;
            const scaffold = interpolate(frame, [scaffoldAt, scaffoldAt + 14], [0, 1], clamp);
            const y = interpolate(frame, [scaffoldAt, scaffoldAt + 16], [28, 0], clamp);
            const active = frame >= start;

            return (
              <React.Fragment key={i}>
                {/* Thin rule between adjacent stats. */}
                {i > 0 ? (
                  <span
                    style={{
                      alignSelf: "center",
                      width: "var(--rule-w)",
                      height: "30%",
                      background: "var(--rule)",
                      opacity: scaffold * 0.6,
                    }}
                  />
                ) : null}
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "flex-start",
                    flex: 1,
                    opacity: scaffold,
                    transform: `translateY(${y}px)`,
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--font-display-en)",
                      fontWeight: 900,
                      fontSize: "var(--t-display-1)",
                      lineHeight: 0.9,
                      letterSpacing: "var(--hero-num-track)",
                      // dim placeholder until the word lands, then accent + glow while ticking.
                      color: active ? "var(--accent)" : "var(--text-faint)",
                      textShadow: active
                        ? `0 0 ${interpolate(rolling, [0, 1], [12, 40], clamp)}px var(--accent-glow)`
                        : "none",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {active ? fmtStat(live, st) : "—"}
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "var(--t-micro)",
                      letterSpacing: "var(--track-caps)",
                      textTransform: "uppercase",
                      color: "var(--text-mute)",
                      marginTop: "var(--space-5)",
                      textAlign: "center",
                    }}
                  >
                    {st.label}
                  </div>
                  {st.sub ? (
                    <div
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "var(--t-micro)",
                        color: "var(--text-faint)",
                        marginTop: "var(--space-2)",
                        textAlign: "center",
                        maxWidth: "22ch",
                        lineHeight: 1.5,
                      }}
                    >
                      {st.sub}
                    </div>
                  ) : null}
                </div>
              </React.Fragment>
            );
          })}
        </div>

        {/* Closing line — `accentPhrase` emphasized in --accent if present. */}
        <div
          style={{
            fontFamily: "var(--font-display-en)",
            fontWeight: 900,
            fontSize: "var(--t-h2)",
            lineHeight: 1.1,
            textAlign: "center",
            color: "var(--text)",
            opacity: interpolate(frame, [closerRf, closerRf + 5], [0, 1], clamp),
            transform: `translateY(${interpolate(closerS, [0, 1], [24, 0])}px)`,
          }}
        >
          {renderCloser(closer, accentPhrase)}
        </div>
      </div>
    </Surface>
  );
};

// Highlight `accentPhrase` within the closer in --accent; rest in --text.
function renderCloser(closer: string, accentPhrase?: string): React.ReactNode {
  if (!accentPhrase) return closer;
  const idx = closer.toLowerCase().indexOf(accentPhrase.toLowerCase());
  if (idx === -1) return closer;
  return (
    <>
      {closer.slice(0, idx)}
      <span style={{ color: "var(--accent)" }}>{closer.slice(idx, idx + accentPhrase.length)}</span>
      {closer.slice(idx + accentPhrase.length)}
    </>
  );
}
