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

export const calloutLine: EffectPreset = {
  id: 'callout-line',
  name: 'Callout Line',
  category: 'annotation',
  description: 'Animated pointer line connecting to an element. Draws from origin to target with optional label.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'label',
      type: 'string',
      label: 'Label',
      description: 'Callout text label',
      required: true,
    },
    {
      name: 'startX',
      type: 'number',
      label: 'Start X',
      description: 'Line start X position (0-1)',
      required: false,
      default: 0.2,
      min: 0,
      max: 1,
      step: 0.05,
    },
    {
      name: 'startY',
      type: 'number',
      label: 'Start Y',
      description: 'Line start Y position (0-1)',
      required: false,
      default: 0.8,
      min: 0,
      max: 1,
      step: 0.05,
    },
    {
      name: 'endX',
      type: 'number',
      label: 'End X',
      description: 'Line end X position (0-1)',
      required: false,
      default: 0.7,
      min: 0,
      max: 1,
      step: 0.05,
    },
    {
      name: 'endY',
      type: 'number',
      label: 'End Y',
      description: 'Line end Y position (0-1)',
      required: false,
      default: 0.3,
      min: 0,
      max: 1,
      step: 0.05,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration',
      required: false,
      default: 3,
      min: 1,
      max: 10,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Color',
      description: 'Line and label color',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'thickness',
      type: 'number',
      label: 'Thickness',
      description: 'Line thickness in pixels',
      required: false,
      default: 3,
      min: 1,
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
  ],
  defaults: {
    startX: 0.2,
    startY: 0.8,
    endX: 0.7,
    endY: 0.3,
    duration: 3,
    color: '#0ea5e9',
    thickness: 3,
    style: 'custom',
  },
  preview: '/previews/callout-line.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 3,
        style: style.id,
        background: style.colors.background,
        calloutLine: {
          label: params.label || '',
          startX: params.startX ?? 0.2,
          startY: params.startY ?? 0.8,
          endX: params.endX ?? 0.7,
          endY: params.endY ?? 0.3,
          color: style.colors.accent,
          thickness: params.thickness ?? 3,
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 3,
      calloutLine: {
        label: params.label || '',
        startX: params.startX ?? 0.2,
        startY: params.startY ?? 0.8,
        endX: params.endX ?? 0.7,
        endY: params.endY ?? 0.3,
        color: params.color || '#0ea5e9',
        thickness: params.thickness ?? 3,
      },
    };
  },
};

export const calloutBox: EffectPreset = {
  id: 'callout-box',
  name: 'Callout Box',
  category: 'annotation',
  description: 'Animated highlight box or circle that draws attention to a region.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'x',
      type: 'number',
      label: 'Center X',
      description: 'Center X position (0-1)',
      required: false,
      default: 0.5,
      min: 0,
      max: 1,
      step: 0.05,
    },
    {
      name: 'y',
      type: 'number',
      label: 'Center Y',
      description: 'Center Y position (0-1)',
      required: false,
      default: 0.5,
      min: 0,
      max: 1,
      step: 0.05,
    },
    {
      name: 'width',
      type: 'number',
      label: 'Width',
      description: 'Box width (0-1)',
      required: false,
      default: 0.3,
      min: 0.1,
      max: 0.9,
      step: 0.05,
    },
    {
      name: 'height',
      type: 'number',
      label: 'Height',
      description: 'Box height (0-1)',
      required: false,
      default: 0.2,
      min: 0.1,
      max: 0.9,
      step: 0.05,
    },
    {
      name: 'shape',
      type: 'select',
      label: 'Shape',
      description: 'Shape of the highlight',
      required: false,
      options: ['rectangle', 'circle', 'rounded'],
      default: 'rectangle',
    },
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Animation style',
      required: false,
      options: ['stroke', 'fill', 'pulse'],
      default: 'stroke',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration',
      required: false,
      default: 3,
      min: 1,
      max: 10,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Color',
      description: 'Highlight color',
      required: false,
      default: '#ef4444',
    },
    {
      name: 'thickness',
      type: 'number',
      label: 'Stroke Thickness',
      description: 'Border thickness (for stroke style)',
      required: false,
      default: 4,
      min: 1,
      max: 12,
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
    x: 0.5,
    y: 0.5,
    width: 0.3,
    height: 0.2,
    shape: 'rectangle',
    style: 'stroke',
    duration: 3,
    color: '#ef4444',
    thickness: 4,
    essayStyle: 'custom',
  },
  preview: '/previews/callout-box.mp4',

  toEngineData(params) {
    // Note: using essayStyle to avoid conflict with animation style param
    const styleId = params.essayStyle as string | undefined;
    const style = (styleId && styleId !== 'none' && styleId !== 'custom')
      ? getStyle(styleId)
      : null;

    if (style) {
      return {
        duration: params.duration ?? 3,
        style: style.id,
        background: style.colors.background,
        calloutBox: {
          x: params.x ?? 0.5,
          y: params.y ?? 0.5,
          width: params.width ?? 0.3,
          height: params.height ?? 0.2,
          shape: params.shape || 'rectangle',
          style: params.style || 'stroke',
          color: style.colors.accent,
          thickness: params.thickness ?? 4,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 3,
      calloutBox: {
        x: params.x ?? 0.5,
        y: params.y ?? 0.5,
        width: params.width ?? 0.3,
        height: params.height ?? 0.2,
        shape: params.shape || 'rectangle',
        style: params.style || 'stroke',
        color: params.color || '#ef4444',
        thickness: params.thickness ?? 4,
      },
    };
  },
};

export const annotationPresets = [calloutLine, calloutBox];
