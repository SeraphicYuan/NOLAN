/**
 * Layout Templates
 *
 * Predefined region configurations for common video essay layouts.
 * All values are percentages (0-1) of frame dimensions.
 */

import type { Region, LayoutTemplate } from './types.js';

/**
 * Safe margins for video content (avoid edges being cut off on TVs/monitors)
 */
const SAFE = {
  margin: 0.05,      // 5% margin from edges
  innerMargin: 0.02, // 2% gap between regions
};

/**
 * Template definitions.
 * Each template maps region names to their positions.
 */
export const TEMPLATES: Record<LayoutTemplate, Record<string, Region>> = {
  /**
   * Center - Single centered region
   * Good for: titles, quotes, statistics
   */
  'center': {
    main: {
      x: 0.1,
      y: 0.1,
      w: 0.8,
      h: 0.8,
      align: 'center',
      valign: 'center',
    },
  },

  /**
   * Full - Full bleed with safe margins
   * Good for: image effects, backgrounds with overlay text
   */
  'full': {
    main: {
      x: SAFE.margin,
      y: SAFE.margin,
      w: 1 - SAFE.margin * 2,
      h: 1 - SAFE.margin * 2,
      align: 'center',
      valign: 'center',
    },
  },

  /**
   * Lower Third - Bottom bar
   * Good for: names, citations, sources
   */
  'lower-third': {
    main: {
      x: SAFE.margin,
      y: 0.82,
      w: 0.5,
      h: 0.13,
      align: 'left',
      valign: 'center',
      padding: 0.01,
    },
  },

  /**
   * Upper Third - Top bar
   * Good for: chapter titles, section labels
   */
  'upper-third': {
    main: {
      x: SAFE.margin,
      y: SAFE.margin,
      w: 0.9,
      h: 0.12,
      align: 'left',
      valign: 'center',
      padding: 0.01,
    },
  },

  /**
   * Split - Left/right 50-50
   * Good for: comparisons, before/after
   */
  'split': {
    left: {
      x: SAFE.margin,
      y: SAFE.margin,
      w: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      h: 1 - SAFE.margin * 2,
      align: 'center',
      valign: 'center',
    },
    right: {
      x: 0.5 + SAFE.innerMargin / 2,
      y: SAFE.margin,
      w: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      h: 1 - SAFE.margin * 2,
      align: 'center',
      valign: 'center',
    },
  },

  /**
   * Split 60-40 - Left emphasis
   * Good for: main content + sidebar
   */
  'split-60-40': {
    left: {
      x: SAFE.margin,
      y: SAFE.margin,
      w: 0.6 - SAFE.margin - SAFE.innerMargin / 2,
      h: 1 - SAFE.margin * 2,
      align: 'center',
      valign: 'center',
    },
    right: {
      x: 0.6 + SAFE.innerMargin / 2,
      y: SAFE.margin,
      w: 0.4 - SAFE.margin - SAFE.innerMargin / 2,
      h: 1 - SAFE.margin * 2,
      align: 'center',
      valign: 'center',
    },
  },

  /**
   * Split 40-60 - Right emphasis
   * Good for: sidebar + main content
   */
  'split-40-60': {
    left: {
      x: SAFE.margin,
      y: SAFE.margin,
      w: 0.4 - SAFE.margin - SAFE.innerMargin / 2,
      h: 1 - SAFE.margin * 2,
      align: 'center',
      valign: 'center',
    },
    right: {
      x: 0.4 + SAFE.innerMargin / 2,
      y: SAFE.margin,
      w: 0.6 - SAFE.margin - SAFE.innerMargin / 2,
      h: 1 - SAFE.margin * 2,
      align: 'center',
      valign: 'center',
    },
  },

  /**
   * Thirds - Three equal columns
   * Good for: comparing three items, timelines
   */
  'thirds': {
    left: {
      x: SAFE.margin,
      y: SAFE.margin,
      w: (1 - SAFE.margin * 2 - SAFE.innerMargin * 2) / 3,
      h: 1 - SAFE.margin * 2,
      align: 'center',
      valign: 'center',
    },
    center: {
      x: SAFE.margin + (1 - SAFE.margin * 2 - SAFE.innerMargin * 2) / 3 + SAFE.innerMargin,
      y: SAFE.margin,
      w: (1 - SAFE.margin * 2 - SAFE.innerMargin * 2) / 3,
      h: 1 - SAFE.margin * 2,
      align: 'center',
      valign: 'center',
    },
    right: {
      x: SAFE.margin + ((1 - SAFE.margin * 2 - SAFE.innerMargin * 2) / 3 + SAFE.innerMargin) * 2,
      y: SAFE.margin,
      w: (1 - SAFE.margin * 2 - SAFE.innerMargin * 2) / 3,
      h: 1 - SAFE.margin * 2,
      align: 'center',
      valign: 'center',
    },
  },

  /**
   * Split with Lower - Two columns + bottom bar
   * Good for: comparison with shared context/citation
   */
  'split-with-lower': {
    left: {
      x: SAFE.margin,
      y: SAFE.margin,
      w: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      h: 0.75,
      align: 'center',
      valign: 'center',
    },
    right: {
      x: 0.5 + SAFE.innerMargin / 2,
      y: SAFE.margin,
      w: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      h: 0.75,
      align: 'center',
      valign: 'center',
    },
    bottom: {
      x: SAFE.margin,
      y: 0.82,
      w: 1 - SAFE.margin * 2,
      h: 0.13,
      align: 'left',
      valign: 'center',
      padding: 0.01,
    },
  },

  /**
   * Presenter - Main content + lower third
   * Good for: main visual with speaker/source attribution
   */
  'presenter': {
    main: {
      x: 0.1,
      y: 0.08,
      w: 0.8,
      h: 0.7,
      align: 'center',
      valign: 'center',
    },
    lower: {
      x: SAFE.margin,
      y: 0.82,
      w: 0.5,
      h: 0.13,
      align: 'left',
      valign: 'center',
      padding: 0.01,
    },
  },

  /**
   * Grid 2x2 - Four equal quadrants
   * Good for: multiple comparisons, dashboards
   */
  'grid-2x2': {
    'top-left': {
      x: SAFE.margin,
      y: SAFE.margin,
      w: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      h: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      align: 'center',
      valign: 'center',
    },
    'top-right': {
      x: 0.5 + SAFE.innerMargin / 2,
      y: SAFE.margin,
      w: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      h: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      align: 'center',
      valign: 'center',
    },
    'bottom-left': {
      x: SAFE.margin,
      y: 0.5 + SAFE.innerMargin / 2,
      w: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      h: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      align: 'center',
      valign: 'center',
    },
    'bottom-right': {
      x: 0.5 + SAFE.innerMargin / 2,
      y: 0.5 + SAFE.innerMargin / 2,
      w: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      h: 0.5 - SAFE.margin - SAFE.innerMargin / 2,
      align: 'center',
      valign: 'center',
    },
  },
};

/**
 * Default layout template
 */
export const DEFAULT_TEMPLATE: LayoutTemplate = 'center';

/**
 * Check if a string is a valid template name
 */
export function isLayoutTemplate(value: unknown): value is LayoutTemplate {
  return typeof value === 'string' && value in TEMPLATES;
}
