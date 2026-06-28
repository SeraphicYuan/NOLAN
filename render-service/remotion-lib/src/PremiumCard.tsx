import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring} from 'remotion';
import {Theme, resolveTheme} from './theme';

export type PremiumCardProps = {
  kicker?: string;
  title: string;
  subtitle?: string;
  theme?: string | Partial<Theme>;             // SHARED
  cardStyle?: 'glass' | 'gradient' | 'spotlight'; // effect-specific
  durationInFrames: number;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const PremiumCard: React.FC<PremiumCardProps> = ({
  kicker, title, subtitle, theme, cardStyle = 'glass',
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const th = resolveTheme(theme);
  // slow drifting gradient mesh background
  const a = interpolate(frame, [0, durationInFrames], [0, 36]);
  const bgImage =
    `radial-gradient(circle at ${28 + a}% 32%, ${th.accent}44, transparent 42%),` +
    `radial-gradient(circle at ${74 - a}% 72%, ${th.up}33, transparent 46%)`;
  const titleS = spring({frame: frame - 6, fps, durationInFrames: 20, config: {damping: 200}});
  const subO = interpolate(frame, [22, 38], [0, 1], clamp);
  const kickO = interpolate(frame, [4, 16], [0, 1], clamp);

  const panel: React.CSSProperties =
    cardStyle === 'glass'
      ? {background: 'rgba(255,255,255,0.06)', backdropFilter: 'blur(18px)', border: '1px solid rgba(255,255,255,0.14)', boxShadow: '0 30px 90px rgba(0,0,0,0.55)'}
      : cardStyle === 'gradient'
        ? {background: `linear-gradient(135deg, ${th.accent}22, ${th.up}1a)`, border: `1px solid ${th.accent}44`}
        : {background: 'transparent'}; // spotlight = no panel, just glow bg

  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily}}>
      <AbsoluteFill style={{backgroundImage: bgImage}} />
      <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
        <div style={{...panel, borderRadius: 34, padding: '74px 110px', textAlign: 'center', maxWidth: 1500}}>
          {kicker && (
            <div style={{color: th.accent, fontSize: 36, fontWeight: 800, letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 26, opacity: kickO}}>
              {kicker}
            </div>
          )}
          <div style={{color: th.fg, fontSize: 110, fontWeight: 800, letterSpacing: '-0.02em', lineHeight: 1.05, transform: `translateY(${interpolate(titleS, [0, 1], [40, 0])}px)`, opacity: titleS}}>
            {title}
          </div>
          {subtitle && (
            <div style={{color: th.muted, fontSize: 44, fontWeight: 500, marginTop: 30, opacity: subO}}>
              {subtitle}
            </div>
          )}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
