/**
 * Asset Management System for Render Service
 *
 * Provides access to visual assets (icons, shapes) for motion effects.
 * Assets can come from:
 * 1. Embedded common icons (bundled with render-service)
 * 2. Style-specific assets from filesystem
 * 3. Common assets from filesystem (fallback)
 *
 * Asset selection logic:
 * 1. If style has a specific version → use it
 * 2. Else fall back to common version
 * 3. Variant parameter allows selecting alternatives (e.g., "arrow-ribbon.svg")
 */

import * as fs from 'fs';
import * as path from 'path';

// Embedded common icons (24x24 viewBox, currentColor stroke)
// These are bundled so render-service works standalone
export const EMBEDDED_ICONS: Record<string, string> = {
  check: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="20 6 9 17 4 12"></polyline>
</svg>`,

  star: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
</svg>`,

  'arrow-up': `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="12" y1="19" x2="12" y2="5"></line>
  <polyline points="5 12 12 5 19 12"></polyline>
</svg>`,

  'trending-up': `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline>
  <polyline points="17 6 23 6 23 12"></polyline>
</svg>`,

  code: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="16 18 22 12 16 6"></polyline>
  <polyline points="8 6 2 12 8 18"></polyline>
</svg>`,

  database: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
  <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
  <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
</svg>`,

  users: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
  <circle cx="9" cy="7" r="4"></circle>
  <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
  <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
</svg>`,

  zap: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
</svg>`,

  award: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="8" r="7"></circle>
  <polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"></polyline>
</svg>`,

  // Note: growth, data, brand are handled via ICON_ALIASES below

  service: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"></circle>
  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
</svg>`,

  innovation: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="9" y1="18" x2="15" y2="18"></line>
  <line x1="10" y1="22" x2="14" y2="22"></line>
  <path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"></path>
</svg>`,
};

// Alias mapping for backward compatibility
const ICON_ALIASES: Record<string, string> = {
  growth: 'trending-up',
  data: 'database',
  brand: 'award',
};

/**
 * Valid characters pattern for path components
 */
const VALID_NAME_PATTERN = /^[a-zA-Z0-9_\-.\/]+$/;

/**
 * Sanitize path component to prevent path traversal
 */
function sanitizePath(name: string, allowSlash = false): string {
  if (!name) {
    throw new Error('Name cannot be empty');
  }

  if (name.includes('\x00')) {
    throw new Error('Name cannot contain null bytes');
  }

  if (name.includes('..')) {
    throw new Error("Name cannot contain '..' (path traversal)");
  }

  // Normalize separators
  name = name.replace(/\\/g, '/');

  // Check for absolute paths
  if (name.startsWith('/') || (name.length > 1 && name[1] === ':')) {
    throw new Error('Name cannot be an absolute path');
  }

  if (!VALID_NAME_PATTERN.test(name)) {
    throw new Error(`Name contains invalid characters: ${name}`);
  }

  if (!allowSlash && name.includes('/')) {
    throw new Error('Name cannot contain path separators');
  }

  return name;
}

/**
 * Asset Manager for render-service
 */
export class AssetManager {
  private assetsDir: string;
  private stylesDir: string;
  private commonDir: string;

  constructor(assetsDir?: string) {
    // Default to project root's assets folder
    this.assetsDir = assetsDir || path.resolve(__dirname, '../../../assets');
    this.stylesDir = path.join(this.assetsDir, 'styles');
    this.commonDir = path.join(this.assetsDir, 'common');
  }

  /**
   * Get icon SVG content
   *
   * Lookup order:
   * 1. Style-specific filesystem: assets/styles/{styleId}/icons/{name}.svg
   * 2. Common filesystem: assets/common/icons/{name}.svg
   * 3. Embedded icons (bundled in code)
   *
   * @param iconName Icon name (e.g., "check", "star")
   * @param styleId Optional style for style-specific icons
   * @param variant Optional variant suffix
   * @param color Optional color to replace currentColor
   * @returns SVG string or null if not found
   */
  getIcon(
    iconName: string,
    styleId?: string,
    variant?: string,
    color?: string
  ): string | null {
    let svg: string | null = null;

    // Resolve alias first
    const resolvedName = ICON_ALIASES[iconName] || iconName;

    // 1. Try style-specific filesystem if styleId provided
    if (styleId) {
      svg = this.getAssetContent(styleId, `icons/${resolvedName}.svg`, variant);
    }

    // 2. Try common filesystem (use dummy style to trigger common fallback)
    if (!svg) {
      const commonPath = this.getAssetPath('_unused_', `icons/${resolvedName}.svg`, variant);
      if (commonPath) {
        try {
          svg = fs.readFileSync(commonPath, 'utf-8');
        } catch {
          // Ignore read errors
        }
      }
    }

    // 3. Fall back to embedded icons
    if (!svg) {
      svg = EMBEDDED_ICONS[resolvedName] || null;
    }

    // Apply color if specified
    if (svg && color) {
      svg = svg.replace(/currentColor/g, color);
    }

    return svg;
  }

  /**
   * Get asset content from filesystem
   *
   * @param styleId Style identifier
   * @param assetName Asset path (e.g., "icons/check.svg")
   * @param variant Optional variant suffix
   * @returns File content or null
   */
  getAssetContent(
    styleId: string,
    assetName: string,
    variant?: string
  ): string | null {
    const assetPath = this.getAssetPath(styleId, assetName, variant);
    if (!assetPath) return null;

    try {
      return fs.readFileSync(assetPath, 'utf-8');
    } catch {
      return null;
    }
  }

  /**
   * Get asset path with style fallback
   *
   * @param styleId Style identifier
   * @param assetName Asset path
   * @param variant Optional variant suffix
   * @returns Absolute path or null
   */
  getAssetPath(
    styleId: string,
    assetName: string,
    variant?: string
  ): string | null {
    try {
      styleId = sanitizePath(styleId, false);
      assetName = sanitizePath(assetName, true);
      if (variant) {
        variant = sanitizePath(variant, false);
      }
    } catch {
      return null;
    }

    // Apply variant to asset name (preserving parent directory)
    if (variant) {
      const ext = path.extname(assetName);
      const dir = path.dirname(assetName);
      const base = path.basename(assetName, ext);
      const newName = `${base}-${variant}${ext}`;
      assetName = dir !== '.' ? path.join(dir, newName) : newName;
    }

    // Try style-specific first
    const stylePath = path.join(this.stylesDir, styleId, assetName);
    if (fs.existsSync(stylePath)) {
      // Verify path is within assets dir (defense in depth)
      const resolved = path.resolve(stylePath);
      if (resolved.startsWith(path.resolve(this.assetsDir))) {
        return resolved;
      }
    }

    // Fall back to common
    const commonPath = path.join(this.commonDir, assetName);
    if (fs.existsSync(commonPath)) {
      const resolved = path.resolve(commonPath);
      if (resolved.startsWith(path.resolve(this.assetsDir))) {
        return resolved;
      }
    }

    return null;
  }

  /**
   * Check if icon exists
   */
  hasIcon(iconName: string, styleId?: string): boolean {
    const resolved = ICON_ALIASES[iconName] || iconName;

    // Check embedded first
    if (EMBEDDED_ICONS[resolved]) return true;

    // Check filesystem
    if (styleId) {
      return this.getAssetPath(styleId, `icons/${resolved}.svg`) !== null;
    }

    return false;
  }

  /**
   * List available icons
   */
  listIcons(styleId?: string): string[] {
    const icons = new Set(Object.keys(EMBEDDED_ICONS));

    // Add filesystem icons
    if (styleId) {
      const styleIconDir = path.join(this.stylesDir, styleId, 'icons');
      if (fs.existsSync(styleIconDir)) {
        for (const file of fs.readdirSync(styleIconDir)) {
          if (file.endsWith('.svg')) {
            icons.add(file.replace('.svg', ''));
          }
        }
      }
    }

    const commonIconDir = path.join(this.commonDir, 'icons');
    if (fs.existsSync(commonIconDir)) {
      for (const file of fs.readdirSync(commonIconDir)) {
        if (file.endsWith('.svg')) {
          icons.add(file.replace('.svg', ''));
        }
      }
    }

    return Array.from(icons).sort();
  }

  /**
   * List available variants for an asset
   *
   * For "icons/arrow.svg", returns variants like ["ribbon", "3d"] if
   * "icons/arrow-ribbon.svg" and "icons/arrow-3d.svg" exist.
   */
  listVariants(styleId: string, assetName: string): string[] {
    try {
      styleId = sanitizePath(styleId, false);
      assetName = sanitizePath(assetName, true);
    } catch {
      return [];
    }

    const variants = new Set<string>();
    const ext = path.extname(assetName);
    const dir = path.dirname(assetName);
    const baseName = path.basename(assetName, ext);

    // Check style-specific directory
    const styleDir = path.join(this.stylesDir, styleId, dir);
    if (fs.existsSync(styleDir)) {
      for (const file of fs.readdirSync(styleDir)) {
        if (
          file.startsWith(baseName + '-') &&
          file.endsWith(ext) &&
          file !== assetName
        ) {
          const variant = file.slice(baseName.length + 1, -ext.length);
          if (variant) variants.add(variant);
        }
      }
    }

    // Check common directory
    const commonDir = path.join(this.commonDir, dir);
    if (fs.existsSync(commonDir)) {
      for (const file of fs.readdirSync(commonDir)) {
        if (
          file.startsWith(baseName + '-') &&
          file.endsWith(ext) &&
          file !== assetName
        ) {
          const variant = file.slice(baseName.length + 1, -ext.length);
          if (variant) variants.add(variant);
        }
      }
    }

    return Array.from(variants).sort();
  }
}

// Global singleton
export const assetManager = new AssetManager();

// Convenience exports
export function getIcon(
  iconName: string,
  styleId?: string,
  variant?: string,
  color?: string
): string | null {
  return assetManager.getIcon(iconName, styleId, variant, color);
}

export function hasIcon(iconName: string, styleId?: string): boolean {
  return assetManager.hasIcon(iconName, styleId);
}

export function listIcons(styleId?: string): string[] {
  return assetManager.listIcons(styleId);
}

export function listVariants(styleId: string, assetName: string): string[] {
  return assetManager.listVariants(styleId, assetName);
}
