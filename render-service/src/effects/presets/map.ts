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

export const mapFlyover: EffectPreset = {
  id: 'map-flyover',
  name: 'Map Flyover',
  category: 'map',
  description: 'Pan and zoom across a map image, visiting multiple points of interest. For geographic storytelling and location narratives.',
  engine: 'remotion',
  parameters: [
    {
      name: 'map',
      type: 'image',
      label: 'Map Image',
      description: 'The map image to animate over',
      required: true,
    },
    {
      name: 'points',
      type: 'items',
      label: 'Points',
      description: 'Points to visit on the map',
      required: true,
      itemSchema: [
        {
          name: 'x',
          type: 'number',
          label: 'X Position',
          description: 'Horizontal position (0-1)',
          required: true,
          min: 0,
          max: 1,
          step: 0.05,
        },
        {
          name: 'y',
          type: 'number',
          label: 'Y Position',
          description: 'Vertical position (0-1)',
          required: true,
          min: 0,
          max: 1,
          step: 0.05,
        },
        {
          name: 'zoom',
          type: 'number',
          label: 'Zoom',
          description: 'Zoom level at this point (1-3)',
          required: false,
          default: 1.2,
          min: 1,
          max: 3,
          step: 0.1,
        },
        {
          name: 'label',
          type: 'string',
          label: 'Label',
          description: 'Label to show at this point',
          required: false,
        },
      ],
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration in seconds',
      required: false,
      default: 8,
      min: 4,
      max: 30,
    },
    {
      name: 'show_labels',
      type: 'boolean',
      label: 'Show Labels',
      description: 'Show point labels',
      required: false,
      default: true,
    },
    {
      name: 'show_marker',
      type: 'boolean',
      label: 'Show Marker',
      description: 'Show animated marker that follows the path',
      required: false,
      default: true,
    },
    {
      name: 'show_trail',
      type: 'boolean',
      label: 'Show Trail',
      description: 'Show trail line behind the marker',
      required: false,
      default: true,
    },
    {
      name: 'marker_color',
      type: 'color',
      label: 'Marker Color',
      description: 'Color of the marker and trail (ignored if style set)',
      required: false,
      default: '#ef4444',
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
    duration: 8,
    show_labels: true,
    show_marker: true,
    show_trail: true,
    marker_color: '#ef4444',
    style: 'custom',
  },
  preview: '/previews/map-flyover.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 8,
        style: style.id,
        map_image_path: params.map,
        map_points: params.points || [],
        show_map_labels: params.show_labels !== false,
        show_marker: params.show_marker !== false,
        show_trail: params.show_trail !== false,
        marker_color: style.colors.accent,
        textColor: style.colors.primaryText,
        fontFamily: style.typography.bodyFont,
        texture: style.texture,
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 8,
      map_image_path: params.map,
      map_points: params.points || [],
      show_map_labels: params.show_labels !== false,
      show_marker: params.show_marker !== false,
      show_trail: params.show_trail !== false,
      marker_color: params.marker_color || '#ef4444',
    };
  },
};

export const locationPin: EffectPreset = {
  id: 'location-pin',
  name: 'Location Pin',
  category: 'map',
  description: 'Animated pin drops onto a location with bounce effect and optional label.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'x',
      type: 'number',
      label: 'X Position',
      description: 'Pin X position (0-1)',
      required: false,
      default: 0.5,
      min: 0,
      max: 1,
      step: 0.05,
    },
    {
      name: 'y',
      type: 'number',
      label: 'Y Position',
      description: 'Pin Y position (0-1)',
      required: false,
      default: 0.5,
      min: 0,
      max: 1,
      step: 0.05,
    },
    {
      name: 'label',
      type: 'string',
      label: 'Label',
      description: 'Location label text',
      required: false,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Pin Color',
      description: 'Color of the pin',
      required: false,
      default: '#ef4444',
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Drop animation duration',
      required: false,
      default: 2,
      min: 1,
      max: 5,
    },
    {
      name: 'pulse',
      type: 'select',
      label: 'Pulse Effect',
      description: 'Add pulse effect after drop',
      required: false,
      options: ['true', 'false'],
      default: 'true',
    },
    {
      name: 'background',
      type: 'color',
      label: 'Background',
      description: 'Background color (ignored if style set)',
      required: false,
      default: '#1e293b',
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
    x: 0.5,
    y: 0.5,
    color: '#ef4444',
    duration: 2,
    pulse: 'true',
    background: '#1e293b',
    style: 'custom',
  },
  preview: '/previews/location-pin.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 2,
        style: style.id,
        background: style.colors.background,
        locationPin: {
          x: params.x ?? 0.5,
          y: params.y ?? 0.5,
          label: params.label || '',
          color: style.colors.accent,
          pulse: params.pulse !== 'false',
          textColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 2,
      background: params.background || '#1e293b',
      locationPin: {
        x: params.x ?? 0.5,
        y: params.y ?? 0.5,
        label: params.label || '',
        color: params.color || '#ef4444',
        pulse: params.pulse !== 'false',
      },
    };
  },
};

export const mapPresets = [mapFlyover, locationPin];
