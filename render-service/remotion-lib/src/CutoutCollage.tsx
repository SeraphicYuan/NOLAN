import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate } from "remotion";

// CutoutCollage — the editorial-print collage shot: a background-removed
// SUBJECT (rembg cutout, generated python-side by the motion executor's
// pre-pass) staged over a flat paper-toned field, with a soft contact
// shadow and a slow scale-in. The stop-motion stutter and rough edges come
// from the Chapter step's texture wrapper (scene.texture), not from here —
// one owner per concern.
//
// props:
//   cutoutSrc  staged basename of the subject PNG (alpha) — required
//   label?     small caption under the subject (museum-tag convention)
//   bg?        "paper" (theme surface + fiber tint) | "flat" (theme surface)
//   align?     "center" | "left" | "right" — where the subject sits

export type CutoutCollageProps = {
  cutoutSrc: string;
  label?: string;
  bg?: "paper" | "flat";
  align?: "center" | "left" | "right";
  durationInFrames?: number;
};

export const CutoutCollage: React.FC<CutoutCollageProps> = ({
  cutoutSrc, label, bg = "paper", align = "center",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // the editorial scale-in: 70% -> 100% over ~2s, steep ease-out
  const t = interpolate(frame, [0, fps * 2], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const eased = 1 - Math.pow(1 - t, 3);
  const scale = 0.7 + 0.3 * eased;
  const justify = align === "left" ? "flex-start" : align === "right" ? "flex-end" : "center";

  return (
    <AbsoluteFill style={{ background: "var(--surface)" }}>
      {bg === "paper" ? (
        <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%",
          mixBlendMode: "multiply", opacity: 0.35, pointerEvents: "none" }}>
          <defs>
            <filter id="cc-fiber" x="0" y="0" width="100%" height="100%">
              <feTurbulence type="fractalNoise" baseFrequency="0.012 0.017" numOctaves={4} seed={11} result="f" />
              <feColorMatrix in="f" type="matrix"
                values="0 0 0 0 0.93  0 0 0 0 0.90  0 0 0 0 0.84  0 0 0 0 1" />
            </filter>
          </defs>
          <rect width="100%" height="100%" filter="url(#cc-fiber)" />
        </svg>
      ) : null}
      <AbsoluteFill style={{ display: "flex", flexDirection: "column", alignItems: justify,
        justifyContent: "center", padding: "6% 10%" }}>
        <div style={{ transform: `scale(${scale.toFixed(4)})`, transformOrigin: "50% 80%",
          display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}>
          <Img
            src={staticFile(cutoutSrc)}
            style={{ maxWidth: "62vw", maxHeight: "68vh", objectFit: "contain",
              filter: "drop-shadow(0 22px 34px rgba(0,0,0,0.38))" }}
          />
          {label ? (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 24,
              letterSpacing: "0.14em", textTransform: "uppercase",
              color: "var(--text-2)", background: "var(--surface)",
              padding: "6px 16px", border: "1px solid var(--text-2)" }}>
              {label}
            </div>
          ) : null}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
