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

export const progressCircular: EffectPreset = {
  id: 'progress-circular',
  name: 'Circular Progress',
  category: 'progress',
  description: 'Animated circular progress ring filling up to a percentage. Great for showing completion, stats, or loading indicators.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'value',
      type: 'number',
      label: 'Percentage',
      description: 'Progress percentage (0-100)',
      required: true,
      min: 0,
      max: 100,
    },
    {
      name: 'label',
      type: 'string',
      label: 'Label',
      description: 'Text label below the progress',
      required: false,
    },
    {
      name: 'title',
      type: 'string',
      label: 'Title',
      description: 'Optional title above the progress',
      required: false,
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
      label: 'Progress Color',
      description: 'Color of the progress arc',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'track_color',
      type: 'color',
      label: 'Track Color',
      description: 'Color of the background track',
      required: false,
      default: '#e2e8f0',
    },
    {
      name: 'size',
      type: 'number',
      label: 'Size',
      description: 'Diameter of the progress ring',
      required: false,
      default: 300,
      min: 100,
      max: 600,
    },
    {
      name: 'thickness',
      type: 'number',
      label: 'Thickness',
      description: 'Width of the progress ring',
      required: false,
      default: 24,
      min: 8,
      max: 60,
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
    color: '#0ea5e9',
    track_color: '#e2e8f0',
    size: 300,
    thickness: 24,
    style: 'custom',
  },
  preview: '/previews/progress-circular.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 4,
        style: style.id,
        background: style.colors.background,
        title: params.title || '',
        progress: {
          type: 'circular',
          value: Math.min(100, Math.max(0, Number(params.value) || 0)),
          label: params.label || '',
          color: style.colors.accent,
          track_color: style.colors.muted,
          size: params.size ?? 300,
          thickness: params.thickness ?? 24,
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 4,
      title: params.title || '',
      progress: {
        type: 'circular',
        value: Math.min(100, Math.max(0, Number(params.value) || 0)),
        label: params.label || '',
        color: params.color || '#0ea5e9',
        track_color: params.track_color || '#e2e8f0',
        size: params.size ?? 300,
        thickness: params.thickness ?? 24,
      },
    };
  },
};

export const progressBar: EffectPreset = {
  id: 'progress-bar',
  name: 'Progress Bar',
  category: 'progress',
  description: 'Horizontal progress bar filling from left to right. Classic progress indicator with percentage display.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'value',
      type: 'number',
      label: 'Percentage',
      description: 'Progress percentage (0-100)',
      required: true,
      min: 0,
      max: 100,
    },
    {
      name: 'label',
      type: 'string',
      label: 'Label',
      description: 'Text label for the progress bar',
      required: false,
    },
    {
      name: 'title',
      type: 'string',
      label: 'Title',
      description: 'Optional title above the progress',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total animation duration',
      required: false,
      default: 3,
      min: 1,
      max: 10,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Progress Color',
      description: 'Color of the progress fill',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'track_color',
      type: 'color',
      label: 'Track Color',
      description: 'Color of the background track',
      required: false,
      default: '#e2e8f0',
    },
    {
      name: 'width',
      type: 'number',
      label: 'Width',
      description: 'Width of the progress bar',
      required: false,
      default: 600,
      min: 200,
      max: 1200,
    },
    {
      name: 'height',
      type: 'number',
      label: 'Height',
      description: 'Height of the progress bar',
      required: false,
      default: 32,
      min: 12,
      max: 80,
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
    color: '#0ea5e9',
    track_color: '#e2e8f0',
    width: 600,
    height: 32,
    style: 'custom',
  },
  preview: '/previews/progress-bar.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 3,
        style: style.id,
        background: style.colors.background,
        title: params.title || '',
        progress: {
          type: 'bar',
          value: Math.min(100, Math.max(0, Number(params.value) || 0)),
          label: params.label || '',
          color: style.colors.accent,
          track_color: style.colors.muted,
          width: params.width ?? 600,
          height: params.height ?? 32,
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 3,
      title: params.title || '',
      progress: {
        type: 'bar',
        value: Math.min(100, Math.max(0, Number(params.value) || 0)),
        label: params.label || '',
        color: params.color || '#0ea5e9',
        track_color: params.track_color || '#e2e8f0',
        width: params.width ?? 600,
        height: params.height ?? 32,
      },
    };
  },
};

export const progressPresets = [progressCircular, progressBar];
