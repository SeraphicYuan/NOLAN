import React from "react";
import { Series, Audio, staticFile, useVideoConfig } from "remotion";
import { BLOCKS } from "./blocks";
import { Captions } from "./Captions";
import { PostFX, type PostFXProps } from "./Effects";

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
        const Block = (BLOCKS as Record<string, React.FC<Record<string, unknown>>>)[s.block];
        return (
          <Series.Sequence key={i} premountFor={premountFor} durationInFrames={Math.max(1, s.durationInFrames)}>
            {s.audioSrc ? <Audio src={staticFile(s.audioSrc)} /> : null}
            {Block ? (
              <Block
                {...s.props}
                revealFrames={s.revealFrames}
                words={s.words ?? []}
                durationInFrames={s.durationInFrames}
              />
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
