import React from "react";
import { Composition } from "remotion";
import { ListReveal } from "./ListReveal";

// duration is data-driven from the job's durationInFrames
const dur = ({ props }: { props: { durationInFrames?: number } }) => ({
  durationInFrames: props.durationInFrames ?? 120,
});

export const Root: React.FC = () => (
  <>
    <Composition
      id="ListReveal"
      component={ListReveal as React.FC<Record<string, unknown>>}
      durationInFrames={120}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{ items: [], revealFrames: [], durationInFrames: 120 }}
      calculateMetadata={dur}
    />
  </>
);
