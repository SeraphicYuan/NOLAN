import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';
import {Theme, resolveTheme} from './theme';

// BarRace — the racing bar chart: values grow AND overtake, bars reordering
// smoothly as the leader changes. Distinct from a static bar chart; use when the
// story is a race/accumulation over time. Rows are placed by a soft-rank so
// crossings glide instead of snapping.
export type BarRaceProps = {
  title?: string;
  bars: {label: string; value: number; color?: string}[];
  prefix?: string;
  suffix?: string;
  theme?: string | Partial<Theme>;
  durationInFrames: number;
};

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));
const commafy = (n: number) => Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');

export const BarRace: React.FC<BarRaceProps> = ({
  title = '', bars, prefix = '', suffix = '', theme, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: cfgDur} = useVideoConfig();
  const th = resolveTheme(theme);
  const total = Math.max(2, durationInFrames || cfgDur || 150);
  const list = (bars || []).slice(0, 8);
  const n = list.length || 1;

  const grow = interpolate(frame, [10, total * 0.82], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  // per-bar staggered growth toward its value
  const cur = list.map((b, i) => {
    const g = interpolate(frame, [10 + i * 4, total * 0.82], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
    return b.value * g;
  });
  const maxV = Math.max(1, ...cur, ...list.map((b) => b.value * grow));

  const rowH = 108, barMax = 1180, left = 360, topPad = title ? 210 : 120;
  const scale = Math.max(1, ...cur) || 1;

  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily}}>
      {title ? (
        <div style={{position: 'absolute', top: 84, left, fontSize: 60, fontWeight: 800, color: th.fg, letterSpacing: '-0.02em'}}>{title}</div>
      ) : null}
      {list.map((b, i) => {
        // soft rank: how many bars currently exceed this one (continuous)
        // steep soft-rank: near-integer separation (no row overlap) but still glides on a crossing
        const rank = cur.reduce((acc, v, j) => (j === i ? acc : acc + sigmoid((v - cur[i]) / (scale * 0.014 + 1))), 0);
        const y = topPad + rank * rowH;
        const w = interpolate(cur[i] / maxV, [0, 1], [0, barMax]);
        const color = b.color || th.accent;
        const appear = interpolate(frame, [i * 3, i * 3 + 12], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
        return (
          <div key={i} style={{position: 'absolute', top: y, left: 0, right: 0, height: rowH, display: 'flex', alignItems: 'center', opacity: appear}}>
            <div style={{width: left - 40, textAlign: 'right', paddingRight: 24, fontSize: 40, fontWeight: 700, color: th.fg}}>{b.label}</div>
            <div style={{position: 'relative', height: 74, width: Math.max(6, w), borderRadius: 10,
              background: `linear-gradient(90deg, ${color}cc, ${color})`, boxShadow: `0 6px 24px ${color}44`}}>
              <div style={{position: 'absolute', right: -18, top: '50%', transform: 'translate(100%,-50%)', fontSize: 40, fontWeight: 800,
                color: th.fg, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap'}}>{prefix}{commafy(cur[i])}{suffix}</div>
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
