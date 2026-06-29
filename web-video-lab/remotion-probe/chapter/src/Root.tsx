import React from "react";
import { Composition } from "remotion";
import { Chapter } from "./Chapter";

// Composition length = sum of the steps' durations (one Series.Sequence each).
const calc = ({ props }: { props: { steps?: { durationInFrames?: number }[] } }) => ({
  durationInFrames:
    (props?.steps || []).reduce((a, s) => a + (s.durationInFrames || 0), 0) || 120,
});

export const Root: React.FC = () => (
  <Composition
    id="Chapter"
    component={Chapter as React.FC<Record<string, unknown>>}
    durationInFrames={120}
    fps={30}
    width={1920}
    height={1080}
    defaultProps={{ steps: [] }}
    calculateMetadata={calc}
  />
);
