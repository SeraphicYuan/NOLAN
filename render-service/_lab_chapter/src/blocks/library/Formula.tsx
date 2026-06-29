import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import katex from "katex";
import "katex/dist/katex.min.css";
import { Surface } from "../../Surface";

// BESPOKE LaTeX-formula block. Renders a single KaTeX display-mode equation,
// large and centered, with a "write-on" entrance: the math is clipped
// left→right so it appears to be drawn in across the first ~55% of the step,
// under a subtle opacity/scale lift. Optional kicker (above) and caption
// (below) fade in only AFTER the formula finishes drawing.
//
// KaTeX renders to an HTML string (output: "html") injected via
// dangerouslySetInnerHTML. Its internals inherit `currentColor`, so the
// wrapper's `color: var(--text)` themes the math without touching KaTeX CSS.
// Everything around the math uses semantic theme tokens only. Wrapped in
// <Surface>, no <Audio>. Frames are step-relative (Remotion resets per step).

type Word = { text: string; startFrame: number; endFrame: number };
export type FormulaProps = {
  latex: string;
  caption?: string;
  kicker?: string;
  // Entrance cue(s), step-relative. revealFrames[0] starts the draw-in.
  revealFrames: number[];
  // Per-word timeline for THIS step (step-relative) — accepted for contract
  // parity; the draw-in is timed off revealFrames + step duration.
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Formula: React.FC<FormulaProps> = ({
  latex,
  caption,
  kicker,
  revealFrames,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const start = revealFrames[0] ?? 0;
  // Deliberate draw-in across roughly the first 55% of the step.
  const drawSpan = Math.max(12, Math.round((durationInFrames - start) * 0.55));
  const drawEnd = start + drawSpan;

  // KaTeX → HTML (memoized on latex). throwOnError:false keeps a broken
  // formula from crashing the render; output:"html" avoids MathML duplication.
  const html = React.useMemo(
    () =>
      katex.renderToString(latex, {
        displayMode: true,
        throwOnError: false,
        output: "html",
      }),
    [latex],
  );

  // Write-on: clip the formula left→right as p goes 0→1.
  const p = interpolate(frame, [start, drawEnd], [0, 1], clamp);
  // Subtle opacity + scale lift on entrance.
  const enter = spring({ frame: frame - start, fps, durationInFrames: 16, config: { damping: 200 } });
  const formulaOpacity = interpolate(frame, [start, start + 8], [0, 1], clamp);
  const scale = interpolate(enter, [0, 1], [0.94, 1]);

  // kicker fades in with the formula; caption fades in only after the draw.
  const kickerOpacity = interpolate(frame, [start, start + 8], [0, 1], clamp);
  const captionOpacity = interpolate(frame, [drawEnd, drawEnd + 12], [0, 1], clamp);

  return (
    <Surface>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
          alignItems: "center",
          justifyContent: "center",
          gap: "var(--space-6)",
          textAlign: "center",
        }}
      >
        {kicker ? (
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--t-micro)",
              letterSpacing: "var(--track-caps)",
              textTransform: "uppercase",
              color: "var(--text-mute)",
              opacity: kickerOpacity,
            }}
          >
            {kicker}
          </div>
        ) : null}

        {/* hero: the KaTeX display-mode math, drawn on left→right */}
        <div
          style={{
            opacity: formulaOpacity,
            transform: `scale(${scale})`,
            clipPath: `inset(0 ${100 * (1 - p)}% 0 0)`,
            WebkitClipPath: `inset(0 ${100 * (1 - p)}% 0 0)`,
            color: "var(--text)",
            fontSize: 64,
            lineHeight: 1.2,
            maxWidth: "84%",
          } as React.CSSProperties}
        >
          <div dangerouslySetInnerHTML={{ __html: html }} />
        </div>

        {caption ? (
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--t-body)",
              color: "var(--text-mute)",
              maxWidth: "62%",
              opacity: captionOpacity,
            }}
          >
            {caption}
          </div>
        ) : null}
      </div>
    </Surface>
  );
};
