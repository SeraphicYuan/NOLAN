import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {Theme, resolveTheme} from './theme';
import {jaggedPath} from './shapes';

export type KShapeProps = {
  title: string;
  topLabel: string;
  bottomLabel: string;
  theme?: string | Partial<Theme>;   // SHARED style
  lineStyle: 'straight' | 'zigzag';  // effect-specific
  jitter: number;
  segments: number;
  durationInFrames: number;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const KShape: React.FC<KShapeProps> = ({
  title, topLabel, bottomLabel, theme, lineStyle, jitter, segments,
}) => {
  const frame = useCurrentFrame();
  const {width, height, durationInFrames} = useVideoConfig();
  const th = resolveTheme(theme);
  const x0 = 360, y0 = 560, x1 = 1440, topY = 220, botY = 940;
  const j = lineStyle === 'zigzag' ? jitter : 0;
  const segs = lineStyle === 'zigzag' ? segments : 1;
  const topPath = jaggedPath(x0, y0, x1, topY, segs, j, 'top');
  const botPath = jaggedPath(x0, y0, x1, botY, segs, j, 'bot');
  const draw = interpolate(frame, [12, durationInFrames * 0.72], [0, 1], clamp);
  const labelO = interpolate(draw, [0.85, 1], [0, 1], clamp);
  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily}}>
      <div style={{position: 'absolute', top: 90, width: '100%', textAlign: 'center', color: th.fg, fontSize: 62, fontWeight: 800, letterSpacing: '-0.02em'}}>
        {title}
      </div>
      <svg width={width} height={height} style={{position: 'absolute'}}>
        <path d={topPath} fill="none" stroke={th.up} strokeWidth={11} strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} />
        <path d={botPath} fill="none" stroke={th.down} strokeWidth={11} strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} />
        <circle cx={x0} cy={y0} r={13} fill={th.fg} />
        <circle cx={x1} cy={topY} r={14} fill={th.up} opacity={labelO} />
        <circle cx={x1} cy={botY} r={14} fill={th.down} opacity={labelO} />
      </svg>
      <div style={{position: 'absolute', left: x1 + 26, top: topY - 56, color: th.up, fontSize: 44, fontWeight: 800, opacity: labelO}}>{topLabel}</div>
      <div style={{position: 'absolute', left: x1 + 26, top: botY - 6, color: th.down, fontSize: 44, fontWeight: 800, opacity: labelO}}>{bottomLabel}</div>
    </AbsoluteFill>
  );
};
