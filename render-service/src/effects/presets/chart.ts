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

export const chartBarRace: EffectPreset = {
  id: 'chart-bar-race',
  name: 'Bar Race',
  category: 'chart',
  description: 'Animated bar chart with bars growing in sequence. Racing bar effect for comparing multiple values.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'items',
      type: 'items',
      label: 'Data Items',
      description: 'Items to display as bars',
      required: true,
      itemSchema: [
        {
          name: 'label',
          type: 'string',
          label: 'Label',
          description: 'Bar label',
          required: true,
        },
        {
          name: 'value',
          type: 'number',
          label: 'Value',
          description: 'Bar value',
          required: true,
        },
        {
          name: 'color',
          type: 'color',
          label: 'Color',
          description: 'Override bar color (optional)',
          required: false,
        },
      ],
    },
    {
      name: 'title',
      type: 'string',
      label: 'Title',
      description: 'Chart title',
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
      description: 'Default bar color',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'max',
      type: 'number',
      label: 'Max Value',
      description: 'Maximum value for scale (auto if not set)',
      required: false,
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
    style: 'custom',
    color: '#0ea5e9',
  },
  preview: '/previews/chart-bar-race.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 6,
        style: style.id,
        title: params.title || '',
        background: style.colors.background,
        chart: {
          type: 'bar',
          color: style.colors.accent,
          labelColor: style.colors.primaryText,
          max: params.max,
          items: params.items || [],
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 6,
      title: params.title || '',
      chart: {
        type: 'bar',
        color: params.color || '#0ea5e9',
        max: params.max,
        items: params.items || [],
      },
    };
  },
};

export const chartBarCallout: EffectPreset = {
  id: 'chart-bar-callout',
  name: 'Bar Chart with Callouts',
  category: 'chart',
  description: 'Bar chart with animated callout annotations pointing to specific bars. For highlighting data with explanatory notes.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'items',
      type: 'items',
      label: 'Data Items',
      description: 'Items to display as bars',
      required: true,
      itemSchema: [
        {
          name: 'label',
          type: 'string',
          label: 'Label',
          description: 'Bar label',
          required: true,
        },
        {
          name: 'value',
          type: 'number',
          label: 'Value',
          description: 'Bar value',
          required: true,
        },
      ],
    },
    {
      name: 'callouts',
      type: 'items',
      label: 'Callouts',
      description: 'Annotations pointing to bars',
      required: false,
      itemSchema: [
        {
          name: 'target_index',
          type: 'number',
          label: 'Target Bar',
          description: 'Which bar to point to (0-indexed)',
          required: true,
        },
        {
          name: 'label',
          type: 'string',
          label: 'Text',
          description: 'Callout text',
          required: true,
        },
        {
          name: 'color',
          type: 'color',
          label: 'Color',
          description: 'Callout color',
          required: false,
          default: '#ef4444',
        },
      ],
    },
    {
      name: 'title',
      type: 'string',
      label: 'Title',
      description: 'Chart title',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total duration',
      required: false,
      default: 8,
      min: 4,
      max: 20,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Default Color',
      description: 'Default bar color (ignored if style set)',
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
    duration: 8,
    style: 'custom',
    color: '#0ea5e9',
  },
  preview: '/previews/chart-bar-callout.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const callouts = (params.callouts as Array<{
      target_index: number;
      label: string;
      color?: string;
    }>) || [];

    if (style) {
      return {
        duration: params.duration ?? 8,
        style: style.id,
        title: params.title || '',
        background: style.colors.background,
        chart: {
          type: 'bar',
          color: style.colors.accent,
          labelColor: style.colors.primaryText,
          items: params.items || [],
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
        callouts: callouts.map(c => ({
          label: c.label,
          target_type: 'bar',
          target_index: c.target_index,
          color: c.color || style.colors.accent,
          fontFamily: style.typography.bodyFont,
          dx: 160,
          dy: -140,
        })),
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 8,
      title: params.title || '',
      chart: {
        type: 'bar',
        color: params.color || '#0ea5e9',
        items: params.items || [],
      },
      callouts: callouts.map(c => ({
        label: c.label,
        target_type: 'bar',
        target_index: c.target_index,
        color: c.color || '#ef4444',
        dx: 160,
        dy: -140,
      })),
    };
  },
};

export const chartLine: EffectPreset = {
  id: 'chart-line',
  name: 'Line Chart',
  category: 'chart',
  description: 'Animated line chart with points connecting in sequence. For showing trends and time-series data.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'items',
      type: 'items',
      label: 'Data Points',
      description: 'Points on the line chart',
      required: true,
      itemSchema: [
        {
          name: 'label',
          type: 'string',
          label: 'Label',
          description: 'Point label (e.g., month, year)',
          required: true,
        },
        {
          name: 'value',
          type: 'number',
          label: 'Value',
          description: 'Point value',
          required: true,
        },
      ],
    },
    {
      name: 'title',
      type: 'string',
      label: 'Title',
      description: 'Chart title',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total animation duration',
      required: false,
      default: 5,
      min: 3,
      max: 15,
    },
    {
      name: 'color',
      type: 'color',
      label: 'Line Color',
      description: 'Color of the line',
      required: false,
      default: '#0ea5e9',
    },
    {
      name: 'fill',
      type: 'boolean',
      label: 'Fill Area',
      description: 'Fill area under the line',
      required: false,
      default: true,
    },
    {
      name: 'show_points',
      type: 'boolean',
      label: 'Show Points',
      description: 'Show dots at each data point',
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
    duration: 5,
    style: 'custom',
    color: '#0ea5e9',
    fill: true,
    show_points: true,
  },
  preview: '/previews/chart-line.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);

    if (style) {
      return {
        duration: params.duration ?? 5,
        style: style.id,
        title: params.title || '',
        background: style.colors.background,
        chart: {
          type: 'line',
          color: style.colors.accent,
          labelColor: style.colors.primaryText,
          fill: params.fill !== false,
          show_points: params.show_points !== false,
          items: params.items || [],
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      title: params.title || '',
      chart: {
        type: 'line',
        color: params.color || '#0ea5e9',
        fill: params.fill !== false,
        show_points: params.show_points !== false,
        items: params.items || [],
      },
    };
  },
};

export const chartPie: EffectPreset = {
  id: 'chart-pie',
  name: 'Pie Chart',
  category: 'chart',
  description: 'Animated pie chart with segments growing from center. Each segment appears with percentage label.',
  engine: 'motion-canvas',
  parameters: [
    {
      name: 'items',
      type: 'items',
      label: 'Data Segments',
      description: 'Segments of the pie chart',
      required: true,
      itemSchema: [
        {
          name: 'label',
          type: 'string',
          label: 'Label',
          description: 'Segment label',
          required: true,
        },
        {
          name: 'value',
          type: 'number',
          label: 'Value',
          description: 'Segment value',
          required: true,
        },
        {
          name: 'color',
          type: 'color',
          label: 'Color',
          description: 'Segment color (auto if not set)',
          required: false,
        },
      ],
    },
    {
      name: 'title',
      type: 'string',
      label: 'Title',
      description: 'Chart title',
      required: false,
    },
    {
      name: 'duration',
      type: 'duration',
      label: 'Duration',
      description: 'Total animation duration',
      required: false,
      default: 5,
      min: 3,
      max: 15,
    },
    {
      name: 'donut',
      type: 'boolean',
      label: 'Donut Style',
      description: 'Show as donut chart with hole in center',
      required: false,
      default: false,
    },
    {
      name: 'show_percentages',
      type: 'boolean',
      label: 'Show Percentages',
      description: 'Display percentage on each segment',
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
    duration: 5,
    style: 'custom',
    donut: false,
    show_percentages: true,
  },
  preview: '/previews/chart-pie.mp4',

  toEngineData(params) {
    const style = resolveStyleParam(params);
    const defaultColors = ['#0ea5e9', '#8b5cf6', '#f97316', '#10b981', '#ef4444', '#eab308', '#ec4899'];
    const items = (params.items as Array<{ label: string; value: number; color?: string }>) || [];
    const coloredItems = items.map((item, index) => ({
      ...item,
      color: item.color || defaultColors[index % defaultColors.length],
    }));

    if (style) {
      // Use style-consistent colors for pie segments
      const styleColors = [
        style.colors.accent,
        style.colors.primaryText,
        style.colors.secondaryText,
        style.colors.muted,
      ];
      const styledItems = items.map((item, index) => ({
        ...item,
        color: item.color || styleColors[index % styleColors.length],
      }));

      return {
        duration: params.duration ?? 5,
        style: style.id,
        title: params.title || '',
        background: style.colors.background,
        chart: {
          type: 'pie',
          donut: params.donut === true,
          show_percentages: params.show_percentages !== false,
          items: styledItems,
          labelColor: style.colors.primaryText,
          fontFamily: style.typography.bodyFont,
          texture: style.texture,
        },
      };
    }

    // Legacy mode
    return {
      duration: params.duration ?? 5,
      title: params.title || '',
      chart: {
        type: 'pie',
        donut: params.donut === true,
        show_percentages: params.show_percentages !== false,
        items: coloredItems,
      },
    };
  },
};

export const chartPresets = [chartBarRace, chartBarCallout, chartLine, chartPie];
