// render-service/src/engines/infographic.ts
import { JSDOM } from 'jsdom';
import * as fs from 'fs';
import * as path from 'path';
import { RenderEngine, RenderResult } from './types.js';

/**
 * Infographic rendering engine using @antv/infographic with JSDOM
 * Renders infographic specifications to SVG files
 */
export class InfographicEngine implements RenderEngine {
  name = 'infographic';

  async render(spec: Record<string, unknown>, outputDir: string): Promise<RenderResult> {
    try {
      // Setup JSDOM environment with a container for the infographic
      const dom = new JSDOM('<!DOCTYPE html><html><body><div id="container"></div></body></html>', {
        pretendToBeVisual: true,
      });

      // Store original globals to restore later
      const originalWindow = (global as Record<string, unknown>).window;
      const originalDocument = (global as Record<string, unknown>).document;

      // Set globals for @antv/infographic (requires browser-like environment)
      (global as Record<string, unknown>).window = dom.window;
      (global as Record<string, unknown>).document = dom.window.document;

      try {
        // Dynamic import after setting up globals
        const { Infographic } = await import('@antv/infographic');

        const container = dom.window.document.getElementById('container');

        if (!container) {
          throw new Error('Container element not found');
        }

        // Create Infographic instance with dimensions from spec
        const infographic = new Infographic({
          container: container,
          width: (spec.width as number) || 1920,
          height: (spec.height as number) || 1080,
        });

        // Build infographic markup from spec and render
        const markup = this.buildMarkup(spec);
        infographic.render(markup);

        // Extract SVG from container
        const svg = container.querySelector('svg');
        if (!svg) {
          throw new Error('No SVG generated');
        }

        const svgString = svg.outerHTML;

        // Ensure output directory exists
        fs.mkdirSync(outputDir, { recursive: true });

        // Save SVG file (later phases will convert to MP4)
        const outputPath = path.join(outputDir, `infographic_${Date.now()}.svg`);
        fs.writeFileSync(outputPath, svgString, 'utf8');

        // Cleanup
        infographic.destroy();
        dom.window.close();

        return {
          success: true,
          outputPath,
        };
      } finally {
        // Restore original globals
        if (originalWindow !== undefined) {
          (global as Record<string, unknown>).window = originalWindow;
        } else {
          delete (global as Record<string, unknown>).window;
        }
        if (originalDocument !== undefined) {
          (global as Record<string, unknown>).document = originalDocument;
        } else {
          delete (global as Record<string, unknown>).document;
        }
      }
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  /**
   * Build @antv/infographic markup DSL from spec
   * The library uses a custom DSL format for defining infographics
   */
  private buildMarkup(spec: Record<string, unknown>): string {
    const template = (spec.template as string) || 'list-row-simple';
    const data = spec.data as Record<string, unknown> | undefined;

    // Build infographic DSL markup
    let markup = `infographic ${template}\n`;

    // Add data section if provided
    if (data) {
      markup += 'data\n';

      // Handle items array (common in list-based templates)
      if (data.items && Array.isArray(data.items)) {
        markup += '  items\n';
        for (const item of data.items) {
          if (typeof item === 'object' && item !== null) {
            const obj = item as Record<string, unknown>;
            markup += `    - label ${obj.label || ''}\n`;
            if (obj.desc) markup += `      desc ${obj.desc}\n`;
            if (obj.value !== undefined) markup += `      value ${obj.value}\n`;
            if (obj.icon) markup += `      icon ${obj.icon}\n`;
          } else {
            markup += `    - label ${item}\n`;
          }
        }
      }

      // Handle title if provided
      if (data.title) {
        markup += `  title ${data.title}\n`;
      }

      // Handle subtitle if provided
      if (data.subtitle) {
        markup += `  subtitle ${data.subtitle}\n`;
      }
    }

    // Add theme if specified
    if (spec.theme) {
      markup += `theme ${spec.theme}\n`;
    }

    return markup;
  }
}
