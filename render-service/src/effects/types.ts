// Parameter types for effect configuration
export type ParameterType =
  | 'string'    // TextInput - single line text
  | 'text'      // TextArea - multiline text
  | 'number'    // NumberInput - numeric value
  | 'duration'  // DurationSlider - time in seconds (1-30)
  | 'color'     // ColorPicker - hex color value
  | 'image'     // ImageUpload - file path
  | 'select'    // SelectDropdown - one of predefined options
  | 'boolean'   // Checkbox - true/false
  | 'items';    // ItemsList - array of objects

// Definition of a single parameter
export interface ParameterDef {
  name: string;
  type: ParameterType;
  label: string;
  description?: string;
  required: boolean;
  default?: unknown;
  options?: string[];           // For 'select' type
  itemSchema?: ParameterDef[];  // For 'items' type - defines structure of each item
  min?: number;                 // For 'number' and 'duration'
  max?: number;
  step?: number;                // For 'number'
}

// Supported rendering engines
export type EffectEngine = 'remotion' | 'motion-canvas' | 'infographic';

// Effect categories for organization
export type EffectCategory =
  | 'image'
  | 'quote'
  | 'statistic'
  | 'chart'
  | 'comparison'
  | 'title'
  | 'transition'
  | 'map'
  | 'data'
  | 'progress'
  | 'text'
  | 'annotation'
  | 'overlay';

// An effect preset definition
export interface EffectPreset {
  id: string;                          // Unique identifier: "image-ken-burns"
  name: string;                        // Human readable: "Ken Burns"
  category: EffectCategory;
  description: string;                 // For UI and LLM context
  engine: EffectEngine;
  parameters: ParameterDef[];
  defaults: Record<string, unknown>;
  preview?: string;                    // Path to preview media

  // Transform user params to engine-specific data format
  toEngineData: (params: Record<string, unknown>) => Record<string, unknown>;
}

// Simplified effect info for API responses
export interface EffectInfo {
  id: string;
  name: string;
  category: EffectCategory;
  description: string;
  engine: EffectEngine;
  parameters: ParameterDef[];
  defaults: Record<string, unknown>;
  preview?: string;
}

// Request to render using an effect
export interface EffectRenderRequest {
  effect: string;                      // Effect ID
  params: Record<string, unknown>;     // User-provided parameters
}
