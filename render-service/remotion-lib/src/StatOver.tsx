import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';
import {Theme, resolveTheme} from './theme';

// StatOver — the SCALE operator's payoff: a big count-up NUMBER over a tangible-referent shot
// (stadium crowd / city aerial / grains of sand), with a caption. Every text/number style comes
// from the video's THEME (resolveTheme → fontFamily/fg/accent/bg), like counter / kinetic-text /
// bar-compare — so it matches the rest of the piece. background = still, videoSrc = live footage.
export type StatOverProps = {
  value: number;                 // the number to count up to
  prefix?: string;               // e.g. "$"
  suffix?: string;               // e.g. "B", "%"
  caption?: string;              // e.g. "the annual budget"
  decimals?: number;             // decimal places (default 0)
  background?: string;           // staged still basename
  videoSrc?: string;             // staged video basename (live referent footage)
  accent?: string;               // optional override of theme.accent
  theme?: string | Partial<Theme>;
  durationInFrames: number;
};

const easeOut = Easing.out(Easing.cubic);
const cover: React.CSSProperties = {width: '100%', height: '100%', objectFit: 'cover'};

const commafy = (n: number, decimals: number) => {
  const r = decimals > 0 ? n.toFixed(decimals) : Math.round(n).toString();
  const [i, d] = r.split('.');
  const ii = i.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return d ? `${ii}.${d}` : ii;
};

export const StatOver: React.FC<StatOverProps> = ({
  value, prefix = '', suffix = '', caption = '', decimals = 0,
  background, videoSrc, accent, theme, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: cfgDur, fps} = useVideoConfig();
  const total = Math.max(2, durationInFrames || cfgDur || 120);
  const th = resolveTheme(theme);
  const hi = accent || th.accent;

  const countEnd = Math.min(total - 6, Math.round(total * 0.62));
  const n = interpolate(frame, [8, countEnd], [0, value], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeOut});
  const appear = interpolate(frame, [4, 20], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const capAppear = interpolate(frame, [countEnd - 6, countEnd + 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily}}>
      {videoSrc ? <OffthreadVideo src={staticFile(videoSrc)} style={cover} muted />
        : background ? <Img src={staticFile(background)} style={cover} /> : null}
      {/* legibility scrim keyed to the theme background */}
      <AbsoluteFill style={{background: `linear-gradient(180deg, ${th.bg}22 0%, ${th.bg}66 55%, ${th.bg}cc 100%)`}} />
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', opacity: appear}}>
        <div style={{
          fontWeight: 900, fontSize: 220, lineHeight: 0.95, letterSpacing: '-0.03em', color: hi,
          textShadow: `0 6px 30px ${th.bg}cc`, fontVariantNumeric: 'tabular-nums',
        }}>{prefix}{commafy(n, decimals)}{suffix}</div>
        {caption ? (
          <div style={{
            marginTop: 18, fontSize: 40, fontWeight: 600, color: th.fg, opacity: capAppear,
            letterSpacing: '0.01em', textShadow: `0 2px 12px ${th.bg}aa`,
          }}>{caption}</div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
