import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {Theme, resolveTheme} from './theme';

// CameraShake — handheld shake over a still/clip for tension or an impact beat.
// The shake spikes at the start and decays; an optional white flash punctuates
// frame 0. intensity 0..1 scales the throw. background = still, videoSrc = clip.
export type CameraShakeProps = {
  background?: string;
  videoSrc?: string;
  intensity?: number;    // 0..1
  flash?: boolean;       // impact flash at the start
  label?: string;
  theme?: string | Partial<Theme>;
  durationInFrames: number;
};

// deterministic pseudo-noise in [-1,1] (sum of incommensurate sines)
const noise = (f: number, seed: number) =>
  Math.sin(f * 0.9 * seed) * 0.5 + Math.sin(f * 1.7 * seed + 1.3) * 0.3 + Math.sin(f * 2.9 * seed + 2.1) * 0.2;

export const CameraShake: React.FC<CameraShakeProps> = ({
  background, videoSrc, intensity = 0.6, flash = true, label = '', theme, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: cfgDur} = useVideoConfig();
  const th = resolveTheme(theme);
  const total = Math.max(2, durationInFrames || cfgDur || 120);

  // envelope: strong shake early, settles by ~60%
  const env = interpolate(frame, [0, total * 0.55], [1, 0.08], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const amp = 46 * Math.max(0, Math.min(1, intensity)) * env;
  const tx = noise(frame, 1.0) * amp;
  const ty = noise(frame, 1.31) * amp * 0.8;
  const rot = noise(frame, 0.7) * 1.4 * env * Math.max(0, Math.min(1, intensity));

  const flashOp = flash ? interpolate(frame, [0, 5], [0.85, 0], {extrapolateRight: 'clamp'}) : 0;

  const media = videoSrc
    ? <OffthreadVideo src={staticFile(videoSrc)} style={{width: '100%', height: '100%', objectFit: 'cover'}} muted />
    : background
      ? <Img src={staticFile(background)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      : <div style={{width: '100%', height: '100%', background: th.neutral}} />;

  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily, overflow: 'hidden'}}>
      {/* scale up so shake never exposes an edge */}
      <AbsoluteFill style={{transform: `translate(${tx}px, ${ty}px) rotate(${rot}deg) scale(1.14)`}}>
        {media}
      </AbsoluteFill>
      <AbsoluteFill style={{background: '#ffffff', opacity: flashOp}} />
      {label ? (
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'flex-end', padding: 80}}>
          <div style={{fontSize: 52, fontWeight: 800, color: th.fg, textShadow: `0 3px 20px ${th.bg}`}}>{label}</div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
