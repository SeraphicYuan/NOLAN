// Motion-demo renderer: seek each composed frame timeline frame-by-frame, screenshot, encode to MP4.
// Reuses the standalone-unwrap approach (no hyperframes runtime needed) with seek(t,false) so
// onUpdate reveals fire. Concatenates the given frame ids into ONE reel for eyeballing.
//   node render_reel.mjs <manifest.json>   where manifest = {framesDir, out, ids:[...], fps?}
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import puppeteer from 'puppeteer';

const MAN = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const FRAMESDIR = MAN.framesDir, OUTMP4 = MAN.out;
const FPS = parseInt(MAN.fps || 30, 10);
const IDS = MAN.ids.map(s => String(s).trim()).filter(Boolean);
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const FFMPEG = 'D:\\env\\nolan\\Lib\\site-packages\\imageio_ffmpeg\\binaries\\ffmpeg-win-x86_64-v7.1.exe';
const TMP = path.join(path.dirname(OUTMP4), '_frames');
fs.rmSync(TMP, { recursive: true, force: true });
fs.mkdirSync(TMP, { recursive: true });
fs.mkdirSync(path.dirname(OUTMP4), { recursive: true });

const standalone = tpl => {
  const inner = tpl.replace(/^\s*<template>/, '').replace(/<\/template>\s*$/, '');
  return `<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:#F1F3F2;}</style>
</head><body>${inner}</body></html>`;
};

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'], protocolTimeout: 120000 });
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
const paint = () => new Promise(r => setTimeout(r, 25));

let g = 0;
for (const id of IDS) {
  const file = path.join(FRAMESDIR, `${id}.html`);
  if (!fs.existsSync(file)) { console.log(`  ! missing ${id}.html — skipped`); continue; }
  await page.setContent(standalone(fs.readFileSync(file, 'utf8')), { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction(fid => !!(window.__timelines && window.__timelines[fid]), { timeout: 20000 }, id).catch(() => {});
  const dur = await page.evaluate(fid => (window.__timelines[fid] ? window.__timelines[fid].duration() : 3), id);
  const n = Math.max(1, Math.round(dur * FPS));
  for (let f = 0; f < n; f++) {
    await page.evaluate((fid, tt) => { window.__timelines[fid].seek(tt, false); return 1; }, id, f / FPS);
    await paint();
    await page.screenshot({ path: path.join(TMP, `frame-${String(g).padStart(5, '0')}.png`), clip: { x: 0, y: 0, width: 1920, height: 1080 } });
    g++;
  }
  console.log(`  rendered ${id}: ${n} frames (${dur.toFixed(1)}s)`);
}
await browser.close();

console.log(`encoding ${g} frames -> ${OUTMP4}`);
const r = spawnSync(FFMPEG, ['-y', '-framerate', String(FPS), '-i', path.join(TMP, 'frame-%05d.png'),
  '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-movflags', '+faststart', OUTMP4],
  { stdio: ['ignore', 'ignore', 'inherit'] });
fs.rmSync(TMP, { recursive: true, force: true });
console.log(r.status === 0 ? `OK -> ${OUTMP4}` : `FFMPEG FAILED (${r.status})`);
process.exit(r.status === 0 ? 0 : 1);
