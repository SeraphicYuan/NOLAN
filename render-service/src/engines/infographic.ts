// render-service/src/engines/infographic.ts
import * as fs from 'fs';
import * as path from 'path';
import puppeteer from 'puppeteer';
import type { RenderSpec } from '../jobs/types.js';
import { RenderEngine, RenderResult } from './types.js';
import { ensureDir } from './utils.js';
import { EXTENDED_THEMES, INFOGRAPHIC_THEME_PRESETS } from '../themes.js';

type EngineMode = 'auto' | 'antv' | 'svg';

/**
 * Infographic engine with @antv/infographic (browser) and SVG fallback.
 */
export class InfographicEngine implements RenderEngine {
  name = 'infographic';

  async render(spec: RenderSpec, outputDir: string): Promise<RenderResult> {
    console.log('[InfographicEngine] Starting render...');

    const mode = this.getEngineMode(spec);
    const data = spec.data as Record<string, unknown> | undefined;
    const items = this.normalizeItems(data?.items);
    const hasItems = items.length > 0;
    if (!hasItems && mode !== 'svg') {
      console.warn('[InfographicEngine] No items provided; skipping AntV and using SVG fallback.');
    }
    if (mode !== 'svg' && hasItems) {
      const antvResult = await this.renderWithAntv(spec, outputDir);
      if (antvResult.success || mode === 'antv') {
        return antvResult;
      }
      console.warn('[InfographicEngine] AntV failed, falling back to SVG:', antvResult.error);
    }

    return this.renderWithSvg(spec, outputDir);
  }

  private getEngineMode(spec: RenderSpec): EngineMode {
    const specAny = spec as unknown as Record<string, unknown>;
    const specMode = (spec.engine_mode ?? specAny.engineMode ?? specAny.mode) as string | undefined;
    const envMode = process.env.INFOGRAPHIC_ENGINE;
    const raw = (specMode || envMode || 'auto').toLowerCase();
    if (raw === 'antv' || raw === 'svg' || raw === 'auto') {
      return raw as EngineMode;
    }
    return 'auto';
  }

  private async renderWithAntv(spec: RenderSpec, outputDir: string): Promise<RenderResult> {
    try {
      const width = (spec.width as number) || 1920;
      const height = (spec.height as number) || 1080;
      const markup = this.getMarkup(spec);
      const formats = this.resolveOutputFormats(spec);
      console.log('[InfographicEngine] Output formats:', formats.join(', '));

      const svgContent = await this.renderMarkupWithPuppeteer(markup, width, height);

      ensureDir(outputDir);
      const baseName = `infographic_${Date.now()}`;
      const svgPath = path.join(outputDir, `${baseName}.svg`);
      if (formats.includes('svg')) {
        fs.writeFileSync(svgPath, svgContent, 'utf8');
      }
      let pngPath: string | null = null;
      if (formats.includes('png')) {
        const pngBuffer = await this.renderSvgToPng(svgContent, width, height);
        pngPath = path.join(outputDir, `${baseName}.png`);
        fs.writeFileSync(pngPath, pngBuffer);
      }

      const outputPath = formats.includes('svg') ? svgPath : pngPath ?? svgPath;
      console.log('[InfographicEngine] AntV output saved to:', outputPath);

      return {
        success: true,
        outputPath,
      };
    } catch (error) {
      console.error('[InfographicEngine] AntV error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  private async renderMarkupWithPuppeteer(markup: string, width: number, height: number): Promise<string> {
    const bundlePath = this.getInfographicBundlePath();
    const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH || process.env.CHROME_PATH;

    const browser = await puppeteer.launch({
      headless: true,
      executablePath,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    let page: puppeteer.Page | null = null;
    const debugEnabled = process.env.INFOGRAPHIC_DEBUG === '1';
    const consoleMessages: string[] = [];
    try {
      page = await browser.newPage();
      await page.setViewport({ width, height, deviceScaleFactor: 1 });
      if (debugEnabled) {
        page.on('console', (msg) => consoleMessages.push(`[console.${msg.type()}] ${msg.text()}`));
        page.on('pageerror', (err) => {
          const message = err instanceof Error ? err.message : String(err);
          consoleMessages.push(`[pageerror] ${message}`);
        });
      }

      const html = `<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      html, body { margin: 0; padding: 0; background: transparent; }
      #container { width: ${width}px; height: ${height}px; }
    </style>
  </head>
  <body>
    <div id="container"></div>
  </body>
</html>`;

      await page.setContent(html, { waitUntil: 'domcontentloaded' });
      await page.addScriptTag({ path: bundlePath });

      if (debugEnabled) {
        await page.evaluate(() => {
          (window as any).INFOGRAPHIC_DEBUG = true;
        });
      }

      const renderDiagnostics = await page.evaluate(
        async ({ markupText, widthPx, heightPx }) => {
          const container = document.getElementById('container');
          if (!container) {
            throw new Error('Infographic container not found');
          }
          const lib = (window as any).AntVInfographic || (window as any).InfographicLib;
          const Infographic = lib?.Infographic || (window as any).Infographic;
          if (!Infographic) {
            throw new Error('Infographic export not found on window');
          }

          const errors: string[] = [];
          const warnings: string[] = [];
          let parseErrors: string[] = [];
          let parseWarnings: string[] = [];
          let parsedOptionsSummary: Record<string, unknown> | null = null;
          const enableDebug = (window as any).INFOGRAPHIC_DEBUG === true;
          if (lib?.parseSyntax) {
            const parsed = lib.parseSyntax(markupText);
            parseErrors = (parsed?.errors || []).map((e: unknown) =>
              e instanceof Error ? e.message : String(e)
            );
            parseWarnings = (parsed?.warnings || []).map((w: unknown) =>
              w instanceof Error ? w.message : String(w)
            );
            const options = parsed?.options || {};
            const data = options.data || {};
            const templateName = options.template || null;
            if (enableDebug) {
              const templateList =
                typeof lib?.getTemplates === 'function' ? lib.getTemplates() : null;
              const templateKeys = Array.isArray(templateList) ? templateList : [];
              parsedOptionsSummary = {
                hasDesign: Boolean(options.design),
                hasData: Boolean(options.data),
                itemCount: Array.isArray(data.items) ? data.items.length : 0,
                template: templateName,
                templateExists: templateName && typeof lib?.getTemplate === 'function'
                  ? Boolean(lib.getTemplate(templateName))
                  : null,
                templateKeysSample: templateKeys.slice(0, 20),
              };
            }
          }
          const infographic = new Infographic({
            container: '#container',
            width: widthPx,
            height: heightPx,
          });
          if (typeof infographic.on === 'function') {
            infographic.on('error', (err: unknown) => {
              const message = err instanceof Error ? err.message : String(err);
              errors.push(message);
            });
            infographic.on('warning', (warn: unknown) => {
              const message = warn instanceof Error ? warn.message : String(warn);
              warnings.push(message);
            });
          }
          const result = infographic.render(markupText);
          if (result && typeof (result as Promise<unknown>).then === 'function') {
            await result;
          }
          return {
            errors,
            warnings,
            containerHTML: enableDebug ? container.innerHTML.slice(0, 2000) : null,
            parseErrors,
            parseWarnings,
            parsedOptionsSummary,
          };
        },
        { markupText: markup, widthPx: width, heightPx: height }
      );

      if (renderDiagnostics.parseErrors.length || renderDiagnostics.errors.length) {
        const details = [
          renderDiagnostics.parseErrors.length
            ? `Parse errors: ${renderDiagnostics.parseErrors.join('; ')}`
            : null,
          renderDiagnostics.parseWarnings.length
            ? `Parse warnings: ${renderDiagnostics.parseWarnings.join('; ')}`
            : null,
          renderDiagnostics.errors.length
            ? `Render errors: ${renderDiagnostics.errors.join('; ')}`
            : null,
          renderDiagnostics.warnings.length
            ? `Render warnings: ${renderDiagnostics.warnings.join('; ')}`
            : null,
        ]
          .filter(Boolean)
          .join(' | ');
        const summary = renderDiagnostics.parsedOptionsSummary
          ? `Parsed options: ${JSON.stringify(renderDiagnostics.parsedOptionsSummary)}`
          : null;
        const message = [details, summary].filter(Boolean).join(' | ');
        if (message) {
          throw new Error(message);
        }
      }

      await page.waitForSelector('svg', { timeout: 15000 });
      const svg = await page.$eval('svg', (el) => el.outerHTML);

      await page.close();
      return svg;
    } catch (error) {
      const debugDetails: string[] = [];
      if (debugEnabled && consoleMessages.length) {
        debugDetails.push(`Console:\n${consoleMessages.join('\n')}`);
      }
      if (page && debugEnabled) {
        try {
          const debugSnapshot = await page.evaluate(() => {
            const container = document.getElementById('container');
            const svg = document.querySelector('svg');
            const lib = (window as any).AntVInfographic || (window as any).InfographicLib;
            return {
              hasContainer: Boolean(container),
              containerChildren: container ? container.children.length : 0,
              containerHTML: container ? container.innerHTML.slice(0, 2000) : null,
              hasSvg: Boolean(svg),
              bodyHTML: document.body.innerHTML.slice(0, 2000),
              libKeys: lib ? Object.keys(lib) : [],
            };
          });
          debugDetails.push(`Snapshot:\n${JSON.stringify(debugSnapshot, null, 2)}`);
        } catch {
          // ignore debug extraction failures
        }
      }
      const detailText = debugDetails.length ? `\n${debugDetails.join('\n\n')}` : '';
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`${message}${detailText}`);
    } finally {
      await browser.close();
    }
  }

  private getInfographicBundlePath(): string {
    const bundlePath = path.join(
      process.cwd(),
      'node_modules',
      '@antv',
      'infographic',
      'dist',
      'infographic.min.js'
    );

    if (!fs.existsSync(bundlePath)) {
      throw new Error('Infographic bundle not found. Run npm install in render-service.');
    }

    return bundlePath;
  }

  private getMarkup(spec: RenderSpec): string {
    if (typeof spec.markup === 'string' && spec.markup.trim()) {
      return spec.markup;
    }
    return this.buildMarkup(spec);
  }

  private buildMarkup(spec: RenderSpec): string {
    const template = this.resolveTemplate(spec);
    const data = (spec.data as Record<string, unknown>) || {};
    const title = (data.title as string) || '';
    const theme = this.resolveThemeName(spec, data);
    const themeConfig = this.resolveThemeConfig(spec, data);
    const items = this.prepareItemsForTemplate(template, this.normalizeItems(data.items));

    let markup = `infographic ${template}\n`;
    if (themeConfig || (theme && theme !== 'default')) {
      markup += this.buildThemeMarkup(theme, themeConfig);
    }
    markup += 'data\n';

    if (title) {
      markup += `  title ${this.normalizeText(title)}\n`;
    }

    if (items.length) {
      markup += '  items\n';
      for (const item of items) {
        if (item.label) {
          markup += `    - label ${this.normalizeText(item.label)}\n`;
        } else {
          markup += '    -\n';
        }
        if (item.desc) {
          markup += `      desc ${this.normalizeText(item.desc)}\n`;
        }
        if (item.value !== undefined) {
          markup += `      value ${this.normalizeText(String(item.value))}\n`;
        }
        if (item.children && item.children.length) {
          markup += '      children\n';
          for (const child of item.children) {
            if (child.label) {
              markup += `        - label ${this.normalizeText(child.label)}\n`;
            } else {
              markup += '        -\n';
            }
            if (child.desc) {
              markup += `          desc ${this.normalizeText(child.desc)}\n`;
            }
            if (child.value !== undefined) {
              markup += `          value ${this.normalizeText(String(child.value))}\n`;
            }
          }
        }
      }
    }

    return markup;
  }

  private resolveOutputFormats(spec: RenderSpec): string[] {
    const data = (spec.data as Record<string, unknown>) || {};
    const specAny = spec as unknown as Record<string, unknown>;
    const raw =
      (Array.isArray(data.output_formats) ? data.output_formats : null) ??
      (Array.isArray(specAny.output_formats) ? specAny.output_formats : null);
    const exportPng =
      typeof data.export_png === 'boolean'
        ? data.export_png
        : typeof specAny.export_png === 'boolean'
          ? specAny.export_png
          : false;
    const formats = new Set<string>();
    if (Array.isArray(raw)) {
      for (const entry of raw) {
        if (typeof entry === 'string') {
          formats.add(entry.toLowerCase());
        }
      }
    }
    if (exportPng) {
      formats.add('png');
    }
    if (formats.size === 0) {
      formats.add('svg');
    }
    return Array.from(formats);
  }

  private resolveTemplate(spec: RenderSpec): string {
    const specAny = spec as unknown as Record<string, unknown>;
    const data = (spec.data as Record<string, unknown>) || {};
    const rawTemplate =
      typeof spec.template === 'string'
        ? spec.template
        : typeof specAny.template === 'string'
          ? specAny.template
          : '';
    const normalized = rawTemplate.trim().toLowerCase();
    if (normalized && normalized !== 'auto') {
      return this.resolveAntvTemplate(rawTemplate);
    }
    const inferred = this.inferTemplateFromData(data);
    return this.resolveAntvTemplate(inferred);
  }

  private inferTemplateFromData(data: Record<string, unknown>): string {
    const typeHint =
      typeof data.template_type === 'string'
        ? data.template_type.toLowerCase()
        : typeof data.type === 'string'
          ? data.type.toLowerCase()
          : '';
    if (typeHint.includes('compare') || typeHint.includes('comparison')) {
      return 'comparison';
    }
    if (typeHint.includes('timeline')) {
      return 'timeline';
    }
    const items = this.normalizeItems(data.items);
    if (items.length === 2 && (typeHint.includes('vs') || typeHint.includes('compare'))) {
      return 'comparison';
    }
    const hasDates = Array.isArray(data.items)
      ? data.items.some((item) => {
          if (typeof item === 'object' && item !== null) {
            const record = item as Record<string, unknown>;
            return typeof record.date === 'string' || typeof record.year === 'string';
          }
          return false;
        })
      : false;
    if (hasDates) {
      return 'timeline';
    }
    if (items.length <= 4) {
      return 'steps';
    }
    return 'list';
  }

  private resolveAntvTemplate(template: string): string {
    const normalized = template.trim();
    if (!normalized) {
      return 'list-row-horizontal-icon-arrow';
    }

    const aliasMap: Record<string, string> = {
      steps: 'sequence-steps-simple',
      'sequence-steps-simple': 'sequence-steps-simple',
      list: 'list-row-simple-horizontal-arrow',
      'list-row-simple': 'list-row-simple-horizontal-arrow',
      comparison: 'compare-binary-horizontal-simple-vs',
      timeline: 'sequence-steps-simple',
    };

    return aliasMap[normalized] || normalized;
  }

  private normalizeItems(
    rawItems: unknown
  ): Array<{ label?: string; desc?: string; value?: string | number; children?: Array<{ label?: string; desc?: string; value?: string | number }> }> {
    if (!Array.isArray(rawItems)) {
      return [];
    }

    return rawItems.map((item) => {
      if (typeof item === 'string' || typeof item === 'number') {
        return { label: String(item) };
      }

      if (typeof item === 'object' && item !== null) {
        const obj = item as Record<string, unknown>;
        const children = this.normalizeItems(obj.children);
        return {
          label: typeof obj.label === 'string' ? obj.label : undefined,
          desc:
            typeof obj.desc === 'string'
              ? obj.desc
              : typeof obj.description === 'string'
                ? obj.description
                : undefined,
          value: typeof obj.value === 'string' || typeof obj.value === 'number' ? obj.value : undefined,
          children: children.length ? children : undefined,
        };
      }

      return {};
    });
  }

  private prepareItemsForTemplate(
    template: string,
    items: Array<{ label?: string; desc?: string; value?: string | number; children?: Array<{ label?: string; desc?: string; value?: string | number }> }>
  ): Array<{ label?: string; desc?: string; value?: string | number; children?: Array<{ label?: string; desc?: string; value?: string | number }> }> {
    if (!template.startsWith('compare-')) {
      return items;
    }
    if (items.some((item) => Array.isArray(item.children) && item.children.length)) {
      return items;
    }
    if (items.length === 0) {
      return items;
    }

    const leftChildren: typeof items = [];
    const rightChildren: typeof items = [];
    items.forEach((item, index) => {
      if (index % 2 === 0) {
        leftChildren.push(item);
      } else {
        rightChildren.push(item);
      }
    });

    return [
      {
        label: leftChildren[0]?.label || 'Group A',
        children: leftChildren,
      },
      {
        label: rightChildren[0]?.label || 'Group B',
        children: rightChildren,
      },
    ];
  }

  private getThemeColors(theme: string): { primary: string; secondary: string; text: string; bg: string; accent: string } {
    const t = EXTENDED_THEMES[theme] ?? EXTENDED_THEMES.default;
    return {
      primary: t.primary,
      secondary: t.secondary,
      text: t.text,
      bg: t.background,
      accent: t.accent ?? '#e74c3c',
    };
  }

  private escapeXml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  }

  private normalizeText(text: string): string {
    return text.replace(/\s+/g, ' ').trim();
  }

  private resolveThemeName(spec: RenderSpec, data: Record<string, unknown> | undefined): string {
    const specAny = spec as unknown as Record<string, unknown>;
    const dataRecord = data ?? {};
    const raw =
      typeof spec.theme === 'string'
        ? spec.theme
        : typeof dataRecord.theme === 'string'
          ? dataRecord.theme
          : typeof dataRecord.palette === 'string'
            ? dataRecord.palette
            : typeof specAny.theme === 'string'
              ? specAny.theme
              : '';
    return raw ? raw : 'default';
  }

  private resolveThemeConfig(
    spec: RenderSpec,
    data: Record<string, unknown> | undefined
  ): Record<string, unknown> | null {
    const specAny = spec as unknown as Record<string, unknown>;
    const dataRecord = data ?? {};
    const ref =
      typeof specAny.theme_config_ref === 'string'
        ? specAny.theme_config_ref
        : typeof specAny.themeConfigRef === 'string'
          ? specAny.themeConfigRef
          : typeof dataRecord.theme_config_ref === 'string'
            ? dataRecord.theme_config_ref
            : typeof dataRecord.themeConfigRef === 'string'
              ? dataRecord.themeConfigRef
              : null;
    if (ref && INFOGRAPHIC_THEME_PRESETS[ref]) {
      return INFOGRAPHIC_THEME_PRESETS[ref];
    }
    const raw =
      typeof specAny.theme_config === 'object'
        ? specAny.theme_config
        : typeof specAny.themeConfig === 'object'
          ? specAny.themeConfig
          : typeof dataRecord.theme_config === 'object'
            ? dataRecord.theme_config
            : typeof dataRecord.themeConfig === 'object'
              ? dataRecord.themeConfig
              : null;
    if (!raw || Array.isArray(raw)) {
      return null;
    }
    return raw as Record<string, unknown>;
  }

  private buildThemeMarkup(theme: string, themeConfig: Record<string, unknown> | null): string {
    const lines: string[] = ['theme'];
    if (theme) {
      lines.push(`  type ${this.normalizeText(theme)}`);
    }
    if (themeConfig) {
      this.appendThemeLines(lines, themeConfig, 1);
    }
    return `${lines.join('\n')}\n`;
  }

  private appendThemeLines(lines: string[], value: Record<string, unknown>, depth: number): void {
    const indent = '  '.repeat(depth);
    for (const [key, raw] of Object.entries(value)) {
      if (raw === null || raw === undefined) {
        continue;
      }
      if (Array.isArray(raw)) {
        const list = raw.filter((entry) => entry !== null && entry !== undefined);
        if (!list.length) {
          continue;
        }
        const formatted = list.map((entry) => String(entry)).join(', ');
        lines.push(`${indent}${key} ${formatted}`);
        continue;
      }
      if (typeof raw === 'object') {
        lines.push(`${indent}${key}`);
        this.appendThemeLines(lines, raw as Record<string, unknown>, depth + 1);
        continue;
      }
      lines.push(`${indent}${key} ${this.normalizeText(String(raw))}`);
    }
  }

  private async renderSvgToPng(svgContent: string, width: number, height: number): Promise<Buffer> {
    const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH || process.env.CHROME_PATH;
    const browser = await puppeteer.launch({
      headless: true,
      executablePath,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    try {
      const page = await browser.newPage();
      await page.setViewport({ width, height, deviceScaleFactor: 1 });
      const html = `<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      html, body { margin: 0; padding: 0; background: transparent; }
      svg { width: ${width}px; height: ${height}px; display: block; }
    </style>
  </head>
  <body>
    ${svgContent}
  </body>
</html>`;
      await page.setContent(html, { waitUntil: 'domcontentloaded' });
      const buffer = await page.screenshot({ type: 'png' });
      await page.close();
      return Buffer.isBuffer(buffer) ? buffer : Buffer.from(buffer);
    } finally {
      await browser.close();
    }
  }

  private async renderWithSvg(spec: RenderSpec, outputDir: string): Promise<RenderResult> {
    console.log('[InfographicEngine] Starting SVG fallback render...');

    try {
      const width = (spec.width as number) || 1920;
      const height = (spec.height as number) || 1080;
      const data = spec.data as Record<string, unknown> | undefined;
      const template = this.resolveTemplate(spec);
      const theme = this.resolveThemeName(spec, data);
      const formats = this.resolveOutputFormats(spec);
      console.log('[InfographicEngine] Output formats:', formats.join(', '));

      const colors = this.getThemeColors(theme);
      const items = this.normalizeItems(data?.items);

      let svgContent: string;
      if (items.length === 0) {
        svgContent = this.generateTitleCardSVG(data, width, height, colors);
      } else {
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
            svgContent = this.generateStepsSVG(data, width, height, colors);
        }
      }

      ensureDir(outputDir);
      const baseName = `infographic_${Date.now()}`;
      const svgPath = path.join(outputDir, `${baseName}.svg`);
      if (formats.includes('svg')) {
        fs.writeFileSync(svgPath, svgContent, 'utf8');
      }
      let pngPath: string | null = null;
      if (formats.includes('png')) {
        const pngBuffer = await this.renderSvgToPng(svgContent, width, height);
        pngPath = path.join(outputDir, `${baseName}.png`);
        fs.writeFileSync(pngPath, pngBuffer);
      }
      const outputPath = formats.includes('svg') ? svgPath : pngPath ?? svgPath;

      console.log('[InfographicEngine] SVG output saved to:', outputPath);

      return {
        success: true,
        outputPath,
      };
    } catch (error) {
      console.error('[InfographicEngine] SVG fallback error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
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
    const items = this.normalizeItems(data?.items);
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
    const items = this.normalizeItems(data?.items);
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
    const items = this.normalizeItems(data?.items);
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

  /**
   * Generate a title card for text-only scenes.
   */
  private generateTitleCardSVG(
    data: Record<string, unknown> | undefined,
    width: number,
    height: number,
    colors: { primary: string; secondary: string; text: string; bg: string; accent: string }
  ): string {
    const title = (data?.title as string) || 'Title';
    const fontSize = Math.min(120, Math.max(64, Math.round(width * 0.06)));
    const sublineY = Math.round(height * 0.6);

    return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">
  <defs>
    <linearGradient id="titleGradient" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:${colors.primary};stop-opacity:1" />
      <stop offset="100%" style="stop-color:${colors.secondary};stop-opacity:1" />
    </linearGradient>
  </defs>
  <rect width="${width}" height="${height}" fill="${colors.bg}"/>
  <text x="${width / 2}" y="${height / 2}" font-family="Arial, sans-serif" font-size="${fontSize}"
        font-weight="700" fill="${colors.text}" text-anchor="middle" dominant-baseline="middle">
    ${this.escapeXml(title)}
  </text>
  <line x1="${width * 0.3}" y1="${sublineY}" x2="${width * 0.7}" y2="${sublineY}"
        stroke="url(#titleGradient)" stroke-width="6" stroke-linecap="round" opacity="0.85"/>
</svg>`;
  }
}
