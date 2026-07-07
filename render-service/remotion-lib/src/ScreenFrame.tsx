import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig, spring, interpolate} from 'remotion';
import {Theme, resolveTheme} from './theme';

// ScreenFrame — wrap a screenshot / screen-recording in a device mockup (browser
// window, laptop, or phone). The essential "here's the product / the tweet / the
// article" device for explainers. Content = a staged image (background) or video
// (videoSrc); chrome is theme-styled and scales in gently.
export type ScreenFrameProps = {
  background?: string;   // screenshot image basename (staged into public/)
  videoSrc?: string;     // screen-recording video basename (staged)
  device?: 'browser' | 'laptop' | 'phone';
  url?: string;          // browser address-bar text
  label?: string;        // caption under the frame
  accent?: string;
  theme?: string | Partial<Theme>;
  durationInFrames: number;
};

export const ScreenFrame: React.FC<ScreenFrameProps> = ({
  background, videoSrc, device = 'browser', url = '', label = '', accent, theme, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const th = resolveTheme(theme);
  const hi = accent || th.accent;

  const enter = spring({frame, fps, config: {damping: 200, mass: 0.7}});
  const scale = interpolate(enter, [0, 1], [0.92, 1]);
  const opacity = interpolate(frame, [0, 12], [0, 1], {extrapolateRight: 'clamp'});

  const content = videoSrc
    ? <OffthreadVideo src={staticFile(videoSrc)} style={{width: '100%', height: '100%', objectFit: 'cover'}} muted />
    : background
      ? <Img src={staticFile(background)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      : <div style={{width: '100%', height: '100%', background: th.neutral}} />;

  // device geometry (centred in a 1920×1080 frame)
  const chrome = th.bg === '#ffffff' ? '#e9e9ee' : '#2a2a30';
  const bezel = th.bg === '#ffffff' ? '#d0d0d6' : '#111114';

  let win: React.ReactNode;
  if (device === 'phone') {
    const w = 500, h = 1000;
    win = (
      <div style={{width: w, height: h, borderRadius: 56, background: bezel, padding: 12,
        boxShadow: `0 40px 120px ${th.bg}dd, 0 0 0 2px ${hi}22`}}>
        <div style={{position: 'relative', width: '100%', height: '100%', borderRadius: 44, overflow: 'hidden', background: th.neutral}}>
          {content}
          <div style={{position: 'absolute', top: 14, left: '50%', transform: 'translateX(-50%)', width: 150, height: 30, borderRadius: 20, background: '#000'}} />
          <div style={{position: 'absolute', bottom: 12, left: '50%', transform: 'translateX(-50%)', width: 140, height: 6, borderRadius: 4, background: '#ffffffaa'}} />
        </div>
      </div>
    );
  } else if (device === 'laptop') {
    const w = 1380, h = 862;
    win = (
      <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
        <div style={{width: w, height: h, borderRadius: 20, background: bezel, padding: 16,
          boxShadow: `0 40px 120px ${th.bg}dd`}}>
          <div style={{position: 'relative', width: '100%', height: '100%', borderRadius: 8, overflow: 'hidden', background: th.neutral}}>{content}</div>
        </div>
        <div style={{width: w * 1.06, height: 26, borderRadius: '0 0 16px 16px', background: bezel,
          boxShadow: `0 16px 40px ${th.bg}aa`}}>
          <div style={{width: 160, height: 10, borderRadius: '0 0 10px 10px', background: '#00000055', margin: '0 auto'}} />
        </div>
      </div>
    );
  } else {
    const w = 1440, h = 862;
    win = (
      <div style={{width: w, height: h, borderRadius: 16, overflow: 'hidden', background: bezel,
        boxShadow: `0 40px 120px ${th.bg}dd, 0 0 0 1px ${th.muted}22`}}>
        <div style={{height: 60, background: chrome, display: 'flex', alignItems: 'center', padding: '0 20px', gap: 16}}>
          <div style={{display: 'flex', gap: 9}}>
            {[th.down, hi, th.up].map((c, i) => <div key={i} style={{width: 15, height: 15, borderRadius: '50%', background: c}} />)}
          </div>
          <div style={{flex: 1, height: 34, borderRadius: 8, background: th.bg, display: 'flex', alignItems: 'center',
            padding: '0 16px', color: th.muted, fontSize: 20, fontFamily: th.fontFamily, maxWidth: 720, margin: '0 auto'}}>
            {url || 'example.com'}
          </div>
          <div style={{width: 60}} />
        </div>
        <div style={{width: '100%', height: h - 60, background: th.neutral}}>{content}</div>
      </div>
    );
  }

  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily, alignItems: 'center', justifyContent: 'center'}}>
      <AbsoluteFill style={{background: `radial-gradient(ellipse 70% 60% at 50% 42%, ${hi}12 0%, transparent 70%)`}} />
      <div style={{transform: `scale(${scale})`, opacity, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 34}}>
        {win}
        {label ? <div style={{fontSize: 40, fontWeight: 600, color: th.fg, letterSpacing: '0.01em'}}>{label}</div> : null}
      </div>
    </AbsoluteFill>
  );
};
