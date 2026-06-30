import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";
import { type Word } from "../../primitives/RollingNumber";

// Rebuild of NOLAN's PIL ProgressBarRenderer: a single-bar progress indicator.
// A mono-caps `label` fades in, a rounded track (--surface-2) appears, then an
// --accent fill grows its width 0 -> `progress` via a spring keyed to
// revealFrames[0]. A --font-display-en percentage readout rides the fill's
// leading edge, counting 0 -> round(progress*100)% in lockstep with the spring.
// Optional `milestones` render as --rule ticks + mono-caps labels evenly along
// the track, brightening to --text-2 as the fill sweeps past each.
// ONLY semantic theme tokens; <Surface>-wrapped; no random/date/timers/CSS-
// transitions. `useCurrentFrame()` is step-relative (Remotion resets per step).
export type ProgressBarProps = {
  progress: number; // 0.0–1.0
  label?: string;
  showPercentage?: boolean; // default true
  milestones?: string[]; // optional tick labels spaced along the track
  revealFrames: number[]; // [in cue]
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const ProgressBar: React.FC<ProgressBarProps> = ({
  progress,
  label,
  showPercentage = true,
  milestones,
  revealFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const target = Math.max(0, Math.min(1, progress));
  const rf = revealFrames[0] ?? 0;

  // Single spring is the source of truth: it drives the fill width, the readout
  // count-up, and the milestone brightening so everything stays in lockstep.
  const grow = spring({ frame: frame - rf, fps, durationInFrames: 30, config: { damping: 200 } });
  const filled = grow * target; // current fraction, 0 -> target
  const fillPct = filled * 100;
  const shownPct = Math.round(filled * 100);

  // Label fades in just ahead of the bar; track appears with it.
  const labelIn = interpolate(frame, [rf, rf + 8], [0, 1], clamp);
  const trackIn = interpolate(frame, [rf, rf + 6], [0, 1], clamp);

  const ticks = milestones ?? [];

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
        }}
      >
        {label ? (
          <div
            style={{
              opacity: labelIn,
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

        {/* track + growing fill + leading-edge readout + milestone ticks */}
        <div style={{ opacity: trackIn, position: "relative", paddingTop: "var(--space-9)" }}>
          {/* the readout sits above the fill's leading edge, counting up */}
          {showPercentage ? (
            <div
              style={{
                position: "absolute",
                top: 0,
                left: `${fillPct}%`,
                transform: "translateX(-50%)",
                fontFamily: "var(--font-display-en)",
                fontSize: "var(--t-h2)",
                fontWeight: 900,
                lineHeight: 1,
                color: "var(--accent)",
                fontVariantNumeric: "tabular-nums",
                textShadow: `0 0 ${interpolate(grow, [0, 1], [8, 32], clamp)}px var(--accent-glow)`,
                whiteSpace: "nowrap",
              }}
            >
              {shownPct}
              <span style={{ fontSize: "0.5em", marginLeft: "var(--space-1, 2px)" }}>%</span>
            </div>
          ) : null}

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
                boxShadow: "0 0 var(--space-5) var(--accent-glow)",
              }}
            />
          </div>

          {/* milestone ticks + labels evenly spaced along the track */}
          {ticks.length > 0
            ? ticks.map((m, i) => {
                // Even spacing across the track interior (skip the 0% edge).
                const frac = (i + 1) / ticks.length;
                const passed = filled >= frac;
                return (
                  <div
                    key={i}
                    style={{
                      position: "absolute",
                      top: "var(--space-9)",
                      left: `${frac * 100}%`,
                      transform: "translateX(-50%)",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: "var(--space-2)",
                    }}
                  >
                    <div
                      style={{
                        width: "2px",
                        height: "var(--space-7)",
                        background: "var(--rule)",
                        opacity: passed ? 1 : 0.5,
                      }}
                    />
                    <div
                      style={{
                        marginTop: "var(--space-2)",
                        fontFamily: "var(--font-mono)",
                        fontSize: "var(--t-micro)",
                        letterSpacing: "var(--track-caps)",
                        textTransform: "uppercase",
                        whiteSpace: "nowrap",
                        color: passed ? "var(--text-2)" : "var(--text-mute)",
                      }}
                    >
                      {m}
                    </div>
                  </div>
                );
              })
            : null}
        </div>
      </div>
    </Surface>
  );
};
