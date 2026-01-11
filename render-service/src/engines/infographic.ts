// render-service/src/engines/infographic.ts
import * as fs from 'fs';
import * as path from 'path';
import { RenderEngine, RenderResult } from './types.js';

/**
 * Simple SVG-based infographic engine
 * Generates infographics using native SVG templates
 * Note: @antv/infographic had browser-only limitations, so we use direct SVG generation
 */
export class InfographicEngine implements RenderEngine {
  name = 'infographic';

  async render(spec: Record<string, unknown>, outputDir: string): Promise<RenderResult> {
    console.log('[InfographicEngine] Starting SVG render...');

    try {
      const width = (spec.width as number) || 1920;
      const height = (spec.height as number) || 1080;
      const template = (spec.template as string) || 'steps';
      const data = spec.data as Record<string, unknown> | undefined;
      const theme = (spec.theme as string) || 'default';

      // Get theme colors
      const colors = this.getThemeColors(theme);

      // Generate SVG based on template
      let svgContent: string;
      switch (template) {
        case 'steps':
        case 'sequence-steps-simple':
          svgContent = this.generateStepsSVG(data, width, height, colors);
          break;
        case 'list':
        case 'list-row-simple':
          svgContent = this.generateListSVG(data, width, height, colors);
          break;
        case 'comparison':
          svgContent = this.generateComparisonSVG(data, width, height, colors);
          break;
        default:
          // Default to steps template
          svgContent = this.generateStepsSVG(data, width, height, colors);
      }

      // Ensure output directory exists
      fs.mkdirSync(outputDir, { recursive: true });

      // Save SVG file
      const outputPath = path.join(outputDir, `infographic_${Date.now()}.svg`);
      fs.writeFileSync(outputPath, svgContent, 'utf8');

      console.log('[InfographicEngine] SVG saved to:', outputPath);

      return {
        success: true,
        outputPath,
      };
    } catch (error) {
      console.error('[InfographicEngine] Error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  private getThemeColors(theme: string): { primary: string; secondary: string; text: string; bg: string; accent: string } {
    const themes: Record<string, { primary: string; secondary: string; text: string; bg: string; accent: string }> = {
      default: {
        primary: '#3498db',
        secondary: '#2ecc71',
        text: '#2c3e50',
        bg: '#ffffff',
        accent: '#e74c3c',
      },
      dark: {
        primary: '#9b59b6',
        secondary: '#1abc9c',
        text: '#ecf0f1',
        bg: '#2c3e50',
        accent: '#e74c3c',
      },
      warm: {
        primary: '#e67e22',
        secondary: '#f39c12',
        text: '#34495e',
        bg: '#fdf6e3',
        accent: '#c0392b',
      },
      cool: {
        primary: '#2980b9',
        secondary: '#27ae60',
        text: '#2c3e50',
        bg: '#ecf0f1',
        accent: '#8e44ad',
      },
    };
    return themes[theme] || themes.default;
  }

  private escapeXml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  }

  /**
   * Generate a steps/sequence infographic
   */
  private generateStepsSVG(
    data: Record<string, unknown> | undefined,
    width: number,
    height: number,
    colors: { primary: string; secondary: string; text: string; bg: string; accent: string }
  ): string {
    const items = (data?.items as Array<{ label?: string; desc?: string }>) || [];
    const title = (data?.title as string) || '';

    const padding = 60;
    const titleHeight = title ? 80 : 0;
    const availableWidth = width - padding * 2;
    const availableHeight = height - padding * 2 - titleHeight;

    const stepWidth = items.length > 0 ? availableWidth / items.length : availableWidth;
    const circleRadius = Math.min(40, stepWidth / 4);

    let svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">
  <defs>
    <linearGradient id="stepGradient" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:${colors.primary};stop-opacity:1" />
      <stop offset="100%" style="stop-color:${colors.secondary};stop-opacity:1" />
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="2" dy="2" stdDeviation="3" flood-opacity="0.3"/>
    </filter>
  </defs>

  <!-- Background -->
  <rect width="${width}" height="${height}" fill="${colors.bg}"/>
`;

    // Title
    if (title) {
      svg += `
  <!-- Title -->
  <text x="${width / 2}" y="${padding + 30}" font-family="Arial, sans-serif" font-size="32"
        font-weight="bold" fill="${colors.text}" text-anchor="middle">${this.escapeXml(title)}</text>
`;
    }

    const startY = padding + titleHeight + availableHeight / 2;

    // Connection line
    if (items.length > 1) {
      const lineStartX = padding + stepWidth / 2;
      const lineEndX = width - padding - stepWidth / 2;
      svg += `
  <!-- Connection Line -->
  <line x1="${lineStartX}" y1="${startY}" x2="${lineEndX}" y2="${startY}"
        stroke="url(#stepGradient)" stroke-width="4" stroke-dasharray="10,5"/>
`;
    }

    // Steps
    items.forEach((item, index) => {
      const x = padding + stepWidth * index + stepWidth / 2;
      const stepColor = index % 2 === 0 ? colors.primary : colors.secondary;

      svg += `
  <!-- Step ${index + 1} -->
  <g transform="translate(${x}, ${startY})">
    <circle r="${circleRadius}" fill="${stepColor}" filter="url(#shadow)"/>
    <text y="5" font-family="Arial, sans-serif" font-size="24" font-weight="bold"
          fill="white" text-anchor="middle">${index + 1}</text>
  </g>
  <text x="${x}" y="${startY + circleRadius + 30}" font-family="Arial, sans-serif"
        font-size="18" font-weight="bold" fill="${colors.text}" text-anchor="middle">
    ${this.escapeXml(item.label || `Step ${index + 1}`)}
  </text>
`;
      if (item.desc) {
        svg += `
  <text x="${x}" y="${startY + circleRadius + 55}" font-family="Arial, sans-serif"
        font-size="14" fill="${colors.text}" text-anchor="middle" opacity="0.8">
    ${this.escapeXml(item.desc)}
  </text>
`;
      }
    });

    svg += `
</svg>`;

    return svg;
  }

  /**
   * Generate a list infographic
   */
  private generateListSVG(
    data: Record<string, unknown> | undefined,
    width: number,
    height: number,
    colors: { primary: string; secondary: string; text: string; bg: string; accent: string }
  ): string {
    const items = (data?.items as Array<{ label?: string; desc?: string; value?: string | number }>) || [];
    const title = (data?.title as string) || '';

    const padding = 60;
    const titleHeight = title ? 80 : 0;
    const itemHeight = items.length > 0 ? Math.min(80, (height - padding * 2 - titleHeight) / items.length) : 80;

    let svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">
  <defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="2" dy="2" stdDeviation="3" flood-opacity="0.2"/>
    </filter>
  </defs>

  <!-- Background -->
  <rect width="${width}" height="${height}" fill="${colors.bg}"/>
`;

    // Title
    if (title) {
      svg += `
  <!-- Title -->
  <text x="${padding}" y="${padding + 30}" font-family="Arial, sans-serif" font-size="32"
        font-weight="bold" fill="${colors.text}">${this.escapeXml(title)}</text>
`;
    }

    // List items
    items.forEach((item, index) => {
      const y = padding + titleHeight + index * itemHeight + 20;
      const itemColor = index % 2 === 0 ? colors.primary : colors.secondary;

      svg += `
  <!-- Item ${index + 1} -->
  <g transform="translate(${padding}, ${y})">
    <rect x="0" y="0" width="${width - padding * 2}" height="${itemHeight - 10}"
          rx="8" fill="${colors.bg}" stroke="${itemColor}" stroke-width="2" filter="url(#shadow)"/>
    <circle cx="30" cy="${(itemHeight - 10) / 2}" r="15" fill="${itemColor}"/>
    <text x="30" y="${(itemHeight - 10) / 2 + 5}" font-family="Arial, sans-serif" font-size="14"
          font-weight="bold" fill="white" text-anchor="middle">${index + 1}</text>
    <text x="60" y="${(itemHeight - 10) / 2 - 5}" font-family="Arial, sans-serif" font-size="18"
          font-weight="bold" fill="${colors.text}">${this.escapeXml(item.label || `Item ${index + 1}`)}</text>
`;
      if (item.desc) {
        svg += `
    <text x="60" y="${(itemHeight - 10) / 2 + 15}" font-family="Arial, sans-serif" font-size="14"
          fill="${colors.text}" opacity="0.7">${this.escapeXml(item.desc)}</text>
`;
      }
      if (item.value !== undefined) {
        svg += `
    <text x="${width - padding * 2 - 20}" y="${(itemHeight - 10) / 2 + 5}" font-family="Arial, sans-serif"
          font-size="20" font-weight="bold" fill="${itemColor}" text-anchor="end">${this.escapeXml(String(item.value))}</text>
`;
      }
      svg += `
  </g>
`;
    });

    svg += `
</svg>`;

    return svg;
  }

  /**
   * Generate a comparison infographic
   */
  private generateComparisonSVG(
    data: Record<string, unknown> | undefined,
    width: number,
    height: number,
    colors: { primary: string; secondary: string; text: string; bg: string; accent: string }
  ): string {
    const items = (data?.items as Array<{ label?: string; desc?: string }>) || [];
    const title = (data?.title as string) || 'Comparison';

    const padding = 60;
    const columnWidth = (width - padding * 3) / 2;

    let svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">
  <defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="2" dy="2" stdDeviation="3" flood-opacity="0.2"/>
    </filter>
  </defs>

  <!-- Background -->
  <rect width="${width}" height="${height}" fill="${colors.bg}"/>

  <!-- Title -->
  <text x="${width / 2}" y="${padding + 30}" font-family="Arial, sans-serif" font-size="32"
        font-weight="bold" fill="${colors.text}" text-anchor="middle">${this.escapeXml(title)}</text>

  <!-- Left Column -->
  <rect x="${padding}" y="${padding + 60}" width="${columnWidth}" height="${height - padding * 2 - 60}"
        rx="12" fill="${colors.primary}" opacity="0.1" filter="url(#shadow)"/>
  <text x="${padding + columnWidth / 2}" y="${padding + 100}" font-family="Arial, sans-serif" font-size="24"
        font-weight="bold" fill="${colors.primary}" text-anchor="middle">${items[0]?.label || 'Option A'}</text>

  <!-- Right Column -->
  <rect x="${width - padding - columnWidth}" y="${padding + 60}" width="${columnWidth}" height="${height - padding * 2 - 60}"
        rx="12" fill="${colors.secondary}" opacity="0.1" filter="url(#shadow)"/>
  <text x="${width - padding - columnWidth / 2}" y="${padding + 100}" font-family="Arial, sans-serif" font-size="24"
        font-weight="bold" fill="${colors.secondary}" text-anchor="middle">${items[1]?.label || 'Option B'}</text>

  <!-- VS Badge -->
  <circle cx="${width / 2}" cy="${height / 2}" r="40" fill="${colors.accent}"/>
  <text x="${width / 2}" y="${height / 2 + 8}" font-family="Arial, sans-serif" font-size="24"
        font-weight="bold" fill="white" text-anchor="middle">VS</text>
</svg>`;

    return svg;
  }
}
