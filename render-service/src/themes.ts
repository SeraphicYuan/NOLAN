/**
 * Centralized theme definitions for all rendering engines.
 */

export type Theme = {
  background: string;
  primary: string;
  secondary: string;
  text: string;
  muted: string;
  accent?: string;
};

/**
 * Core theme palette used across engines.
 */
export const THEMES: Record<string, Theme> = {
  default: {
    background: '#ffffff',
    primary: '#1d4ed8',
    secondary: '#0f766e',
    text: '#0f172a',
    muted: '#475569',
    accent: '#f97316',
  },
  dark: {
    background: '#0b1120',
    primary: '#38bdf8',
    secondary: '#f472b6',
    text: '#e2e8f0',
    muted: '#94a3b8',
    accent: '#f59e0b',
  },
  warm: {
    background: '#fff7ed',
    primary: '#ea580c',
    secondary: '#d97706',
    text: '#431407',
    muted: '#78350f',
    accent: '#c2410c',
  },
  cool: {
    background: '#f0f9ff',
    primary: '#0284c7',
    secondary: '#0f766e',
    text: '#0f172a',
    muted: '#475569',
    accent: '#8b5cf6',
  },
};

/**
 * Extended themes for specific use cases (SVG infographics).
 */
export const EXTENDED_THEMES: Record<string, Theme> = {
  ...THEMES,
  'brand-ink': {
    background: '#f8fafc',
    primary: '#0f172a',
    secondary: '#1d4ed8',
    text: '#0f172a',
    muted: '#475569',
    accent: '#f97316',
  },
  'brand-slate': {
    background: '#f1f5f9',
    primary: '#1e293b',
    secondary: '#0ea5e9',
    text: '#0f172a',
    muted: '#475569',
    accent: '#14b8a6',
  },
  'docu-amber': {
    background: '#fff7ed',
    primary: '#b45309',
    secondary: '#f59e0b',
    text: '#3f2a06',
    muted: '#78350f',
    accent: '#c2410c',
  },
  'docu-forest': {
    background: '#f0fdf4',
    primary: '#14532d',
    secondary: '#22c55e',
    text: '#052e16',
    muted: '#166534',
    accent: '#0f766e',
  },
};

/**
 * AntV/Infographic specific theme presets.
 */
export const INFOGRAPHIC_THEME_PRESETS: Record<string, Record<string, unknown>> = {
  'docu-dark-minimal': {
    colorBg: '#111827',
    colorPrimary: '#38bdf8',
    palette: ['#38bdf8', '#a78bfa', '#f472b6'],
    base: {
      text: { fill: '#f8fafc' },
    },
    item: {
      label: { fill: '#f8fafc' },
      value: { fill: '#f8fafc' },
    },
  },
  'docu-warm-soft': {
    colorBg: '#fff7ed',
    colorPrimary: '#f59e0b',
    palette: ['#f59e0b', '#f97316', '#fb7185'],
    base: {
      text: { fill: '#3f2a06' },
    },
    item: {
      label: { fill: '#3f2a06' },
      value: { fill: '#3f2a06' },
    },
  },
};

/**
 * Get a theme by name, falling back to default if not found.
 */
export function getTheme(name: string): Theme {
  return EXTENDED_THEMES[name] ?? THEMES[name] ?? THEMES.default;
}

/**
 * Resolve background color from theme name.
 */
export function resolveBackgroundFromTheme(themeName: string, defaultBg = '#ffffff'): string {
  const theme = THEMES[themeName.toLowerCase()];
  return theme?.background ?? defaultBg;
}
