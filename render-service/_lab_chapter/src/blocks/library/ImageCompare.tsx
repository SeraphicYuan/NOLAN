import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

// ImageCompare — two artworks (or two details) side by side, for contrast/opposition
// in the ART flow (e.g. Death-the-tormentor vs Death-the-companion; pope vs ploughman).
// ComparisonVS is for TEXT columns; this is for IMAGES. Museum-neutral stage; each
// panel slides in on its cue, a center rule + optional verdict land last.
type Word = { text: string; startFrame: number; endFrame: number };
type Side = { src: string; label?: string; caption?: string };
export type ImageCompareProps = {
  kicker?: string;
  left: Side;
  right: Side;
  verdict?: string;
  revealFrames: number[];   // [left cue, right cue, verdict cue]
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Slow, deterministic Ken Burns drift so a held woodcut never sits dead-static
// (art flow: "always-lift"). dir flips the horizontal drift per panel.
const Panel: React.FC<{ side: Side; from: number; t: number; frame: number; dur: number; dir: number }> = ({ side, from, t, frame, dur, dir }) => {
  const k = interpolate(frame, [0, dur], [0, 1], clamp);
  return (
  <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--space-4)",
    opacity: t, transform: `translateX(${interpolate(t, [0, 1], [from, 0])}px)` }}>
    <Img src={staticFile(side.src)} style={{ maxHeight: "62vh", maxWidth: "100%", width: "auto", height: "auto",
      boxShadow: "0 24px 70px rgba(0,0,0,0.55)", transformOrigin: "center",
      transform: `scale(${1 + 0.04 * k}) translate(${dir * 7 * k}px, ${-5 * k}px)` }} />
    {side.label ? (
      <div style={{ fontFamily: "var(--font-display-cn)", fontWeight: 700, fontSize: 28, color: "var(--text)" }}>{side.label}</div>
    ) : null}
    {side.caption ? (
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 15, letterSpacing: "var(--track-caps)", textTransform: "uppercase",
        color: "var(--text-mute)", textAlign: "center", maxWidth: "26ch" }}>{side.caption}</div>
    ) : null}
  </div>
  );
};

export const ImageCompare: React.FC<ImageCompareProps> = ({ kicker, left, right, verdict, revealFrames, words: _w, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const [lc, rc, vc] = [revealFrames[0] ?? 0, revealFrames[1] ?? (revealFrames[0] ?? 0) + 20, revealFrames[2] ?? durationInFrames - 40];
  const lt = spring({ frame: frame - lc, fps, durationInFrames: 22, config: { damping: 200 } });
  const rt = spring({ frame: frame - rc, fps, durationInFrames: 22, config: { damping: 200 } });
  const kickerOp = interpolate(frame - lc, [-8, 6], [0, 1], clamp);
  const vt = interpolate(frame - vc, [0, 14], [0, 1], clamp);

  return (
    <AbsoluteFill style={{ background: "var(--surface)", display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", padding: "var(--space-9)", gap: "var(--space-5)" }}>
      {kicker ? (
        <div style={{ opacity: kickerOp, fontFamily: "var(--font-mono)", color: "var(--text-mute)",
          letterSpacing: "var(--track-caps)", textTransform: "uppercase", fontSize: "var(--t-micro)" }}>{kicker}</div>
      ) : null}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "var(--space-7)", width: "100%" }}>
        <Panel side={left} from={-60} t={lt} frame={frame} dur={durationInFrames} dir={-1} />
        <div style={{ width: "var(--rule-w)", alignSelf: "stretch", minHeight: "40vh", background: "var(--rule)",
          opacity: Math.min(lt, rt) }} />
        <Panel side={right} from={60} t={rt} frame={frame} dur={durationInFrames} dir={1} />
      </div>
      {verdict ? (
        <div style={{ opacity: vt, transform: `translateY(${interpolate(vt, [0, 1], [16, 0])}px)`,
          fontFamily: "var(--font-display-cn)", fontWeight: 700, fontSize: "var(--t-h2)", color: "var(--text)",
          textAlign: "center", maxWidth: "70%" }}>{verdict}</div>
      ) : null}
    </AbsoluteFill>
  );
};
