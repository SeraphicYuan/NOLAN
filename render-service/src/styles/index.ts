/**
 * Essay Style System
 *
 * Public API for the style system.
 */

// Types
export type {
  EssayStyle,
  TextSegment,
  AccentedTextInput,
  AccentedText,
  AccentTarget,
  SafeArea,
  ResolvedTextSizes,
  StyleValidation,
} from './types.js';

export { GLOBAL_DEFAULTS } from './types.js';

// Styles
export {
  noirEssay,
  coldData,
  modernCreator,
  STYLES,
  DEFAULT_STYLE_ID,
  getStyle,
  getStyleIds,
  getStyleSummaries,
} from './styles.js';

// Accent resolution
export {
  resolveAccent,
  stripAccentMarkup,
  hasAccentMarkup,
  colorizeSegments,
} from './accent.js';

/**
 * Style options for preset dropdowns
 * Includes 'custom' for legacy/manual color selection
 */
export const STYLE_OPTIONS = [
  'custom',
  'noir-essay',
  'cold-data',
  'modern-creator',
  'academic-paper',
  'documentary',
  'podcast-visual',
  'retro-synthwave',
  'breaking-news',
  'minimalist-white',
  'true-crime',
  'nature-documentary',
] as const;

// Helpers
export {
  getSafeArea,
  resolveTextSizes,
  getMotionFrames,
  getMotionSeconds,
  buildGradient,
  getTextureSettings,
  applyTextCase,
  getFontProps,
  validateStyle,
  mergeStyleOverrides,
  validateSceneContent,
} from './helpers.js';

export type { SceneContent } from './helpers.js';
