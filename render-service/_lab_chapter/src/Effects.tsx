import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Surface } from "./Surface";

// PostFX — a post-processing "shader" tier. @remotion/effects (GLSL via HtmlInCanvas)
// needs Remotion ≥4.0.455 + Chrome 149+; we're on 4.0.404 with an older headless
// Chromium and can't touch the shared render-service. So we get the same outcomes
// (bloom, color grade, film grain, vignette) from the browser's own GPU primitives:
// SVG filters (feGaussianBlur / feColorMatrix / feComponentTransfer / feTurbulence)
// + blend-mode overlays. Fully deterministic — grain is seeded by the frame number.
// Wrap a scene: <PostFX grade="warm" bloom={0.5} grain={0.12} vignette={0.4}>…</PostFX>.

type Grade = "none" | "warm" | "cool" | "noir" | "vivid";
const GRADE: Record<Grade, string> = {
  none: "1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 1 0",
  warm: "1.10 0 0 0 0  0 1.02 0 0 0  0 0 0.90 0 0  0 0 0 1 0",
  cool: "0.92 0 0 0 0  0 1.0 0 0 0  0 0 1.12 0 0  0 0 0 1 0",
  noir: "0.33 0.34 0.33 0 0  0.33 0.34 0.33 0 0  0.33 0.34 0.33 0 0  0 0 0 1 0",
  vivid: "1.30 -0.15 -0.15 0 0  -0.10 1.25 -0.15 0 0  -0.10 -0.15 1.25 0 0  0 0 0 1 0",
};

export type PostFXProps = {
  id?: string;
  grade?: Grade;
  bloom?: number;     // 0..1 — bright-area light bleed
  grain?: number;     // 0..1 — film grain (frame-seeded shimmer)
  vignette?: number;  // 0..1 — darkened edges
  children: React.ReactNode;
};

export const PostFX: React.FC<PostFXProps> = ({
  id = "pfx", grade = "none", bloom = 0, grain = 0, vignette = 0, children,
}) => {
  const frame = useCurrentFrame();
  const bBlur = bloom * 14;
  const bGain = 1 + bloom * 1.1;

  return (
    <AbsoluteFill>
      {/* filter defs */}
      <svg width={0} height={0} style={{ position: "absolute" }}>
        <defs>
          <filter id={`${id}-main`} x="-10%" y="-10%" width="120%" height="120%" colorInterpolationFilters="sRGB">
            <feColorMatrix type="matrix" values={GRADE[grade]} in="SourceGraphic" result="graded" />
            {bloom > 0.001 ? (
              <>
                <feGaussianBlur in="graded" stdDeviation={bBlur} result="blur" />
                <feComponentTransfer in="blur" result="bright">
                  <feFuncR type="linear" slope={bGain} />
                  <feFuncG type="linear" slope={bGain} />
                  <feFuncB type="linear" slope={bGain} />
                </feComponentTransfer>
                <feMerge>
                  <feMergeNode in="bright" />
                  <feMergeNode in="graded" />
                </feMerge>
              </>
            ) : null}
          </filter>
          <filter id={`${id}-grain`} x="0" y="0" width="100%" height="100%">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={Math.floor(frame) % 211} result="n" />
            <feColorMatrix in="n" type="saturate" values="0" />
          </filter>
        </defs>
      </svg>

      {/* graded + bloomed scene */}
      <AbsoluteFill style={{ filter: `url(#${id}-main)` }}>{children}</AbsoluteFill>

      {/* film grain overlay (frame-seeded, deterministic) */}
      {grain > 0.001 ? (
        <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%",
          mixBlendMode: "overlay", opacity: grain, pointerEvents: "none" }}>
          <rect width="100%" height="100%" filter={`url(#${id}-grain)`} />
        </svg>
      ) : null}

      {/* vignette overlay */}
      {vignette > 0.001 ? (
        <AbsoluteFill style={{ pointerEvents: "none",
          background: `radial-gradient(ellipse 75% 75% at 50% 48%, transparent 55%, rgba(0,0,0,${vignette}) 100%)` }} />
      ) : null}
    </AbsoluteFill>
  );
};

// Side-by-side demo: same bright-accent scene, RAW (left) vs PostFX (right).
const FXContent: React.FC = () => (
  <Surface>
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", gap: "var(--space-5)" }}>
      <div style={{ fontFamily: "var(--font-display-en)", fontWeight: 900, fontSize: 220, lineHeight: 0.9,
        color: "var(--accent)", textShadow: "0 0 30px var(--accent-glow)", fontVariantNumeric: "tabular-nums" }}>847%</div>
      <div style={{ width: 220, height: 4, background: "var(--accent)", boxShadow: "0 0 14px var(--accent-glow)" }} />
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 26, letterSpacing: "var(--track-caps)",
        textTransform: "uppercase", color: "var(--text-mute)" }}>peak drawdown avoided</div>
    </div>
  </Surface>
);

const Tag: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ position: "absolute", bottom: 40, left: 0, right: 0, textAlign: "center", zIndex: 9,
    fontFamily: "var(--font-mono)", fontSize: 22, letterSpacing: "0.3em", textTransform: "uppercase",
    color: "var(--text-2)" }}>{children}</div>
);

export const FXSpike: React.FC = () => (
  <AbsoluteFill style={{ flexDirection: "row" }}>
    <div style={{ position: "relative", width: "50%", height: "100%", overflow: "hidden" }}>
      <FXContent />
      <Tag>raw</Tag>
    </div>
    <div style={{ position: "absolute", top: "8%", bottom: "8%", left: "50%", width: 2, background: "rgba(255,255,255,0.2)", zIndex: 9 }} />
    <div style={{ position: "relative", width: "50%", height: "100%", overflow: "hidden" }}>
      <PostFX grade="warm" bloom={0.55} grain={0.14} vignette={0.5}><FXContent /></PostFX>
      <Tag>postfx · warm + bloom + grain + vignette</Tag>
    </div>
  </AbsoluteFill>
);
