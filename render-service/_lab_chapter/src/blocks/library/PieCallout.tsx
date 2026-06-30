import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";
import { useCountToWord, type Word } from "../../primitives/RollingNumber";
import { fmtNum } from "../../primitives/chart";

// BESPOKE block: rebuild of NOLAN's PIL PieCalloutRenderer. A donut chart whose
// highlighted slice represents a percentage, with a title + explanatory text
// beside it. Charts are GEOMETRY computed per frame (per chart.tsx): the accent
// arc sweeps 0 -> percentage% via stroke-dasharray/offset over the circumference,
// the big number counts up in the hole keyed to the spoken word, and the info
// column slides in on its own cue. Pure function of frame; ONLY semantic tokens;
// <Surface>-wrapped. `useCurrentFrame()` is step-relative.
export type PieCalloutProps = {
  percentage: number;     // 0-100
  infoTitle?: string;
  infoText?: string;
  sliceLabel?: string;
  word?: string;          // spoken word to sweep/count on
  revealFrames: number[]; // [donut cue, info cue]
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// donut geometry (SVG user units)
const SIZE = 320;
const STROKE = 40;
const R = (SIZE - STROKE) / 2;
const C = 2 * Math.PI * R;
const CX = SIZE / 2;

export const PieCallout: React.FC<PieCalloutProps> = ({
  percentage, infoTitle, infoText, sliceLabel, word, revealFrames, words,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const pct = Math.max(0, Math.min(100, percentage));
  const donutCue = revealFrames[0] ?? 0;
  const infoCue = revealFrames[1] ?? donutCue + 18;

  // The count-up drives BOTH the hole number and the arc length, so the slice
  // sweep and the number stay locked together. Keyed to the spoken word when
  // present, else to the donut cue.
  const { live, rolling } = useCountToWord(words, word ?? "", pct, {
    fallback: donutCue,
    spanSec: 0.8,
  });

  // donut container fades/scales in on its cue
  const donutIn = spring({ frame: frame - donutCue, fps, durationInFrames: 18, config: { damping: 200 } });
  const dashLen = (live / 100) * C; // accent arc length, in sync with `live`

  // info column slides in from the right on its own cue
  const infoIn = spring({ frame: frame - infoCue, fps, durationInFrames: 22, config: { damping: 200 } });
  const infoX = interpolate(infoIn, [0, 1], [48, 0], clamp);

  return (
    <Surface>
      <div style={{
        display: "flex", flexDirection: "row", height: "100%",
        justifyContent: "center", alignItems: "center", gap: "var(--space-10)",
      }}>
        {/* ── DONUT ─────────────────────────────────────────────── */}
        <div style={{
          position: "relative", flexShrink: 0,
          opacity: donutIn,
          transform: `scale(${interpolate(donutIn, [0, 1], [0.92, 1], clamp)})`,
        }}>
          <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
            {/* full track ring */}
            <circle
              cx={CX} cy={CX} r={R} fill="none"
              stroke="var(--surface-2)" strokeWidth={STROKE}
            />
            <circle
              cx={CX} cy={CX} r={R} fill="none"
              stroke="var(--rule)" strokeWidth={STROKE} opacity={0.4}
            />
            {/* accent arc — sweeps from the top (rotate -90) */}
            <circle
              cx={CX} cy={CX} r={R} fill="none"
              stroke="var(--accent)" strokeWidth={STROKE} strokeLinecap="round"
              strokeDasharray={`${dashLen} ${C}`}
              strokeDashoffset={0}
              transform={`rotate(-90 ${CX} ${CX})`}
              style={{ filter: `drop-shadow(0 0 ${interpolate(rolling, [0, 1], [8, 22], clamp)}px var(--accent-glow))` }}
            />
          </svg>

          {/* big percentage in the hole */}
          <div style={{
            position: "absolute", inset: 0,
            display: "flex", flexDirection: "column",
            justifyContent: "center", alignItems: "center", gap: "var(--space-2)",
          }}>
            <div style={{
              fontFamily: "var(--font-display-en)", fontWeight: 900,
              fontSize: "var(--t-display-2)", lineHeight: 1,
              color: "var(--accent)", fontVariantNumeric: "tabular-nums",
              textShadow: `0 0 ${interpolate(rolling, [0, 1], [10, 36], clamp)}px var(--accent-glow)`,
            } as React.CSSProperties}>
              {fmtNum(live, { suffix: "%" })}
            </div>
            {sliceLabel ? (
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
                letterSpacing: "var(--track-caps)", textTransform: "uppercase",
                color: "var(--text-mute)", opacity: donutIn,
              }}>{sliceLabel}</div>
            ) : null}
          </div>
        </div>

        {/* ── INFO COLUMN ───────────────────────────────────────── */}
        {infoTitle || infoText ? (
          <div style={{
            display: "flex", flexDirection: "column", gap: "var(--space-5)",
            maxWidth: "40%",
            opacity: infoIn,
            transform: `translateX(${infoX}px)`,
            borderLeft: "2px solid var(--rule)",
            paddingLeft: "var(--space-7)",
          }}>
            {infoTitle ? (
              <div style={{
                fontFamily: "var(--font-display-cn)", fontSize: "var(--t-h2)",
                lineHeight: 1.15, color: "var(--text)",
              }}>{infoTitle}</div>
            ) : null}
            {infoText ? (
              <div style={{
                fontFamily: "var(--font-body)", fontSize: "var(--t-body)",
                lineHeight: 1.5, color: "var(--text-2)",
              }}>{infoText}</div>
            ) : null}
          </div>
        ) : null}
      </div>
    </Surface>
  );
};
