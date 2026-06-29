import React from "react";
import { Composition } from "remotion";
import { Chapter } from "./Chapter";
import { Montage, montageDuration, type MontageStep, type Transition } from "./Montage";
import { FXSpike } from "./Effects";

// Chapter length = sum of the steps' durations (one Series.Sequence each, hard cuts).
const calcChapter = ({ props }: { props: { steps?: { durationInFrames?: number }[] } }) => ({
  durationInFrames:
    (props?.steps || []).reduce((a, s) => a + (s.durationInFrames || 0), 0) || 120,
});

// Montage length = sum(durations) − sum(transition overlaps).
const calcMontage = ({ props }: { props: { steps?: MontageStep[]; transitions?: Transition[] } }) => ({
  durationInFrames: montageDuration(props?.steps || [], props?.transitions || []),
});

export const Root: React.FC = () => (
  <>
    <Composition
      id="Chapter"
      component={Chapter as React.FC<Record<string, unknown>>}
      durationInFrames={120} fps={30} width={1920} height={1080}
      defaultProps={{ steps: [], captions: false }}
      calculateMetadata={calcChapter}
    />
    <Composition
      id="Montage"
      component={Montage as React.FC<Record<string, unknown>>}
      durationInFrames={120} fps={30} width={1920} height={1080}
      defaultProps={{ steps: [], transitions: [], motionBlur: false }}
      calculateMetadata={calcMontage}
    />
    <Composition id="FXSpike" component={FXSpike as React.FC<Record<string, unknown>>}
      durationInFrames={60} fps={30} width={1920} height={1080} />
  </>
);
