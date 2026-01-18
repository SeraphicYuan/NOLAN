import type { EffectPreset } from '../types.js';
import { getStyle, resolveAccent, colorizeSegments } from '../../styles/index.js';
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

export const titleCard: EffectPreset = {
  id: 'title-card',
  name: 'Title Card',
  category: 'title',
  description: 'Full-screen title card with fade in/out. Opening slide style for video introductions and section headers.',
  engine: 'remotion',
  parameters: [
    {
      name: 'title',
      type: 'string',
      label: 'Title',
      description: 'Main title text (use **word** for accent)',
      required: true,
    },
    {
      name: 'subtitle',
      type: 'string',
      label: 'Subtitle',
      description: 'Subtitle text (optional)',
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
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if style set)',
      required: false,
      default: '#0f172a',
    },
    {
      name: 'color',
      type: 'color',
      label: 'Text Color',
      description: 'Text color (ignored if style set)',
      required: false,
      default: '#ffffff',
    },
  ],
  defaults: {
    duration: 4,
    style: 'custom',
    background: '#0f172a',
    color: '#ffffff',
  },
  preview: '/previews/title-card.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const title = params.title as string || '';
    const subtitle = params.subtitle as string || '';

    if (style) {
      // Style-driven rendering
      const titleAccent = resolveAccent({ text: title }, style, true);
      const titleSegments = colorizeSegments(titleAccent.segments, style);

      return {
        duration: params.duration ?? 4,
        style: style.id,
        title_card: {
          title: title,
          titleSegments,
          subtitle,
          background: style.colors.background,
          color: style.colors.primaryText,
          accentColor: style.colors.accent,
          fontSize: style.textScale1080p.h1,
          subtitleSize: style.textScale1080p.h2,
          fontFamily: style.typography.titleFont,
          fontWeight: style.typography.titleWeight,
          texture: style.texture,
        },
      };
    }

    // Legacy mode - direct color params
    return {
      duration: params.duration ?? 4,
      title_card: {
        title,
        subtitle,
        background: params.background || '#0f172a',
        color: params.color || '#ffffff',
      },
    };
  },
};

export const titleChapter: EffectPreset = {
  id: 'title-chapter',
  name: 'Chapter Heading',
  category: 'title',
  description: 'Chapter heading with number and title. For breaking content into numbered sections.',
  engine: 'remotion',
  parameters: [
    {
      name: 'number',
      type: 'string',
      label: 'Number',
      description: 'Chapter number (e.g., "01", "Part 1")',
      required: true,
    },
    {
      name: 'title',
      type: 'string',
      label: 'Title',
      description: 'Chapter title (use **word** for accent)',
      required: true,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration in seconds',
      required: false,
      default: 3,
      min: 2,
      max: 8,
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
      name: 'visualStyle',
      type: 'select',
      label: 'Visual Style',
      description: 'Layout style',
      required: false,
      default: 'minimal',
      options: ['minimal', 'bold', 'elegant'],
    },
  ],
  defaults: {
    duration: 3,
    style: 'custom',
    visualStyle: 'minimal',
  },
  preview: '/previews/title-chapter.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const number = params.number as string || '';
    const title = params.title as string || '';
    const duration = params.duration ?? 3;

    if (style) {
      // Number is always accented in chapter headings
      const titleAccent = resolveAccent({ text: title }, style, true);
      const titleSegments = colorizeSegments(titleAccent.segments, style);

      return {
        duration,
        style: style.id,
        chapter: {
          number,
          title,
          titleSegments,
          numberColor: style.colors.accent,  // number uses accent
          titleColor: style.colors.primaryText,
          background: style.colors.background,
          fontSize: style.textScale1080p.h2,
          numberSize: style.textScale1080p.h1,
          fontFamily: style.typography.titleFont,
          visualStyle: params.visualStyle || 'minimal',
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration,
      chapters: [
        {
          title: `${number} ${title}`,
          subtitle: '',
          start: 0,
          duration,
        },
      ],
    };
  },
};

export const titleLowerThird: EffectPreset = {
  id: 'title-lower-third',
  name: 'Lower Third',
  category: 'title',
  description: 'Lower third overlay with name and role. Speaker identification style for interviews and presentations.',
  engine: 'remotion',
  parameters: [
    {
      name: 'name',
      type: 'string',
      label: 'Name',
      description: "Person's name",
      required: true,
    },
    {
      name: 'role',
      type: 'string',
      label: 'Role',
      description: 'Title/role/affiliation',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Display duration in seconds',
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
      name: 'position',
      type: 'select',
      label: 'Position',
      description: 'Horizontal position',
      required: false,
      default: 'left',
      options: ['left', 'center', 'right'],
    },
    {
      name: 'color',
      type: 'color',
      label: 'Accent Color',
      description: 'Accent color (ignored if style set)',
      required: false,
      default: '#0ea5e9',
    },
  ],
  defaults: {
    duration: 4,
    style: 'custom',
    position: 'left',
    color: '#0ea5e9',
  },
  preview: '/previews/title-lower-third.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const name = params.name as string || '';
    const role = params.role as string || '';
    const position = params.position as string || 'left';

    if (style) {
      return {
        duration: params.duration ?? 4,
        style: style.id,
        lower_third: {
          name,
          role,
          position,
          nameColor: style.colors.primaryText,
          roleColor: style.colors.secondaryText,
          accentColor: style.colors.accent,
          background: style.colors.background,
          fontSize: style.textScale1080p.body,
          roleSize: style.textScale1080p.caption,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 4,
      lower_third: {
        name,
        role,
        position,
        color: params.color || '#0ea5e9',
      },
    };
  },
};

export const titlePresets = [titleCard, titleChapter, titleLowerThird];
