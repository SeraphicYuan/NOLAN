import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig, spring, interpolate} from 'remotion';
import {Theme, resolveTheme} from './theme';

// PictureInPicture — a floating inset window over a full-frame main shot. Reaction,
// "meanwhile", commentary, or a detail feed. The inset slides in from a corner
// with a shadow + accent ring. background/videoSrc = main; foreground = inset image.
export type PictureInPictureProps = {
  background?: string;   // main still
  videoSrc?: string;     // main clip
  foreground?: string;   // inset image
  corner?: 'br' | 'bl' | 'tr' | 'tl';
  inset_label?: string;
  accent?: string;
  theme?: string | Partial<Theme>;
  durationInFrames: number;
};

const cover: React.CSSProperties = {width: '100%', height: '100%', objectFit: 'cover'};

export const PictureInPicture: React.FC<PictureInPictureProps> = ({
  background, videoSrc, foreground, corner = 'br', inset_label = '', accent, theme, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const th = resolveTheme(theme);
  const hi = accent || th.accent;

  const iw = Math.round(width * 0.34), ih = Math.round(iw * 9 / 16);
  const margin = 72;
  const right = corner.endsWith('r');
  const bottom = corner.startsWith('b');
  const x = right ? width - iw - margin : margin;
  const y = bottom ? height - ih - margin : margin;

  const enter = spring({frame, fps, config: {damping: 200, mass: 0.8}});
  const offX = (right ? 1 : -1) * (1 - enter) * (iw + margin + 40);
  const opacity = interpolate(frame, [0, 10], [0, 1], {extrapolateRight: 'clamp'});

  const main = videoSrc
    ? <OffthreadVideo src={staticFile(videoSrc)} style={cover} muted />
    : background ? <Img src={staticFile(background)} style={cover} /> : <AbsoluteFill style={{background: th.neutral}} />;

  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily, overflow: 'hidden'}}>
      {main}
      <div style={{position: 'absolute', left: x, top: y, width: iw, height: ih, transform: `translateX(${offX}px)`, opacity,
        borderRadius: 16, overflow: 'hidden', border: `3px solid ${hi}`, boxShadow: `0 24px 60px ${th.bg}, 0 0 0 1px ${th.bg}88`}}>
        {foreground ? <Img src={staticFile(foreground)} style={cover} /> : <AbsoluteFill style={{background: th.accent}} />}
        {inset_label ? (
          <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, padding: '10px 16px', fontSize: 26, fontWeight: 700,
            color: '#fff', background: 'linear-gradient(transparent, #000c)'}}>{inset_label}</div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
