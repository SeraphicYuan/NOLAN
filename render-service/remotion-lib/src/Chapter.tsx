import React from "react";
import { Series, Audio, Freeze, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { BLOCKS } from "./blocks";
import { COMPS } from "./comps";
import { Captions } from "./Captions";
import { PostFX, type PostFXProps } from "./Effects";
import { driftScale } from "./camera";

// Render story v2: a Chapter step can be a library BLOCK, a hosted motion
// COMP (same components as the standalone compositions), or raw VIDEO
// (block "Video": {src, startFromFrames?} — narration stays the step audio,
// the clip is muted and loops if shorter than its step).
const STEP_COMPONENTS: Record<string, React.FC<Record<string, unknown>>> = {
  ...(COMPS as Record<string, React.FC<Record<string, unknown>>>),
  ...(BLOCKS as Record<string, React.FC<Record<string, unknown>>>),
};

const VideoStep: React.FC<{ src: string; startFromFrames?: number }> = ({ src, startFromFrames }) => (
  <OffthreadVideo
    src={staticFile(src)}
    startFrom={Math.max(0, Math.round(startFromFrames ?? 0))}
    muted
    loop
    style={{ width: "100%", height: "100%", objectFit: "cover" }}
  />
);

export type ChapterFX = Omit<PostFXProps, "children">;

// The Chapter driver: a Series of steps. Each step renders its block for its
// narration's duration, with the step's audio. useCurrentFrame() inside a
// Series.Sequence is step-relative, so a block's revealFrames / words (derived
// from that step's word timestamps) line up with the spoken words automatically.
// `captions` overlays a word-synced subtitle band on every step.
export type WordFrame = { text: string; startFrame: number; endFrame: number };
export type ChapterStep = {
  block: string;
  props: Record<string, unknown>;
  revealFrames: number[];
  words?: WordFrame[];
  captionWords?: WordFrame[];
  audioSrc?: string;
  durationInFrames: number;
  transitionIn?: "dissolve" | "fade";
  // texture grammar (nolan/texture.py is the vocabulary owner):
  jitter?: { fps: number; amp: number };   // stop-motion stutter (posterized time + nudge)
  edge?: "rough" | "boil";                 // torn-paper outline via SVG displacement
};

// deterministic pseudo-random in [-1, 1] — renders must be reproducible
const prand = (seed: number) => {
  const s = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return (s - Math.floor(s)) * 2 - 1;
};

// Stop-motion texture: the child subtree sees QUANTIZED time (Freeze), so all
// its internal animation updates at `jfps` like cel animation on twos/threes,
// while the wrapper nudges position/rotation once per held frame — the
// "cut paper under a stop-motion camera" look. Audio + captions are rendered
// OUTSIDE this wrapper in Chapter, so narration and word-sync stay exact.
const Jitter: React.FC<{ j?: { fps: number; amp: number }; seed: number; children: React.ReactNode }> = ({ j, seed, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!j || !(j.amp > 0) || !(j.fps > 0)) return <>{children}</>;
  const hold = Math.max(1, Math.round(fps / j.fps));
  const q = Math.floor(frame / hold) * hold;
  const step = q / hold;
  const dx = prand(seed * 7919 + step) * j.amp;
  const dy = prand(seed * 6197 + step + 0.37) * j.amp;
  const rot = prand(seed * 3557 + step + 0.71) * j.amp * 0.08;
  return (
    <div style={{ width: "100%", height: "100%", transform: `translate(${dx.toFixed(2)}px, ${dy.toFixed(2)}px) rotate(${rot.toFixed(3)}deg)` }}>
      <Freeze frame={q}>{children}</Freeze>
    </div>
  );
};

// Torn-paper outlines: fractal displacement over the step's rendered alpha —
// the browser-native analog of Turbulent Displace + Roughen Edges. "boil"
// re-seeds the turbulence on the jitter cadence so the outline undulates.
const EDGE_SCALE = { rough: 6, boil: 9 } as const;

const Edge: React.FC<{ kind?: "rough" | "boil"; seed: number; jfps?: number; children: React.ReactNode }> = ({ kind, seed, jfps, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!kind || !EDGE_SCALE[kind]) return <>{children}</>;
  const hold = Math.max(1, Math.round(fps / (jfps || 8)));
  const boilSeed = kind === "boil" ? Math.floor(frame / hold) % 97 : 0;
  const fid = `edge-${seed}-${kind}`;
  return (
    <div style={{ width: "100%", height: "100%", filter: `url(#${fid})` }}>
      <svg width={0} height={0} style={{ position: "absolute" }}>
        <defs>
          <filter id={fid} x="-5%" y="-5%" width="110%" height="110%">
            <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves={2} seed={seed * 13 + boilSeed} result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale={EDGE_SCALE[kind]} xChannelSelector="R" yChannelSelector="G" />
          </filter>
        </defs>
      </svg>
      {children}
    </div>
  );
};

// How a step ENTERS: a short opacity ramp from the theme background.
// Duration-preserving by design — narration owns duration, so a true overlap
// dissolve (which shortens the cut) is not offered. Frame counts assume 30fps
// (dissolve ≈ 0.27s, fade ≈ 0.47s); audio is NOT wrapped — it starts on the cut.
const RAMP_FRAMES = { dissolve: 8, fade: 14 } as const;

const TransitionIn: React.FC<{ kind?: "dissolve" | "fade"; children: React.ReactNode }> = ({ kind, children }) => {
  const frame = useCurrentFrame();
  if (!kind || !RAMP_FRAMES[kind]) return <>{children}</>;
  const opacity = interpolate(frame, [0, RAMP_FRAMES[kind]], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return <div style={{ opacity, width: "100%", height: "100%" }}>{children}</div>;
};

// Camera grammar rule 5 at the STEP level: blocks animate in and then sit
// dead for the rest of their narration (the bench audit: bar-compare,
// comparison, counter, title all froze by midpoint). A slow canvas push —
// broadcast "pillow motion" — keeps every frame alive. Blocks that move
// their own camera are excluded (double drift compounds).
const SELF_MOVING = new Set(["Video", "ArtworkStage", "StillMotion"]);

const AmbientDrift: React.FC<{ active: boolean; children: React.ReactNode }> = ({ active, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!active) return <>{children}</>;
  const s = driftScale(frame, fps, 1.035);
  return (
    <div style={{ width: "100%", height: "100%", transform: `scale(${s})`, transformOrigin: "50% 45%" }}>
      {children}
    </div>
  );
};

export const Chapter: React.FC<{ steps: ChapterStep[]; captions?: boolean; fx?: ChapterFX }> = ({ steps, captions, fx }) => {
  const { fps } = useVideoConfig();
  // Premount each beat ~0.5s early so its async assets (fonts, Img, KaTeX, Lottie,
  // delayRender work) resolve before the cut — kills first-frame pop-in. Remotion
  // keeps premounted <Audio> silent until the sequence actually starts, so this
  // does NOT shift narration timing.
  const premountFor = Math.round(fps * 0.5);
  const series = (
    <Series>
      {steps.map((s, i) => {
        const Block = s.block === "Video"
          ? (VideoStep as unknown as React.FC<Record<string, unknown>>)
          : STEP_COMPONENTS[s.block];
        return (
          <Series.Sequence key={i} premountFor={premountFor} durationInFrames={Math.max(1, s.durationInFrames)}>
            {s.audioSrc ? <Audio src={staticFile(s.audioSrc)} /> : null}
            {Block ? (
              <TransitionIn kind={s.transitionIn}>
                <AmbientDrift active={!SELF_MOVING.has(s.block) && !s.jitter}>
                  <Jitter j={s.jitter} seed={i + 1}>
                    <Edge kind={s.edge} seed={i + 1} jfps={s.jitter?.fps}>
                      <Block
                        {...s.props}
                        revealFrames={s.revealFrames}
                        words={s.words ?? []}
                        durationInFrames={s.durationInFrames}
                      />
                    </Edge>
                  </Jitter>
                </AmbientDrift>
              </TransitionIn>
            ) : null}
            {captions ? <Captions words={s.captionWords ?? s.words ?? []} /> : null}
          </Series.Sequence>
        );
      })}
    </Series>
  );
  // Optional global post-processing (color grade / bloom / grain / vignette).
  return fx ? <PostFX {...fx}>{series}</PostFX> : series;
};
