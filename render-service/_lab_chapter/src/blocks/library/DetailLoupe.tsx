import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

// DetailLoupe — "look closely here." Shows the whole artwork with a region marked,
// and a magnified crop of that region beside it (context retained, detail enlarged) —
// for the ART flow's "what's smuggled in this corner" beat. Region is fractions
// (0..1) of the image; the loupe crops via an absolutely-scaled <Img> in a clipped box.
type Word = { text: string; startFrame: number; endFrame: number };
export type DetailLoupeProps = {
  src: string;
  region: { x: number; y: number; w: number; h: number };
  label?: string;
  caption?: string;
  revealFrames: number[];   // [whole cue, loupe cue]
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const DetailLoupe: React.FC<DetailLoupeProps> = ({ src, region, label, caption, revealFrames, words: _w, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const r0 = revealFrames[0] ?? 0;
  const r1 = revealFrames[1] ?? r0 + 24;
  const wholeOp = interpolate(frame - r0, [0, 16], [0, 1], clamp);
  const markOp = interpolate(frame - r0, [10, 24], [0, 1], clamp);
  const loupeS = spring({ frame: frame - r1, fps, durationInFrames: 22, config: { damping: 200 } });
  const { x, y, w, h } = region;

  return (
    <AbsoluteFill style={{ background: "var(--surface)", display: "flex", flexDirection: "row", alignItems: "center",
      justifyContent: "center", gap: "var(--space-9)", padding: "var(--space-9)" }}>
      {/* the whole artwork with the region marked */}
      <div style={{ position: "relative", height: "70vh", opacity: wholeOp }}>
        <Img src={staticFile(src)} style={{ display: "block", height: "100%", width: "auto", boxShadow: "0 24px 70px rgba(0,0,0,0.55)" }} />
        <div style={{ position: "absolute", left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%`,
          border: "2px solid var(--accent)", borderRadius: 3, boxShadow: "0 0 16px var(--accent-glow)", opacity: markOp }} />
      </div>

      {/* magnified crop of the region */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--space-4)",
        opacity: interpolate(loupeS, [0, 1], [0, 1]), transform: `scale(${interpolate(loupeS, [0, 1], [0.85, 1])})` }}>
        <div style={{ position: "relative", width: "44vh", height: "44vh", overflow: "hidden", borderRadius: "var(--r-sm, 6px)",
          border: "var(--rule-w, 2px) solid var(--accent)", boxShadow: "0 24px 70px rgba(0,0,0,0.55), 0 0 26px var(--accent-glow)", background: "var(--surface-2)" }}>
          <Img src={staticFile(src)} style={{ position: "absolute", width: `${100 / w}%`, height: `${100 / h}%`,
            left: `${-(x / w) * 100}%`, top: `${-(y / h) * 100}%`, maxWidth: "none" }} />
        </div>
        {label ? (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 16, letterSpacing: "var(--track-caps)", textTransform: "uppercase",
            color: "var(--accent)" }}>{label}</div>
        ) : null}
        {caption ? (
          <div style={{ fontFamily: "var(--font-body)", fontSize: "var(--t-body)", color: "var(--text-2)", textAlign: "center", maxWidth: "30ch" }}>{caption}</div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
