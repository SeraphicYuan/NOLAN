import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// BESPOKE block: a horizontal comparison bar chart whose bars grow.
// Each bar's full length is proportional to value / max(values); the bar
// animates its width via a spring staggered from `revealFrames`, and the
// printed value counts up 0 -> value as the bar grows. ONLY semantic theme
// tokens. <Surface>-wrapped, no <Audio>. `useCurrentFrame()` is step-relative
// (Remotion resets it per Series.Sequence).
type Bar = { label: string; value: number; accent?: boolean };
export type BarChartProps = {
  title?: string;
  bars: Bar[];
  unit?: string;
  caption?: string;
  revealFrames: number[];
  words: { text: string; startFrame: number; endFrame: number }[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const BarChart: React.FC<BarChartProps> = ({ title, bars, unit, caption, revealFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const max = Math.max(...bars.map((b) => b.value), 0) || 1;

  return (
    <Surface>
      <div style={{
        display: "flex", flexDirection: "column", height: "100%",
        justifyContent: "center", alignItems: "stretch", gap: "var(--space-9)",
      }}>
        {title ? (
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)",
          }}>{title}</div>
        ) : null}

        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-7)" }}>
          {bars.map((b, i) => {
            const rf = revealFrames[i] ?? 0;
            // Spring drives both the bar's grow and the count-up (0 -> 1).
            const grow = spring({ frame: frame - rf, fps, durationInFrames: 24, config: { damping: 200 } });
            const appear = interpolate(frame, [rf, rf + 6], [0, 1], clamp);
            const fullPct = (b.value / max) * 100;
            const widthPct = grow * fullPct;
            const shown = grow * b.value;
            const isAccent = b.accent === true;

            return (
              <div key={i} style={{ opacity: appear, display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                {/* label above the bar */}
                <div style={{
                  fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
                  letterSpacing: "var(--track-caps)", textTransform: "uppercase",
                  color: isAccent ? "var(--text-2)" : "var(--text-mute)",
                }}>{b.label}</div>

                {/* track + growing bar + value at the end */}
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-5)" }}>
                  <div style={{
                    position: "relative", flex: 1, height: "var(--space-7)",
                    background: "var(--surface-2)", borderRadius: "var(--space-2)", overflow: "hidden",
                  }}>
                    <div style={{
                      position: "absolute", left: 0, top: 0, bottom: 0,
                      width: `${widthPct}%`,
                      background: isAccent ? "var(--accent)" : "var(--surface-3)",
                      borderRadius: "var(--space-2)",
                      boxShadow: isAccent ? "0 0 var(--space-5) var(--accent-glow)" : "none",
                    }} />
                  </div>
                  <div style={{
                    minWidth: "5ch", textAlign: "right",
                    fontFamily: "var(--font-display-en)", fontWeight: 900, fontSize: "var(--t-h2)", lineHeight: 1,
                    fontVariantNumeric: "tabular-nums",
                    color: isAccent ? "var(--accent)" : "var(--text-faint)",
                  } as React.CSSProperties}>
                    {shown.toFixed(1)}
                    {unit ? (
                      <span style={{
                        fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
                        color: "var(--text-mute)", marginLeft: "var(--space-2)",
                      }}>{unit}</span>
                    ) : null}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {caption ? (
          <div style={{
            fontFamily: "var(--font-body)", fontSize: "var(--t-small)", color: "var(--text-mute)",
          }}>{caption}</div>
        ) : null}
      </div>
    </Surface>
  );
};
