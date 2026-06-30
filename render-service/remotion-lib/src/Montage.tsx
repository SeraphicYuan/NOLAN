import React from "react";
import { useVideoConfig } from "remotion";
import { TransitionSeries, linearTiming, springTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";
import { clockWipe } from "@remotion/transitions/clock-wipe";
import { CameraMotionBlur } from "@remotion/motion-blur";
import { BLOCKS } from "./blocks";

// Montage — the TRANSITION layer (a scene grammar between beats). Unlike the
// narrated Chapter (hard cuts, audio-safe — overlapping <Audio> would overlap
// speech), Montage strings *silent* cards/charts with designed transitions
// (@remotion/transitions) + optional camera motion-blur. Film-grammar default:
// cut within a topic, fade/dissolve between topics. Per-gap transition is
// configurable; total duration accounts for the overlap each transition steals.
export type WordFrame = { text: string; startFrame: number; endFrame: number };
export type MontageStep = {
  block: string;
  props: Record<string, unknown>;
  revealFrames: number[];
  words?: WordFrame[];
  durationInFrames: number;
};
export type Transition = { type?: "fade" | "slide" | "wipe" | "clockWipe"; durationInFrames?: number; direction?: string };

const present = (t: Transition, w: number, h: number) => {
  switch (t.type) {
    case "slide": return slide({ direction: (t.direction as never) ?? "from-right" });
    case "wipe": return wipe({ direction: (t.direction as never) ?? "from-left" });
    case "clockWipe": return clockWipe({ width: w, height: h });
    default: return fade();
  }
};

export const Montage: React.FC<{ steps: MontageStep[]; transitions?: Transition[]; motionBlur?: boolean }> = ({
  steps, transitions = [], motionBlur = false,
}) => {
  const { width, height } = useVideoConfig();
  const body = (
    <TransitionSeries>
      {steps.flatMap((s, i) => {
        const Block = (BLOCKS as Record<string, React.FC<Record<string, unknown>>>)[s.block];
        const seq = (
          <TransitionSeries.Sequence key={`s${i}`} durationInFrames={Math.max(1, s.durationInFrames)}>
            {Block ? (
              <Block {...s.props} revealFrames={s.revealFrames} words={s.words ?? []} durationInFrames={s.durationInFrames} />
            ) : null}
          </TransitionSeries.Sequence>
        );
        if (i === steps.length - 1) return [seq];
        const t = transitions[i] ?? { type: "fade", durationInFrames: 16 };
        const dur = t.durationInFrames ?? 16;
        const timing = t.type === "slide" || t.type === "clockWipe"
          ? springTiming({ config: { damping: 200 }, durationInFrames: dur })
          : linearTiming({ durationInFrames: dur });
        return [seq,
          <TransitionSeries.Transition key={`t${i}`} presentation={present(t, width, height)} timing={timing} />];
      })}
    </TransitionSeries>
  );
  return motionBlur ? <CameraMotionBlur>{body}</CameraMotionBlur> : body;
};

/** Total frames a montage occupies = sum(durations) − sum(transition overlaps). */
export const montageDuration = (steps: MontageStep[], transitions: Transition[] = []): number => {
  const sum = steps.reduce((a, s) => a + Math.max(1, s.durationInFrames), 0);
  const overlap = steps.slice(0, -1).reduce((a, _s, i) => a + ((transitions[i]?.durationInFrames ?? 16)), 0);
  return Math.max(1, sum - overlap);
};
