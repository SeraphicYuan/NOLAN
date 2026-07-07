import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {Theme, resolveTheme} from './theme';

// Typewriter — text that builds character-by-character. mode 'type' reveals
// left-to-right with a blinking cursor (letters, code, a terminal, a telegram);
// mode 'decode' scrambles each glyph then locks it (Matrix / data-feed energy).
export type TypewriterProps = {
  text: string;
  mode?: 'type' | 'decode';
  cursor?: boolean;
  accent?: string;
  theme?: string | Partial<Theme>;
  durationInFrames: number;
};

const MONO = "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace";
const GLYPHS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&$@!?';

export const Typewriter: React.FC<TypewriterProps> = ({
  text, mode = 'type', cursor = true, accent, theme, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: cfgDur} = useVideoConfig();
  const th = resolveTheme(theme);
  const total = Math.max(2, durationInFrames || cfgDur || 120);
  const hi = accent || th.accent;

  const chars = Array.from(text || '');
  const revealEnd = Math.round(total * 0.72);
  const perChar = chars.length > 0 ? (revealEnd - 10) / chars.length : 0;
  const shown = interpolate(frame, [10, revealEnd], [0, chars.length], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const rendered = chars.map((ch, i) => {
    const revealAt = 10 + i * perChar;
    if (frame >= revealAt) return ch;
    if (mode === 'decode' && frame > revealAt - perChar * 6 && ch.trim() !== '') {
      // scrambling window before this char locks
      return GLYPHS[(Math.floor(frame * 1.7) + i * 13) % GLYPHS.length];
    }
    return mode === 'decode' ? '' : '';
  }).join('');

  const cursorOn = cursor && frame < revealEnd + 12 && Math.floor(frame / 15) % 2 === 0;

  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily, alignItems: 'center', justifyContent: 'center', padding: 160}}>
      <div style={{fontFamily: MONO, fontSize: 72, fontWeight: 600, color: th.fg, lineHeight: 1.35, letterSpacing: '0.01em',
        maxWidth: 1500, textAlign: 'center', whiteSpace: 'pre-wrap'}}>
        {mode === 'decode' ? <span style={{color: hi}}>{rendered}</span> : rendered}
        {cursorOn ? <span style={{color: hi}}>▋</span> : null}
      </div>
    </AbsoluteFill>
  );
};
