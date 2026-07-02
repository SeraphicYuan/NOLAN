import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';

// SplitScreen — the "collision" render for the relational/dialectical operator: two stills
// side by side (left = background, right = foreground), each with a slow opposing push, a thin
// divider, and optional labels. Shot A + shot B on screen at once = the juxtaposition.
export type SplitScreenProps = {
  background: string;           // left image (staged basename)
  foreground: string;          // right image (staged basename)
  leftLabel?: string;
  rightLabel?: string;
  durationInFrames: number;
};

const easeInOut = Easing.inOut(Easing.cubic);
const cover: React.CSSProperties = {width: '100%', height: '100%', objectFit: 'cover', display: 'block'};

const Half: React.FC<{src: string; p: number; dir: number; label?: string; side: 'left' | 'right'}> = ({src, p, dir, label, side}) => {
  const scale = interpolate(p, [0, 1], [1.06, 1.16]);
  const tx = interpolate(p, [0, 1], [2 * dir, -2 * dir]);
  return (
    <div style={{position: 'absolute', top: 0, [side]: 0, width: '50%', height: '100%', overflow: 'hidden'}}>
      <AbsoluteFill style={{transform: `translateX(${tx}%) scale(${scale})`}}>
        <Img src={staticFile(src)} style={cover} />
      </AbsoluteFill>
      {label ? (
        <div style={{position: 'absolute', left: 0, right: 0, bottom: 28, textAlign: 'center'}}>
          <span style={{
            fontFamily: 'system-ui, sans-serif', fontWeight: 700, fontSize: 26, color: '#fff',
            letterSpacing: '0.04em', textTransform: 'uppercase',
            background: 'rgba(0,0,0,0.45)', padding: '6px 14px', borderRadius: 4,
          }}>{label}</span>
        </div>
      ) : null}
    </div>
  );
};

export const SplitScreen: React.FC<SplitScreenProps> = ({background, foreground, leftLabel, rightLabel, durationInFrames}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: cfgDur} = useVideoConfig();
  const total = Math.max(2, durationInFrames || cfgDur || 120);
  const p = interpolate(frame, [0, total - 1], [0, 1], {extrapolateRight: 'clamp', easing: easeInOut});
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      <Half src={background} p={p} dir={1} label={leftLabel} side="left" />
      <Half src={foreground} p={p} dir={-1} label={rightLabel} side="right" />
      <div style={{position: 'absolute', top: 0, bottom: 0, left: '50%', width: 3, marginLeft: -1.5, background: 'rgba(255,255,255,0.85)'}} />
    </AbsoluteFill>
  );
};
