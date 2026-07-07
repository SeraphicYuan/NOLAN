import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';
import {Theme, resolveTheme} from './theme';

// BeforeAfter — a slider wipe revealing an "after" image over a "before" image.
// The canonical restoration / change / claim-vs-reality device. A divider handle
// sweeps left→right after a brief hold; labels sit in the bottom corners.
// background = before image, foreground = after image (both staged).
export type BeforeAfterProps = {
  background?: string;   // before
  foreground?: string;   // after
  before_label?: string;
  after_label?: string;
  accent?: string;
  theme?: string | Partial<Theme>;
  durationInFrames: number;
};

const cover: React.CSSProperties = {width: '100%', height: '100%', objectFit: 'cover'};

export const BeforeAfter: React.FC<BeforeAfterProps> = ({
  background, foreground, before_label = '', after_label = '', accent, theme, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: cfgDur} = useVideoConfig();
  const th = resolveTheme(theme);
  const total = Math.max(2, durationInFrames || cfgDur || 120);
  const hi = accent || th.accent;

  const split = interpolate(frame, [total * 0.12, total * 0.78], [0.04, 0.96],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)});
  const pct = split * 100;

  const labelStyle: React.CSSProperties = {
    position: 'absolute', bottom: 56, padding: '10px 22px', borderRadius: 10, fontSize: 34, fontWeight: 700,
    color: th.fg, background: `${th.bg}cc`, backdropFilter: 'blur(6px)',
  };

  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily, overflow: 'hidden'}}>
      {/* before (full frame) */}
      {background ? <Img src={staticFile(background)} style={cover} /> : <AbsoluteFill style={{background: th.neutral}} />}
      {/* after, revealed from the left up to the split */}
      <AbsoluteFill style={{clipPath: `inset(0 ${100 - pct}% 0 0)`}}>
        {foreground ? <Img src={staticFile(foreground)} style={cover} /> : <AbsoluteFill style={{background: th.accent}} />}
      </AbsoluteFill>
      {/* divider + handle */}
      <div style={{position: 'absolute', top: 0, bottom: 0, left: `${pct}%`, width: 4, background: hi, transform: 'translateX(-2px)', boxShadow: `0 0 24px ${hi}aa`}} />
      <div style={{position: 'absolute', top: '50%', left: `${pct}%`, width: 72, height: 72, borderRadius: '50%',
        transform: 'translate(-50%,-50%)', background: hi, display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: th.bg, fontSize: 30, fontWeight: 900, boxShadow: `0 8px 30px ${th.bg}aa`}}>⟺</div>
      {before_label ? <div style={{...labelStyle, left: 56}}>{before_label}</div> : null}
      {after_label ? <div style={{...labelStyle, right: 56, opacity: interpolate(frame, [total * 0.2, total * 0.35], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>{after_label}</div> : null}
    </AbsoluteFill>
  );
};
