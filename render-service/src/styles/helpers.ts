/**
 * Style Helper Functions
 *
 * Utilities for applying styles to rendering.
 */

import type { EssayStyle, SafeArea, ResolvedTextSizes, StyleValidation } from './types.js';
import { resolveAccent } from './accent.js';

/**
 * Calculate safe area for text placement
 *
 * @param style - The essay style
 * @param width - Video width in pixels
 * @param height - Video height in pixels
 * @returns Safe area boundaries
 */
export function getSafeArea(style: EssayStyle, width: number, height: number): SafeArea {
  const marginX = style.layout.marginX * width;
  const marginY = style.layout.marginY * height;

  return {
    x: marginX,
    y: marginY,
    width: width - marginX * 2,
    height: height - marginY * 2,
    maxTextWidth: style.layout.maxTextWidth * width,
  };
}

/**
 * Scale text sizes from 1080p reference to target resolution
 *
 * @param style - The essay style
 * @param videoHeight - Target video height in pixels
 * @returns Scaled text sizes
 */
export function resolveTextSizes(style: EssayStyle, videoHeight: number): ResolvedTextSizes {
  const scaleFactor = videoHeight / 1080;

  return {
    h1: Math.round(style.textScale1080p.h1 * scaleFactor),
    h2: Math.round(style.textScale1080p.h2 * scaleFactor),
    body: Math.round(style.textScale1080p.body * scaleFactor),
    caption: Math.round(style.textScale1080p.caption * scaleFactor),
  };
}

/**
 * Get motion timing in frames
 *
 * @param style - The essay style
 * @param fps - Frames per second (default 30)
 * @returns Timing values in frames
 */
export function getMotionFrames(
  style: EssayStyle,
  fps: number = 30
): {
  enter: number;
  exit: number;
  hold: number;
  total: number;
} {
  return {
    enter: style.motion.enterFrames,
    exit: style.motion.exitFrames,
    hold: style.motion.holdFrames,
    total: style.motion.enterFrames + style.motion.holdFrames + style.motion.exitFrames,
  };
}

/**
 * Convert motion timing to seconds
 *
 * @param style - The essay style
 * @param fps - Frames per second (default 30)
 * @returns Timing values in seconds
 */
export function getMotionSeconds(
  style: EssayStyle,
  fps: number = 30
): {
  enter: number;
  exit: number;
  hold: number;
  total: number;
} {
  const frames = getMotionFrames(style, fps);
  return {
    enter: frames.enter / fps,
    exit: frames.exit / fps,
    hold: frames.hold / fps,
    total: frames.total / fps,
  };
}

/**
 * Build CSS-style gradient string
 */
export function buildGradient(style: EssayStyle): string | null {
  if (!style.texture.gradient) {
    return null;
  }

  const { from, to, angle } = style.texture.gradient;
  return `linear-gradient(${angle}deg, ${from}, ${to})`;
}

/**
 * Get texture overlay settings
 */
export function getTextureSettings(style: EssayStyle): {
  grain: boolean;
  grainOpacity: number;
  vignette: boolean;
  gradient: string | null;
} {
  return {
    grain: style.texture.grainOpacity > 0,
    grainOpacity: style.texture.grainOpacity,
    vignette: style.texture.vignette,
    gradient: buildGradient(style),
  };
}

/**
 * Apply text case transformation
 */
export function applyTextCase(text: string, style: EssayStyle): string {
  switch (style.typography.case) {
    case 'uppercase':
      return text.toUpperCase();
    case 'title':
      return toTitleCase(text);
    case 'sentence':
    default:
      return text;
  }
}

/**
 * Convert string to Title Case
 */
function toTitleCase(text: string): string {
  const smallWords = new Set([
    'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'in',
    'nor', 'of', 'on', 'or', 'so', 'the', 'to', 'up', 'yet',
  ]);

  return text
    .toLowerCase()
    .split(' ')
    .map((word, index) => {
      // Always capitalize first and last word
      if (index === 0 || !smallWords.has(word)) {
        return word.charAt(0).toUpperCase() + word.slice(1);
      }
      return word;
    })
    .join(' ');
}

/**
 * Build font CSS properties from style
 */
export function getFontProps(
  style: EssayStyle,
  level: 'h1' | 'h2' | 'body' | 'caption',
  videoHeight: number = 1080
): {
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  letterSpacing: string;
} {
  const sizes = resolveTextSizes(style, videoHeight);
  const isTitle = level === 'h1' || level === 'h2';

  return {
    fontFamily: isTitle ? style.typography.titleFont : style.typography.bodyFont,
    fontSize: sizes[level],
    fontWeight: isTitle ? style.typography.titleWeight : style.typography.bodyWeight,
    letterSpacing: isTitle ? `${style.typography.titleLetterSpacingEm}em` : '0',
  };
}

/**
 * Validate style has required properties
 */
export function validateStyle(style: unknown): style is EssayStyle {
  if (!style || typeof style !== 'object') {
    return false;
  }

  const s = style as Record<string, unknown>;

  return (
    typeof s.id === 'string' &&
    typeof s.name === 'string' &&
    typeof s.colors === 'object' &&
    typeof s.typography === 'object' &&
    typeof s.layout === 'object' &&
    typeof s.textScale1080p === 'object' &&
    typeof s.motion === 'object' &&
    typeof s.texture === 'object' &&
    typeof s.accentUsage === 'object'
  );
}

/**
 * Merge partial style overrides with a base style
 */
export function mergeStyleOverrides(
  base: EssayStyle,
  overrides: Partial<EssayStyle>
): EssayStyle {
  return {
    ...base,
    ...overrides,
    colors: { ...base.colors, ...overrides.colors },
    typography: { ...base.typography, ...overrides.typography },
    layout: { ...base.layout, ...overrides.layout },
    textScale1080p: { ...base.textScale1080p, ...overrides.textScale1080p },
    motion: { ...base.motion, ...overrides.motion },
    texture: { ...base.texture, ...overrides.texture },
    accentUsage: { ...base.accentUsage, ...overrides.accentUsage },
  };
}

/**
 * Scene content for validation
 */
export interface SceneContent {
  title?: string;
  body?: string;
  items?: Array<{ text?: string; label?: string }>;
}

/**
 * Validate scene content against a style's accent rules
 *
 * Checks:
 * - Accent count limits for titles and body text
 * - Forbidden patterns (full sentences as accents)
 * - Empty or missing content warnings
 *
 * @param content - Scene content to validate
 * @param style - The essay style to validate against
 * @returns Validation result with errors and warnings
 */
export function validateSceneContent(
  content: SceneContent,
  style: EssayStyle
): StyleValidation {
  const errors: string[] = [];
  const warnings: string[] = [];

  // Validate title if present
  if (content.title && content.title.trim()) {
    const titleResult = resolveAccent({ text: content.title }, style, true);

    if (titleResult.accentCount > style.accentUsage.maxWordsPerTitle) {
      errors.push(
        `Title has ${titleResult.accentCount} accents, max allowed is ${style.accentUsage.maxWordsPerTitle}`
      );
    }

    // Check for forbidden patterns
    for (const pattern of style.accentUsage.forbiddenPatterns) {
      if (content.title.toLowerCase().includes(pattern.toLowerCase())) {
        warnings.push(`Title contains discouraged pattern: "${pattern}"`);
      }
    }
  } else if (content.title === '') {
    warnings.push('Title is empty');
  }

  // Validate body if present
  if (content.body && content.body.trim()) {
    const bodyResult = resolveAccent({ text: content.body }, style, false);

    if (bodyResult.accentCount > style.accentUsage.maxWordsPerBody) {
      errors.push(
        `Body has ${bodyResult.accentCount} accents, max allowed is ${style.accentUsage.maxWordsPerBody}`
      );
    }

    // Check for full sentences as accents (text between ** that contains a period)
    const accentMatches = content.body.match(/\*\*([^*]+)\*\*/g) || [];
    for (const match of accentMatches) {
      const accentText = match.slice(2, -2);
      if (accentText.includes('.') || accentText.split(' ').length > 5) {
        errors.push(`Accent "${accentText.slice(0, 20)}..." is too long or contains full sentence`);
      }
    }
  }

  // Validate items if present
  if (content.items && Array.isArray(content.items)) {
    content.items.forEach((item, index) => {
      const itemText = item.text || item.label || '';
      if (itemText.trim()) {
        const itemResult = resolveAccent({ text: itemText }, style, false);
        if (itemResult.accentCount > style.accentUsage.maxWordsPerBody) {
          warnings.push(
            `Item ${index + 1} has ${itemResult.accentCount} accents, consider reducing`
          );
        }
      }
    });
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
}
