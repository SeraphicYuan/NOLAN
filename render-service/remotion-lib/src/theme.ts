// SHARED style tokens — common to every curated Remotion effect.
// A scene passes `theme` as a preset name ("dark-editorial") or a partial override
// object ({accent:"#0af"}). Effect-specific style vars (lineStyle, barStyle,
// shapeStyle, …) live on each composition's own props.
import {FONT} from './fonts';

export type Theme = {
  bg: string;        // background
  fg: string;        // primary text
  muted: string;     // secondary text
  accent: string;    // highlight / annotation
  up: string;        // positive / rising (green)
  down: string;      // negative / falling (red)
  neutral: string;   // baseline / inactive (gray)
  fontFamily: string;
  speed: number;     // animation speed multiplier (1 = normal, <1 slower)
};

export const THEMES: Record<string, Theme> = {
  'dark-editorial': {
    bg: '#0c0c10', fg: '#f5f5f7', muted: '#c9c9d2', accent: '#ffd23b',
    up: '#46e08a', down: '#ff4d4d', neutral: '#6b7280',
    fontFamily: `${FONT}, "Segoe UI", Arial, sans-serif`, speed: 1,
  },
  light: {
    bg: '#f5f5f8', fg: '#12121a', muted: '#5a5a66', accent: '#e0461f',
    up: '#13a05f', down: '#d8392f', neutral: '#9aa0a8',
    fontFamily: `${FONT}, "Segoe UI", Arial, sans-serif`, speed: 1,
  },
  'high-contrast': {
    bg: '#000000', fg: '#ffffff', muted: '#bdbdbd', accent: '#ffe000',
    up: '#00e676', down: '#ff1744', neutral: '#7a7a7a',
    fontFamily: `${FONT}, "Segoe UI", Arial, sans-serif`, speed: 1,
  },
};

export const resolveTheme = (t?: string | Partial<Theme>): Theme => {
  const base = THEMES['dark-editorial'];
  if (!t) return base;
  if (typeof t === 'string') return THEMES[t] ?? base;
  return {...base, ...t};
};
