// render-service/src/engines/types.ts
import type { RenderSpec } from '../jobs/types.js';
/**
 * Result from a render operation
 */
export interface RenderResult {
  success: boolean;
  outputPath?: string;
  error?: string;
}

/**
 * Interface for render engines
 * Each engine must implement this interface to be used by the render service
 */
export interface RenderEngine {
  /** Name identifier for the engine */
  name: string;

  /**
   * Render a spec to output
   * @param spec - The specification for what to render
   * @param outputDir - Directory to save output files
   * @returns Promise resolving to RenderResult
   */
  render(spec: RenderSpec, outputDir: string): Promise<RenderResult>;
}
