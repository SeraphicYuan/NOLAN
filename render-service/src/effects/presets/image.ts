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

export const imageKenBurns: EffectPreset = {
  id: 'image-ken-burns',
  name: 'Ken Burns',
  category: 'image',
  description: 'Slow pan and zoom across a still image. Classic documentary technique for bringing photos to life.',
  engine: 'remotion',
  parameters: [
    {
      name: 'image',
      type: 'image',
      label: 'Image',
      description: 'The image to animate',
      required: true,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Effect duration in seconds',
      required: false,
      default: 6,
      min: 2,
      max: 30,
    },
    {
      name: 'direction',
      type: 'select',
      label: 'Direction',
      description: 'Pan direction',
      required: false,
      default: 'left-to-right',
      options: ['left-to-right', 'right-to-left', 'top-to-bottom', 'bottom-to-top'],
    },
    {
      name: 'zoom',
      type: 'select',
      label: 'Zoom',
      description: 'Zoom behavior',
      required: false,
      default: 'zoom-in',
      options: ['zoom-in', 'zoom-out', 'none'],
    },
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Visual style preset (applies texture overlays)',
      required: false,
      default: 'custom',
      options: ['custom', 'noir-essay', 'cold-data', 'modern-creator', 'academic-paper', 'documentary', 'podcast-visual', 'retro-synthwave', 'breaking-news', 'minimalist-white', 'true-crime', 'nature-documentary'],
    },
  ],
  defaults: {
    duration: 6,
    direction: 'left-to-right',
    zoom: 'zoom-in',
    style: 'custom',
  },
  preview: '/previews/image-ken-burns.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const direction = params.direction as string || 'left-to-right';
    const zoom = params.zoom as string || 'zoom-in';

    // Calculate start/end positions based on direction
    let startX = 0.5, startY = 0.5, endX = 0.5, endY = 0.5;
    const panAmount = 0.15;

    switch (direction) {
      case 'left-to-right':
        startX = 0.5 - panAmount;
        endX = 0.5 + panAmount;
        break;
      case 'right-to-left':
        startX = 0.5 + panAmount;
        endX = 0.5 - panAmount;
        break;
      case 'top-to-bottom':
        startY = 0.5 - panAmount;
        endY = 0.5 + panAmount;
        break;
      case 'bottom-to-top':
        startY = 0.5 + panAmount;
        endY = 0.5 - panAmount;
        break;
    }

    // Calculate zoom values
    let zoomFrom = 1.0, zoomTo = 1.0;
    if (zoom === 'zoom-in') {
      zoomFrom = 1.0;
      zoomTo = 1.3;
    } else if (zoom === 'zoom-out') {
      zoomFrom = 1.3;
      zoomTo = 1.0;
    }

    if (style) {
      return {
        duration: params.duration ?? 6,
        style: style.id,
        texture: style.texture,
        image_focus: {
          image_path: params.image,
          x_from: startX,
          y_from: startY,
          x_to: endX,
          y_to: endY,
          zoom_from: zoomFrom,
          zoom_to: zoomTo,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 6,
      image_focus: {
        image_path: params.image,
        x_from: startX,
        y_from: startY,
        x_to: endX,
        y_to: endY,
        zoom_from: zoomFrom,
        zoom_to: zoomTo,
      },
    };
  },
};

export const imageZoomFocus: EffectPreset = {
  id: 'image-zoom-focus',
  name: 'Zoom Focus',
  category: 'image',
  description: 'Start wide, zoom into a specific region of interest. For revealing details or directing attention.',
  engine: 'remotion',
  parameters: [
    {
      name: 'image',
      type: 'image',
      label: 'Image',
      description: 'The image to animate',
      required: true,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Effect duration in seconds',
      required: false,
      default: 4,
      min: 2,
      max: 15,
    },
    {
      name: 'focus_x',
      type: 'number',
      label: 'Focus X',
      description: 'Horizontal focus point (0-1, 0.5 = center)',
      required: false,
      default: 0.5,
      min: 0,
      max: 1,
      step: 0.05,
    },
    {
      name: 'focus_y',
      type: 'number',
      label: 'Focus Y',
      description: 'Vertical focus point (0-1, 0.5 = center)',
      required: false,
      default: 0.5,
      min: 0,
      max: 1,
      step: 0.05,
    },
    {
      name: 'zoom_level',
      type: 'number',
      label: 'Zoom Level',
      description: 'Final zoom multiplier',
      required: false,
      default: 2.0,
      min: 1.5,
      max: 4,
      step: 0.1,
    },
    {
      name: 'style',
      type: 'select',
      label: 'Style',
      description: 'Visual style preset (applies texture overlays)',
      required: false,
      default: 'custom',
      options: ['custom', 'noir-essay', 'cold-data', 'modern-creator', 'academic-paper', 'documentary', 'podcast-visual', 'retro-synthwave', 'breaking-news', 'minimalist-white', 'true-crime', 'nature-documentary'],
    },
  ],
  defaults: {
    duration: 4,
    focus_x: 0.5,
    focus_y: 0.5,
    zoom_level: 2.0,
    style: 'custom',
  },
  preview: '/previews/image-zoom-focus.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 4,
        style: style.id,
        texture: style.texture,
        image_focus: {
          image_path: params.image,
          x: params.focus_x ?? 0.5,
          y: params.focus_y ?? 0.5,
          zoom_from: 1.0,
          zoom_to: params.zoom_level ?? 2.0,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 4,
      image_focus: {
        image_path: params.image,
        x: params.focus_x ?? 0.5,
        y: params.focus_y ?? 0.5,
        zoom_from: 1.0,
        zoom_to: params.zoom_level ?? 2.0,
      },
    };
  },
};

export const photoFrame: EffectPreset = {
  id: 'photo-frame',
  name: 'Photo Frame',
  category: 'image',
  description: 'Image displayed in an animated photo frame with optional tilt and shadow.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'style',
      type: 'select',
      label: 'Frame Style',
      description: 'Style of the photo frame',
      required: false,
      options: ['polaroid', 'simple', 'vintage', 'modern'],
      default: 'polaroid',
    },
    {
      name: 'tilt',
      type: 'number',
      label: 'Tilt Angle',
      description: 'Rotation angle in degrees',
      required: false,
      default: 5,
      min: -15,
      max: 15,
      step: 1,
    },
    {
      name: 'caption',
      type: 'string',
      label: 'Caption',
      description: 'Caption text below image',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Display duration',
      required: false,
      default: 4,
      min: 2,
      max: 15,
    },
    {
      name: 'animation',
      type: 'select',
      label: 'Animation',
      description: 'Entry animation style',
      required: false,
      options: ['drop', 'slide', 'fade', 'none'],
      default: 'drop',
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if essayStyle set)',
      required: false,
      default: '#1e293b',
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
    style: 'polaroid',
    essayStyle: 'custom',
    tilt: 5,
    duration: 4,
    animation: 'drop',
    background: '#1e293b',
  },
  preview: '/previews/photo-frame.mp4',

  toEngineData(params) {
    // Note: using essayStyle to avoid conflict with frame style param
    const styleId = params.essayStyle as string | undefined;
    const style = (styleId && styleId !== 'none' && styleId !== 'custom')
      ? getStyle(styleId)
      : null;

    if (style) {
      return {
        duration: params.duration ?? 4,
        style: style.id,
        background: style.colors.background,
        photoFrame: {
          style: params.style || 'polaroid',
          tilt: params.tilt ?? 5,
          caption: params.caption || '',
          animation: params.animation || 'drop',
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 4,
      background: params.background || '#1e293b',
      photoFrame: {
        style: params.style || 'polaroid',
        tilt: params.tilt ?? 5,
        caption: params.caption || '',
        animation: params.animation || 'drop',
      },
    };
  },
};

export const documentReveal: EffectPreset = {
  id: 'document-reveal',
  name: 'Document Reveal',
  category: 'image',
  description: 'Paper or document unfolds/slides into view. Great for showing text sources.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'title',
      type: 'string',
      label: 'Title',
      description: 'Document title/header',
      required: false,
    },
    {
      name: 'content',
      type: 'text',
      label: 'Content',
      description: 'Document body text',
      required: true,
    },
    {
      name: 'style',
      type: 'select',
      label: 'Document Style',
      description: 'Visual style of the document',
      required: false,
      options: ['paper', 'official', 'newspaper', 'letter'],
      default: 'paper',
    },
    {
      name: 'animation',
      type: 'select',
      label: 'Animation',
      description: 'Entry animation',
      required: false,
      options: ['unfold', 'slide', 'drop'],
      default: 'unfold',
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
      name: 'highlight',
      type: 'string',
      label: 'Highlight Text',
      description: 'Text to highlight in the document',
      required: false,
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
    style: 'paper',
    essayStyle: 'custom',
    animation: 'unfold',
    duration: 5,
    background: '#0f172a',
  },
  preview: '/previews/document-reveal.mp4',

  toEngineData(params) {
    // Note: using essayStyle to avoid conflict with document style param
    const styleId = params.essayStyle as string | undefined;
    const style = (styleId && styleId !== 'none' && styleId !== 'custom')
      ? getStyle(styleId)
      : null;

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        background: style.colors.background,
        document: {
          title: params.title || '',
          content: params.content || '',
          style: params.style || 'paper',
          animation: params.animation || 'unfold',
          highlight: params.highlight || '',
          titleColor: style.colors.primaryText,
          textColor: style.colors.secondaryText,
          highlightColor: style.colors.accent,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      background: params.background || '#0f172a',
      document: {
        title: params.title || '',
        content: params.content || '',
        style: params.style || 'paper',
        animation: params.animation || 'unfold',
        highlight: params.highlight || '',
      },
    };
  },
};

export const imageParallax: EffectPreset = {
  id: 'image-parallax',
  name: 'Parallax Layers',
  category: 'image',
  description: 'Multi-layer parallax movement creating 2.5D depth illusion. Foreground moves faster than background for a cinematic effect.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'image',
      type: 'image',
      label: 'Image',
      description: 'The image to animate with parallax',
      required: true,
    },
    {
      name: 'layers',
      type: 'number',
      label: 'Layers',
      description: 'Number of depth layers (2-5)',
      required: false,
      default: 3,
      min: 2,
      max: 5,
      step: 1,
    },
    {
      name: 'direction',
      type: 'select',
      label: 'Direction',
      description: 'Movement direction',
      required: false,
      options: ['horizontal', 'vertical', 'diagonal'],
      default: 'horizontal',
    },
    {
      name: 'intensity',
      type: 'number',
      label: 'Intensity',
      description: 'Parallax intensity (0.5-2.0)',
      required: false,
      default: 1.0,
      min: 0.5,
      max: 2.0,
      step: 0.1,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Effect duration in seconds',
      required: false,
      default: 6,
      min: 2,
      max: 20,
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
    layers: 3,
    direction: 'horizontal',
    intensity: 1.0,
    duration: 6,
    background: '#0f172a',
    style: 'custom',
  },
  preview: '/previews/image-parallax.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 6,
        style: style.id,
        background: style.colors.background,
        parallax: {
          image_path: params.image,
          layers: params.layers ?? 3,
          direction: params.direction || 'horizontal',
          intensity: params.intensity ?? 1.0,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 6,
      background: params.background || '#0f172a',
      parallax: {
        image_path: params.image,
        layers: params.layers ?? 3,
        direction: params.direction || 'horizontal',
        intensity: params.intensity ?? 1.0,
      },
    };
  },
};

export const imagePresets = [imageKenBurns, imageZoomFocus, photoFrame, documentReveal, imageParallax];
