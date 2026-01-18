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

export const textHighlight: EffectPreset = {
  id: 'text-highlight',
  name: 'Text Highlight',
  category: 'text',
  description: 'Text with animated marker highlight or underline effect. Great for emphasizing key phrases.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'The text to display with highlight',
      required: true,
    },
    {
      name: 'highlight_style',
      type: 'select',
      label: 'Highlight Style',
      description: 'Style of the highlight animation',
      required: false,
      options: ['marker', 'underline', 'box'],
      default: 'marker',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total animation duration',
      required: false,
      default: 4,
      min: 2,
      max: 10,
    },
    {
      name: 'text_color',
      type: 'color',
      label: 'Text Color',
      description: 'Color of the text',
      required: false,
      default: '#0f172a',
    },
    {
      name: 'highlight_color',
      type: 'color',
      label: 'Highlight Color',
      description: 'Color of the highlight',
      required: false,
      default: '#fef08a',
    },
    {
      name: 'font_size',
      type: 'number',
      label: 'Font Size',
      description: 'Size of the text (ignored if style set)',
      required: false,
      default: 64,
      min: 24,
      max: 200,
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
  ],
  defaults: {
    highlight_style: 'marker',
    duration: 4,
    style: 'custom',
    text_color: '#0f172a',
    highlight_color: '#fef08a',
    font_size: 64,
  },
  preview: '/previews/text-highlight.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const text = params.text as string || '';

    if (style) {
      return {
        duration: params.duration ?? 4,
        style: style.id,
        background: style.colors.background,
        highlight: {
          text,
          style: params.highlight_style || 'marker',
          text_color: style.colors.primaryText,
          highlight_color: style.colors.accent,
          font_size: style.textScale1080p.body,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 4,
      highlight: {
        text,
        style: params.highlight_style || 'marker',
        text_color: params.text_color || '#0f172a',
        highlight_color: params.highlight_color || '#fef08a',
        font_size: params.font_size ?? 64,
      },
    };
  },
};

export const textTypewriter: EffectPreset = {
  id: 'text-typewriter',
  name: 'Typewriter',
  category: 'text',
  description: 'Text appears letter by letter with a blinking cursor. Classic typewriter effect for quotes, code, or dramatic reveals.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'text',
      label: 'Text',
      description: 'The text to type out',
      required: true,
    },
    {
      name: 'speed',
      type: 'number',
      label: 'Characters per second',
      description: 'Typing speed',
      required: false,
      default: 15,
      min: 5,
      max: 50,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration (text will finish typing and hold)',
      required: false,
      default: 5,
      min: 2,
      max: 30,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Text Color',
      description: 'Color of the text',
      required: false,
      default: '#ffffff',
    },
    {
      name: 'cursor_color',
      type: 'color',
      label: 'Cursor Color',
      description: 'Color of the blinking cursor',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'font_size',
      type: 'number',
      label: 'Font Size',
      description: 'Font size in pixels',
      required: false,
      default: 48,
      min: 24,
      max: 120,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if style set)',
      required: false,
      default: '#0f172a',
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
  ],
  defaults: {
    speed: 15,
    duration: 5,
    style: 'custom',
    color: '#ffffff',
    cursor_color: '#0ea5e9',
    font_size: 48,
    background: '#0f172a',
  },
  preview: '/previews/text-typewriter.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const text = params.text as string || '';

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        typewriter: {
          text,
          speed: params.speed ?? 15,
          color: style.colors.primaryText,
          cursor_color: style.colors.accent,
          font_size: style.textScale1080p.body,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      background: params.background || '#0f172a',
      typewriter: {
        text,
        speed: params.speed ?? 15,
        color: params.color || '#ffffff',
        cursor_color: params.cursor_color || '#0ea5e9',
        font_size: params.font_size ?? 48,
      },
    };
  },
};

export const textGlitch: EffectPreset = {
  id: 'text-glitch',
  name: 'Glitch Text',
  category: 'text',
  description: 'Digital distortion effect with RGB split and scan lines. Perfect for tech, gaming, or cyberpunk aesthetics.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'The text to display with glitch effect',
      required: true,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total animation duration',
      required: false,
      default: 5,
      min: 2,
      max: 15,
    },
    {
      name: 'intensity',
      type: 'select',
      label: 'Intensity',
      description: 'How intense the glitch effect is',
      required: false,
      options: ['low', 'medium', 'high'],
      default: 'medium',
    },
    {
      name: 'color',
      type: 'color',
      label: 'Base Color',
      description: 'Main text color',
      required: false,
      default: '#ffffff',
    },
    {
      name: 'font_size',
      type: 'number',
      label: 'Font Size',
      description: 'Size of the text (ignored if style set)',
      required: false,
      default: 80,
      min: 32,
      max: 200,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if style set)',
      required: false,
      default: '#0a0a0a',
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
  ],
  defaults: {
    duration: 5,
    intensity: 'medium',
    color: '#ffffff',
    font_size: 80,
    background: '#0a0a0a',
    style: 'custom',
  },
  preview: '/previews/text-glitch.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        glitch: {
          text: params.text || '',
          intensity: params.intensity || 'medium',
          color: style.colors.primaryText,
          font_size: style.textScale1080p.h1,
          fontFamily: style.typography.titleFont,
          accentColor: style.colors.accent,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      background: params.background || '#0a0a0a',
      glitch: {
        text: params.text || '',
        intensity: params.intensity || 'medium',
        color: params.color || '#ffffff',
        font_size: params.font_size ?? 80,
      },
    };
  },
};

export const textBounce: EffectPreset = {
  id: 'text-bounce',
  name: 'Bounce Text',
  category: 'text',
  description: 'Text with bouncy, elastic physics animation. Each letter bounces in with spring dynamics.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'The text to animate',
      required: true,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total animation duration',
      required: false,
      default: 4,
      min: 2,
      max: 10,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Text Color',
      description: 'Color of the text',
      required: false,
      default: '#0f172a',
    },
    {
      name: 'font_size',
      type: 'number',
      label: 'Font Size',
      description: 'Size of the text',
      required: false,
      default: 80,
      min: 32,
      max: 200,
    },
    {
      name: 'style',
      type: 'select',
      label: 'Animation Style',
      description: 'Type of bounce animation',
      required: false,
      options: ['drop', 'scale', 'wave'],
      default: 'drop',
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if essayStyle set)',
      required: false,
      default: '#f8fafc',
    },
    {
      name: 'essayStyle',
      type: 'select',
      label: 'Essay Style',
      description: 'Visual style preset',
      required: false,
      default: 'custom',
      options: ['custom', 'noir-essay', 'cold-data', 'modern-creator', 'academic-paper', 'documentary', 'podcast-visual', 'retro-synthwave', 'breaking-news', 'minimalist-white', 'true-crime', 'nature-documentary'],
    },
  ],
  defaults: {
    duration: 4,
    color: '#0f172a',
    font_size: 80,
    style: 'drop',
    background: '#f8fafc',
    essayStyle: 'custom',
  },
  preview: '/previews/text-bounce.mp4',

  toEngineData(params) {
    // Note: using essayStyle to avoid conflict with animation style param
    const styleId = params.essayStyle as string | undefined;
    const essayStyle = (styleId && styleId !== 'none' && styleId !== 'custom')
      ? getStyle(styleId)
      : null;

    if (essayStyle) {
      return {
        duration: params.duration ?? 4,
        style: essayStyle.id,
        background: essayStyle.colors.background,
        bounce: {
          text: params.text || '',
          color: essayStyle.colors.primaryText,
          font_size: essayStyle.textScale1080p.h1,
          style: params.style || 'drop',
          fontFamily: essayStyle.typography.titleFont,
          accentColor: essayStyle.colors.accent,
          texture: essayStyle.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 4,
      background: params.background || '#f8fafc',
      bounce: {
        text: params.text || '',
        color: params.color || '#0f172a',
        font_size: params.font_size ?? 80,
        style: params.style || 'drop',
      },
    };
  },
};

export const textScramble: EffectPreset = {
  id: 'text-scramble',
  name: 'Text Scramble',
  category: 'text',
  description: 'Text decodes/unscrambles character by character. Matrix/hacker style reveal.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'Final text to reveal',
      required: true,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Decode duration',
      required: false,
      default: 3,
      min: 1,
      max: 10,
    },
    {
      name: 'charset',
      type: 'select',
      label: 'Character Set',
      description: 'Random characters to use',
      required: false,
      options: ['alphanumeric', 'binary', 'symbols', 'katakana'],
      default: 'alphanumeric',
    },
    {
      name: 'color',
      type: 'color',
      label: 'Text Color',
      description: 'Final text color',
      required: false,
      default: '#22c55e',
    },
    {
      name: 'scrambleColor',
      type: 'color',
      label: 'Scramble Color',
      description: 'Color while scrambling',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color',
      required: false,
      default: '#0f172a',
    },
    {
      name: 'font_size',
      type: 'number',
      label: 'Font Size',
      description: 'Size of the text (ignored if style set)',
      required: false,
      default: 64,
      min: 24,
      max: 150,
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
  ],
  defaults: {
    duration: 3,
    charset: 'alphanumeric',
    color: '#22c55e',
    scrambleColor: '#0ea5e9',
    background: '#0f172a',
    font_size: 64,
    style: 'custom',
  },
  preview: '/previews/text-scramble.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 3,
        style: style.id,
        background: style.colors.background,
        scramble: {
          text: params.text || '',
          charset: params.charset || 'alphanumeric',
          color: style.colors.primaryText,
          scrambleColor: style.colors.accent,
          font_size: style.textScale1080p.h2,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 3,
      background: params.background || '#0f172a',
      scramble: {
        text: params.text || '',
        charset: params.charset || 'alphanumeric',
        color: params.color || '#22c55e',
        scrambleColor: params.scrambleColor || '#0ea5e9',
        font_size: params.font_size ?? 64,
      },
    };
  },
};

export const gradientText: EffectPreset = {
  id: 'gradient-text',
  name: 'Gradient Text',
  category: 'text',
  description: 'Animated gradient flowing through text. Eye-catching title effect.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'Text to display',
      required: true,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration',
      required: false,
      default: 4,
      min: 2,
      max: 15,
    },
    {
      name: 'colorStart',
      type: 'color',
      label: 'Start Color',
      description: 'Gradient start color',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'colorMiddle',
      type: 'color',
      label: 'Middle Color',
      description: 'Gradient middle color',
      required: false,
      default: '#a855f7',
    },
    {
      name: 'colorEnd',
      type: 'color',
      label: 'End Color',
      description: 'Gradient end color',
      required: false,
      default: '#ec4899',
    },
    {
      name: 'direction',
      type: 'select',
      label: 'Direction',
      description: 'Gradient flow direction',
      required: false,
      options: ['horizontal', 'vertical', 'diagonal'],
      default: 'horizontal',
    },
    {
      name: 'speed',
      type: 'number',
      label: 'Speed',
      description: 'Animation speed multiplier',
      required: false,
      default: 1,
      min: 0.25,
      max: 3,
      step: 0.25,
    },
    {
      name: 'font_size',
      type: 'number',
      label: 'Font Size',
      description: 'Size of the text',
      required: false,
      default: 80,
      min: 32,
      max: 200,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if style set)',
      required: false,
      default: '#0f172a',
    },
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Visual style preset (uses style colors for gradient)',
      required: false,
      default: 'custom',
      options: ['custom', 'noir-essay', 'cold-data', 'modern-creator', 'academic-paper', 'documentary', 'podcast-visual', 'retro-synthwave', 'breaking-news', 'minimalist-white', 'true-crime', 'nature-documentary'],
    },
  ],
  defaults: {
    duration: 4,
    colorStart: '#0ea5e9',
    colorMiddle: '#a855f7',
    colorEnd: '#ec4899',
    direction: 'horizontal',
    speed: 1,
    font_size: 80,
    background: '#0f172a',
    style: 'custom',
  },
  preview: '/previews/gradient-text.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      // Use style colors for gradient: accent -> primaryText -> secondaryText
      return {
        duration: params.duration ?? 4,
        style: style.id,
        background: style.colors.background,
        gradientText: {
          text: params.text || '',
          colors: [
            style.colors.accent,
            style.colors.primaryText,
            style.colors.secondaryText,
          ],
          direction: params.direction || 'horizontal',
          speed: params.speed ?? 1,
          font_size: style.textScale1080p.h1,
          fontFamily: style.typography.titleFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 4,
      background: params.background || '#0f172a',
      gradientText: {
        text: params.text || '',
        colors: [
          params.colorStart || '#0ea5e9',
          params.colorMiddle || '#a855f7',
          params.colorEnd || '#ec4899',
        ],
        direction: params.direction || 'horizontal',
        speed: params.speed ?? 1,
        font_size: params.font_size ?? 80,
      },
    };
  },
};

export const textPop: EffectPreset = {
  id: 'text-pop',
  name: 'Text Pop',
  category: 'text',
  description: 'Word-by-word reveal with scale and color emphasis. Lyric video style for impactful statements.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'text',
      label: 'Text',
      description: 'The text to animate (words will pop one by one)',
      required: true,
    },
    {
      name: 'emphasis_words',
      type: 'string',
      label: 'Emphasis Words',
      description: 'Comma-separated words to emphasize with color',
      required: false,
    },
    {
      name: 'style',
      type: 'select',
      label: 'Animation Style',
      description: 'How words appear',
      required: false,
      options: ['scale-up', 'drop-in', 'slide-up', 'fade-scale'],
      default: 'scale-up',
    },
    {
      name: 'color',
      type: 'color',
      label: 'Text Color',
      description: 'Default text color',
      required: false,
      default: '#ffffff',
    },
    {
      name: 'emphasis_color',
      type: 'color',
      label: 'Emphasis Color',
      description: 'Color for emphasized words',
      required: false,
      default: '#fbbf24',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total animation duration',
      required: false,
      default: 5,
      min: 2,
      max: 20,
    },
    {
      name: 'font_size',
      type: 'number',
      label: 'Font Size',
      description: 'Size of the text',
      required: false,
      default: 72,
      min: 32,
      max: 200,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if style set)',
      required: false,
      default: '#0f172a',
    },
    {
      name: 'essayStyle',
      type: 'select',
      label: 'Essay Style',
      description: 'Visual style preset (use **word** for accent when set)',
      required: false,
      default: 'custom',
      options: ['custom', 'noir-essay', 'cold-data', 'modern-creator', 'academic-paper', 'documentary', 'podcast-visual', 'retro-synthwave', 'breaking-news', 'minimalist-white', 'true-crime', 'nature-documentary'],
    },
  ],
  defaults: {
    style: 'scale-up',
    essayStyle: 'custom',
    color: '#ffffff',
    emphasis_color: '#fbbf24',
    duration: 5,
    font_size: 72,
    background: '#0f172a',
  },
  preview: '/previews/text-pop.mp4',

  toEngineData(params) {
    // Note: using essayStyle to avoid conflict with animation style param
    const styleId = params.essayStyle as string | undefined;
    const style = (styleId && styleId !== 'none' && styleId !== 'custom')
      ? getStyle(styleId)
      : null;
    const text = params.text as string || '';

    if (style) {
      // Style-driven rendering with accent support
      const accentResult = resolveAccent({ text }, style, false);
      const segments = colorizeSegments(accentResult.segments, style);

      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        textPop: {
          text: stripAccentMarkup(text),
          segments,
          style: params.style || 'scale-up',
          color: style.colors.primaryText,
          emphasis_color: style.colors.accent,
          font_size: style.textScale1080p.h2,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    const emphasisWords = params.emphasis_words
      ? String(params.emphasis_words).split(',').map((w: string) => w.trim().toLowerCase())
      : [];
    return {
      duration: params.duration ?? 5,
      background: params.background || '#0f172a',
      textPop: {
        text,
        emphasis_words: emphasisWords,
        style: params.style || 'scale-up',
        color: params.color || '#ffffff',
        emphasis_color: params.emphasis_color || '#fbbf24',
        font_size: params.font_size ?? 72,
      },
    };
  },
};

export const sourceCitation: EffectPreset = {
  id: 'source-citation',
  name: 'Source Citation',
  category: 'text',
  description: 'Animated source/reference citation. Academic style attribution for credibility in documentaries and video essays.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'source',
      type: 'string',
      label: 'Source',
      description: 'Source name (e.g., "New York Times")',
      required: true,
    },
    {
      name: 'title',
      type: 'string',
      label: 'Article/Report Title',
      description: 'Title of the source material',
      required: false,
    },
    {
      name: 'date',
      type: 'string',
      label: 'Date',
      description: 'Publication date',
      required: false,
    },
    {
      name: 'url',
      type: 'string',
      label: 'URL',
      description: 'Source URL (will be truncated)',
      required: false,
    },
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Citation display style',
      required: false,
      options: ['minimal', 'full', 'academic', 'news'],
      default: 'minimal',
    },
    {
      name: 'position',
      type: 'select',
      label: 'Position',
      description: 'Where to show citation',
      required: false,
      options: ['bottom-left', 'bottom-right', 'bottom-center', 'top-left', 'top-right'],
      default: 'bottom-left',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Display duration',
      required: false,
      default: 4,
      min: 2,
      max: 10,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Text Color',
      description: 'Citation text color (ignored if essayStyle set)',
      required: false,
      default: '#94a3b8',
    },
    {
      name: 'essayStyle',
      type: 'select',
      label: 'Essay Style',
      description: 'Visual style preset',
      required: false,
      default: 'custom',
      options: ['custom', 'noir-essay', 'cold-data', 'modern-creator', 'academic-paper', 'documentary', 'podcast-visual', 'retro-synthwave', 'breaking-news', 'minimalist-white', 'true-crime', 'nature-documentary'],
    },
  ],
  defaults: {
    style: 'minimal',
    essayStyle: 'custom',
    position: 'bottom-left',
    duration: 4,
    color: '#94a3b8',
  },
  preview: '/previews/source-citation.mp4',

  toEngineData(params) {
    // Note: using essayStyle to avoid conflict with citation style param
    const styleId = params.essayStyle as string | undefined;
    const style = (styleId && styleId !== 'none' && styleId !== 'custom')
      ? getStyle(styleId)
      : null;

    if (style) {
      return {
        duration: params.duration ?? 4,
        style: style.id,
        sourceCitation: {
          source: params.source || '',
          title: params.title || '',
          date: params.date || '',
          url: params.url || '',
          style: params.style || 'minimal',
          position: params.position || 'bottom-left',
          color: style.colors.secondaryText,
          accentColor: style.colors.accent,
          fontFamily: style.typography.bodyFont,
          fontSize: style.textScale1080p.caption,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 4,
      sourceCitation: {
        source: params.source || '',
        title: params.title || '',
        date: params.date || '',
        url: params.url || '',
        style: params.style || 'minimal',
        position: params.position || 'bottom-left',
        color: params.color || '#94a3b8',
      },
    };
  },
};

export const textPresets = [textHighlight, textTypewriter, textGlitch, textBounce, textScramble, gradientText, textPop, sourceCitation];
