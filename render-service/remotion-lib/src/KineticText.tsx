import React from 'react';
import {
  AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring,
  OffthreadVideo, staticFile,
} from 'remotion';
import {Theme, resolveTheme} from './theme';
import {Position, resolveAnchor} from './layout';

export type KineticProps = {
  text: string;
  highlights: string[];              // lowercased, punctuation-stripped words to accent
  theme?: string | Partial<Theme>;   // SHARED
  accent?: string;                   // optional override of theme.accent
  position?: Position;               // SHARED layout: vertical placement of the block
  scrim: number;                     // 0..1 darkening when over video
  durationInFrames: number;
  videoSrc?: string;                 // basename in public/ -> OffthreadVideo background
};

const norm = (w: string) => w.toLowerCase().replace(/[^a-z0-9]/g, '');

export const KineticText: React.FC<KineticProps> = ({
  text, highlights, theme, accent, position = 'center', scrim, videoSrc,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height, durationInFrames} = useVideoConfig();
  const th = resolveTheme(theme);
  const hi = accent || th.accent;
  const {fy} = resolveAnchor(position, width, height);
  const offsetY = (fy - 0.5) * height; // vertical placement of the headline block
  const words = text.split(/\s+/).filter(Boolean);
  const stagger = 4;
  const outOpacity = interpolate(
    frame, [durationInFrames - 12, durationInFrames - 1], [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  return (
    <AbsoluteFill style={{backgroundColor: videoSrc ? 'transparent' : th.bg}}>
      {videoSrc && <OffthreadVideo src={staticFile(videoSrc)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />}
      {videoSrc && scrim > 0 && <AbsoluteFill style={{backgroundColor: `rgba(0,0,0,${scrim})`}} />}
      <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: '0 9%'}}>
        <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'baseline', fontSize: 96, gap: '0.18em 0.34em', maxWidth: width * 0.82, opacity: outOpacity, transform: `translateY(${offsetY}px)`}}>
          {words.map((w, i) => {
            const s = spring({frame: frame - i * stagger, fps, durationInFrames: 16, config: {damping: 200}});
            const opacity = interpolate(s, [0, 1], [0, 1]);
            const y = interpolate(s, [0, 1], [44, 0]);
            const isHi = highlights.includes(norm(w));
            return (
              <span key={i} style={{
                display: 'inline-block', opacity, transform: `translateY(${y}px)`,
                fontFamily: th.fontFamily, fontWeight: 800, fontSize: 96, lineHeight: 1.08,
                letterSpacing: '-0.02em', color: isHi ? hi : th.fg,
                textShadow: videoSrc ? '0 2px 18px rgba(0,0,0,0.55)' : 'none',
              }}>
                {w}
              </span>
            );
          })}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
