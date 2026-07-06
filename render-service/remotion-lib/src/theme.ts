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

// One theme system (SOTA #3): stage.mjs resolves the job's NOLAN theme tokens
// into this JSON before every render, so the hosted motion comps inherit the
// same look the blocks get from CSS vars. Comps concat alpha suffixes onto
// these values, so only clean #rrggbb hex is accepted; anything else falls
// back to dark-editorial per-slot.
import activeTokens from './styles/_active-theme.json';

const _hex = (v: unknown): string | undefined => {
  const s = typeof v === 'string' ? v.trim() : '';
  return /^#[0-9a-fA-F]{6}$/.test(s) ? s : undefined;
};

const _at = activeTokens as Record<string, unknown>;
const ACTIVE: Theme = {
  ...THEMES['dark-editorial'],
  bg: _hex(_at.bg) ?? THEMES['dark-editorial'].bg,
  fg: _hex(_at.fg) ?? THEMES['dark-editorial'].fg,
  muted: _hex(_at.muted) ?? THEMES['dark-editorial'].muted,
  accent: _hex(_at.accent) ?? THEMES['dark-editorial'].accent,
  fontFamily: _at.fontFamily
    ? `${_at.fontFamily}, ${FONT}, "Segoe UI", Arial, sans-serif`
    : THEMES['dark-editorial'].fontFamily,
};

export const resolveTheme = (t?: string | Partial<Theme>): Theme => {
  if (!t) return ACTIVE;                       // default = the ACTIVE NOLAN theme
  if (typeof t === 'string') return THEMES[t] ?? ACTIVE;
  return {...ACTIVE, ...t};
};
