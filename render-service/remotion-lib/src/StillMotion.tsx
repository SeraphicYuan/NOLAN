import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';

// StillMotion — turn ONE still into a moving shot for a video essay.
//   ken-burns-in / -out / -pan : motivated camera on one image, zoom-origin at `target`.
//   parallax                   : sharp subject cutout (fg, RGBA) over a blurred, slower bg → 2.5D depth.
//   rack-focus                 : whole frame sharp → background pulls out of focus onto the subject (fg sharp).
//   blur-in                    : blurred → sharp "coming into focus" reveal, over a gentle push.
//   atmospheric                : gentle push + drifting motes + vignette + grade drift ("living" still).
// Pure function of the frame. Images staged into public/ (background = base, foreground = rembg cutout).

type Treatment =
  | 'ken-burns-in' | 'ken-burns-out' | 'ken-burns-pan'
  | 'parallax' | 'rack-focus' | 'blur-in' | 'atmospheric' | 'hold';
export type StillMotionProps = {
  background: string;
  foreground?: string;                 // rembg cutout (parallax, rack-focus)
  treatment?: Treatment;
  target?: {x: number; y: number};
  direction?: 'left' | 'right';
  durationInFrames: number;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const easeInOut = Easing.inOut(Easing.cubic);
const cover: React.CSSProperties = {width: '100%', height: '100%', objectFit: 'cover', display: 'block'};

// deterministic pseudo-random in [0,1) from an integer seed
const rnd = (n: number) => {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return s - Math.floor(s);
};

const Vignette: React.FC<{strength?: number}> = ({strength = 0.55}) => (
  <AbsoluteFill style={{background: `radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,${strength}) 100%)`, pointerEvents: 'none'}} />
);

// drifting dust motes — warm, slow, deterministic
const Motes: React.FC<{frame: number; total: number; count?: number}> = ({frame, total, count = 46}) => {
  const t = frame / Math.max(1, total);
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {Array.from({length: count}).map((_, i) => {
        const x = rnd(i) * 100;
        const yBase = rnd(i + 99) * 120 - 10;
        const y = ((yBase - t * (12 + rnd(i + 7) * 24)) % 120 + 120) % 120 - 10; // drift up, wrap
        const drift = Math.sin((frame / 30) * (0.4 + rnd(i + 3)) + i) * 1.4;
        const size = 1.5 + rnd(i + 5) * 4;
        const op = 0.08 + rnd(i + 11) * 0.22;
        return (
          <div key={i} style={{
            position: 'absolute', left: `${x + drift}%`, top: `${y}%`, width: size, height: size,
            borderRadius: '50%', background: 'rgba(255,240,210,1)', opacity: op,
            filter: 'blur(0.6px)', boxShadow: '0 0 6px rgba(255,225,180,0.6)',
          }} />
        );
      })}
    </AbsoluteFill>
  );
};

export const StillMotion: React.FC<StillMotionProps> = ({
  background, foreground, treatment = 'ken-burns-in',
  target = {x: 0.5, y: 0.5}, direction = 'right', durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: cfgDur} = useVideoConfig();
  const total = Math.max(2, durationInFrames || cfgDur || 120);
  const p = interpolate(frame, [0, total - 1], [0, 1], {...clamp, easing: easeInOut});
  const ox = `${Math.round(target.x * 100)}%`;
  const oy = `${Math.round(target.y * 100)}%`;
  const dir = direction === 'left' ? -1 : 1;

  // --- two-layer treatments (need a cutout) ---
  if ((treatment === 'parallax' || treatment === 'rack-focus') && foreground) {
    if (treatment === 'parallax') {
      const bgShift = interpolate(p, [0, 1], [0, -1.8 * dir]);
      const fgShift = interpolate(p, [0, 1], [0, -5.0 * dir]);
      const bgScale = interpolate(p, [0, 1], [1.18, 1.22]);
      const fgScale = interpolate(p, [0, 1], [1.04, 1.10]);
      return (
        <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
          <AbsoluteFill style={{transform: `translateX(${bgShift}%) scale(${bgScale})`, filter: 'blur(20px) brightness(0.7)'}}>
            <Img src={staticFile(background)} style={cover} />
          </AbsoluteFill>
          <AbsoluteFill style={{transform: `translateX(${fgShift}%) scale(${fgScale})`}}>
            <Img src={staticFile(foreground)} style={cover} />
          </AbsoluteFill>
        </AbsoluteFill>
      );
    }
    // rack-focus: start all sharp, background pulls out of focus onto the (sharp) subject
    const bgBlur = interpolate(p, [0, 0.55, 1], [0, 0, 11], clamp);
    const bgDim = interpolate(p, [0, 0.55, 1], [1, 1, 0.82], clamp);
    const scale = interpolate(p, [0, 1], [1.05, 1.10]);
    return (
      <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
        <AbsoluteFill style={{transform: `scale(${scale})`, transformOrigin: `${ox} ${oy}`, filter: `blur(${bgBlur}px) brightness(${bgDim})`}}>
          <Img src={staticFile(background)} style={cover} />
        </AbsoluteFill>
        <AbsoluteFill style={{transform: `scale(${scale})`, transformOrigin: `${ox} ${oy}`}}>
          <Img src={staticFile(foreground)} style={cover} />
        </AbsoluteFill>
      </AbsoluteFill>
    );
  }

  // --- single-layer camera treatments (+ optional blur-in / atmospheric overlays) ---
  let scale = 1.08, tx = 0;
  if (treatment === 'ken-burns-out') scale = interpolate(p, [0, 1], [1.20, 1.04]);
  else if (treatment === 'ken-burns-pan') {scale = 1.16; tx = interpolate(p, [0, 1], [4 * dir, -4 * dir]);}
  else if (treatment === 'hold') scale = 1.0;
  else scale = interpolate(p, [0, 1], [1.04, 1.20]); // ken-burns-in, blur-in, atmospheric all push in gently

  const blur = treatment === 'blur-in' ? interpolate(p, [0, 0.28], [16, 0], clamp) : 0;

  return (
    <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
      <AbsoluteFill style={{transform: `translateX(${tx}%) scale(${scale})`, transformOrigin: `${ox} ${oy}`, filter: blur ? `blur(${blur}px)` : undefined}}>
        <Img src={staticFile(background)} style={cover} />
      </AbsoluteFill>
      {treatment === 'atmospheric' && (
        <>
          <AbsoluteFill style={{background: interpolate(p, [0, 1], [0, 1]) > 0.5
            ? 'linear-gradient(rgba(30,20,50,0.10), rgba(60,30,10,0.10))'
            : 'linear-gradient(rgba(60,30,10,0.10), rgba(30,20,50,0.10))', mixBlendMode: 'soft-light', pointerEvents: 'none'}} />
          <Motes frame={frame} total={total} />
          <Vignette strength={0.5} />
        </>
      )}
    </AbsoluteFill>
  );
};
