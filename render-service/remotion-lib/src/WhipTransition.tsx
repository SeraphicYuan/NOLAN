import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';
import {Theme, resolveTheme} from './theme';

// WhipTransition — a fast whip-pan with motion blur handing off from one shot to
// the next. The punchy speed-cut that drives modern YouTube pacing. Holds the
// FROM shot, whips (blur + slide + slight scale) through the midpoint, settles on
// the TO shot. background = from image, foreground = to image (both staged).
export type WhipTransitionProps = {
  background?: string;   // from
  foreground?: string;   // to
  direction?: 'left' | 'right';
  theme?: string | Partial<Theme>;
  durationInFrames: number;
};

const cover: React.CSSProperties = {width: '100%', height: '100%', objectFit: 'cover'};

export const WhipTransition: React.FC<WhipTransitionProps> = ({
  background, foreground, direction = 'left', theme, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: cfgDur, width} = useVideoConfig();
  const th = resolveTheme(theme);
  const total = Math.max(2, durationInFrames || cfgDur || 90);
  const sign = direction === 'left' ? -1 : 1;

  const p = interpolate(frame, [total * 0.3, total * 0.7], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)});
  const blur = Math.sin(p * Math.PI) * 46;                 // peaks at the midpoint
  const scale = 1 + Math.sin(p * Math.PI) * 0.1;

  // BOTH layers pan modest distances and crossfade through the midpoint, so the
  // frame is always filled — no empty gap at the handoff.
  const travel = width * 0.55;
  const fromX = -sign * p * travel;
  const toX = sign * (1 - p) * travel;
  const fromOpacity = interpolate(p, [0.35, 0.6], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const toOpacity = interpolate(p, [0.4, 0.65], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const img = (src?: string, fallback?: string) =>
    src ? <Img src={staticFile(src)} style={cover} /> : <AbsoluteFill style={{background: fallback || th.neutral}} />;

  return (
    <AbsoluteFill style={{backgroundColor: th.bg, overflow: 'hidden'}}>
      <AbsoluteFill style={{transform: `translateX(${fromX}px) scale(${scale})`, filter: `blur(${blur}px)`, opacity: fromOpacity}}>
        {img(background)}
      </AbsoluteFill>
      <AbsoluteFill style={{transform: `translateX(${toX}px) scale(${scale})`, filter: `blur(${blur}px)`, opacity: toOpacity}}>
        {img(foreground, th.accent)}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
