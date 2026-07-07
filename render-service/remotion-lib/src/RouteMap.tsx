import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, spring} from 'remotion';
import {Theme, resolveTheme} from './theme';

type Pin = {x: number; y: number; label: string; isNew?: boolean};  // x,y in 0..1
// Motif contract: accumulated (old) pins render settled from frame 0;
// only pins stamped isNew animate in — the map REMEMBERS the journey.
export type RouteMapProps = {
  title: string;
  mapSrc?: string;                        // optional basemap image in public/
  pins: Pin[];
  theme?: string | Partial<Theme>;        // SHARED
  routeStyle?: 'arc' | 'straight';        // effect-specific
  durationInFrames: number;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const RouteMap: React.FC<RouteMapProps> = ({
  title, mapSrc, pins, theme, routeStyle = 'arc',
}) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const th = resolveTheme(theme);
  const pts = pins.map((p) => ({px: p.x * width, py: p.y * height, label: p.label, isNew: !!p.isNew}));
  const anyNew = pts.some((p) => p.isNew);
  // settled pins land instantly; new pins sequence in after a short hold.
  const newIdx = pts.map((p) => p.isNew).map((n, i, a) => a.slice(0, i + 1).filter(Boolean).length - 1);
  const tIn = (i: number) => (anyNew ? (pts[i].isNew ? 24 + newIdx[i] * 20 : 0) : i * 16);

  const route = (a: {px: number; py: number}, b: {px: number; py: number}) => {
    if (routeStyle === 'straight') return `M ${a.px} ${a.py} L ${b.px} ${b.py}`;
    const mx = (a.px + b.px) / 2, my = (a.py + b.py) / 2 - 150;
    return `M ${a.px} ${a.py} Q ${mx} ${my} ${b.px} ${b.py}`;
  };

  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily}}>
      {mapSrc
        ? <Img src={staticFile(mapSrc)} style={{position: 'absolute', width: '100%', height: '100%', objectFit: 'cover', opacity: 0.55}} />
        : <AbsoluteFill style={{backgroundImage: `radial-gradient(circle at 50% 45%, ${th.neutral}22, transparent 60%)`}} />}
      <div style={{position: 'absolute', top: 80, width: '100%', textAlign: 'center', color: th.fg, fontSize: 60, fontWeight: 800, letterSpacing: '-0.02em', textShadow: '0 2px 16px rgba(0,0,0,0.6)'}}>
        {title}
      </div>
      <svg width={width} height={height} style={{position: 'absolute', left: 0, top: 0}}>
        {pts.slice(0, -1).map((a, i) => {
          const b = pts[i + 1];
          const draw = interpolate(frame, [tIn(i + 1) + 4, tIn(i + 1) + 22], [0, 1], clamp);
          return (
            <path key={i} d={route(a, b)} fill="none" stroke={th.accent} strokeWidth={6}
              strokeLinecap="round" strokeDasharray="2 14" pathLength={1}
              style={{strokeDashoffset: 0, opacity: draw}} />
          );
        })}
        {pts.map((p, i) => {
          const s = spring({frame: frame - tIn(i), fps, durationInFrames: 16, config: {damping: 180}});
          const r = interpolate(s, [0, 1], [0, 16]);
          return (
            <g key={i} opacity={s}>
              <circle cx={p.px} cy={p.py} r={r + 10} fill={`${th.accent}33`} />
              <circle cx={p.px} cy={p.py} r={r} fill={th.accent} stroke={th.bg} strokeWidth={4} />
            </g>
          );
        })}
      </svg>
      {pts.map((p, i) => {
        const o = interpolate(frame, [tIn(i) + 6, tIn(i) + 18], [0, 1], clamp);
        return (
          <div key={i} style={{position: 'absolute', left: p.px + 26, top: p.py - 24, color: th.fg, fontSize: 38, fontWeight: 800, opacity: o, textShadow: '0 2px 12px rgba(0,0,0,0.8)'}}>
            {p.label}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
