import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// StepFlow — a numbered sequential process flow for sequence / causality / method
// (a methods section, an algorithm, a pipeline). Each step is a NODE: a mono index
// badge (01, 02, …) in an --accent ring, a display label, and an optional detail
// line. Nodes are joined by connectors (--rule) that DRAW ON one at a time. Steps
// reveal one-at-a-time at revealFrames[i]: the node springs in (opacity + slight
// rise) and the connector toward the next node draws on (scaleX). The most-recently
// revealed node is "active" — its badge fills --accent and glows; earlier nodes
// settle to a calmer --text-2 state. Horizontal = left→right row, vertical = top→down
// column. Wraps content in <Surface>, uses ONLY semantic theme tokens, and is a pure
// function of useCurrentFrame() (no random/dates/timers). No <Audio> — the Chapter
// driver supplies the step narration; useCurrentFrame() is relative to this step.
type Word = { text: string; startFrame: number; endFrame: number };
type Step = { label: string; detail?: string };
export type StepFlowProps = {
  kicker?: string;
  orientation?: "horizontal" | "vertical";
  steps: Step[];                // 2–5 steps
  revealFrames: number[];       // one cue per step
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Is the narration mid-word at this frame? Drives a subtle "speaking" lift on the
// active node so the flow breathes with the voice-over (deterministic — pure frame).
const isSpeaking = (frame: number, words: Word[]): boolean => {
  for (const w of words) if (frame >= w.startFrame && frame < w.endFrame) return true;
  return false;
};

export const StepFlow: React.FC<StepFlowProps> = ({
  kicker,
  orientation = "horizontal",
  steps,
  revealFrames,
  words,
  durationInFrames: _durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const horizontal = orientation === "horizontal";

  // The active step = the latest one whose cue has fired. Its badge fills + glows;
  // earlier ones calm down once a later step has been revealed.
  const rf = (i: number) => revealFrames[i] ?? 0;
  let activeIndex = -1;
  for (let i = 0; i < steps.length; i++) if (frame >= rf(i)) activeIndex = i;
  const speaking = activeIndex >= 0 && isSpeaking(frame, words);

  const kickerRf = rf(0) - 8;
  const kickerS = spring({ frame: frame - kickerRf, fps, durationInFrames: 16, config: { damping: 200 } });

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
        {kicker ? (
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)",
            marginBottom: "var(--space-9)",
            opacity: interpolate(frame, [kickerRf, kickerRf + 5], [0, 1], clamp),
            transform: `translateX(${interpolate(kickerS, [0, 1], [-24, 0])}px)`,
          }}>{kicker}</div>
        ) : null}

        <div style={{
          display: "flex",
          flexDirection: horizontal ? "row" : "column",
          alignItems: horizontal ? "flex-start" : "stretch",
          justifyContent: "center",
          gap: 0,
        }}>
          {steps.map((step, i) => {
            const r = rf(i);
            const s = spring({ frame: frame - r, fps, durationInFrames: 18, config: { damping: 200 } });
            const appear = interpolate(frame, [r, r + 5], [0, 1], clamp);
            const rise = interpolate(s, [0, 1], [horizontal ? 26 : 18, 0]);
            const isActive = i === activeIndex;
            const isLast = i === steps.length - 1;

            // Connector toward the NEXT node draws on once THIS node has revealed.
            const connS = spring({ frame: frame - r, fps, durationInFrames: 20, config: { damping: 200 } });

            // Active badge fills + glows; revealed-but-past badges calm to --text-2.
            const badgeFill = isActive ? "var(--accent-fill)" : "transparent";
            const badgeRing = isActive ? "var(--accent)" : "var(--rule)";
            const badgeText = isActive ? "var(--accent)" : "var(--text-2)";
            const glowPulse = isActive ? (speaking ? 1 : 0.6) : 0;

            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  flexDirection: horizontal ? "row" : "column",
                  alignItems: horizontal ? "flex-start" : "stretch",
                  flex: horizontal ? "1 1 0" : "0 0 auto",
                  minWidth: 0,
                }}
              >
                {/* NODE */}
                <div style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: horizontal ? "center" : "flex-start",
                  textAlign: horizontal ? "center" : "left",
                  flex: horizontal ? "0 0 auto" : "1 1 0",
                  opacity: appear,
                  transform: `translateY(${rise}px)`,
                }}>
                  {/* Index badge */}
                  <div style={{
                    display: "flex", alignItems: "center", justifyContent: "center",
                    width: "var(--space-9)", height: "var(--space-9)",
                    borderRadius: "50%",
                    border: `var(--rule-w) solid ${badgeRing}`,
                    background: badgeFill,
                    boxShadow: `0 0 0 calc(var(--space-2) * ${glowPulse}) var(--accent-glow)`,
                    transform: `scale(${interpolate(s, [0, 1], [0.7, 1])})`,
                    flex: "0 0 auto",
                  }}>
                    <span style={{
                      fontFamily: "var(--font-mono)", fontSize: "var(--t-body)",
                      color: badgeText, lineHeight: 1,
                    }}>{String(i + 1).padStart(2, "0")}</span>
                  </div>

                  {/* Label */}
                  <div style={{
                    fontFamily: "var(--font-display-cn)", fontWeight: 900,
                    fontSize: "var(--t-h2)", lineHeight: 1.08,
                    color: isActive ? "var(--text)" : "var(--text-2)",
                    marginTop: "var(--space-5)",
                    maxWidth: horizontal ? "14ch" : undefined,
                  }}>{step.label}</div>

                  {/* Optional detail */}
                  {step.detail ? (
                    <div style={{
                      fontFamily: "var(--font-body)", fontSize: "var(--t-micro)",
                      color: "var(--text-2)", lineHeight: 1.4,
                      marginTop: "var(--space-3)",
                      maxWidth: horizontal ? "18ch" : "60ch",
                    }}>{step.detail}</div>
                  ) : null}
                </div>

                {/* CONNECTOR toward the next node (drawn from this node outward) */}
                {!isLast ? (
                  horizontal ? (
                    <div style={{
                      flex: "1 1 0",
                      display: "flex", alignItems: "center",
                      // Align the rule with the vertical center of the index badge.
                      height: "var(--space-9)",
                      padding: "0 var(--space-4)",
                    }}>
                      <div style={{ position: "relative", width: "100%", height: "var(--rule-w)" }}>
                        <div style={{
                          position: "absolute", inset: 0,
                          background: "var(--rule)",
                          transform: `scaleX(${connS})`, transformOrigin: "left center",
                        }} />
                        {/* arrowhead */}
                        <div style={{
                          position: "absolute", right: 0, top: "50%",
                          width: "var(--space-3)", height: "var(--space-3)",
                          borderTop: `var(--rule-w) solid var(--rule)`,
                          borderRight: `var(--rule-w) solid var(--rule)`,
                          transform: `translate(50%, -50%) rotate(45deg) scale(${interpolate(connS, [0.7, 1], [0, 1], clamp)})`,
                        }} />
                      </div>
                    </div>
                  ) : (
                    <div style={{
                      // vertical connector under the badge column (badge is --space-9 wide)
                      width: "var(--space-9)",
                      display: "flex", justifyContent: "center",
                      height: "var(--space-8)",
                      padding: "var(--space-3) 0",
                    }}>
                      <div style={{ position: "relative", width: "var(--rule-w)", height: "100%" }}>
                        <div style={{
                          position: "absolute", inset: 0,
                          background: "var(--rule)",
                          transform: `scaleY(${connS})`, transformOrigin: "top center",
                        }} />
                        <div style={{
                          position: "absolute", bottom: 0, left: "50%",
                          width: "var(--space-3)", height: "var(--space-3)",
                          borderRight: `var(--rule-w) solid var(--rule)`,
                          borderBottom: `var(--rule-w) solid var(--rule)`,
                          transform: `translate(-50%, 50%) rotate(45deg) scale(${interpolate(connS, [0.7, 1], [0, 1], clamp)})`,
                        }} />
                      </div>
                    </div>
                  )
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </Surface>
  );
};
