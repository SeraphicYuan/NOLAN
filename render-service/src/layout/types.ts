/**
 * Layout System Types
 *
 * Region-based layout for positioning effects within the video frame.
 * Built on percentage-based coordinates for resolution independence.
 */

/**
 * A region defines a rectangular area within the frame.
 * All values are 0-1 percentages of frame dimensions.
 */
export interface Region {
  /** Left edge position (0 = left, 1 = right) */
  x: number;
  /** Top edge position (0 = top, 1 = bottom) */
  y: number;
  /** Width as fraction of frame width */
  w: number;
  /** Height as fraction of frame height */
  h: number;
  /** Horizontal alignment of content within region */
  align?: 'left' | 'center' | 'right';
  /** Vertical alignment of content within region */
  valign?: 'top' | 'center' | 'bottom';
  /** Internal padding as fraction (applied to all sides) */
  padding?: number;
}

/**
 * Predefined layout templates for common video essay patterns.
 */
export type LayoutTemplate =
  | 'center'           // Single centered region (default)
  | 'full'             // Full bleed with safe margins
  | 'lower-third'      // Bottom bar for names/citations
  | 'upper-third'      // Top bar for titles/labels
  | 'split'            // Left/right 50-50
  | 'split-60-40'      // Left 60%, right 40%
  | 'split-40-60'      // Left 40%, right 60%
  | 'thirds'           // Three equal columns
  | 'split-with-lower' // Left/right + bottom bar
  | 'presenter'        // Main content + lower third
  | 'grid-2x2';        // 2x2 grid

/**
 * Custom layout with user-defined regions.
 */
export interface CustomLayout {
  regions: Record<string, Region>;
}

/**
 * Layout specification - either a template name or custom regions.
 */
export type LayoutSpec = LayoutTemplate | CustomLayout;

/**
 * Resolved layout with all regions defined.
 */
export interface ResolvedLayout {
  template?: LayoutTemplate;
  regions: Record<string, Region>;
}

/**
 * Region names for each template.
 */
export const TEMPLATE_REGIONS: Record<LayoutTemplate, string[]> = {
  'center': ['main'],
  'full': ['main'],
  'lower-third': ['main'],
  'upper-third': ['main'],
  'split': ['left', 'right'],
  'split-60-40': ['left', 'right'],
  'split-40-60': ['left', 'right'],
  'thirds': ['left', 'center', 'right'],
  'split-with-lower': ['left', 'right', 'bottom'],
  'presenter': ['main', 'lower'],
  'grid-2x2': ['top-left', 'top-right', 'bottom-left', 'bottom-right'],
};

/**
 * CSS properties for rendering a region.
 */
export interface RegionStyle {
  position: 'absolute';
  left: string;
  top: string;
  width: string;
  height: string;
  display: 'flex';
  alignItems: 'flex-start' | 'center' | 'flex-end';
  justifyContent: 'flex-start' | 'center' | 'flex-end';
  padding?: string;
  boxSizing: 'border-box';
}

/**
 * Position data for Motion-Canvas (center-based coordinates).
 */
export interface MotionCanvasPosition {
  x: number;
  y: number;
  width: number;
  height: number;
  align: 'left' | 'center' | 'right';
  valign: 'top' | 'center' | 'bottom';
}
