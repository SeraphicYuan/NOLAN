import React, { useEffect, useState } from "react";
import { Lottie } from "@remotion/lottie";
import { staticFile, delayRender, continueRender, useCurrentFrame, interpolate } from "remotion";
import { colorify, getColors } from "lottie-colorify";
import { Surface } from "../../Surface";

// LottieIcon — drop a designer-made Lottie (icon / counter / checkmark / loader)
// as a THEMED asset. We recolor it to the live theme's --accent/--text at render
// (read via getComputedStyle, recolored with lottie-colorify — a pure JSON
// transform), and seek it via @remotion/lottie's frame model (deterministic for
// keyframed assets; reject expression-driven ones at intake). Optional caption.
type Word = { text: string; startFrame: number; endFrame: number };
export type LottieIconProps = {
  src: string;                  // staticFile path to a (keyframed) lottie .json
  size?: number;                // px (default 360)
  caption?: string;
  loop?: boolean;
  monochrome?: boolean;         // tint everything to --accent (default true)
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const cssVar = (name: string, fallback: string) => {
  if (typeof document === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
};

export const LottieIcon: React.FC<LottieIconProps> = ({
  src, size = 360, caption, loop = false, monochrome = true, revealFrames, words: _w, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const r0 = revealFrames[0] ?? 0;
  const [data, setData] = useState<object | null>(null);
  const [handle] = useState(() => delayRender("lottie"));

  useEffect(() => {
    let alive = true;
    fetch(staticFile(src))
      .then((r) => r.json())
      .then((json) => {
        if (!alive) return;
        const accent = cssVar("--accent", "#4dd2ff");
        const text = cssVar("--text", "#e8e8e8");
        // recolor to theme tokens. monochrome → map EVERY color in the asset to
        // --accent (use a transparent-bg, expression-free asset at intake, else a
        // filled bg layer becomes a solid accent block); else first→accent, rest→text.
        let recolored: object;
        try {
          const n = getColors(json).length || 1;
          recolored = colorify(monochrome ? Array(n).fill(accent) : [accent, ...Array(Math.max(0, n - 1)).fill(text)], json) as object;
        } catch {
          recolored = colorify(monochrome ? [accent] : [accent, text], json) as object;
        }
        setData(recolored as object);
        continueRender(handle);
      })
      .catch(() => continueRender(handle));
    return () => { alive = false; };
  }, [src, monochrome, handle]);

  const introOp = interpolate(frame - r0, [0, 10], [0, 1], clamp);
  const capOp = interpolate(frame - r0, [12, 26], [0, 1], clamp);

  return (
    <Surface>
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", gap: "var(--space-5)" }}>
        <div style={{ width: size, height: size, opacity: introOp }}>
          {data ? <Lottie animationData={data} loop={loop} playbackRate={1} /> : null}
        </div>
        {caption ? (
          <div style={{ opacity: capOp, fontFamily: "var(--font-mono)", color: "var(--text-mute)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase", fontSize: "var(--t-micro)" }}>
            {caption}
          </div>
        ) : null}
      </div>
    </Surface>
  );
};
