/**
 * Contact sheet: every rendered SVG on one page, screenshotted, so the verdict comes from LOOKING
 * rather than from byte counts. NOLAN's rule — after rendering anything, extract frames and look.
 *
 *   node sheet.mjs <dir-of-svgs> <out.png>
 *
 * Puppeteer is resolved from render-service (it already ships a downloaded Chromium); the SVGs use
 * <foreignObject> for text, so only a real browser lays them out correctly — an SVG rasteriser
 * like resvg would silently drop every label.
 */
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join, basename, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire('D:/ClaudeProjects/NOLAN/render-service/');
const puppeteer = require('puppeteer');

const [, , dir, outPath] = process.argv;
if (!dir || !outPath) {
  console.error('usage: node sheet.mjs <dir-of-svgs> <out.png>');
  process.exit(2);
}

const files = readdirSync(dir).filter((f) => f.endsWith('.svg')).sort();
if (!files.length) {
  console.error(`no SVGs in ${dir}`);
  process.exit(1);
}

const cards = files.map((f) => {
  // Strip the XML preamble; it is illegal inside an HTML document and would render as text.
  const svg = readFileSync(join(dir, f), 'utf-8').replace(/^[\s\S]*?(?=<svg)/, '');
  return `<figure><figcaption>${basename(f, '.svg')}</figcaption><div class="frame">${svg}</div></figure>`;
});

const html = `<!doctype html><meta charset="utf-8">
<style>
  body { margin:0; padding:24px; background:#3a3a3a; font:13px/1.4 ui-monospace,monospace; }
  .grid { display:grid; grid-template-columns:repeat(2, 1fr); gap:20px; }
  figure { margin:0; }
  figcaption { color:#ddd; padding:4px 0; }
  /* Each card gets a WHITE bed so a theme that paints no background is visibly distinguishable
     from one that paints its shell — an infographic that vanishes on light is a real defect. */
  .frame { background:#fff; padding:10px; display:flex; justify-content:center; align-items:center;
           min-height:220px; }
  .frame svg { max-width:100%; height:auto; }
</style>
<div class="grid">${cards.join('\n')}</div>`;

const tmp = resolve(dir, '_sheet.html');
writeFileSync(tmp, html, 'utf-8');

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1700, height: 1200, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(tmp).href, { waitUntil: 'networkidle0' });
  await page.screenshot({ path: outPath, fullPage: true });
  console.error(`ok ${outPath} (${files.length} cards)`);
} finally {
  await browser.close();
}
