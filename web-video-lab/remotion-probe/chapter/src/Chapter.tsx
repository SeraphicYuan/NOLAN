import React from "react";
import { Series, Audio, staticFile } from "remotion";
import { BLOCKS } from "./blocks";

// The Chapter driver: a Series of steps. Each step renders its block for its
// narration's duration, with the step's audio. useCurrentFrame() inside a
// Series.Sequence is step-relative, so each block's revealFrames (derived from
// that step's word timestamps) line up with the spoken words automatically.
export type ChapterStep = {
  block: string;
  props: Record<string, unknown>;
  revealFrames: number[];
  audioSrc?: string;
  durationInFrames: number;
};

export const Chapter: React.FC<{ steps: ChapterStep[] }> = ({ steps }) => (
  <Series>
    {steps.map((s, i) => {
      const Block = (BLOCKS as Record<string, React.FC<Record<string, unknown>>>)[s.block];
      return (
        <Series.Sequence key={i} durationInFrames={Math.max(1, s.durationInFrames)}>
          {s.audioSrc ? <Audio src={staticFile(s.audioSrc)} /> : null}
          {Block ? (
            <Block {...s.props} revealFrames={s.revealFrames} durationInFrames={s.durationInFrames} />
          ) : null}
        </Series.Sequence>
      );
    })}
  </Series>
);
