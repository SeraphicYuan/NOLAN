import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, interpolate } from "remotion";

// Flashback — NOLAN's PIL FlashbackRenderer, reborn as a frame-driven Remotion beat.
// A single hero image is dropped "back in time": graded to B&W / sepia / vintage via an
// SVG feColorMatrix, ringed by a radial vignette, dusted with a frame-seeded feTurbulence
// film grain (mix-blend overlay), and — when given a yearText — captioned with a big
// display-CN year over a small mono tick. An optional slow Ken Burns scale (1.0→1.08)
// drifts across the whole duration. Same SVG-filter recipe as Effects.tsx PostFX, so it
// stays fully deterministic (grain seeded by Math.floor(frame)) — no random/timers/CSS.
type Word = { text: string; startFrame: number; endFrame: number };

export type FlashbackProps = {
  src: string;
  style?: "bw" | "sepia" | "vintage";   // default "sepia"
  yearText?: string;
  grain?: number;       // 0..1 default 0.18
  vignette?: number;    // 0..1 default 0.55
  kenBurns?: boolean;   // slow drift (default true)
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Per-style feColorMatrix grade (sRGB). bw = desaturated; sepia = classic warm sepia;
// vintage = the same sepia base with lifted contrast applied in a follow-up transfer.
const GRADE: Record<NonNullable<FlashbackProps["style"]>, string> = {
  bw: "0.33 0.34 0.33 0 0  0.33 0.34 0.33 0 0  0.33 0.34 0.33 0 0  0 0 0 1 0",
  sepia: "0.393 0.769 0.189 0 0  0.349 0.686 0.168 0 0  0.272 0.534 0.131 0 0  0 0 0 1 0",
  vintage: "0.393 0.769 0.189 0 0  0.349 0.686 0.168 0 0  0.272 0.534 0.131 0 0  0 0 0 1 0",
};

export const Flashback: React.FC<FlashbackProps> = ({
  src, style = "sepia", yearText, grain = 0.18, vignette = 0.55, kenBurns = true,
  revealFrames, words, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const r0 = revealFrames[0] ?? 0;
  const id = `fb-${r0}`;

  // image rises out of black; year settles in a touch later (after the image reads).
  const imgIn = interpolate(frame - r0, [0, 24], [0, 1], clamp);
  // Ken Burns: a slow, steady push across the FULL clip — never reverses, never bounces.
  const kb = kenBurns ? interpolate(frame, [r0, r0 + durationInFrames], [1.0, 1.08], clamp) : 1.0;

  // Year caption: prefer to land on the last spoken word (the line that earns the memory),
  // else fall back to a fixed beat after reveal. Fades up + drifts a few px.
  const lastWord = words.length ? words[words.length - 1] : undefined;
  const yearAt = lastWord ? Math.min(lastWord.startFrame, r0 + 40) : r0 + 40;
  const yearOp = interpolate(frame, [yearAt, yearAt + 22], [0, 1], clamp);
  const yearRise = interpolate(yearOp, [0, 1], [16, 0]);

  return (
    <AbsoluteFill style={{ background: "var(--surface)", overflow: "hidden" }}>
      {/* filter defs: per-style grade (+ vintage contrast lift) and a frame-seeded grain. */}
      <svg width={0} height={0} style={{ position: "absolute" }}>
        <defs>
          <filter id={`${id}-grade`} x="-5%" y="-5%" width="110%" height="110%" colorInterpolationFilters="sRGB">
            <feColorMatrix type="matrix" values={GRADE[style]} in="SourceGraphic" result="graded" />
            {style === "vintage" ? (
              <feComponentTransfer in="graded">
                <feFuncR type="gamma" amplitude={1.12} exponent={0.88} offset={-0.04} />
                <feFuncG type="gamma" amplitude={1.10} exponent={0.90} offset={-0.03} />
                <feFuncB type="gamma" amplitude={1.06} exponent={0.94} offset={-0.02} />
              </feComponentTransfer>
            ) : null}
          </filter>
          <filter id={`${id}-grain`} x="0" y="0" width="100%" height="100%">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={Math.floor(frame) % 211} result="n" />
            <feColorMatrix in="n" type="saturate" values="0" />
          </filter>
        </defs>
      </svg>

      {/* full-bleed graded hero image (cover) + Ken Burns drift */}
      <AbsoluteFill style={{ opacity: imgIn, filter: `url(#${id}-grade)` }}>
        <Img
          src={staticFile(src)}
          style={{ width: "100%", height: "100%", objectFit: "cover",
            transform: `scale(${kb})`, transformOrigin: "50% 45%" }}
        />
      </AbsoluteFill>

      {/* film grain overlay (frame-seeded, deterministic) */}
      {grain > 0.001 ? (
        <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%",
          mixBlendMode: "overlay", opacity: grain, pointerEvents: "none" }}>
          <rect width="100%" height="100%" filter={`url(#${id}-grain)`} />
        </svg>
      ) : null}

      {/* darkened-edge vignette */}
      {vignette > 0.001 ? (
        <AbsoluteFill style={{ pointerEvents: "none",
          background: `radial-gradient(ellipse 78% 78% at 50% 46%, transparent 52%, rgba(0,0,0,${vignette}) 100%)` }} />
      ) : null}

      {/* year caption — big display-CN over a small mono caps tick, centered/lower */}
      {yearText ? (
        <div style={{ position: "absolute", left: 0, right: 0, bottom: "var(--space-9)",
          display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--space-3)",
          opacity: yearOp, transform: `translateY(${yearRise}px)`, pointerEvents: "none" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)" }}>
            — flashback —
          </div>
          <div style={{ fontFamily: "var(--font-display, var(--font-display-cn))", fontWeight: 700, fontSize: "var(--t-h1)",
            lineHeight: 1, color: "var(--text)", textShadow: "0 6px 28px rgba(0,0,0,0.6)" }}>
            {yearText}
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
