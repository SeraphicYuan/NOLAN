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

export const transitionSlide: EffectPreset = {
  id: 'transition-slide',
  name: 'Slide Transition',
  category: 'transition',
  description: 'Content slides in from an edge with customizable direction and easing. Great for scene transitions.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'Text content to slide in',
      required: true,
    },
    {
      name: 'direction',
      type: 'select',
      label: 'Direction',
      description: 'Direction the content slides from',
      required: false,
      options: ['left', 'right', 'top', 'bottom'],
      default: 'left',
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
      default: 72,
      min: 24,
      max: 200,
    },
    {
      name: 'with_fade',
      type: 'boolean',
      label: 'With Fade',
      description: 'Also fade in while sliding',
      required: false,
      default: true,
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
    direction: 'left',
    duration: 4,
    color: '#0f172a',
    font_size: 72,
    with_fade: true,
    essayStyle: 'custom',
  },
  preview: '/previews/transition-slide.mp4',

  toEngineData(params) {
    // Note: using essayStyle to avoid potential conflicts
    const styleId = params.essayStyle as string | undefined;
    const style = (styleId && styleId !== 'none' && styleId !== 'custom')
      ? getStyle(styleId)
      : null;

    if (style) {
      return {
        duration: params.duration ?? 4,
        style: style.id,
        background: style.colors.background,
        slide: {
          text: params.text || '',
          direction: params.direction || 'left',
          color: style.colors.primaryText,
          font_size: style.textScale1080p.h2,
          fontFamily: style.typography.bodyFont,
          with_fade: params.with_fade !== false,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 4,
      slide: {
        text: params.text || '',
        direction: params.direction || 'left',
        color: params.color || '#0f172a',
        font_size: params.font_size ?? 72,
        with_fade: params.with_fade !== false,
      },
    };
  },
};

export const transitionWipe: EffectPreset = {
  id: 'transition-wipe',
  name: 'Wipe Transition',
  category: 'transition',
  description: 'Screen wipe reveal effect with customizable direction and color. Classic broadcast transition.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'Text to reveal after wipe',
      required: false,
    },
    {
      name: 'direction',
      type: 'select',
      label: 'Direction',
      description: 'Direction of the wipe',
      required: false,
      options: ['left', 'right', 'top', 'bottom'],
      default: 'right',
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
      name: 'wipe_color',
      type: 'color',
      label: 'Wipe Color',
      description: 'Color of the wipe bar',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'text_color',
      type: 'color',
      label: 'Text Color',
      description: 'Color of the revealed text (ignored if style set)',
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
    direction: 'right',
    duration: 3,
    wipe_color: '#0ea5e9',
    text_color: '#0f172a',
    style: 'custom',
  },
  preview: '/previews/transition-wipe.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 3,
        style: style.id,
        background: style.colors.background,
        wipe: {
          text: params.text || '',
          direction: params.direction || 'right',
          wipe_color: style.colors.accent,
          text_color: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 3,
      wipe: {
        text: params.text || '',
        direction: params.direction || 'right',
        wipe_color: params.wipe_color || '#0ea5e9',
        text_color: params.text_color || '#0f172a',
      },
    };
  },
};

export const transitionDissolve: EffectPreset = {
  id: 'transition-dissolve',
  name: 'Dissolve Transition',
  category: 'transition',
  description: 'Smooth crossfade/dissolve between scenes. Classic film transition.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'Text content to fade in',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Dissolve duration',
      required: false,
      default: 3,
      min: 1,
      max: 10,
    },
    {
      name: 'easing',
      type: 'select',
      label: 'Easing',
      description: 'Fade easing style',
      required: false,
      options: ['linear', 'smooth', 'slow-start', 'slow-end'],
      default: 'smooth',
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
    easing: 'smooth',
    color: '#ffffff',
    background: '#0f172a',
    font_size: 64,
    style: 'custom',
  },
  preview: '/previews/transition-dissolve.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 3,
        style: style.id,
        background: style.colors.background,
        dissolve: {
          text: params.text || '',
          easing: params.easing || 'smooth',
          color: style.colors.primaryText,
          font_size: style.textScale1080p.body,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 3,
      background: params.background || '#0f172a',
      dissolve: {
        text: params.text || '',
        easing: params.easing || 'smooth',
        color: params.color || '#ffffff',
        font_size: params.font_size ?? 64,
      },
    };
  },
};

export const transitionZoom: EffectPreset = {
  id: 'transition-zoom',
  name: 'Zoom Transition',
  category: 'transition',
  description: 'Camera pushes forward/backward through to next scene.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'Text content to zoom into',
      required: false,
    },
    {
      name: 'direction',
      type: 'select',
      label: 'Direction',
      description: 'Zoom direction',
      required: false,
      options: ['in', 'out'],
      default: 'in',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Zoom duration',
      required: false,
      default: 3,
      min: 1,
      max: 10,
    },
    {
      name: 'focal_x',
      type: 'number',
      label: 'Focal X',
      description: 'Focal point X (0-1)',
      required: false,
      default: 0.5,
      min: 0,
      max: 1,
      step: 0.1,
    },
    {
      name: 'focal_y',
      type: 'number',
      label: 'Focal Y',
      description: 'Focal point Y (0-1)',
      required: false,
      default: 0.5,
      min: 0,
      max: 1,
      step: 0.1,
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
    direction: 'in',
    duration: 3,
    focal_x: 0.5,
    focal_y: 0.5,
    color: '#ffffff',
    background: '#0f172a',
    font_size: 64,
    style: 'custom',
  },
  preview: '/previews/transition-zoom.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 3,
        style: style.id,
        background: style.colors.background,
        zoom: {
          text: params.text || '',
          direction: params.direction || 'in',
          focal_x: params.focal_x ?? 0.5,
          focal_y: params.focal_y ?? 0.5,
          color: style.colors.primaryText,
          font_size: style.textScale1080p.body,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 3,
      background: params.background || '#0f172a',
      zoom: {
        text: params.text || '',
        direction: params.direction || 'in',
        focal_x: params.focal_x ?? 0.5,
        focal_y: params.focal_y ?? 0.5,
        color: params.color || '#ffffff',
        font_size: params.font_size ?? 64,
      },
    };
  },
};

export const zoomBlur: EffectPreset = {
  id: 'zoom-blur',
  name: 'Zoom Blur',
  category: 'transition',
  description: 'Speed zoom with radial motion blur. Creates dramatic zoom-through effect popular in action sequences and transitions.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'Text to display during zoom',
      required: false,
    },
    {
      name: 'direction',
      type: 'select',
      label: 'Direction',
      description: 'Zoom direction',
      required: false,
      options: ['in', 'out'],
      default: 'in',
    },
    {
      name: 'intensity',
      type: 'number',
      label: 'Blur Intensity',
      description: 'Strength of motion blur (0-1)',
      required: false,
      default: 0.7,
      min: 0,
      max: 1,
      step: 0.1,
    },
    {
      name: 'speed',
      type: 'select',
      label: 'Speed',
      description: 'Animation speed',
      required: false,
      options: ['slow', 'medium', 'fast', 'instant'],
      default: 'medium',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration',
      required: false,
      default: 2,
      min: 0.5,
      max: 5,
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
    direction: 'in',
    intensity: 0.7,
    speed: 'medium',
    duration: 2,
    color: '#ffffff',
    background: '#0f172a',
    style: 'custom',
  },
  preview: '/previews/zoom-blur.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 2,
        style: style.id,
        background: style.colors.background,
        zoomBlur: {
          text: params.text || '',
          direction: params.direction || 'in',
          intensity: params.intensity ?? 0.7,
          speed: params.speed || 'medium',
          color: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 2,
      background: params.background || '#0f172a',
      zoomBlur: {
        text: params.text || '',
        direction: params.direction || 'in',
        intensity: params.intensity ?? 0.7,
        speed: params.speed || 'medium',
        color: params.color || '#ffffff',
      },
    };
  },
};

export const glitchTransition: EffectPreset = {
  id: 'glitch-transition',
  name: 'Glitch Transition',
  category: 'transition',
  description: 'Digital glitch distortion with RGB split, scan lines, and noise. Popular cyberpunk/tech aesthetic for video essays.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'Text to display with glitch effect',
      required: false,
    },
    {
      name: 'intensity',
      type: 'select',
      label: 'Intensity',
      description: 'Glitch intensity level',
      required: false,
      options: ['subtle', 'medium', 'intense', 'chaos'],
      default: 'medium',
    },
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Glitch visual style',
      required: false,
      options: ['digital', 'analog', 'vhs', 'matrix'],
      default: 'digital',
    },
    {
      name: 'rgb_split',
      type: 'select',
      label: 'RGB Split',
      description: 'Enable chromatic aberration',
      required: false,
      options: ['true', 'false'],
      default: 'true',
    },
    {
      name: 'scan_lines',
      type: 'select',
      label: 'Scan Lines',
      description: 'Show scan line overlay',
      required: false,
      options: ['true', 'false'],
      default: 'true',
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
      label: 'Primary Color',
      description: 'Main glitch color',
      required: false,
      default: '#00ff00',
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if essayStyle set)',
      required: false,
      default: '#0a0a0a',
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
    intensity: 'medium',
    style: 'digital',
    rgb_split: 'true',
    scan_lines: 'true',
    duration: 3,
    color: '#00ff00',
    background: '#0a0a0a',
    essayStyle: 'custom',
  },
  preview: '/previews/glitch-transition.mp4',

  toEngineData(params) {
    // Note: using essayStyle to avoid conflict with glitch style param
    const styleId = params.essayStyle as string | undefined;
    const style = (styleId && styleId !== 'none' && styleId !== 'custom')
      ? getStyle(styleId)
      : null;

    if (style) {
      return {
        duration: params.duration ?? 3,
        style: style.id,
        background: style.colors.background,
        glitch: {
          text: params.text || '',
          intensity: params.intensity || 'medium',
          style: params.style || 'digital',
          rgb_split: params.rgb_split !== 'false',
          scan_lines: params.scan_lines !== 'false',
          color: style.colors.accent,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 3,
      background: params.background || '#0a0a0a',
      glitch: {
        text: params.text || '',
        intensity: params.intensity || 'medium',
        style: params.style || 'digital',
        rgb_split: params.rgb_split !== 'false',
        scan_lines: params.scan_lines !== 'false',
        color: params.color || '#00ff00',
      },
    };
  },
};

export const transitionPresets = [transitionSlide, transitionWipe, transitionDissolve, transitionZoom, zoomBlur, glitchTransition];
