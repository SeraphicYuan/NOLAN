import React from "react";
import { Img, staticFile, useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { Surface } from "../../Surface";
import { useKenBurns, Spotlight, SketchBox, type Region } from "../../primitives/annotate";

// PaperFigure — the lift-and-place tier. For an *empirical* figure we can't
// honestly redraw (an attention heatmap, a plot of real data, a sample output),
// we show the paper's own image on a themed "exhibit card" — a light specimen
// panel framed by the theme's rule/accent + a cited source. The signature motion
// stays "compute, don't capture": as the narration names a region, the figure is
// GUIDED — a word-synced highlight marks it, a spotlight dims the rest, and
// (optionally) the camera pushes in (Ken Burns). All frame-driven + deterministic.
// Highlight coords are fractions (0..1) of the image box.
type Word = { text: string; startFrame: number; endFrame: number };
type Highlight = { word: string; x: number; y: number; w: number; h: number; label?: string };
export type PaperFigureProps = {
  src: string;
  kicker?: string;
  source?: string;
  highlights?: Highlight[];
  spotlight?: boolean;            // dim-the-rest around the active region (default on)
  zoom?: boolean;                 // Ken Burns push-in toward the active region (default off)
  annotate?: "box" | "sketch";   // marker style (default "box")
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const _norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

const triggerFrame = (word: string, words: Word[], fallback: number): number => {
  const t = _norm(word);
  for (const w of words) {
    const wn = _norm(w.text);
    if (wn && (wn === t || (t.length >= 3 && wn.length >= 3 && (wn.includes(t) || t.includes(wn)))))
      return w.startFrame;
  }
  return fallback;
};

export const PaperFigure: React.FC<PaperFigureProps> = ({
  src, kicker, source, highlights = [], spotlight = true, zoom = false, annotate = "box",
  revealFrames, words, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const r0 = revealFrames[0] ?? 0;

  const intro = spring({ frame: frame - r0, fps, config: { damping: 200 }, durationInFrames: 24 });
  const cardOp = interpolate(intro, [0, 1], [0, 1]);
  const cardY = interpolate(intro, [0, 1], [26, 0]);
  const kickerOp = interpolate(frame - r0, [4, 18], [0, 1], clamp);

  // Resolve each highlight to its spoken trigger; the "focus" is the most-recently
  // triggered active one — spotlight + zoom track it.
  const hs = highlights.map((h, i) => {
    const tf = triggerFrame(h.word, words, r0 + 30 + i * 24);
    return { ...h, tf, active: frame >= tf };
  });
  const focus = hs.filter((h) => h.active).reduce<(typeof hs)[number] | null>(
    (a, b) => (!a || b.tf > a.tf ? b : a), null);
  const focusRegion: Region | null = focus ? { x: focus.x, y: focus.y, w: focus.w, h: focus.h } : null;
  const focusProg = focus ? interpolate(frame - focus.tf, [2, 22], [0, 1], clamp) : 0;
  const kb = useKenBurns(!!focus && zoom, focusRegion, focusProg);

  return (
    <Surface>
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", gap: "var(--space-4)" }}>
        {kicker ? (
          <div style={{ opacity: kickerOp, fontFamily: "var(--font-mono)", color: "var(--text-mute)",
            letterSpacing: "var(--track-caps)", textTransform: "uppercase", fontSize: "var(--t-micro)" }}>
            {kicker}
          </div>
        ) : null}

        {/* exhibit card — a light specimen panel framed by the theme */}
        <div style={{ position: "relative", opacity: cardOp, transform: `translateY(${cardY}px)`,
          width: "min(64%, 1180px)", background: "#f7f7f4", borderRadius: "var(--r-sm, 6px)",
          border: "var(--rule-w, 2px) var(--rule-style, solid) var(--accent)",
          boxShadow: "var(--elev-5)", padding: 18, overflow: "hidden" }}>

          {/* image box — Ken Burns transforms this whole layer (img + overlays) */}
          <div style={{ position: "relative", transform: kb.transform, transformOrigin: kb.transformOrigin,
            transition: "none" }}>
            <Img src={staticFile(src)} style={{ display: "block", width: "100%", height: "auto" }} />

            {/* spotlight: dim everything except the focus region */}
            {spotlight ? (
              <Spotlight region={focusRegion} amount={focus ? focusProg : 0} id={`pf-${r0}`} />
            ) : null}

            {/* word-synced highlight markers over the figure (fractions of image) */}
            {hs.map((h, i) => {
              if (!h.active) return null;
              const local = frame - h.tf;
              const pop = spring({ frame: local, fps, config: { damping: 180 }, durationInFrames: 16 });
              const op = interpolate(local, [0, 8], [0, 1], clamp);
              const draw = interpolate(local, [2, 20], [0, 1], clamp);
              const glow = interpolate(local, [0, 10, 26], [0, 1, 0.4], clamp);
              return (
                <div key={i} style={{ position: "absolute",
                  left: `${h.x * 100}%`, top: `${h.y * 100}%`,
                  width: `${h.w * 100}%`, height: `${h.h * 100}%`,
                  opacity: op, transform: `scale(${interpolate(pop, [0, 1], [0.9, 1])})` }}>
                  {annotate === "sketch" ? (
                    <SketchBox w={220} h={140} draw={draw} seed={7 + i} />
                  ) : (
                    <div style={{ position: "absolute", inset: 0, border: `2px solid var(--accent)`,
                      borderRadius: 4, background: "var(--accent-fill)",
                      boxShadow: `0 0 ${18 * glow}px var(--accent-glow)` }} />
                  )}
                  {h.label ? (
                    <div style={{ position: "absolute", top: -26, left: 0, whiteSpace: "nowrap",
                      fontFamily: "var(--font-mono)", fontSize: 16, color: "var(--accent)",
                      letterSpacing: "var(--track-caps)", textTransform: "uppercase",
                      textShadow: "0 1px 6px rgba(0,0,0,.5)" }}>{h.label}</div>
                  ) : null}
                </div>
              );
            })}
          </div>

          {source ? (
            <div style={{ position: "absolute", right: 12, bottom: 8, fontFamily: "var(--font-mono)",
              fontSize: 13, color: "#9a9a93", letterSpacing: "0.04em", zIndex: 3 }}>{source}</div>
          ) : null}
        </div>
      </div>
    </Surface>
  );
};
