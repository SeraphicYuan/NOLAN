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

export const splitScreen: EffectPreset = {
  id: 'split-screen',
  name: 'Split Screen',
  category: 'comparison',
  description: 'Multi-panel split screen with animated reveals. Compare 2-4 items side by side.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'panels',
      type: 'items',
      label: 'Panels',
      description: 'Array of panels with title, subtitle, color',
      required: true,
      itemSchema: [
        { name: 'title', type: 'string', label: 'Title', required: true },
        { name: 'subtitle', type: 'string', label: 'Subtitle', required: false },
        { name: 'color', type: 'color', label: 'Color', required: false },
      ],
    },
    {
      name: 'layout',
      type: 'select',
      label: 'Layout',
      description: 'Panel arrangement',
      required: false,
      options: ['horizontal', 'vertical', 'grid'],
      default: 'horizontal',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration',
      required: false,
      default: 5,
      min: 2,
      max: 15,
    },
    {
      name: 'gap',
      type: 'number',
      label: 'Gap',
      description: 'Gap between panels in pixels',
      required: false,
      default: 4,
      min: 0,
      max: 20,
    },
    {
      name: 'animation',
      type: 'select',
      label: 'Animation',
      description: 'Animation style',
      required: false,
      options: ['slide', 'fade', 'expand'],
      default: 'slide',
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
    layout: 'horizontal',
    duration: 5,
    gap: 4,
    animation: 'slide',
    essayStyle: 'custom',
  },
  preview: '/previews/split-screen.mp4',

  toEngineData(params) {
    // Note: using essayStyle to avoid potential conflicts
    const styleId = params.essayStyle as string | undefined;
    const style = (styleId && styleId !== 'none' && styleId !== 'custom')
      ? getStyle(styleId)
      : null;

    const panels = Array.isArray(params.panels) ? params.panels : [
      { title: 'Option A', color: '#0ea5e9' },
      { title: 'Option B', color: '#22c55e' },
    ];

    if (style) {
      // For style mode, use style colors for panels unless explicitly set
      const styleColors = [style.colors.accent, style.colors.secondaryText, style.colors.primaryText, style.colors.muted];
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        splitScreen: {
          panels: panels.map((p: Record<string, unknown>, i: number) => ({
            title: p.title || `Panel ${i + 1}`,
            subtitle: p.subtitle || '',
            color: p.color || styleColors[i % styleColors.length],
          })),
          layout: params.layout || 'horizontal',
          gap: params.gap ?? 4,
          animation: params.animation || 'slide',
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      splitScreen: {
        panels: panels.map((p: Record<string, unknown>, i: number) => ({
          title: p.title || `Panel ${i + 1}`,
          subtitle: p.subtitle || '',
          color: p.color || ['#0ea5e9', '#22c55e', '#eab308', '#ef4444'][i % 4],
        })),
        layout: params.layout || 'horizontal',
        gap: params.gap ?? 4,
        animation: params.animation || 'slide',
      },
    };
  },
};

export const compareBeforeAfter: EffectPreset = {
  id: 'compare-before-after',
  name: 'Before/After Wipe',
  category: 'comparison',
  description: 'Slider-style wipe transition revealing before and after states. Classic comparison effect for transformations.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'before_label',
      type: 'string',
      label: 'Before Label',
      description: 'Label for the before state',
      required: false,
      default: 'Before',
    },
    {
      name: 'after_label',
      type: 'string',
      label: 'After Label',
      description: 'Label for the after state',
      required: false,
      default: 'After',
    },
    {
      name: 'before_color',
      type: 'color',
      label: 'Before Color',
      description: 'Background color for before state',
      required: false,
      default: '#64748b',
    },
    {
      name: 'after_color',
      type: 'color',
      label: 'After Color',
      description: 'Background color for after state',
      required: false,
      default: '#22c55e',
    },
    {
      name: 'direction',
      type: 'select',
      label: 'Direction',
      description: 'Wipe direction',
      required: false,
      options: ['horizontal', 'vertical'],
      default: 'horizontal',
    },
    {
      name: 'pause_middle',
      type: 'number',
      label: 'Pause at Middle',
      description: 'Seconds to pause at 50% reveal',
      required: false,
      default: 1,
      min: 0,
      max: 5,
      step: 0.5,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration',
      required: false,
      default: 5,
      min: 2,
      max: 15,
    },
    {
      name: 'show_slider',
      type: 'select',
      label: 'Show Slider',
      description: 'Show animated slider handle',
      required: false,
      options: ['true', 'false'],
      default: 'true',
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
    before_label: 'Before',
    after_label: 'After',
    before_color: '#64748b',
    after_color: '#22c55e',
    direction: 'horizontal',
    pause_middle: 1,
    duration: 5,
    show_slider: 'true',
    style: 'custom',
  },
  preview: '/previews/compare-before-after.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        beforeAfter: {
          before_label: params.before_label || 'Before',
          after_label: params.after_label || 'After',
          before_color: style.colors.secondaryText,
          after_color: style.colors.accent,
          direction: params.direction || 'horizontal',
          pause_middle: params.pause_middle ?? 1,
          show_slider: params.show_slider !== 'false',
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      beforeAfter: {
        before_label: params.before_label || 'Before',
        after_label: params.after_label || 'After',
        before_color: params.before_color || '#64748b',
        after_color: params.after_color || '#22c55e',
        direction: params.direction || 'horizontal',
        pause_middle: params.pause_middle ?? 1,
        show_slider: params.show_slider !== 'false',
      },
    };
  },
};

export const comparisonPresets = [splitScreen, compareBeforeAfter];
