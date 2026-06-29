import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../Surface";

// Chapter-library block: three "archetype" cards each maxed on one axis and
// crashed on the rest — the point being that well-roundedness is rare. Wraps
// content in <Surface>, uses ONLY semantic theme tokens, reveals one card per
// frame in `revealFrames` (i=0,1,2) then a closing line at revealFrames[3].
// No <Audio> — the Chapter driver supplies the step narration.
// `useCurrentFrame()` is relative to this step's start.
type Card = {
  name: string;
  maxLabel: string;
  maxVal: number; // 0..1, the maxed trait (filled in --accent)
  lowLabel: string;
  lowVal: number; // 0..1, the crashed trait (filled in --text-faint)
  flaw: string;
};
export type ArchetypeCardsProps = {
  kicker?: string;
  cards: Card[];
  closer: string;
  revealFrames: number[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// One horizontal stat bar that grows its fill width via spring when its card
// reveals. `tone` selects the fill token: --accent (maxed) vs --text-faint
// (crashed).
const StatBar: React.FC<{
  label: string;
  value: number;
  tone: "max" | "low";
  rf: number;
}> = ({ label, value, tone, rf }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // Bar grows after the card has begun settling.
  const grow = spring({ frame: frame - (rf + 4), fps, durationInFrames: 22, config: { damping: 200 } });
  const w = interpolate(grow, [0, 1], [0, Math.max(0, Math.min(1, value)) * 100], clamp);
  const fill = tone === "max" ? "var(--accent)" : "var(--text-faint)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
        letterSpacing: "var(--track-caps)", textTransform: "uppercase",
        color: tone === "max" ? "var(--text-2)" : "var(--text-mute)",
      }}>{label}</div>
      <div style={{ height: "var(--space-3)", background: "var(--surface-3)", borderRadius: 999, overflow: "hidden" }}>
        <div style={{ width: `${w}%`, height: "100%", background: fill, borderRadius: 999 }} />
      </div>
    </div>
  );
};

export const ArchetypeCards: React.FC<ArchetypeCardsProps> = ({ kicker, cards, closer, revealFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Kicker rides in just before the first card.
  const kickerRf = (revealFrames[0] ?? 0) - 6;
  const kickerS = spring({ frame: frame - kickerRf, fps, durationInFrames: 16, config: { damping: 200 } });

  // Closer at revealFrames[3].
  const closerRf = revealFrames[3] ?? 0;
  const closerS = spring({ frame: frame - closerRf, fps, durationInFrames: 18, config: { damping: 200 } });

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
        {kicker ? (
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)",
            marginBottom: "var(--space-7)",
            opacity: interpolate(frame, [kickerRf, kickerRf + 5], [0, 1], clamp),
            transform: `translateX(${interpolate(kickerS, [0, 1], [-24, 0])}px)`,
          }}>{kicker}</div>
        ) : null}

        {/* Three cards in a row across the stage. */}
        <div style={{ display: "flex", gap: "var(--space-7)", alignItems: "stretch" }}>
          {cards.map((c, i) => {
            const rf = revealFrames[i] ?? 0;
            const s = spring({ frame: frame - rf, fps, durationInFrames: 18, config: { damping: 200 } });
            const appear = interpolate(frame, [rf, rf + 5], [0, 1], clamp);
            const y = interpolate(s, [0, 1], [60, 0]);
            const scale = interpolate(s, [0, 1], [0.92, 1]);
            return (
              <div key={i} style={{
                flex: 1,
                display: "flex", flexDirection: "column", gap: "var(--space-6)",
                background: "var(--surface-2)",
                padding: "var(--space-7)",
                borderTop: "var(--rule-w) solid var(--accent)",
                opacity: appear,
                transform: `translateY(${y}px) scale(${scale})`,
                transformOrigin: "center bottom",
              }}>
                <div style={{
                  fontFamily: "var(--font-display-en)", fontWeight: 900,
                  fontSize: "var(--t-h1)", lineHeight: 1, letterSpacing: "var(--hero-num-track)",
                  color: "var(--text)",
                }}>{c.name}</div>

                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
                  <StatBar label={c.maxLabel} value={c.maxVal} tone="max" rf={rf} />
                  <StatBar label={c.lowLabel} value={c.lowVal} tone="low" rf={rf} />
                </div>

                <div style={{
                  fontFamily: "var(--font-body)", fontSize: "var(--t-body)",
                  color: "var(--text-mute)", lineHeight: 1.3, marginTop: "auto",
                }}>{c.flaw}</div>
              </div>
            );
          })}
        </div>

        {/* Closing line below the row. */}
        <div style={{
          marginTop: "var(--space-9)",
          fontFamily: "var(--font-display-en)", fontWeight: 900,
          fontSize: "var(--t-h1)", lineHeight: 1.05, color: "var(--text)",
          opacity: interpolate(frame, [closerRf, closerRf + 6], [0, 1], clamp),
          transform: `translateY(${interpolate(closerS, [0, 1], [40, 0])}px)`,
        }}>{closer}</div>
      </div>
    </Surface>
  );
};
