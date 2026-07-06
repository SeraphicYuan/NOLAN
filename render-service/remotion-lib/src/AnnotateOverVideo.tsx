import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {Theme, resolveTheme} from './theme';
import {scribbleEllipse} from './shapes';

export type AnnotateProps = {
  videoSrc?: string;
  focusX: number; focusY: number; rx: number; ry: number;
  label: string;
  theme?: string | Partial<Theme>;       // SHARED
  shapeStyle?: 'clean' | 'scribble';     // effect-specific
  accent?: string;
  scrim: number;
  durationInFrames: number;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const AnnotateOverVideo: React.FC<AnnotateProps> = ({
  videoSrc, focusX = 0.5, focusY = 0.42, rx = 190, ry = 120, label,
  theme, shapeStyle = 'clean', accent, scrim = 0,
}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const th = resolveTheme(theme);
  const stroke = accent || th.accent;
  const cx = focusX * width, cy = focusY * height;
  const circ = 2 * Math.PI * ((rx + ry) / 2);
  const drawC = interpolate(frame, [10, 42], [0, 1], clamp);
  const arrowP = interpolate(frame, [44, 60], [0, 1], clamp);
  const labelO = interpolate(frame, [58, 70], [0, 1], clamp);
  const ax0 = cx - 480, ay0 = cy + 340;
  const ax1 = cx - (rx + 26), ay1 = cy + 52;
  const aX = ax0 + (ax1 - ax0) * arrowP, aY = ay0 + (ay1 - ay0) * arrowP;
  const scribble = scribbleEllipse(cx, cy, rx, ry, 'annot', 14, 46, -11);
  return (
    <AbsoluteFill style={{backgroundColor: 'transparent', fontFamily: th.fontFamily}}>
      {videoSrc && <OffthreadVideo src={staticFile(videoSrc)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />}
      {scrim > 0 && <AbsoluteFill style={{backgroundColor: `rgba(0,0,0,${scrim})`}} />}
      <svg width={width} height={height} style={{position: 'absolute', left: 0, top: 0}}>
        {shapeStyle === 'scribble' ? (
          <path d={scribble} fill="none" stroke={stroke} strokeWidth={8} strokeLinecap="round" strokeLinejoin="round"
            pathLength={1} strokeDasharray={1} strokeDashoffset={1 - drawC} />
        ) : (
          <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke={stroke} strokeWidth={9}
            strokeDasharray={circ} strokeDashoffset={circ * (1 - drawC)} strokeLinecap="round"
            transform={`rotate(-11 ${cx} ${cy})`} />
        )}
        {arrowP > 0 && <line x1={ax0} y1={ay0} x2={aX} y2={aY} stroke={stroke} strokeWidth={8} strokeLinecap="round" />}
        {arrowP > 0.92 && <polygon points={`${ax1},${ay1} ${ax1 - 26},${ay1 + 4} ${ax1 - 4},${ay1 + 26}`} fill={stroke} />}
      </svg>
      {label && (
        <div style={{position: 'absolute', left: ax0 - 30, top: ay0 + 24, color: stroke, fontSize: 48, fontWeight: 800, opacity: labelO, textShadow: '0 2px 14px rgba(0,0,0,0.75)', maxWidth: 560}}>
          {label}
        </div>
      )}
    </AbsoluteFill>
  );
};
