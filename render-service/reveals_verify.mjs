// Seek-safety + look verifier for the compose.py text-reveal vocabulary.
// For each rv-*.html frame: unwrap the <template> to a standalone page, load it, seek the
// paused timeline to fixed times, screenshot (for eyeballing), and prove DETERMINISM
// (seek t -> hash A; seek 0; seek t -> hash B; A must equal B) — the seek-safety contract.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import puppeteer from 'puppeteer';

// manifest (argv[2]) = {framesDir, snapsDir, ids?, look?, det?} — defaults to the reveals-demo.
const MAN = process.argv[2] ? JSON.parse(fs.readFileSync(process.argv[2], 'utf8')) : {};
const FRAMES = MAN.framesDir || 'D:\\ClaudeProjects\\NOLAN\\render-service\\_lab_hyperframes\\videos\\reveals-demo\\compositions\\frames';
const SNAPS = MAN.snapsDir || 'D:\\ClaudeProjects\\NOLAN\\render-service\\_lab_hyperframes\\videos\\reveals-demo\\snapshots';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
fs.mkdirSync(SNAPS, { recursive: true });

const frames = (MAN.ids ? MAN.ids.map(id => `${id}.html`) : fs.readdirSync(FRAMES).filter(f => f.endsWith('.html')));
const LOOK = MAN.look || [0.9, 2.7];   // in-progress, landed
const DET = MAN.det || 1.0;            // determinism probe time
const hash = b => crypto.createHash('sha256').update(b).digest('hex').slice(0, 12);

function standalone(tplHtml) {
  const inner = tplHtml.replace(/^\s*<template>/, '').replace(/<\/template>\s*$/, '');
  return `<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:#F1F3F2;}</style>
</head><body>${inner}</body></html>`;
}

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'], protocolTimeout: 120000 });
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
// GSAP seek() updates the DOM synchronously; a paused timeline never ticks rAF in headless,
// so settle with a plain paint delay (Node-side), NOT requestAnimationFrame.
const settle = () => new Promise(r => setTimeout(r, 90));

let allDet = true;
for (const file of frames) {
  const id = file.replace('.html', '');
  const html = standalone(fs.readFileSync(path.join(FRAMES, file), 'utf8'));
  await page.setContent(html, { waitUntil: 'load', timeout: 30000 });
  // wait for gsap (CDN) + the frame script to register the timeline
  await page.waitForFunction(fid => !!(window.__timelines && window.__timelines[fid]), { timeout: 20000 }, id)
    .catch(() => {});
  const ok = await page.evaluate(fid => !!(window.__timelines && window.__timelines[fid]), id);
  if (!ok) { console.log(`  ✗ ${id}: window.__timelines['${id}'] MISSING (gsap/script error)`); allDet = false; continue; }

  // seek(tt, false): suppressEvents=false so onUpdate callbacks FIRE (scramble/typewriter/glitch/count-up
  // depend on them, as the real renderer does). Return a primitive — tl.seek() returns the circular timeline.
  const seek = t => page.evaluate((fid, tt) => { window.__timelines[fid].seek(tt, false); return 1; }, id, t);
  const shot = async t => { await seek(t); await settle(); return await page.screenshot({ clip: { x: 0, y: 0, width: 1920, height: 1080 } }); };

  for (const t of LOOK) {
    const buf = await shot(t);
    fs.writeFileSync(path.join(SNAPS, `${id}-at-${t}.png`), buf);
  }
  // determinism: hash at DET, jump away, return, hash again
  const a = hash(await shot(DET));
  await shot(0.0);
  const b = hash(await shot(DET));
  const det = a === b;
  allDet = allDet && det;
  console.log(`  ${det ? '✓' : '✗'} ${id.padEnd(14)} determinism@${DET}s ${a} == ${b} -> ${det ? 'DETERMINISTIC' : 'MISMATCH'}`);
}
await browser.close();
console.log(allDet ? '\nALL DETERMINISTIC (seek-safe) — screenshots in snapshots/' : '\nSOME NON-DETERMINISTIC — investigate');
process.exit(allDet ? 0 : 1);
