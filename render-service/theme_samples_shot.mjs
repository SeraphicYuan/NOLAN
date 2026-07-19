// Screenshot every mounted theme×archetype sample (from themes/_samples/manifest.json) at its
// finished state. Static seeds have no timeline; seeking is a no-op but kept for future animated seeds.
// Usage: node theme_samples_shot.mjs [samples_dir]   (default ../themes/_samples)
import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';

const DIR = process.argv[2] || path.resolve('..', 'themes', '_samples');
const manifest = JSON.parse(fs.readFileSync(path.join(DIR, 'manifest.json'), 'utf-8'));

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox', '--disable-setuid-sandbox'] });
let ok = 0, bad = 0;
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  for (const cell of manifest) {
    try {
      await page.goto('file://' + path.join(DIR, cell.html).replace(/\\/g, '/'), { waitUntil: 'load', timeout: 20000 });
      await page.waitForFunction(() => window.__timelines && Object.keys(window.__timelines).length > 0, { timeout: 2500 }).catch(() => {});
      await page.evaluate(async () => { if (document.fonts && document.fonts.ready) await document.fonts.ready; });
      await new Promise((r) => setTimeout(r, 220));
      await page.evaluate(() => { for (const k in (window.__timelines || {})) { const tl = window.__timelines[k]; tl.pause(); tl.totalTime(tl.totalDuration()); } });
      await new Promise((r) => setTimeout(r, 120));
      const stage = await page.$('#stage');
      await stage.screenshot({ path: path.join(DIR, cell.png) });
      ok++;
    } catch (e) {
      bad++;
      console.log(`FAIL ${cell.png}: ${String(e).slice(0, 80)}`);
    }
  }
} finally { await browser.close(); }
console.log(`shot ${ok} cells${bad ? `, ${bad} failed` : ''}`);
