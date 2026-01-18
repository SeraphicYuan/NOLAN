import type { EffectPreset, EffectInfo, EffectCategory } from './types.js';
import {
  imagePresets,
  quotePresets,
  chartPresets,
  titlePresets,
  statisticPresets,
  mapPresets,
  textPresets,
  progressPresets,
  countdownPresets,
  transitionPresets,
  timelinePresets,
  annotationPresets,
  comparisonPresets,
  overlayPresets,
} from './presets/index.js';

// All registered effect presets
const allPresets: EffectPreset[] = [
  ...imagePresets,
  ...quotePresets,
  ...chartPresets,
  ...titlePresets,
  ...statisticPresets,
  ...mapPresets,
  ...textPresets,
  ...progressPresets,
  ...countdownPresets,
  ...transitionPresets,
  ...timelinePresets,
  ...annotationPresets,
  ...comparisonPresets,
  ...overlayPresets,
];

// Index by ID for fast lookup
const presetsById: Map<string, EffectPreset> = new Map(
  allPresets.map((preset) => [preset.id, preset])
);

// All available categories
export const categories: EffectCategory[] = [
  'image',
  'quote',
  'statistic',
  'chart',
  'comparison',
  'title',
  'transition',
  'map',
  'data',
  'progress',
  'text',
  'annotation',
  'overlay',
];

/**
 * Get all registered effects as simplified info objects (for API response)
 */
export function getAllEffects(): EffectInfo[] {
  return allPresets.map((preset) => ({
    id: preset.id,
    name: preset.name,
    category: preset.category,
    description: preset.description,
    engine: preset.engine,
    parameters: preset.parameters,
    defaults: preset.defaults,
    preview: preset.preview,
  }));
}

/**
 * Get effects filtered by category
 */
export function getEffectsByCategory(category: EffectCategory): EffectInfo[] {
  return getAllEffects().filter((effect) => effect.category === category);
}

/**
 * Get a specific effect preset by ID
 */
export function getEffectById(id: string): EffectPreset | undefined {
  return presetsById.get(id);
}

/**
 * Check if an effect ID exists
 */
export function hasEffect(id: string): boolean {
  return presetsById.has(id);
}

/**
 * Get effect info (without toEngineData function) by ID
 */
export function getEffectInfo(id: string): EffectInfo | undefined {
  const preset = presetsById.get(id);
  if (!preset) return undefined;

  return {
    id: preset.id,
    name: preset.name,
    category: preset.category,
    description: preset.description,
    engine: preset.engine,
    parameters: preset.parameters,
    defaults: preset.defaults,
    preview: preset.preview,
  };
}

/**
 * Transform effect params to engine-specific data format
 */
export function transformToEngineData(
  effectId: string,
  params: Record<string, unknown>
): { engine: string; data: Record<string, unknown> } | null {
  const preset = presetsById.get(effectId);
  if (!preset) return null;

  // Merge defaults with provided params
  const mergedParams = { ...preset.defaults, ...params };

  return {
    engine: preset.engine,
    data: preset.toEngineData(mergedParams),
  };
}

/**
 * Get a summary of effects for LLM context (condensed format)
 */
export function getEffectsSummaryForLLM(): string {
  const lines: string[] = ['Available motion effects:'];

  const byCategory = new Map<EffectCategory, EffectInfo[]>();
  for (const effect of getAllEffects()) {
    const list = byCategory.get(effect.category) || [];
    list.push(effect);
    byCategory.set(effect.category, list);
  }

  for (const [category, effects] of byCategory) {
    lines.push('');
    lines.push(`${category.toUpperCase()} EFFECTS:`);
    for (const effect of effects) {
      lines.push(`- ${effect.id}: ${effect.description}`);
    }
  }

  return lines.join('\n');
}

// Export types
export type { EffectPreset, EffectInfo, EffectCategory, ParameterDef } from './types.js';
export type { ParameterType, EffectEngine, EffectRenderRequest } from './types.js';
