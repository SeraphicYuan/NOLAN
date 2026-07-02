import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';

// StillMotion — turn ONE still into a moving shot for a video essay.
//   ken-burns-in / -out / -pan : motivated camera on a single image, zoom-origin at `target`
//                                (the salient point), eased for a premium feel.
//   parallax                   : sharp subject cutout (foreground, RGBA) over a blurred,
//                                more-slowly-moving copy of the image → fake 2.5D depth.
// Everything is a pure function of the frame. Images are staged into public/ (background =
// the base image, foreground = the rembg cutout) by render.mjs.

type Treatment = 'ken-burns-in' | 'ken-burns-out' | 'ken-burns-pan' | 'parallax' | 'hold';
export type StillMotionProps = {
  background: string;              // staged basename of the base image
  foreground?: string;            // staged basename of the subject cutout (parallax)
  treatment?: Treatment;
  target?: {x: number; y: number}; // salient point 0..1 (zoom origin / focal point)
  direction?: 'left' | 'right';   // pan direction
  durationInFrames: number;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const easeInOut = Easing.inOut(Easing.cubic);

export const StillMotion: React.FC<StillMotionProps> = ({
  background, foreground, treatment = 'ken-burns-in',
  target = {x: 0.5, y: 0.5}, direction = 'right', durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: cfgDur} = useVideoConfig();
  const total = Math.max(2, durationInFrames || cfgDur || 120);
  const p = interpolate(frame, [0, total - 1], [0, 1], {...clamp, easing: easeInOut}); // 0..1 eased
  const ox = `${Math.round(target.x * 100)}%`;
  const oy = `${Math.round(target.y * 100)}%`;
  const dir = direction === 'left' ? -1 : 1;
  const cover: React.CSSProperties = {width: '100%', height: '100%', objectFit: 'cover', display: 'block'};

  if (treatment === 'parallax' && foreground) {
    // background: blurred, larger, drifts a little; foreground: sharp, drifts more → depth.
    const bgShift = interpolate(p, [0, 1], [0, -1.8 * dir]);   // % of width
    const fgShift = interpolate(p, [0, 1], [0, -5.0 * dir]);
    const bgScale = interpolate(p, [0, 1], [1.18, 1.22]);
    const fgScale = interpolate(p, [0, 1], [1.04, 1.10]);
    return (
      <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
        {/* heavy blur + darken so the residual subject in the base image reads as soft depth, not a ghost */}
        <AbsoluteFill style={{transform: `translateX(${bgShift}%) scale(${bgScale})`, filter: 'blur(20px) brightness(0.7)'}}>
          <Img src={staticFile(background)} style={cover} />
        </AbsoluteFill>
        <AbsoluteFill style={{transform: `translateX(${fgShift}%) scale(${fgScale})`}}>
          <Img src={staticFile(foreground)} style={cover} />
        </AbsoluteFill>
      </AbsoluteFill>
    );
  }

  // Ken Burns family (also the parallax fallback when there's no cutout)
  let scale = 1.08, tx = 0;
  if (treatment === 'ken-burns-in') {
    scale = interpolate(p, [0, 1], [1.04, 1.20]);
  } else if (treatment === 'ken-burns-out') {
    scale = interpolate(p, [0, 1], [1.20, 1.04]);
  } else if (treatment === 'ken-burns-pan') {
    scale = 1.16;
    tx = interpolate(p, [0, 1], [4 * dir, -4 * dir]);        // drift across
  } else if (treatment === 'hold') {
    scale = 1.0;
  }
  return (
    <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
      <AbsoluteFill style={{transform: `translateX(${tx}%) scale(${scale})`, transformOrigin: `${ox} ${oy}`}}>
        <Img src={staticFile(background)} style={cover} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
