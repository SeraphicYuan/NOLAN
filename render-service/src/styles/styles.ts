/**
 * Essay Style Library
 *
 * Pre-defined styles for different video essay tones.
 * Each style is a complete visual language.
 */

import type { EssayStyle } from './types.js';

/**
 * Noir Essay
 * Tags: cinematic, analysis, default
 * Use: Philosophy, history, long-form essays
 */
export const noirEssay: EssayStyle = {
  id: 'noir-essay',
  name: 'Noir Essay',
  description: 'Cinematic dark style for serious analysis. Philosophy, history, long-form essays.',
  tags: ['cinematic', 'analysis', 'default', 'dark'],

  colors: {
    background: '#0E0E10',
    primaryText: '#F5F5F5',
    secondaryText: '#A1A1AA',
    accent: '#C9A227',      // gold
    muted: '#52525B',
  },

  typography: {
    titleFont: 'Inter',
    bodyFont: 'Inter',
    quoteFont: 'Georgia',
    titleWeight: 600,
    bodyWeight: 400,
    titleLetterSpacingEm: 0.02,
    case: 'title',
  },

  layout: {
    marginX: 0.1,
    marginY: 0.15,
    maxTextWidth: 0.65,
    align: 'center',
  },

  textScale1080p: {
    h1: 80,
    h2: 56,
    body: 40,
    caption: 28,
  },

  motion: {
    enterFrames: 20,
    exitFrames: 15,
    holdFrames: 60,
    easing: 'easeOut',
    textDriftPx: 2,
  },

  texture: {
    grainOpacity: 0.03,
    vignette: true,
    gradient: null,
  },

  accentUsage: {
    maxWordsPerTitle: 1,
    maxWordsPerBody: 2,
    allowedTargets: ['numbers', 'dates', 'percentages', 'money', 'explicit_only'],
    forbiddenPatterns: ['full sentence', 'more than 3 words'],
  },
};

/**
 * Cold Data
 * Tags: tech, finance, data
 * Use: Markets, AI, geopolitics
 */
export const coldData: EssayStyle = {
  id: 'cold-data',
  name: 'Cold Data',
  description: 'Clean, technical style for data-driven content. Tech, finance, geopolitics.',
  tags: ['tech', 'finance', 'data', 'clean'],

  colors: {
    background: '#0B132B',
    primaryText: '#EAEAEA',
    secondaryText: '#94A3B8',
    accent: '#4EA8DE',      // blue
    muted: '#475569',
  },

  typography: {
    titleFont: 'Inter',
    bodyFont: 'Inter',
    quoteFont: null,
    titleWeight: 700,
    bodyWeight: 400,
    titleLetterSpacingEm: 0,
    case: 'sentence',
  },

  layout: {
    marginX: 0.1,
    marginY: 0.12,
    maxTextWidth: 0.7,
    align: 'left',
  },

  textScale1080p: {
    h1: 72,
    h2: 48,
    body: 36,
    caption: 24,
  },

  motion: {
    enterFrames: 15,
    exitFrames: 10,
    holdFrames: 45,
    easing: 'easeInOut',
    textDriftPx: 0,       // no drift - precise
  },

  texture: {
    grainOpacity: 0,      // no texture - clean
    vignette: false,
    gradient: null,
  },

  accentUsage: {
    maxWordsPerTitle: 2,
    maxWordsPerBody: 3,
    allowedTargets: ['numbers', 'percentages', 'money', 'explicit_only'],
    forbiddenPatterns: ['emotional words', 'adjectives'],
  },
};

/**
 * Modern Creator
 * Tags: youtube, general
 * Use: Mixed-topic essays, general content
 */
export const modernCreator: EssayStyle = {
  id: 'modern-creator',
  name: 'Modern Creator',
  description: 'Contemporary YouTube style. Versatile for mixed-topic essays.',
  tags: ['youtube', 'general', 'modern', 'versatile'],

  colors: {
    background: '#0F172A',
    primaryText: '#E5E7EB',
    secondaryText: '#9CA3AF',
    accent: '#22D3EE',      // cyan
    muted: '#4B5563',
  },

  typography: {
    titleFont: 'Inter',
    bodyFont: 'Inter',
    quoteFont: null,
    titleWeight: 700,
    bodyWeight: 400,
    titleLetterSpacingEm: -0.01,
    case: 'title',
  },

  layout: {
    marginX: 0.08,
    marginY: 0.1,
    maxTextWidth: 0.75,
    align: 'center',
  },

  textScale1080p: {
    h1: 88,
    h2: 56,
    body: 42,
    caption: 28,
  },

  motion: {
    enterFrames: 12,
    exitFrames: 8,
    holdFrames: 50,
    easing: 'easeOut',
    textDriftPx: 1,
  },

  texture: {
    grainOpacity: 0.015,
    vignette: false,
    gradient: {
      from: '#0F172A',
      to: '#1E293B',
      angle: 180,
    },
  },

  accentUsage: {
    maxWordsPerTitle: 2,
    maxWordsPerBody: 2,
    allowedTargets: ['numbers', 'percentages', 'caps', 'explicit_only'],
    forbiddenPatterns: [],
  },
};

/**
 * Academic Paper
 * Tags: scholarly, formal, educational
 * Use: Research explainers, academic content, lectures
 */
export const academicPaper: EssayStyle = {
  id: 'academic-paper',
  name: 'Academic Paper',
  description: 'Scholarly style with serif fonts. Research explainers, educational content.',
  tags: ['scholarly', 'formal', 'educational', 'serif'],

  colors: {
    background: '#FDFCF9',
    primaryText: '#1A1A1A',
    secondaryText: '#4A4A4A',
    accent: '#8B0000',      // dark red
    muted: '#7A7A7A',
  },

  typography: {
    titleFont: 'Georgia',
    bodyFont: 'Georgia',
    quoteFont: 'Georgia',
    titleWeight: 700,
    bodyWeight: 400,
    titleLetterSpacingEm: 0,
    case: 'sentence',
  },

  layout: {
    marginX: 0.15,
    marginY: 0.12,
    maxTextWidth: 0.6,
    align: 'center',
  },

  textScale1080p: {
    h1: 64,
    h2: 44,
    body: 36,
    caption: 24,
  },

  motion: {
    enterFrames: 25,
    exitFrames: 20,
    holdFrames: 70,
    easing: 'easeOut',
    textDriftPx: 0,
  },

  texture: {
    grainOpacity: 0.02,
    vignette: false,
    gradient: null,
  },

  accentUsage: {
    maxWordsPerTitle: 1,
    maxWordsPerBody: 1,
    allowedTargets: ['dates', 'numbers', 'explicit_only'],
    forbiddenPatterns: ['emotional words', 'slang'],
  },
};

/**
 * Documentary
 * Tags: investigative, neutral, serious
 * Use: Investigative journalism, documentaries
 */
export const documentary: EssayStyle = {
  id: 'documentary',
  name: 'Documentary',
  description: 'Neutral investigative style. Journalism, documentaries, explainers.',
  tags: ['investigative', 'neutral', 'serious', 'journalism'],

  colors: {
    background: '#1A1A1A',
    primaryText: '#FFFFFF',
    secondaryText: '#B0B0B0',
    accent: '#FF4444',      // red for emphasis
    muted: '#666666',
  },

  typography: {
    titleFont: 'Inter',
    bodyFont: 'Inter',
    quoteFont: 'Georgia',
    titleWeight: 600,
    bodyWeight: 400,
    titleLetterSpacingEm: 0.01,
    case: 'uppercase',
  },

  layout: {
    marginX: 0.08,
    marginY: 0.1,
    maxTextWidth: 0.8,
    align: 'left',
  },

  textScale1080p: {
    h1: 72,
    h2: 48,
    body: 38,
    caption: 26,
  },

  motion: {
    enterFrames: 18,
    exitFrames: 12,
    holdFrames: 55,
    easing: 'easeInOut',
    textDriftPx: 1,
  },

  texture: {
    grainOpacity: 0.04,
    vignette: true,
    gradient: null,
  },

  accentUsage: {
    maxWordsPerTitle: 2,
    maxWordsPerBody: 2,
    allowedTargets: ['numbers', 'dates', 'caps', 'explicit_only'],
    forbiddenPatterns: ['opinion words', 'adjectives'],
  },
};

/**
 * Podcast Visual
 * Tags: warm, conversational, friendly
 * Use: Podcast clips, interviews, discussions
 */
export const podcastVisual: EssayStyle = {
  id: 'podcast-visual',
  name: 'Podcast Visual',
  description: 'Warm conversational style. Podcast clips, interviews, discussions.',
  tags: ['warm', 'conversational', 'friendly', 'podcast'],

  colors: {
    background: '#1C1917',
    primaryText: '#FAFAF9',
    secondaryText: '#A8A29E',
    accent: '#FB923C',      // orange
    muted: '#78716C',
  },

  typography: {
    titleFont: 'Inter',
    bodyFont: 'Inter',
    quoteFont: 'Inter',
    titleWeight: 600,
    bodyWeight: 400,
    titleLetterSpacingEm: 0,
    case: 'sentence',
  },

  layout: {
    marginX: 0.1,
    marginY: 0.12,
    maxTextWidth: 0.7,
    align: 'center',
  },

  textScale1080p: {
    h1: 76,
    h2: 52,
    body: 40,
    caption: 28,
  },

  motion: {
    enterFrames: 14,
    exitFrames: 10,
    holdFrames: 50,
    easing: 'easeOut',
    textDriftPx: 1,
  },

  texture: {
    grainOpacity: 0.02,
    vignette: false,
    gradient: {
      from: '#1C1917',
      to: '#292524',
      angle: 180,
    },
  },

  accentUsage: {
    maxWordsPerTitle: 2,
    maxWordsPerBody: 3,
    allowedTargets: ['numbers', 'caps', 'explicit_only'],
    forbiddenPatterns: [],
  },
};

/**
 * Retro Synthwave
 * Tags: 80s, neon, synthwave
 * Use: Retro content, music, nostalgia
 */
export const retroSynthwave: EssayStyle = {
  id: 'retro-synthwave',
  name: 'Retro Synthwave',
  description: '80s neon aesthetic. Retro content, music videos, nostalgia pieces.',
  tags: ['80s', 'neon', 'synthwave', 'retro'],

  colors: {
    background: '#0D0221',
    primaryText: '#FF00FF',
    secondaryText: '#00FFFF',
    accent: '#FF6B35',      // neon orange
    muted: '#541388',
  },

  typography: {
    titleFont: 'Inter',
    bodyFont: 'Inter',
    quoteFont: null,
    titleWeight: 800,
    bodyWeight: 500,
    titleLetterSpacingEm: 0.05,
    case: 'uppercase',
  },

  layout: {
    marginX: 0.1,
    marginY: 0.15,
    maxTextWidth: 0.7,
    align: 'center',
  },

  textScale1080p: {
    h1: 96,
    h2: 64,
    body: 44,
    caption: 30,
  },

  motion: {
    enterFrames: 10,
    exitFrames: 8,
    holdFrames: 40,
    easing: 'easeOut',
    textDriftPx: 3,
  },

  texture: {
    grainOpacity: 0.05,
    vignette: true,
    gradient: {
      from: '#0D0221',
      to: '#1A0533',
      angle: 0,
    },
  },

  accentUsage: {
    maxWordsPerTitle: 3,
    maxWordsPerBody: 3,
    allowedTargets: ['numbers', 'dates', 'explicit_only'],
    forbiddenPatterns: [],
  },
};

/**
 * Breaking News
 * Tags: urgent, news, broadcast
 * Use: News coverage, current events, breaking stories
 */
export const breakingNews: EssayStyle = {
  id: 'breaking-news',
  name: 'Breaking News',
  description: 'Urgent news broadcast style. Current events, breaking stories.',
  tags: ['urgent', 'news', 'broadcast', 'CNN'],

  colors: {
    background: '#1E3A5F',
    primaryText: '#FFFFFF',
    secondaryText: '#B8D4E8',
    accent: '#DC2626',      // urgent red
    muted: '#4B6584',
  },

  typography: {
    titleFont: 'Inter',
    bodyFont: 'Inter',
    quoteFont: null,
    titleWeight: 700,
    bodyWeight: 500,
    titleLetterSpacingEm: 0.02,
    case: 'uppercase',
  },

  layout: {
    marginX: 0.05,
    marginY: 0.08,
    maxTextWidth: 0.9,
    align: 'left',
  },

  textScale1080p: {
    h1: 84,
    h2: 56,
    body: 42,
    caption: 28,
  },

  motion: {
    enterFrames: 8,
    exitFrames: 6,
    holdFrames: 35,
    easing: 'easeInOut',
    textDriftPx: 0,
  },

  texture: {
    grainOpacity: 0,
    vignette: false,
    gradient: {
      from: '#1E3A5F',
      to: '#0F2744',
      angle: 90,
    },
  },

  accentUsage: {
    maxWordsPerTitle: 2,
    maxWordsPerBody: 2,
    allowedTargets: ['numbers', 'dates', 'caps', 'explicit_only'],
    forbiddenPatterns: ['opinion words'],
  },
};

/**
 * Minimalist White
 * Tags: clean, light, minimal, Apple
 * Use: Product content, explainers, tutorials
 */
export const minimalistWhite: EssayStyle = {
  id: 'minimalist-white',
  name: 'Minimalist White',
  description: 'Clean light mode style. Product explainers, tutorials, presentations.',
  tags: ['clean', 'light', 'minimal', 'Apple'],

  colors: {
    background: '#FFFFFF',
    primaryText: '#1D1D1F',
    secondaryText: '#6E6E73',
    accent: '#0071E3',      // Apple blue
    muted: '#A1A1A6',
  },

  typography: {
    titleFont: 'Inter',
    bodyFont: 'Inter',
    quoteFont: null,
    titleWeight: 600,
    bodyWeight: 400,
    titleLetterSpacingEm: -0.02,
    case: 'sentence',
  },

  layout: {
    marginX: 0.15,
    marginY: 0.15,
    maxTextWidth: 0.6,
    align: 'center',
  },

  textScale1080p: {
    h1: 72,
    h2: 48,
    body: 36,
    caption: 24,
  },

  motion: {
    enterFrames: 20,
    exitFrames: 15,
    holdFrames: 60,
    easing: 'easeOut',
    textDriftPx: 0,
  },

  texture: {
    grainOpacity: 0,
    vignette: false,
    gradient: null,
  },

  accentUsage: {
    maxWordsPerTitle: 1,
    maxWordsPerBody: 1,
    allowedTargets: ['numbers', 'explicit_only'],
    forbiddenPatterns: ['emotional words', 'caps'],
  },
};

/**
 * True Crime
 * Tags: dark, dramatic, suspense
 * Use: True crime, mystery, thriller content
 */
export const trueCrime: EssayStyle = {
  id: 'true-crime',
  name: 'True Crime',
  description: 'Dark dramatic style for suspenseful content. True crime, mysteries.',
  tags: ['dark', 'dramatic', 'suspense', 'mystery'],

  colors: {
    background: '#0A0A0A',
    primaryText: '#E5E5E5',
    secondaryText: '#737373',
    accent: '#B91C1C',      // blood red
    muted: '#404040',
  },

  typography: {
    titleFont: 'Georgia',
    bodyFont: 'Inter',
    quoteFont: 'Georgia',
    titleWeight: 400,
    bodyWeight: 400,
    titleLetterSpacingEm: 0.05,
    case: 'uppercase',
  },

  layout: {
    marginX: 0.12,
    marginY: 0.15,
    maxTextWidth: 0.65,
    align: 'center',
  },

  textScale1080p: {
    h1: 68,
    h2: 48,
    body: 38,
    caption: 26,
  },

  motion: {
    enterFrames: 30,
    exitFrames: 20,
    holdFrames: 70,
    easing: 'easeOut',
    textDriftPx: 2,
  },

  texture: {
    grainOpacity: 0.06,
    vignette: true,
    gradient: null,
  },

  accentUsage: {
    maxWordsPerTitle: 1,
    maxWordsPerBody: 2,
    allowedTargets: ['dates', 'caps', 'explicit_only'],
    forbiddenPatterns: ['casual words', 'slang'],
  },
};

/**
 * Nature Documentary
 * Tags: nature, earthy, organic
 * Use: Nature content, environmental topics
 */
export const natureDocumentary: EssayStyle = {
  id: 'nature-documentary',
  name: 'Nature Documentary',
  description: 'Organic earthy style. Nature content, environmental topics, wildlife.',
  tags: ['nature', 'earthy', 'organic', 'Attenborough'],

  colors: {
    background: '#1A2E1A',
    primaryText: '#E8F0E8',
    secondaryText: '#A3B8A3',
    accent: '#4ADE80',      // nature green
    muted: '#5C7A5C',
  },

  typography: {
    titleFont: 'Georgia',
    bodyFont: 'Inter',
    quoteFont: 'Georgia',
    titleWeight: 400,
    bodyWeight: 400,
    titleLetterSpacingEm: 0.01,
    case: 'sentence',
  },

  layout: {
    marginX: 0.1,
    marginY: 0.12,
    maxTextWidth: 0.7,
    align: 'center',
  },

  textScale1080p: {
    h1: 70,
    h2: 48,
    body: 38,
    caption: 26,
  },

  motion: {
    enterFrames: 25,
    exitFrames: 20,
    holdFrames: 65,
    easing: 'easeOut',
    textDriftPx: 1,
  },

  texture: {
    grainOpacity: 0.03,
    vignette: true,
    gradient: {
      from: '#1A2E1A',
      to: '#0D1A0D',
      angle: 180,
    },
  },

  accentUsage: {
    maxWordsPerTitle: 1,
    maxWordsPerBody: 2,
    allowedTargets: ['numbers', 'caps', 'explicit_only'],
    forbiddenPatterns: ['technical jargon'],
  },
};

/**
 * All available styles indexed by ID
 */
export const STYLES: Record<string, EssayStyle> = {
  'noir-essay': noirEssay,
  'cold-data': coldData,
  'modern-creator': modernCreator,
  'academic-paper': academicPaper,
  'documentary': documentary,
  'podcast-visual': podcastVisual,
  'retro-synthwave': retroSynthwave,
  'breaking-news': breakingNews,
  'minimalist-white': minimalistWhite,
  'true-crime': trueCrime,
  'nature-documentary': natureDocumentary,
};

/**
 * Default style when none specified
 */
export const DEFAULT_STYLE_ID = 'noir-essay';

/**
 * Get a style by ID, returns default if not found
 */
export function getStyle(id: string): EssayStyle {
  return STYLES[id] ?? STYLES[DEFAULT_STYLE_ID];
}

/**
 * Get all available style IDs
 */
export function getStyleIds(): string[] {
  return Object.keys(STYLES);
}

/**
 * Get style metadata for API responses (without full config)
 */
export function getStyleSummaries(): Array<{
  id: string;
  name: string;
  description: string;
  tags: string[];
}> {
  return Object.values(STYLES).map((style) => ({
    id: style.id,
    name: style.name,
    description: style.description,
    tags: style.tags,
  }));
}
