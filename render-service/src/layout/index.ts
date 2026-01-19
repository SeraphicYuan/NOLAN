/**
 * Layout System
 *
 * Resolves layout specifications to regions and converts to engine-specific formats.
 *
 * ## Engine Support
 *
 * | Engine       | Layout Support | Notes |
 * |--------------|----------------|-------|
 * | Remotion     | ✅ Full        | Uses CSS positioning via regionToRemotionStyle() |
 * | Motion Canvas| ⚠️ Partial     | Has internal Layout component but ignores layout parameter |
 * | Infographic  | ❌ None        | SVG generation uses fixed positioning |
 *
 * ## Future Work
 *
 * - Motion Canvas: Add regionToMotionCanvas() integration
 * - Infographic: Support layout for title positioning
 * - Composition endpoint: Render multiple effects in different regions
 */

import type {
  Region,
  LayoutSpec,
  LayoutTemplate,
  CustomLayout,
  ResolvedLayout,
  RegionStyle,
  MotionCanvasPosition,
} from './types.js';
import { TEMPLATES, DEFAULT_TEMPLATE, isLayoutTemplate } from './templates.js';

// Re-export types
export type {
  Region,
  LayoutSpec,
  LayoutTemplate,
  CustomLayout,
  ResolvedLayout,
  RegionStyle,
  MotionCanvasPosition,
};

// Re-export template utilities
export { TEMPLATES, DEFAULT_TEMPLATE, isLayoutTemplate };

/**
 * Validate a region's values are within 0-1 range.
 *
 * @param region - Region to validate
 * @returns Validated region with clamped values
 */
function validateRegion(region: Region): Region {
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  return {
    ...region,
    x: clamp(region.x),
    y: clamp(region.y),
    w: clamp(region.w),
    h: clamp(region.h),
    padding: region.padding !== undefined ? clamp(region.padding) : undefined,
  };
}

/**
 * Validate all regions in a layout.
 *
 * @param regions - Regions to validate
 * @returns Validated regions
 */
function validateRegions(regions: Record<string, Region>): Record<string, Region> {
  const validated: Record<string, Region> = {};
  for (const [name, region] of Object.entries(regions)) {
    validated[name] = validateRegion(region);
  }
  return validated;
}

/**
 * Resolve a layout specification to concrete regions.
 *
 * @param layout - Template name, custom regions, or undefined for default
 * @returns Resolved layout with all regions defined
 */
export function resolveLayout(layout?: LayoutSpec): ResolvedLayout {
  // No layout specified - use default
  if (!layout) {
    return {
      template: DEFAULT_TEMPLATE,
      regions: TEMPLATES[DEFAULT_TEMPLATE],
    };
  }

  // Template name
  if (typeof layout === 'string') {
    if (isLayoutTemplate(layout)) {
      return {
        template: layout,
        regions: TEMPLATES[layout],
      };
    }
    // Invalid template name - fall back to default
    console.warn(`Unknown layout template: ${layout}, using default`);
    return {
      template: DEFAULT_TEMPLATE,
      regions: TEMPLATES[DEFAULT_TEMPLATE],
    };
  }

  // Custom layout with regions - validate values
  if (typeof layout === 'object' && layout.regions) {
    return {
      regions: validateRegions(layout.regions),
    };
  }

  // Invalid format - fall back to default
  return {
    template: DEFAULT_TEMPLATE,
    regions: TEMPLATES[DEFAULT_TEMPLATE],
  };
}

/**
 * Get the primary/main region from a layout.
 * Used when rendering a single effect.
 *
 * @param layout - Resolved layout
 * @returns The main region (first region or 'main' if exists)
 */
export function getMainRegion(layout: ResolvedLayout): Region {
  // Prefer 'main' region if it exists
  if (layout.regions.main) {
    return layout.regions.main;
  }
  // Otherwise return first region
  const regionNames = Object.keys(layout.regions);
  if (regionNames.length > 0) {
    return layout.regions[regionNames[0]];
  }
  // Fallback to center
  return TEMPLATES.center.main;
}

/**
 * Convert a region to Remotion CSS properties.
 *
 * @param region - Region definition
 * @returns CSS properties for AbsoluteFill or div
 */
export function regionToRemotionStyle(region: Region): RegionStyle {
  return {
    position: 'absolute',
    left: `${region.x * 100}%`,
    top: `${region.y * 100}%`,
    width: `${region.w * 100}%`,
    height: `${region.h * 100}%`,
    display: 'flex',
    alignItems: region.valign === 'top' ? 'flex-start'
              : region.valign === 'bottom' ? 'flex-end'
              : 'center',
    justifyContent: region.align === 'left' ? 'flex-start'
                  : region.align === 'right' ? 'flex-end'
                  : 'center',
    padding: region.padding ? `${region.padding * 100}%` : undefined,
    boxSizing: 'border-box',
  };
}

/**
 * Convert a region to Motion-Canvas position data.
 * Motion-Canvas uses center-based coordinates.
 *
 * @param region - Region definition
 * @param width - Frame width in pixels
 * @param height - Frame height in pixels
 * @returns Position data for Motion-Canvas
 */
export function regionToMotionCanvas(
  region: Region,
  width: number,
  height: number
): MotionCanvasPosition {
  // Convert from top-left corner to center position
  const centerX = (region.x + region.w / 2) * width - width / 2;
  const centerY = (region.y + region.h / 2) * height - height / 2;

  return {
    x: centerX,
    y: centerY,
    width: region.w * width,
    height: region.h * height,
    align: region.align ?? 'center',
    valign: region.valign ?? 'center',
  };
}

/**
 * Apply style layout settings to a region.
 * Merges style.layout values with region defaults.
 *
 * @param region - Base region
 * @param styleLayout - Layout settings from EssayStyle
 * @returns Region with style applied
 */
export function applyStyleToRegion(
  region: Region,
  styleLayout?: {
    marginX?: number;
    marginY?: number;
    maxTextWidth?: number;
    align?: 'left' | 'center';
  }
): Region {
  if (!styleLayout) {
    return region;
  }

  return {
    ...region,
    // Override alignment from style if not explicitly set
    align: region.align ?? styleLayout.align ?? 'center',
    // Apply style margins as padding within the region
    padding: region.padding ?? Math.min(styleLayout.marginX ?? 0, styleLayout.marginY ?? 0),
  };
}

/**
 * Create layout data to pass to engine.
 *
 * @param layout - Layout specification (template name or custom)
 * @param region - Optional specific region name (for composition)
 * @param styleLayout - Optional style layout settings
 * @returns Layout data for engine
 */
export function createLayoutData(
  layout?: LayoutSpec,
  region?: string,
  styleLayout?: {
    marginX?: number;
    marginY?: number;
    maxTextWidth?: number;
    align?: 'left' | 'center';
  }
): {
  template?: LayoutTemplate;
  region: Region;
  regionName: string;
} {
  const resolved = resolveLayout(layout);

  // Get specific region or main region
  let targetRegion: Region;
  let regionName: string;

  if (region && resolved.regions[region]) {
    targetRegion = resolved.regions[region];
    regionName = region;
  } else {
    targetRegion = getMainRegion(resolved);
    regionName = 'main';
  }

  // Apply style layout settings
  const finalRegion = applyStyleToRegion(targetRegion, styleLayout);

  return {
    template: resolved.template,
    region: finalRegion,
    regionName,
  };
}

/**
 * Get all available template names.
 */
export function getLayoutTemplates(): LayoutTemplate[] {
  return Object.keys(TEMPLATES) as LayoutTemplate[];
}

/**
 * Get region names for a template.
 */
export function getTemplateRegions(template: LayoutTemplate): string[] {
  const regions = TEMPLATES[template];
  return regions ? Object.keys(regions) : [];
}
