import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig, interpolate, spring} from 'remotion';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {resolveTheme} from './theme';

type Seg = {src: string; label: string; category: string};
export type ShowcaseProps = {
  segments: Seg[];
  introTitle: string;
  perFrames: number;
  introFrames: number;
  durationInFrames: number;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const th = resolveTheme('dark-editorial');

const Intro: React.FC<{title: string; count: number}> = ({title, count}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame, fps, durationInFrames: 20, config: {damping: 200}});
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', textAlign: 'center'}}>
      <AbsoluteFill style={{backgroundImage: `radial-gradient(circle at 50% 42%, ${th.accent}33, transparent 55%)`}} />
      <div style={{color: th.accent, fontSize: 30, fontWeight: 800, letterSpacing: '0.22em', textTransform: 'uppercase', opacity: s}}>
        Curated Remotion source
      </div>
      <div style={{color: th.fg, fontSize: 84, fontWeight: 800, marginTop: 20, transform: `translateY(${interpolate(s, [0, 1], [30, 0])}px)`, opacity: s}}>
        {title}
      </div>
      <div style={{color: th.muted, fontSize: 38, marginTop: 18, opacity: interpolate(frame, [14, 28], [0, 1], clamp)}}>
        {count} effects · kinetic-text · charts · annotations · map · cards
      </div>
    </AbsoluteFill>
  );
};

const Label: React.FC<{index: number; total: number; name: string; category: string}> = ({index, total, name, category}) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [2, 12], [0, 1], clamp);
  return (
    <div style={{position: 'absolute', left: 64, bottom: 64, opacity: o, textShadow: '0 2px 16px rgba(0,0,0,0.85)'}}>
      <div style={{color: th.accent, fontSize: 26, fontWeight: 800, letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 8}}>{category}</div>
      <div style={{display: 'flex', alignItems: 'baseline', gap: 18}}>
        <span style={{color: th.accent, fontSize: 34, fontWeight: 800}}>{String(index).padStart(2, '0')}/{String(total).padStart(2, '0')}</span>
        <span style={{color: th.fg, fontSize: 52, fontWeight: 800}}>{name}</span>
      </div>
    </div>
  );
};

export const Showcase: React.FC<ShowcaseProps> = ({segments, introTitle, perFrames, introFrames}) => {
  const xfade = linearTiming({durationInFrames: 14});
  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily}}>
      <TransitionSeries>
        <TransitionSeries.Sequence durationInFrames={introFrames}>
          <Intro title={introTitle} count={segments.length} />
        </TransitionSeries.Sequence>
        {segments.map((s, i) => (
          <React.Fragment key={i}>
            <TransitionSeries.Transition timing={xfade} presentation={fade()} />
            <TransitionSeries.Sequence durationInFrames={perFrames}>
              <AbsoluteFill style={{backgroundColor: th.bg}}>
                <OffthreadVideo src={staticFile(s.src)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
                <Label index={i + 1} total={segments.length} name={s.label} category={s.category} />
              </AbsoluteFill>
            </TransitionSeries.Sequence>
          </React.Fragment>
        ))}
      </TransitionSeries>
    </AbsoluteFill>
  );
};
