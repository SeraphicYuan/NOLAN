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

export const statCounterRoll: EffectPreset = {
  id: 'stat-counter-roll',
  name: 'Counter Roll',
  category: 'statistic',
  description: 'Number rolls up from 0 to target value. Classic counter animation for revealing statistics and counts.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'value',
      type: 'number',
      label: 'Value',
      description: 'Target number to count to',
      required: true,
    },
    {
      name: 'label',
      type: 'string',
      label: 'Label',
      description: 'Label text below number',
      required: false,
    },
    {
      name: 'prefix',
      type: 'string',
      label: 'Prefix',
      description: 'Prefix (e.g., "$")',
      required: false,
    },
    {
      name: 'suffix',
      type: 'string',
      label: 'Suffix',
      description: 'Suffix (e.g., "%", "M")',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Roll duration in seconds',
      required: false,
      default: 3,
      min: 1,
      max: 10,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Number Color',
      description: 'Color of the number (ignored if style set)',
      required: false,
      default: '#0ea5e9',
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
    style: 'custom',
    color: '#0ea5e9',
  },
  preview: '/previews/stat-counter-roll.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 3,
        style: style.id,
        background: style.colors.background,
        counter: {
          value: params.value as number,
          prefix: (params.prefix as string) || '',
          suffix: (params.suffix as string) || '',
          label: (params.label as string) || '',
          color: style.colors.accent,
          labelColor: style.colors.secondaryText,
          size: style.textScale1080p.h1,
          fontFamily: style.typography.titleFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 3,
      counter: {
        value: params.value as number,
        prefix: (params.prefix as string) || '',
        suffix: (params.suffix as string) || '',
        label: (params.label as string) || '',
        color: params.color || '#0ea5e9',
        size: 120,
      },
    };
  },
};

export const statBarGrow: EffectPreset = {
  id: 'stat-bar-grow',
  name: 'Bar Grow',
  category: 'statistic',
  description: 'Horizontal bar grows from left to represent value. Good for showing progress or single-value comparisons.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'value',
      type: 'number',
      label: 'Value',
      description: 'Value (determines bar length)',
      required: true,
    },
    {
      name: 'max',
      type: 'number',
      label: 'Max Value',
      description: 'Maximum value for scale',
      required: false,
      default: 100,
    },
    {
      name: 'label',
      type: 'string',
      label: 'Label',
      description: 'Label text',
      required: false,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Bar Color',
      description: 'Color of the bar',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Grow duration in seconds',
      required: false,
      default: 2,
      min: 1,
      max: 6,
    },
    {
      name: 'show_value',
      type: 'boolean',
      label: 'Show Value',
      description: 'Display value at end of bar',
      required: false,
      default: true,
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
    max: 100,
    duration: 2,
    style: 'custom',
    color: '#0ea5e9',
    show_value: true,
  },
  preview: '/previews/stat-bar-grow.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 2,
        style: style.id,
        background: style.colors.background,
        chart: {
          type: 'bar',
          color: style.colors.accent,
          labelColor: style.colors.primaryText,
          max: params.max ?? 100,
          fontFamily: style.typography.bodyFont,
          items: [
            {
              label: params.label || '',
              value: params.value,
            },
          ],
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 2,
      chart: {
        type: 'bar',
        color: params.color || '#0ea5e9',
        max: params.max ?? 100,
        items: [
          {
            label: params.label || '',
            value: params.value,
          },
        ],
      },
    };
  },
};

export const statHighlightPulse: EffectPreset = {
  id: 'stat-highlight-pulse',
  name: 'Highlight Pulse',
  category: 'statistic',
  description: 'Number appears with pulsing highlight effect. Draws attention to key figures and important data points.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'value',
      type: 'string',
      label: 'Value',
      description: 'The value to display (can include formatting)',
      required: true,
    },
    {
      name: 'label',
      type: 'string',
      label: 'Label',
      description: 'Label text',
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
      name: 'color',
      type: 'color',
      label: 'Text Color',
      description: 'Color of the value',
      required: false,
      default: '#ffffff',
    },
    {
      name: 'pulse_color',
      type: 'color',
      label: 'Pulse Color',
      description: 'Highlight pulse color (ignored if style set)',
      required: false,
      default: '#fbbf24',
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
    duration: 4,
    style: 'custom',
    color: '#ffffff',
    pulse_color: '#fbbf24',
  },
  preview: '/previews/stat-highlight-pulse.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 4,
        style: style.id,
        background: style.colors.background,
        kinetic: {
          color: style.colors.primaryText,
          accentColor: style.colors.accent,
          size: style.textScale1080p.h1,
          fontFamily: style.typography.titleFont,
          phrases: [
            { text: params.value as string, hold: 1.5 },
            ...(params.label ? [{ text: params.label as string, hold: 0.8 }] : []),
          ],
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 4,
      background: '#0f172a',
      kinetic: {
        color: params.color || '#ffffff',
        size: 144,
        phrases: [
          { text: params.value as string, hold: 1.5 },
          ...(params.label ? [{ text: params.label as string, hold: 0.8 }] : []),
        ],
      },
    };
  },
};

export const statisticPresets = [statCounterRoll, statBarGrow, statHighlightPulse];
