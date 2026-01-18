import type { EffectPreset } from '../types.js';
import { getStyle } from '../../styles/index.js';
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

export const timelineHorizontal: EffectPreset = {
  id: 'timeline-horizontal',
  name: 'Horizontal Timeline',
  category: 'data',
  description: 'Animated horizontal timeline with milestones appearing in sequence. Great for project roadmaps, history, or process flows.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'items',
      type: 'items',
      label: 'Milestones',
      description: 'Timeline milestones/events',
      required: true,
      itemSchema: [
        {
          name: 'label',
          type: 'string',
          label: 'Label',
          description: 'Milestone title',
          required: true,
        },
        {
          name: 'date',
          type: 'string',
          label: 'Date/Period',
          description: 'Date or time period',
          required: false,
        },
        {
          name: 'color',
          type: 'color',
          label: 'Color',
          description: 'Milestone color (optional)',
          required: false,
        },
      ],
    },
    {
      name: 'title',
      type: 'string',
      label: 'Title',
      description: 'Timeline title',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total animation duration',
      required: false,
      default: 6,
      min: 3,
      max: 15,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Default Color',
      description: 'Default milestone color',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'line_color',
      type: 'color',
      label: 'Line Color',
      description: 'Color of the timeline line (ignored if style set)',
      required: false,
      default: '#cbd5e1',
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
    duration: 6,
    color: '#0ea5e9',
    line_color: '#cbd5e1',
    style: 'custom',
  },
  preview: '/previews/timeline-horizontal.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const items = (params.items as Array<{ label: string; date?: string; color?: string }>) || [];

    if (style) {
      const styleColors = [style.colors.accent, style.colors.primaryText, style.colors.secondaryText];
      const coloredItems = items.map((item, index) => ({
        ...item,
        color: item.color || styleColors[index % styleColors.length],
      }));

      return {
        duration: params.duration ?? 6,
        style: style.id,
        background: style.colors.background,
        title: params.title || '',
        timeline: {
          items: coloredItems,
          color: style.colors.accent,
          line_color: style.colors.muted,
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    const defaultColors = ['#0ea5e9', '#8b5cf6', '#10b981', '#f97316', '#ef4444'];
    const coloredItems = items.map((item, index) => ({
      ...item,
      color: item.color || defaultColors[index % defaultColors.length],
    }));

    return {
      duration: params.duration ?? 6,
      title: params.title || '',
      timeline: {
        items: coloredItems,
        color: params.color || '#0ea5e9',
        line_color: params.line_color || '#cbd5e1',
      },
    };
  },
};

export const timelinePresets = [timelineHorizontal];
