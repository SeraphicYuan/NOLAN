import type { EffectPreset } from '../types.js';
import { getStyle } from '../../styles/index.js';
import type { EssayStyle } from '../../styles/types.js';

/**
 * Resolve style from params - returns style object or null for legacy mode
 */
function resolveStyleParam(params: Record<string, unknown>): EssayStyle | null {
  const styleId = params.essayStyle as string | undefined;
  if (!styleId || styleId === 'none' || styleId === 'custom') {
    return null;
  }
  return getStyle(styleId);
}

export const pictureInPicture: EffectPreset = {
  id: 'picture-in-picture',
  name: 'Picture in Picture',
  category: 'overlay',
  description: 'Floating video/image window overlay. Slides in from corner with shadow.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'position',
      type: 'select',
      label: 'Position',
      description: 'Corner position of the PiP window',
      required: false,
      options: ['top-left', 'top-right', 'bottom-left', 'bottom-right'],
      default: 'bottom-right',
    },
    {
      name: 'size',
      type: 'number',
      label: 'Size',
      description: 'Size relative to screen (0.1-0.5)',
      required: false,
      default: 0.25,
      min: 0.1,
      max: 0.5,
      step: 0.05,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Display duration',
      required: false,
      default: 5,
      min: 2,
      max: 30,
    },
    {
      name: 'border',
      type: 'select',
      label: 'Border',
      description: 'Show border/frame',
      required: false,
      options: ['true', 'false'],
      default: 'true',
    },
    {
      name: 'borderColor',
      type: 'color',
      label: 'Border Color',
      description: 'Color of the border',
      required: false,
      default: '#ffffff',
    },
    {
      name: 'background',
      type: 'color',
      label: 'Content Background',
      description: 'Background color of PiP content',
      required: false,
      default: '#1e293b',
    },
    {
      name: 'label',
      type: 'string',
      label: 'Label',
      description: 'Optional label text inside PiP',
      required: false,
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
    position: 'bottom-right',
    size: 0.25,
    duration: 5,
    border: 'true',
    borderColor: '#ffffff',
    background: '#1e293b',
    essayStyle: 'custom',
  },
  preview: '/previews/picture-in-picture.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        pip: {
          position: params.position || 'bottom-right',
          size: params.size ?? 0.25,
          border: params.border !== 'false',
          borderColor: style.colors.accent,
          background: style.colors.background,
          label: params.label || '',
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      pip: {
        position: params.position || 'bottom-right',
        size: params.size ?? 0.25,
        border: params.border !== 'false',
        borderColor: params.borderColor || '#ffffff',
        background: params.background || '#1e293b',
        label: params.label || '',
      },
    };
  },
};

export const vhsRetro: EffectPreset = {
  id: 'vhs-retro',
  name: 'VHS Retro',
  category: 'overlay',
  description: 'VHS/CRT style overlay with scanlines, noise, and color distortion.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'intensity',
      type: 'number',
      label: 'Intensity',
      description: 'Effect intensity (0-1)',
      required: false,
      default: 0.5,
      min: 0,
      max: 1,
      step: 0.1,
    },
    {
      name: 'scanlines',
      type: 'select',
      label: 'Scanlines',
      description: 'Show CRT scanlines',
      required: false,
      options: ['true', 'false'],
      default: 'true',
    },
    {
      name: 'noise',
      type: 'select',
      label: 'Noise',
      description: 'Add static noise',
      required: false,
      options: ['true', 'false'],
      default: 'true',
    },
    {
      name: 'colorShift',
      type: 'select',
      label: 'Color Shift',
      description: 'RGB color separation',
      required: false,
      options: ['true', 'false'],
      default: 'true',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Effect duration',
      required: false,
      default: 5,
      min: 1,
      max: 30,
    },
    {
      name: 'text',
      type: 'string',
      label: 'Text Overlay',
      description: 'Optional text to display with VHS effect',
      required: false,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if essayStyle set)',
      required: false,
      default: '#0f172a',
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
    intensity: 0.5,
    scanlines: 'true',
    noise: 'true',
    colorShift: 'true',
    duration: 5,
    background: '#0f172a',
    essayStyle: 'custom',
  },
  preview: '/previews/vhs-retro.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        vhs: {
          intensity: params.intensity ?? 0.5,
          scanlines: params.scanlines !== 'false',
          noise: params.noise !== 'false',
          colorShift: params.colorShift !== 'false',
          text: params.text || '',
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      background: params.background || '#0f172a',
      vhs: {
        intensity: params.intensity ?? 0.5,
        scanlines: params.scanlines !== 'false',
        noise: params.noise !== 'false',
        colorShift: params.colorShift !== 'false',
        text: params.text || '',
      },
    };
  },
};

export const filmGrain: EffectPreset = {
  id: 'film-grain',
  name: 'Film Grain',
  category: 'overlay',
  description: 'Subtle film grain texture overlay for cinematic look.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'intensity',
      type: 'number',
      label: 'Intensity',
      description: 'Grain intensity (0-1)',
      required: false,
      default: 0.3,
      min: 0,
      max: 1,
      step: 0.1,
    },
    {
      name: 'size',
      type: 'number',
      label: 'Grain Size',
      description: 'Size multiplier of grain',
      required: false,
      default: 1,
      min: 0.5,
      max: 3,
      step: 0.25,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Effect duration',
      required: false,
      default: 5,
      min: 1,
      max: 30,
    },
    {
      name: 'text',
      type: 'string',
      label: 'Text Overlay',
      description: 'Optional text to display',
      required: false,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if essayStyle set)',
      required: false,
      default: '#0f172a',
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
    intensity: 0.3,
    size: 1,
    duration: 5,
    background: '#0f172a',
    essayStyle: 'custom',
  },
  preview: '/previews/film-grain.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        filmGrain: {
          intensity: params.intensity ?? 0.3,
          size: params.size ?? 1,
          text: params.text || '',
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      background: params.background || '#0f172a',
      filmGrain: {
        intensity: params.intensity ?? 0.3,
        size: params.size ?? 1,
        text: params.text || '',
      },
    };
  },
};

export const lightLeak: EffectPreset = {
  id: 'light-leak',
  name: 'Light Leak',
  category: 'overlay',
  description: 'Organic light leak and film burn overlay. Adds warmth, nostalgia, and texture to footage. Popular in documentary and video essay styles.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Type of light leak effect',
      required: false,
      options: ['warm', 'cool', 'rainbow', 'burn', 'flare'],
      default: 'warm',
    },
    {
      name: 'intensity',
      type: 'number',
      label: 'Intensity',
      description: 'Effect intensity (0-1)',
      required: false,
      default: 0.5,
      min: 0,
      max: 1,
      step: 0.1,
    },
    {
      name: 'position',
      type: 'select',
      label: 'Position',
      description: 'Where the light leak originates',
      required: false,
      options: ['left', 'right', 'top', 'bottom', 'corner', 'center'],
      default: 'corner',
    },
    {
      name: 'animated',
      type: 'select',
      label: 'Animated',
      description: 'Animate the light leak movement',
      required: false,
      options: ['true', 'false'],
      default: 'true',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Effect duration',
      required: false,
      default: 5,
      min: 1,
      max: 30,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Tint Color',
      description: 'Override color tint (ignored if essayStyle set)',
      required: false,
      default: '#ff6b35',
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if essayStyle set)',
      required: false,
      default: '#0f172a',
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
    style: 'warm',
    intensity: 0.5,
    position: 'corner',
    animated: 'true',
    duration: 5,
    color: '#ff6b35',
    background: '#0f172a',
    essayStyle: 'custom',
  },
  preview: '/previews/light-leak.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        lightLeak: {
          style: params.style || 'warm',
          intensity: params.intensity ?? 0.5,
          position: params.position || 'corner',
          animated: params.animated !== 'false',
          color: style.colors.accent,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      background: params.background || '#0f172a',
      lightLeak: {
        style: params.style || 'warm',
        intensity: params.intensity ?? 0.5,
        position: params.position || 'corner',
        animated: params.animated !== 'false',
        color: params.color || '#ff6b35',
      },
    };
  },
};

export const cameraShake: EffectPreset = {
  id: 'camera-shake',
  name: 'Camera Shake',
  category: 'overlay',
  description: 'Handheld camera shake effect. Adds tension, urgency, or documentary realism to footage.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'intensity',
      type: 'select',
      label: 'Intensity',
      description: 'Shake intensity level',
      required: false,
      options: ['subtle', 'moderate', 'intense', 'earthquake'],
      default: 'subtle',
    },
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Type of shake motion',
      required: false,
      options: ['handheld', 'impact', 'nervous', 'smooth'],
      default: 'handheld',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Effect duration',
      required: false,
      default: 3,
      min: 1,
      max: 30,
    },
    {
      name: 'text',
      type: 'string',
      label: 'Text',
      description: 'Optional text to display with shake',
      required: false,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if essayStyle set)',
      required: false,
      default: '#0f172a',
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
    intensity: 'subtle',
    style: 'handheld',
    duration: 3,
    background: '#0f172a',
    essayStyle: 'custom',
  },
  preview: '/previews/camera-shake.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 3,
        style: style.id,
        background: style.colors.background,
        cameraShake: {
          intensity: params.intensity || 'subtle',
          style: params.style || 'handheld',
          text: params.text || '',
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 3,
      background: params.background || '#0f172a',
      cameraShake: {
        intensity: params.intensity || 'subtle',
        style: params.style || 'handheld',
        text: params.text || '',
      },
    };
  },
};

export const screenFrame: EffectPreset = {
  id: 'screen-frame',
  name: 'Screen Frame',
  category: 'overlay',
  description: 'Browser, phone, or laptop mockup frame. Perfect for showing websites, apps, tweets, or any screen content.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'device',
      type: 'select',
      label: 'Device',
      description: 'Type of device frame',
      required: false,
      options: ['browser', 'phone', 'laptop', 'tablet', 'monitor'],
      default: 'browser',
    },
    {
      name: 'url',
      type: 'string',
      label: 'URL Bar',
      description: 'URL to show in browser address bar',
      required: false,
    },
    {
      name: 'title',
      type: 'string',
      label: 'Title',
      description: 'Window/app title',
      required: false,
    },
    {
      name: 'content_text',
      type: 'text',
      label: 'Content Text',
      description: 'Text content to display inside frame',
      required: false,
    },
    {
      name: 'theme',
      type: 'select',
      label: 'Theme',
      description: 'Light or dark theme',
      required: false,
      options: ['light', 'dark'],
      default: 'dark',
    },
    {
      name: 'animation',
      type: 'select',
      label: 'Animation',
      description: 'Entry animation',
      required: false,
      options: ['fade', 'slide-up', 'scale', 'none'],
      default: 'scale',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Display duration',
      required: false,
      default: 5,
      min: 2,
      max: 20,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Scene background color (ignored if essayStyle set)',
      required: false,
      default: '#0f172a',
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
    device: 'browser',
    theme: 'dark',
    animation: 'scale',
    duration: 5,
    background: '#0f172a',
    essayStyle: 'custom',
  },
  preview: '/previews/screen-frame.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        screenFrame: {
          device: params.device || 'browser',
          url: params.url || '',
          title: params.title || '',
          content_text: params.content_text || '',
          theme: params.theme || 'dark',
          animation: params.animation || 'scale',
          textColor: style.colors.primaryText,
          accentColor: style.colors.accent,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      background: params.background || '#0f172a',
      screenFrame: {
        device: params.device || 'browser',
        url: params.url || '',
        title: params.title || '',
        content_text: params.content_text || '',
        theme: params.theme || 'dark',
        animation: params.animation || 'scale',
      },
    };
  },
};

export const audioWaveform: EffectPreset = {
  id: 'audio-waveform',
  name: 'Audio Waveform',
  category: 'overlay',
  description: 'Animated audio waveform visualization. Great for podcast clips, music discussions, or audio-focused content.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Waveform visualization style',
      required: false,
      options: ['bars', 'line', 'circular', 'mirrored'],
      default: 'bars',
    },
    {
      name: 'color',
      type: 'color',
      label: 'Color',
      description: 'Waveform color',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'secondary_color',
      type: 'color',
      label: 'Secondary Color',
      description: 'Gradient end color (optional)',
      required: false,
      default: '#a855f7',
    },
    {
      name: 'intensity',
      type: 'number',
      label: 'Intensity',
      description: 'Animation intensity (0.5-2)',
      required: false,
      default: 1.0,
      min: 0.5,
      max: 2.0,
      step: 0.1,
    },
    {
      name: 'label',
      type: 'string',
      label: 'Label',
      description: 'Optional label (e.g., speaker name)',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Animation duration',
      required: false,
      default: 5,
      min: 1,
      max: 30,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if essayStyle set)',
      required: false,
      default: '#0f172a',
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
    style: 'bars',
    color: '#0ea5e9',
    secondary_color: '#a855f7',
    intensity: 1.0,
    duration: 5,
    background: '#0f172a',
    essayStyle: 'custom',
  },
  preview: '/previews/audio-waveform.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        audioWaveform: {
          style: params.style || 'bars',
          color: style.colors.accent,
          secondary_color: style.colors.primaryText,
          intensity: params.intensity ?? 1.0,
          label: params.label || '',
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      background: params.background || '#0f172a',
      audioWaveform: {
        style: params.style || 'bars',
        color: params.color || '#0ea5e9',
        secondary_color: params.secondary_color || '#a855f7',
        intensity: params.intensity ?? 1.0,
        label: params.label || '',
      },
    };
  },
};

export const dataTicker: EffectPreset = {
  id: 'data-ticker',
  name: 'Data Ticker',
  category: 'overlay',
  description: 'Scrolling news/data ticker like CNN or Bloomberg. Perfect for displaying multiple data points, headlines, or stats.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'items',
      type: 'items',
      label: 'Ticker Items',
      description: 'Items to scroll across the ticker',
      required: true,
      itemSchema: [
        { name: 'text', type: 'string', label: 'Text', required: true },
        { name: 'icon', type: 'string', label: 'Icon/Symbol', required: false },
        { name: 'color', type: 'color', label: 'Color', required: false },
      ],
    },
    {
      name: 'position',
      type: 'select',
      label: 'Position',
      description: 'Ticker position on screen',
      required: false,
      options: ['top', 'bottom'],
      default: 'bottom',
    },
    {
      name: 'speed',
      type: 'select',
      label: 'Speed',
      description: 'Scroll speed',
      required: false,
      options: ['slow', 'medium', 'fast'],
      default: 'medium',
    },
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Visual style',
      required: false,
      options: ['news', 'stock', 'sports', 'minimal'],
      default: 'news',
    },
    {
      name: 'label',
      type: 'string',
      label: 'Label',
      description: 'Static label on the left (e.g., "BREAKING")',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration',
      required: false,
      default: 8,
      min: 3,
      max: 30,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Ticker background color',
      required: false,
      default: '#1e3a5f',
    },
    {
      name: 'text_color',
      type: 'color',
      label: 'Text Color',
      description: 'Text color (ignored if essayStyle set)',
      required: false,
      default: '#ffffff',
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
    position: 'bottom',
    speed: 'medium',
    style: 'news',
    essayStyle: 'custom',
    duration: 8,
    background: '#1e3a5f',
    text_color: '#ffffff',
  },
  preview: '/previews/data-ticker.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const items = Array.isArray(params.items) ? params.items : [
      { text: 'Breaking: Major announcement expected today' },
      { text: 'Markets up 2.5% on positive news' },
      { text: 'Weather: Sunny, 72°F' },
    ];

    if (style) {
      return {
        duration: params.duration ?? 8,
        style: style.id,
        dataTicker: {
          items: items.map((item: Record<string, unknown>) => ({
            text: item.text || '',
            icon: item.icon || '',
            color: item.color || style.colors.primaryText,
          })),
          position: params.position || 'bottom',
          speed: params.speed || 'medium',
          style: params.style || 'news',
          label: params.label || '',
          background: style.colors.background,
          text_color: style.colors.primaryText,
          accentColor: style.colors.accent,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 8,
      dataTicker: {
        items: items.map((item: Record<string, unknown>) => ({
          text: item.text || '',
          icon: item.icon || '',
          color: item.color || params.text_color || '#ffffff',
        })),
        position: params.position || 'bottom',
        speed: params.speed || 'medium',
        style: params.style || 'news',
        label: params.label || '',
        background: params.background || '#1e3a5f',
        text_color: params.text_color || '#ffffff',
      },
    };
  },
};

export const socialMediaPost: EffectPreset = {
  id: 'social-media-post',
  name: 'Social Media Post',
  category: 'overlay',
  description: 'Twitter/X, Instagram, Reddit, or TikTok post mockup. Perfect for showing social media reactions, quotes, or discussions.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'platform',
      type: 'select',
      label: 'Platform',
      description: 'Social media platform style',
      required: false,
      options: ['twitter', 'instagram', 'reddit', 'tiktok', 'facebook'],
      default: 'twitter',
    },
    {
      name: 'username',
      type: 'string',
      label: 'Username',
      description: 'Display name or handle',
      required: false,
      default: '@user',
    },
    {
      name: 'handle',
      type: 'string',
      label: 'Handle',
      description: 'Username handle (Twitter/X)',
      required: false,
    },
    {
      name: 'content',
      type: 'text',
      label: 'Content',
      description: 'Post content/text',
      required: true,
    },
    {
      name: 'verified',
      type: 'select',
      label: 'Verified',
      description: 'Show verified badge',
      required: false,
      options: ['true', 'false'],
      default: 'false',
    },
    {
      name: 'likes',
      type: 'string',
      label: 'Likes',
      description: 'Like count to display',
      required: false,
      default: '1.2K',
    },
    {
      name: 'retweets',
      type: 'string',
      label: 'Retweets/Shares',
      description: 'Retweet or share count',
      required: false,
      default: '234',
    },
    {
      name: 'comments',
      type: 'string',
      label: 'Comments',
      description: 'Comment/reply count',
      required: false,
      default: '89',
    },
    {
      name: 'timestamp',
      type: 'string',
      label: 'Timestamp',
      description: 'Post timestamp',
      required: false,
      default: '2h',
    },
    {
      name: 'animation',
      type: 'select',
      label: 'Animation',
      description: 'Entry animation',
      required: false,
      options: ['fade', 'slide-up', 'scale', 'none'],
      default: 'scale',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Display duration',
      required: false,
      default: 5,
      min: 2,
      max: 15,
    },
    {
      name: 'theme',
      type: 'select',
      label: 'Theme',
      description: 'Light or dark theme',
      required: false,
      options: ['light', 'dark'],
      default: 'dark',
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Scene background color (ignored if essayStyle set)',
      required: false,
      default: '#0f172a',
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
    platform: 'twitter',
    username: '@user',
    verified: 'false',
    likes: '1.2K',
    retweets: '234',
    comments: '89',
    timestamp: '2h',
    animation: 'scale',
    duration: 5,
    theme: 'dark',
    essayStyle: 'custom',
    background: '#0f172a',
  },
  preview: '/previews/social-media-post.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        socialPost: {
          platform: params.platform || 'twitter',
          username: params.username || '@user',
          handle: params.handle || params.username || '@user',
          content: params.content || '',
          verified: params.verified === 'true',
          likes: params.likes || '1.2K',
          retweets: params.retweets || '234',
          comments: params.comments || '89',
          timestamp: params.timestamp || '2h',
          animation: params.animation || 'scale',
          theme: params.theme || 'dark',
          // Style overrides for text
          textColor: style.colors.primaryText,
          secondaryColor: style.colors.secondaryText,
          accentColor: style.colors.accent,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      background: params.background || '#0f172a',
      socialPost: {
        platform: params.platform || 'twitter',
        username: params.username || '@user',
        handle: params.handle || params.username || '@user',
        content: params.content || '',
        verified: params.verified === 'true',
        likes: params.likes || '1.2K',
        retweets: params.retweets || '234',
        comments: params.comments || '89',
        timestamp: params.timestamp || '2h',
        animation: params.animation || 'scale',
        theme: params.theme || 'dark',
      },
    };
  },
};

export const videoFrameStack: EffectPreset = {
  id: 'video-frame-stack',
  name: 'Video Frame Stack',
  category: 'overlay',
  description: 'Grid or stack of video thumbnails. Great for showing multiple references, related videos, or creating a "wall of content" effect.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'frames',
      type: 'items',
      label: 'Frames',
      description: 'Video frame items to display',
      required: false,
      itemSchema: [
        { name: 'title', type: 'string', label: 'Title', required: false },
        { name: 'color', type: 'color', label: 'Color', required: false },
      ],
    },
    {
      name: 'count',
      type: 'number',
      label: 'Frame Count',
      description: 'Number of frames to show (if not using items)',
      required: false,
      default: 6,
      min: 2,
      max: 12,
    },
    {
      name: 'layout',
      type: 'select',
      label: 'Layout',
      description: 'Frame arrangement',
      required: false,
      options: ['grid', 'stack', 'cascade', 'carousel'],
      default: 'grid',
    },
    {
      name: 'highlight',
      type: 'number',
      label: 'Highlight Index',
      description: 'Index of frame to highlight (0-based)',
      required: false,
      default: 0,
      min: 0,
      max: 11,
    },
    {
      name: 'animation',
      type: 'select',
      label: 'Animation',
      description: 'Entry animation style',
      required: false,
      options: ['stagger', 'fan-out', 'cascade', 'pop'],
      default: 'stagger',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Display duration',
      required: false,
      default: 5,
      min: 2,
      max: 15,
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Scene background color (ignored if essayStyle set)',
      required: false,
      default: '#0f172a',
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
    count: 6,
    layout: 'grid',
    highlight: 0,
    animation: 'stagger',
    duration: 5,
    background: '#0f172a',
    essayStyle: 'custom',
  },
  preview: '/previews/video-frame-stack.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const count = typeof params.count === 'number' ? params.count : 6;
    const defaultColors = ['#ef4444', '#f59e0b', '#22c55e', '#0ea5e9', '#8b5cf6', '#ec4899'];
    const frames = Array.isArray(params.frames) && params.frames.length > 0
      ? params.frames
      : Array.from({ length: count }, (_, i) => ({
          title: `Video ${i + 1}`,
          color: defaultColors[i % 6],
        }));

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        frameStack: {
          frames: frames.map((f: Record<string, unknown>, i: number) => ({
            title: f.title || `Video ${i + 1}`,
            color: f.color || style.colors.accent,
          })),
          layout: params.layout || 'grid',
          highlight: params.highlight ?? 0,
          animation: params.animation || 'stagger',
          textColor: style.colors.primaryText,
          accentColor: style.colors.accent,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      background: params.background || '#0f172a',
      frameStack: {
        frames: frames.map((f: Record<string, unknown>, i: number) => ({
          title: f.title || `Video ${i + 1}`,
          color: f.color || defaultColors[i % 6],
        })),
        layout: params.layout || 'grid',
        highlight: params.highlight ?? 0,
        animation: params.animation || 'stagger',
      },
    };
  },
};

export const overlayPresets = [pictureInPicture, vhsRetro, filmGrain, lightLeak, cameraShake, screenFrame, audioWaveform, dataTicker, socialMediaPost, videoFrameStack];
