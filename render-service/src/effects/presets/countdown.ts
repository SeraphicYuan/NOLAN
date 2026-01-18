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

export const countdownTimer: EffectPreset = {
  id: 'countdown-timer',
  name: 'Countdown Timer',
  category: 'transition',
  description: 'Animated countdown from a starting number with scale and fade effects. Perfect for intros, transitions, or building anticipation.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'start',
      type: 'number',
      label: 'Start Number',
      description: 'Number to start counting from',
      required: false,
      default: 3,
      min: 1,
      max: 10,
    },
    {
      name: 'end_text',
      type: 'string',
      label: 'End Text',
      description: 'Text to show after countdown (e.g., "GO!", "START")',
      required: false,
      default: 'GO!',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total animation duration',
      required: false,
      default: 4,
      min: 2,
      max: 15,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Text Color',
      description: 'Color of the countdown numbers',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'end_color',
      type: 'color',
      label: 'End Text Color',
      description: 'Color of the final text',
      required: false,
      default: '#10b981',
    },
    {
      name: 'style',
      type: 'select',
      label: 'Animation Style',
      description: 'Style of the countdown animation',
      required: false,
      options: ['scale-fade', 'bounce', 'flip'],
      default: 'scale-fade',
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
    start: 3,
    end_text: 'GO!',
    duration: 4,
    color: '#0ea5e9',
    end_color: '#10b981',
    style: 'scale-fade',
    essayStyle: 'custom',
  },
  preview: '/previews/countdown-timer.mp4',

  toEngineData(params) {
    // Note: using essayStyle to avoid conflict with animation style param
    const styleId = params.essayStyle as string | undefined;
    const style = (styleId && styleId !== 'none' && styleId !== 'custom')
      ? getStyle(styleId)
      : null;

    if (style) {
      return {
        duration: params.duration ?? 4,
        style: style.id,
        background: style.colors.background,
        countdown: {
          start: params.start ?? 3,
          end_text: params.end_text || 'GO!',
          color: style.colors.primaryText,
          end_color: style.colors.accent,
          style: params.style || 'scale-fade',
          fontFamily: style.typography.titleFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 4,
      countdown: {
        start: params.start ?? 3,
        end_text: params.end_text || 'GO!',
        color: params.color || '#0ea5e9',
        end_color: params.end_color || '#10b981',
        style: params.style || 'scale-fade',
      },
    };
  },
};

export const countdownPresets = [countdownTimer];
