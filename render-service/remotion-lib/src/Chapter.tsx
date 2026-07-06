import React from "react";
import { Series, Audio, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
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
                <AmbientDrift active={!SELF_MOVING.has(s.block)}>
                  <Block
                    {...s.props}
                    revealFrames={s.revealFrames}
                    words={s.words ?? []}
                    durationInFrames={s.durationInFrames}
                  />
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
