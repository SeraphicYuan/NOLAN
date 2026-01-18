/**
 * Essay Style System - Type Definitions
 *
 * Decouples motion logic from visual design.
 * Motion presets handle timing/animation, styles handle colors/typography/texture.
 */

/**
 * Core style definition for video essays.
 * One style per video - no mixing.
 */
export interface EssayStyle {
  id: string;
  name: string;
  description: string;
  tags: string[];

  colors: {
    background: string;
    primaryText: string;
    secondaryText: string;
    accent: string;
    muted: string;
  };

  typography: {
    titleFont: string;
    bodyFont: string;
    quoteFont: string | null;
    titleWeight: number;
    bodyWeight: number;
    titleLetterSpacingEm: number;
    case: 'title' | 'sentence' | 'uppercase';
  };

  layout: {
    marginX: number;       // 0-1 (percentage of width)
    marginY: number;       // 0-1 (percentage of height)
    maxTextWidth: number;  // 0-1
    align: 'left' | 'center';
  };

  textScale1080p: {
    h1: number;
    h2: number;
    body: number;
    caption: number;
  };

  motion: {
    enterFrames: number;
    exitFrames: number;
    holdFrames: number;
    easing: 'linear' | 'easeInOut' | 'easeOut' | 'cubic';
    textDriftPx: number;  // subtle motion only (0-3)
  };

  texture: {
    grainOpacity: number;     // 0-0.05
    vignette: boolean;
    gradient: {
      from: string;
      to: string;
      angle: number;
    } | null;
  };

  accentUsage: {
    maxWordsPerTitle: number;
    maxWordsPerBody: number;
    allowedTargets: AccentTarget[];
    forbiddenPatterns: string[];
  };
}

/**
 * What can be auto-accented
 */
export type AccentTarget =
  | 'numbers'
  | 'dates'
  | 'percentages'
  | 'money'
  | 'quotes'
  | 'first_word'
  | 'last_word'
  | 'caps'
  | 'explicit_only';  // only **markup** works

/**
 * A segment of text with accent information
 */
export interface TextSegment {
  text: string;
  accent: boolean;
}

/**
 * Input for text that may contain accent markup
 */
export interface AccentedTextInput {
  text: string;
  accent?: 'auto' | 'none' | string[];  // string[] = specific words to accent
}

/**
 * Result of accent resolution
 */
export interface AccentedText {
  segments: TextSegment[];
  accentCount: number;
  raw: string;
}

/**
 * Safe area calculation result
 */
export interface SafeArea {
  x: number;
  y: number;
  width: number;
  height: number;
  maxTextWidth: number;
}

/**
 * Resolved text sizes for a specific video height
 */
export interface ResolvedTextSizes {
  h1: number;
  h2: number;
  body: number;
  caption: number;
}

/**
 * Global defaults and rules
 */
export const GLOBAL_DEFAULTS = {
  frameRate: 30,
  width: 1920,
  height: 1080,
  safeArea: {
    marginX: 0.1,
    marginY: 0.15,
    maxTextWidth: 0.65,
  },
  rules: {
    maxFontsPerVideo: 2,
    maxAccentWordsPerTitle: 1,
    maxAccentWordsPerBody: 2,
    maxBodyLines: 3,
    noDropShadows: true,
    noGlow: true,
  },
} as const;

/**
 * Style validation result
 */
export interface StyleValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
}
