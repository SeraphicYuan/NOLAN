import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// Chapter-library block: a horizontal timeline that makes one argument visually —
// the cross-domain "old models" sit FAR LEFT (predating everything), while the
// Internet / AI ticks cluster FAR RIGHT, and the wide empty gap between them IS
// the point. A final money note lands struck-through underneath. Wraps content in
// <Surface>, uses ONLY semantic theme tokens, reveals each element at the frame
// given in `revealFrames` (computed upstream from the narration). No <Audio> — the
// Chapter driver supplies the step narration. `useCurrentFrame()` is relative to
// this step's start.
type Anchor = { label: string };
type Tick = { label: string };
export type TimelineProps = {
  kicker?: string;
  headline?: string;
  anchor: Anchor;
  ticks: Tick[];
  note: string;
  moneyNote: string;
  revealFrames: number[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Layout constants: anchor near the left edge, ticks crowded to the right — the
// big gap between ~12% and ~80% is deliberately the visual argument.
const ANCHOR_X = 12; // %
const TICK_START = 80; // %
const TICK_SPAN = 16; // % spread across the ticks

export const Timeline: React.FC<TimelineProps> = ({
  kicker,
  headline,
  anchor,
  ticks,
  note,
  moneyNote,
  revealFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Reveal schedule:
  //   [0]            -> anchor (far-left marker)
  //   [1..ticks]     -> each right-side tick in turn
  //   [+1]           -> the bracket note spanning the gap
  //   [last]         -> the struck-through money note
  const anchorRf = revealFrames[0] ?? 0;
  const tickRf = (i: number) => revealFrames[1 + i] ?? anchorRf;
  const noteRf = revealFrames[1 + ticks.length] ?? tickRf(ticks.length - 1);
  const moneyRf = revealFrames[revealFrames.length - 1] ?? noteRf;

  // The axis starts drawing with the anchor and sweeps left-to-right.
  const axisRf = anchorRf;
  const axisS = spring({ frame: frame - axisRf, fps, durationInFrames: 26, config: { damping: 200 } });

  // Tick x-positions: evenly spaced from TICK_START rightward.
  const tickX = (i: number) =>
    ticks.length <= 1 ? TICK_START : TICK_START + (i / (ticks.length - 1)) * TICK_SPAN;
  const lastTickX = tickX(ticks.length - 1);

  const kickerRf = anchorRf - 8;
  const kickerS = spring({ frame: frame - kickerRf, fps, durationInFrames: 16, config: { damping: 200 } });

  const headRf = anchorRf - 4;
  const headS = spring({ frame: frame - headRf, fps, durationInFrames: 18, config: { damping: 200 } });

  // Bracket spans from the anchor to the last tick once the note fires.
  const bracketW = interpolate(
    spring({ frame: frame - noteRf, fps, durationInFrames: 22, config: { damping: 200 } }),
    [0, 1],
    [0, lastTickX - ANCHOR_X],
    clamp,
  );
  const noteAppear = interpolate(frame, [noteRf + 4, noteRf + 12], [0, 1], clamp);

  // Money strike draws across the "money" chip after it appears.
  const moneyS = spring({ frame: frame - moneyRf, fps, durationInFrames: 20, config: { damping: 200 } });
  const moneyAppear = interpolate(frame, [moneyRf, moneyRf + 5], [0, 1], clamp);
  const strikeW = interpolate(moneyS, [0.4, 1], [0, 100], clamp);

  const Dot: React.FC<{ accent?: boolean; s: number }> = ({ accent, s }) => (
    <span style={{
      position: "absolute", left: "50%", top: "50%",
      width: "var(--space-4)", height: "var(--space-4)", borderRadius: "50%",
      background: accent ? "var(--accent)" : "var(--text)",
      boxShadow: accent ? "0 0 0 var(--space-2) var(--accent-glow)" : "none",
      transform: `translate(-50%, -50%) scale(${s})`,
    }} />
  );

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
        {kicker ? (
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)",
            marginBottom: "var(--space-5)",
            opacity: interpolate(frame, [kickerRf, kickerRf + 5], [0, 1], clamp),
            transform: `translateX(${interpolate(kickerS, [0, 1], [-24, 0])}px)`,
          }}>{kicker}</div>
        ) : null}

        {headline ? (
          <div style={{ overflow: "hidden", marginBottom: "var(--space-9)", paddingBottom: "0.08em" }}>
            <div style={{
              fontFamily: "var(--font-display-en)", fontWeight: 900,
              fontSize: "var(--t-h1)", lineHeight: 1.04, letterSpacing: "var(--hero-num-track)",
              transform: `translateY(${interpolate(headS, [0, 1], [110, 0])}%)`,
              opacity: interpolate(frame, [headRf, headRf + 4], [0, 1], clamp),
            }}>{headline}</div>
          </div>
        ) : null}

        {/* ---- AXIS + MARKERS ------------------------------------------- */}
        <div style={{ position: "relative", height: "var(--space-9)" }}>
          {/* The axis line draws itself left-to-right. */}
          <div style={{
            position: "absolute", left: 0, right: 0, top: "50%",
            height: "var(--rule-w)", background: "var(--rule)",
            transform: `translateY(-50%) scaleX(${axisS})`, transformOrigin: "left center",
          }} />

          {/* Bracket note spanning anchor -> ticks, drawn under the axis. */}
          <div style={{
            position: "absolute", top: "calc(50% + var(--space-5))",
            left: `${ANCHOR_X}%`, width: `${bracketW}%`, height: "var(--space-4)",
            borderLeft: "var(--rule-w) solid var(--rule)",
            borderRight: "var(--rule-w) solid var(--rule)",
            borderBottom: "var(--rule-w) solid var(--rule)",
          }} />
          <div style={{
            position: "absolute", top: "calc(50% + var(--space-6))",
            left: `${ANCHOR_X}%`, width: `${lastTickX - ANCHOR_X}%`,
            textAlign: "center",
            fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)",
            opacity: noteAppear,
          }}>{note}</div>

          {/* Anchor (far left, accent). */}
          {(() => {
            const s = spring({ frame: frame - anchorRf, fps, durationInFrames: 16, config: { damping: 200 } });
            const appear = interpolate(frame, [anchorRf, anchorRf + 5], [0, 1], clamp);
            return (
              <div style={{ position: "absolute", left: `${ANCHOR_X}%`, top: "50%", width: 0, opacity: appear }}>
                <Dot accent s={s} />
                <div style={{
                  position: "absolute", left: "50%", bottom: "var(--space-6)", transform: "translateX(-50%)",
                  whiteSpace: "nowrap", textAlign: "center",
                  fontFamily: "var(--font-display-en)", fontWeight: 900,
                  fontSize: "var(--t-h2)", lineHeight: 1, color: "var(--accent)",
                }}>{anchor.label}</div>
              </div>
            );
          })()}

          {/* Ticks (far right, in --text). */}
          {ticks.map((t, i) => {
            const rf = tickRf(i);
            const s = spring({ frame: frame - rf, fps, durationInFrames: 16, config: { damping: 200 } });
            const appear = interpolate(frame, [rf, rf + 5], [0, 1], clamp);
            return (
              <div key={i} style={{ position: "absolute", left: `${tickX(i)}%`, top: "50%", width: 0, opacity: appear }}>
                <Dot s={s} />
                <div style={{
                  position: "absolute", left: "50%", bottom: "var(--space-6)", transform: "translateX(-50%)",
                  whiteSpace: "nowrap", textAlign: "center",
                  fontFamily: "var(--font-display-en)", fontWeight: 900,
                  fontSize: "var(--t-h2)", lineHeight: 1, color: "var(--text)",
                }}>{t.label}</div>
              </div>
            );
          })}
        </div>

        {/* ---- MONEY NOTE (bottom) -------------------------------------- */}
        <div style={{
          display: "flex", alignItems: "center", gap: "var(--space-5)",
          marginTop: "var(--space-9)", opacity: moneyAppear,
          transform: `translateY(${interpolate(moneyS, [0, 1], [16, 0])}px)`,
        }}>
          <span style={{
            position: "relative", display: "inline-block",
            padding: "var(--space-2) var(--space-4)",
            border: "var(--rule-w) solid var(--rule)", borderRadius: "var(--space-2)",
            background: "var(--surface-2)",
            fontFamily: "var(--font-display-en)", fontWeight: 900,
            fontSize: "var(--t-h2)", lineHeight: 1, color: "var(--text-mute)",
          }}>
            money
            <span style={{
              position: "absolute", left: "var(--space-4)", top: "50%",
              height: "var(--rule-w)", width: `calc((100% - 2 * var(--space-4)) * ${strikeW / 100})`,
              background: "var(--accent)", transform: "translateY(-50%)",
            }} />
          </span>
          <span style={{
            fontFamily: "var(--font-body)", fontSize: "var(--t-body)", color: "var(--text-2)",
          }}>{moneyNote}</span>
        </div>
      </div>
    </Surface>
  );
};
