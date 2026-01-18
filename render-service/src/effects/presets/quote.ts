import type { EffectPreset } from '../types.js';
import { getStyle, resolveAccent, colorizeSegments, stripAccentMarkup } from '../../styles/index.js';
import type { EssayStyle } from '../../styles/types.js';

/**
 * Resolve style from params - returns style object or null for legacy mode
 */
function resolveStyleParam(params: Record<string, unknown>): EssayStyle | null {
  const styleId = params.style as string | undefined;
  if (!styleId || styleId === 'none' || styleId === 'custom') {
    return null;
  }
  return getStyle(styleId);
}

export const quoteFadeCenter: EffectPreset = {
  id: 'quote-fade-center',
  name: 'Fade Center',
  category: 'quote',
  description: 'Text fades in centered on screen. Simple, elegant presentation for quotes and key statements.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'text',
      label: 'Quote Text',
      description: 'The quote to display (use **word** for accent)',
      required: true,
    },
    {
      name: 'author',
      type: 'string',
      label: 'Author',
      description: 'Attribution (optional)',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration in seconds',
      required: false,
      default: 5,
      min: 2,
      max: 15,
    },
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Visual style preset',
      required: false,
      default: 'custom',
      options: ['custom', 'noir-essay', 'cold-data', 'modern-creator', 'academic-paper', 'documentary', 'podcast-visual', 'retro-synthwave', 'breaking-news', 'minimalist-white', 'true-crime', 'nature-documentary'],
    },
    {
      name: 'color',
      type: 'color',
      label: 'Text Color',
      description: 'Color of the quote text (ignored if style set)',
      required: false,
      default: '#ffffff',
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if style set)',
      required: false,
      default: '#0f172a',
    },
  ],
  defaults: {
    duration: 5,
    style: 'custom',
    color: '#ffffff',
    background: '#0f172a',
  },
  preview: '/previews/quote-fade-center.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const text = params.text as string || '';
    const author = params.author as string | undefined;

    if (style) {
      // Style-driven rendering with accent support
      const quoteAccent = resolveAccent({ text }, style, false);
      const quoteSegments = colorizeSegments(quoteAccent.segments, style);

      const phrases: Array<{
        text: string;
        segments?: Array<{ text: string; color: string }>;
        hold: number;
      }> = [
        {
          text: stripAccentMarkup(text),
          segments: quoteSegments,
          hold: 0.8,
        },
      ];

      if (author) {
        phrases.push({
          text: `— ${author}`,
          hold: 0.6,
        });
      }

      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        kinetic: {
          color: style.colors.primaryText,
          accentColor: style.colors.accent,
          size: style.textScale1080p.body,
          fontFamily: style.typography.bodyFont,
          quoteFont: style.typography.quoteFont,
          phrases,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    const phrases = [{ text, hold: 0.8 }];
    if (author) {
      phrases.push({ text: `— ${author}`, hold: 0.6 });
    }

    return {
      duration: params.duration ?? 5,
      background: params.background || '#0f172a',
      kinetic: {
        color: params.color || '#ffffff',
        size: 64,
        phrases,
      },
    };
  },
};

export const quoteKinetic: EffectPreset = {
  id: 'quote-kinetic',
  name: 'Kinetic Typography',
  category: 'quote',
  description: 'Multiple phrases animate in sequence with scale and fade. Kinetic typography style for impactful statement breakdowns.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'phrases',
      type: 'items',
      label: 'Phrases',
      description: 'Phrases to animate in sequence (use **word** for accent)',
      required: true,
      itemSchema: [
        {
          name: 'text',
          type: 'string',
          label: 'Text',
          description: 'The phrase text (use **word** for accent)',
          required: true,
        },
        {
          name: 'hold',
          type: 'number',
          label: 'Hold',
          description: 'Seconds to hold before next phrase',
          required: false,
          default: 0.7,
          min: 0.3,
          max: 3,
          step: 0.1,
        },
      ],
    },
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Visual style preset',
      required: false,
      default: 'custom',
      options: ['custom', 'noir-essay', 'cold-data', 'modern-creator', 'academic-paper', 'documentary', 'podcast-visual', 'retro-synthwave', 'breaking-news', 'minimalist-white', 'true-crime', 'nature-documentary'],
    },
    {
      name: 'color',
      type: 'color',
      label: 'Text Color',
      description: 'Color of the text (ignored if style set)',
      required: false,
      default: '#0f172a',
    },
    {
      name: 'size',
      type: 'number',
      label: 'Font Size',
      description: 'Base font size in pixels (ignored if style set)',
      required: false,
      default: 96,
      min: 48,
      max: 200,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if style set)',
      required: false,
      default: '#ffffff',
    },
  ],
  defaults: {
    style: 'custom',
    color: '#0f172a',
    size: 96,
    background: '#ffffff',
  },
  preview: '/previews/quote-kinetic.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const rawPhrases = params.phrases as Array<{ text: string; hold?: number }> || [];

    // Calculate duration from phrases
    const totalHold = rawPhrases.reduce((acc, p) => acc + (p.hold || 0.7), 0);
    const duration = Math.max(totalHold + 2, 4);

    if (style) {
      // Style-driven rendering with accent support for each phrase
      const phrases = rawPhrases.map((p) => {
        const accent = resolveAccent({ text: p.text }, style, false);
        const segments = colorizeSegments(accent.segments, style);
        return {
          text: stripAccentMarkup(p.text),
          segments,
          hold: p.hold || 0.7,
        };
      });

      return {
        duration,
        style: style.id,
        background: style.colors.background,
        kinetic: {
          color: style.colors.primaryText,
          accentColor: style.colors.accent,
          size: style.textScale1080p.h1,
          fontFamily: style.typography.titleFont,
          fontWeight: style.typography.titleWeight,
          phrases,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration,
      background: params.background || '#ffffff',
      kinetic: {
        color: params.color || '#0f172a',
        size: params.size ?? 96,
        phrases: rawPhrases.map((p) => ({
          text: p.text,
          hold: p.hold || 0.7,
        })),
      },
    };
  },
};

export const quoteDramatic: EffectPreset = {
  id: 'quote-dramatic',
  name: 'Dramatic Reveal',
  category: 'quote',
  description: 'Text scales up from small with emphasis. High impact reveal for shocking statements or climactic moments.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'text',
      label: 'Quote Text',
      description: 'The quote to display (use **word** for accent)',
      required: true,
    },
    {
      name: 'author',
      type: 'string',
      label: 'Author',
      description: 'Attribution (optional)',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration in seconds',
      required: false,
      default: 4,
      min: 2,
      max: 10,
    },
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Visual style preset',
      required: false,
      default: 'custom',
      options: ['custom', 'noir-essay', 'cold-data', 'modern-creator', 'academic-paper', 'documentary', 'podcast-visual', 'retro-synthwave', 'breaking-news', 'minimalist-white', 'true-crime', 'nature-documentary'],
    },
    {
      name: 'color',
      type: 'color',
      label: 'Text Color',
      description: 'Color of the quote text (ignored if style set)',
      required: false,
      default: '#ffffff',
    },
    {
      name: 'accent',
      type: 'color',
      label: 'Accent Color',
      description: 'Accent color for emphasis (ignored if style set)',
      required: false,
      default: '#ef4444',
    },
  ],
  defaults: {
    duration: 4,
    style: 'custom',
    color: '#ffffff',
    accent: '#ef4444',
  },
  preview: '/previews/quote-dramatic.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const text = params.text as string || '';
    const author = params.author as string | undefined;

    if (style) {
      const quoteAccent = resolveAccent({ text }, style, false);
      const quoteSegments = colorizeSegments(quoteAccent.segments, style);

      const phrases: Array<{
        text: string;
        segments?: Array<{ text: string; color: string }>;
        hold: number;
      }> = [
        {
          text: stripAccentMarkup(text),
          segments: quoteSegments,
          hold: 1.2,
        },
      ];

      if (author) {
        phrases.push({
          text: `— ${author}`,
          hold: 0.8,
        });
      }

      return {
        duration: params.duration ?? 4,
        style: style.id,
        background: style.colors.background,
        kinetic: {
          color: style.colors.primaryText,
          accentColor: style.colors.accent,
          size: style.textScale1080p.h2,
          fontFamily: style.typography.titleFont,
          fontWeight: style.typography.titleWeight,
          dramatic: true,
          phrases,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    const phrases = [{ text, hold: 1.2 }];
    if (author) {
      phrases.push({ text: `— ${author}`, hold: 0.8 });
    }

    return {
      duration: params.duration ?? 4,
      background: '#0f172a',
      kinetic: {
        color: params.color || '#ffffff',
        size: 72,
        phrases,
      },
    };
  },
};

export const quotePresets = [quoteFadeCenter, quoteKinetic, quoteDramatic];
