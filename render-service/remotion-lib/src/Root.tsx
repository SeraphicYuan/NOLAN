import React from 'react';
import {Composition} from 'remotion';
import {KineticText} from './KineticText';
import {BarCompare} from './BarCompare';
import {KShape} from './KShape';
import {AnnotateOverVideo} from './AnnotateOverVideo';
import {AnnotateStat} from './AnnotateStat';
import {RouteMap} from './RouteMap';
import {PremiumCard} from './PremiumCard';
import {PhotoMontage} from './PhotoMontage';
import {PhotoGrid} from './PhotoGrid';
import {Showcase} from './Showcase';
// Folded-in flow bundle (was _lab_chapter): the Chapter Series + its blocks.
import {Chapter} from './Chapter';
import {Montage, montageDuration, type MontageStep, type Transition} from './Montage';
import {FXSpike} from './Effects';

// Curated Remotion source — one composition per registered scene type.
// Shared style (`theme`) + per-effect style vars (lineStyle/barStyle/shapeStyle/…).
const dur = ({props}: {props: {durationInFrames?: number}}) => ({
  durationInFrames: props.durationInFrames ?? 120,
});
const common = {fps: 30, width: 1920, height: 1080} as const;

// Chapter length = sum of the steps' durations (one Series.Sequence each, hard cuts).
const calcChapter = ({props}: {props: {steps?: {durationInFrames?: number}[]}}) => ({
  durationInFrames: (props?.steps || []).reduce((a, s) => a + (s.durationInFrames || 0), 0) || 120,
});
const calcMontage = ({props}: {props: {steps?: MontageStep[]; transitions?: Transition[]}}) => ({
  durationInFrames: montageDuration(props?.steps || [], props?.transitions || []),
});

export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="Kinetic" component={KineticText} durationInFrames={120} {...common}
        defaultProps={{
          text: 'Kinetic text', highlights: [] as string[], theme: undefined as any,
          accent: undefined as any, position: 'center' as any, scrim: 0.45, durationInFrames: 120,
          videoSrc: undefined as string | undefined,
        }}
        calculateMetadata={dur}
      />
      <Composition
        id="BarCompare" component={BarCompare} durationInFrames={150} {...common}
        defaultProps={{title: '', bars: [], suffix: '', prefix: '', theme: undefined as any, barStyle: 'gradient' as const, durationInFrames: 150}}
        calculateMetadata={dur}
      />
      <Composition
        id="KShape" component={KShape} durationInFrames={150} {...common}
        defaultProps={{title: '', topLabel: '', bottomLabel: '', theme: undefined as any, lineStyle: 'straight' as const, jitter: 22, segments: 16, durationInFrames: 150}}
        calculateMetadata={dur}
      />
      <Composition
        id="AnnotateOverVideo" component={AnnotateOverVideo} durationInFrames={150} {...common}
        defaultProps={{videoSrc: undefined as string | undefined, focusX: 0.5, focusY: 0.45, rx: 200, ry: 150, label: '', theme: undefined as any, shapeStyle: 'clean' as const, accent: undefined as any, scrim: 0.12, durationInFrames: 150}}
        calculateMetadata={dur}
      />
      <Composition
        id="AnnotateStat" component={AnnotateStat} durationInFrames={150} {...common}
        defaultProps={{value: '', label: '', theme: undefined as any, shapeStyle: 'clean' as const, position: 'center' as any, accent: undefined as any, durationInFrames: 150}}
        calculateMetadata={dur}
      />
      <Composition
        id="RouteMap" component={RouteMap} durationInFrames={150} {...common}
        defaultProps={{title: '', mapSrc: undefined as string | undefined, pins: [], theme: undefined as any, routeStyle: 'arc' as const, durationInFrames: 150}}
        calculateMetadata={dur}
      />
      <Composition
        id="PremiumCard" component={PremiumCard} durationInFrames={150} {...common}
        defaultProps={{kicker: '', title: '', subtitle: '', theme: undefined as any, cardStyle: 'glass' as const, durationInFrames: 150}}
        calculateMetadata={dur}
      />
      <Composition
        id="PhotoMontage" component={PhotoMontage} durationInFrames={300} {...common}
        defaultProps={{
          cards: [] as any[], background: undefined as string | undefined, vignette: 0.5,
          zoomStart: 1.05, zoomEnd: 1.16, panX: -0.04, panY: 0,
          theme: undefined as any, durationInFrames: 300,
        }}
        calculateMetadata={dur}
      />
      <Composition
        id="PhotoGrid" component={PhotoGrid} durationInFrames={360} {...common}
        defaultProps={{
          cards: [] as any[], cols: 8, rows: 5, order: 'one-by-one' as const,
          flyFrom: 'edges' as const, fillStart: 0.2, stagger: 0.08, flyDur: 0.6,
          focusIndex: undefined as any, focusAt: undefined as any, focusMove: 0.7,
          focusHold: 1.6, focusScale: 0.8, margin: 0.05, frame: 'polaroid' as const,
          background: '#241016', vignette: 0.5, theme: undefined as any, durationInFrames: 360,
        }}
        calculateMetadata={dur}
      />
      <Composition
        id="Showcase" component={Showcase} durationInFrames={900} {...common}
        defaultProps={{segments: [], introTitle: 'NOLAN · Remotion Motion Library', perFrames: 120, introFrames: 60, durationInFrames: 900}}
        calculateMetadata={dur}
      />
      {/* ── flow bundle: the Chapter Series of step-blocks (+ Montage, FXSpike) ── */}
      <Composition
        id="Chapter" component={Chapter as React.FC<Record<string, unknown>>}
        durationInFrames={120} {...common}
        defaultProps={{steps: [], captions: false}} calculateMetadata={calcChapter}
      />
      <Composition
        id="Montage" component={Montage as React.FC<Record<string, unknown>>}
        durationInFrames={120} {...common}
        defaultProps={{steps: [], transitions: [], motionBlur: false}} calculateMetadata={calcMontage}
      />
      <Composition id="FXSpike" component={FXSpike as React.FC<Record<string, unknown>>}
        durationInFrames={60} {...common} />
    </>
  );
};
