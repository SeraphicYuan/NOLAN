import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, staticFile, useVideoConfig} from 'remotion';
import {TransitionSeries, linearTiming, springTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {slide} from '@remotion/transitions/slide';
import {wipe} from '@remotion/transitions/wipe';
import {clockWipe} from '@remotion/transitions/clock-wipe';

// ClipMontage — assemble a sequence of b-roll CLIPS/STILLS with shot-to-shot transitions
// (@remotion/transitions). Film grammar: cut within a beat, dissolve/dip between beats.
// Each clip is staged into public/ via the `cards` channel ({src, kind, durationInFrames}).
export type Clip = {src: string; kind?: 'video' | 'image'; durationInFrames: number};
export type ClipTransition = {type?: 'fade' | 'slide' | 'wipe' | 'clockWipe' | 'cut'; durationInFrames?: number; direction?: string};

const cover: React.CSSProperties = {width: '100%', height: '100%', objectFit: 'cover'};

const present = (t: ClipTransition, w: number, h: number) => {
  switch (t.type) {
    case 'slide': return slide({direction: (t.direction as never) ?? 'from-right'});
    case 'wipe': return wipe({direction: (t.direction as never) ?? 'from-left'});
    case 'clockWipe': return clockWipe({width: w, height: h});
    default: return fade();
  }
};

export const clipMontageDuration = (cards: Clip[] = [], transitions: ClipTransition[] = []): number => {
  const sum = cards.reduce((a, c) => a + Math.max(1, c.durationInFrames || 0), 0);
  const overlap = cards.slice(1).reduce((a, _c, i) => {
    const t = transitions[i] ?? {type: 'fade', durationInFrames: 16};
    return a + (t.type === 'cut' ? 0 : (t.durationInFrames ?? 16));
  }, 0);
  return Math.max(1, sum - overlap);
};

export const ClipMontage: React.FC<{cards: Clip[]; transitions?: ClipTransition[]}> = ({cards = [], transitions = []}) => {
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      <TransitionSeries>
        {cards.flatMap((c, i) => {
          const seq = (
            <TransitionSeries.Sequence key={`s${i}`} durationInFrames={Math.max(1, c.durationInFrames)}>
              {c.kind === 'image'
                ? <Img src={staticFile(c.src)} style={cover} />
                : <OffthreadVideo src={staticFile(c.src)} style={cover} muted />}
            </TransitionSeries.Sequence>
          );
          if (i === 0) return [seq];
          const t = transitions[i - 1] ?? {type: 'fade', durationInFrames: 16};
          if (t.type === 'cut') return [seq];             // hard cut — no Transition element
          const timing = (t.type === 'slide' || t.type === 'clockWipe')
            ? springTiming({config: {damping: 200}, durationInFrames: t.durationInFrames ?? 18})
            : linearTiming({durationInFrames: t.durationInFrames ?? 16});
          return [
            <TransitionSeries.Transition key={`t${i}`} presentation={present(t, width, height)} timing={timing} />,
            seq,
          ];
        })}
      </TransitionSeries>
    </AbsoluteFill>
  );
};
