import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring} from 'remotion';
import {Theme, resolveTheme} from './theme';
import {scribbleEllipse} from './shapes';
import {Position, resolveAnchor} from './layout';

export type AnnotateStatProps = {
  value: string;
  label: string;
  theme?: string | Partial<Theme>;       // SHARED
  shapeStyle?: 'clean' | 'scribble';     // effect-specific
  position?: Position;                   // SHARED layout: anchor or {x,y}
  accent?: string;
  durationInFrames: number;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const AnnotateStat: React.FC<AnnotateStatProps> = ({
  value, label, theme, shapeStyle = 'clean', position = 'center', accent,
}) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const th = resolveTheme(theme);
  const stroke = accent || th.accent;
  const {x: cx, y: cy} = resolveAnchor(position, width, height);
  const rx = 470, ry = 210;
  const circ = 2 * Math.PI * ((rx + ry) / 2);
  const draw = interpolate(frame, [16, 50], [0, 1], clamp);
  const pop = spring({frame, fps, durationInFrames: 18, config: {damping: 200}});
  const labelO = interpolate(frame, [44, 60], [0, 1], clamp);
  const scribble = scribbleEllipse(cx, cy, rx, ry, 'stat', 16, 48, -5);
  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily}}>
      {/* value + label block, centered on the anchor (matches the circle) */}
      <div style={{position: 'absolute', left: cx, top: cy, transform: 'translate(-50%, -50%)', textAlign: 'center', whiteSpace: 'nowrap'}}>
        <div style={{color: th.fg, fontSize: 200, fontWeight: 800, transform: `scale(${interpolate(pop, [0, 1], [0.9, 1])})`, opacity: pop, lineHeight: 1}}>
          {value}
        </div>
        <div style={{color: th.muted, fontSize: 44, fontWeight: 600, marginTop: 24, opacity: labelO}}>{label}</div>
      </div>
      <svg width={width} height={height} style={{position: 'absolute', left: 0, top: 0}}>
        {shapeStyle === 'scribble' ? (
          <path d={scribble} fill="none" stroke={stroke} strokeWidth={9} strokeLinecap="round" strokeLinejoin="round"
            pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} />
        ) : (
          <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke={stroke} strokeWidth={11}
            strokeDasharray={circ} strokeDashoffset={circ * (1 - draw)} strokeLinecap="round"
            transform={`rotate(-5 ${cx} ${cy})`} />
        )}
      </svg>
    </AbsoluteFill>
  );
};
