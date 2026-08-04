/**
 * Compose a NOLAN frame, SEEK its paused timeline, and freeze the DOM into self-contained HTML.
 *
 *   node snapshot.mjs <frame.html> <frame-id> <seek-seconds> <out.html>
 *
 * Why a seek and not a screenshot at t=0: a NOLAN block's timeline is created PAUSED and almost
 * every block animates its content in from nothing, so t=0 is BLANK. Publishing blocks naively
 * yields a gallery of empty cards. Seeking to a moment after the reveals have landed is the only
 * way a card shows the block as designed.
 *
 * GSAP writes its tweened values as inline styles, so once seeked the DOM alone carries the visual
 * state — the scripts can be dropped and the result is static, self-contained, and lintable.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire('D:/ClaudeProjects/NOLAN/render-service/');
const puppeteer = require('puppeteer');

const [, , framePath, frameId, seekStr, outPath] = process.argv;
if (!framePath || !frameId || !seekStr || !outPath) {
  console.error('usage: node snapshot.mjs <frame.html> <frame-id> <seek-seconds> <out.html>');
  process.exit(2);
}
const seek = Number(seekStr);

// compose_frame returns a <template>…</template>; unwrap it so the browser actually renders it.
const composed = readFileSync(framePath, 'utf-8')
  .replace(/^\s*<template>/, '').replace(/<\/template>\s*$/, '');

const page_html = `<!doctype html><meta charset="utf-8">
<style>html,body{margin:0;background:#fff}</style>
${composed}`;

const tmp = resolve(outPath + '.live.html');
writeFileSync(tmp, page_html, 'utf-8');

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(tmp).href, { waitUntil: 'networkidle0' });

  const seeked = await page.evaluate((fid, t) => {
    const tl = window.__timelines && window.__timelines[fid];
    if (!tl) return { ok: false, why: 'no timeline ' + fid };
    // seek(t) defaults to suppressEvents:TRUE, which skips onUpdate callbacks. NOLAN's count-up
    // writes its digits from an onUpdate (compose.py:1488 —
    //   tl.fromTo(st,{v:from},{v:to,onUpdate:function(){el.textContent=f(st.v);}})
    // ), so a default seek renders the number as its START value. The first run of this harness
    // published a `stat` card reading "0" instead of "51". Pass suppressEvents:false.
    tl.seek(t, false);
    return { ok: true, duration: tl.duration() };
  }, frameId, seek);

  if (!seeked.ok) {
    console.error(`seek failed: ${seeked.why}`);
    process.exit(1);
  }
  if (seek > seeked.duration) {
    console.error(`seek ${seek}s is past the timeline (${seeked.duration}s) — the card would show the END state`);
    process.exit(1);
  }

  // Freeze: keep the theme <style> and the seeked #root, drop every script.
  const frozen = await page.evaluate(() => {
    document.querySelectorAll('script').forEach((s) => s.remove());
    const style = Array.from(document.querySelectorAll('style')).map((s) => s.textContent).join('\n');
    const root = document.getElementById('root');
    return { style, root: root ? root.outerHTML : null };
  });

  if (!frozen.root) {
    console.error('no #root after seek — nothing to publish');
    process.exit(1);
  }

  const ink = await page.evaluate(() => {
    // Cheap emptiness check: a card that is blank is worse than no card, and nothing else in the
    // pipeline can see it (hf-qa looks for a STUCK frame, the temporal gate for absent MOTION).
    const r = document.getElementById('root');
    return r ? r.innerText.replace(/\s+/g, '').length : 0;
  });
  if (ink < 3) {
    console.error(`frame is visually EMPTY at t=${seek}s (innerText ${ink} chars) — pick a later seek`);
    process.exit(1);
  }

  writeFileSync(outPath,
    `<!doctype html><meta charset="utf-8">\n<style>\nhtml,body{margin:0}\n${frozen.style}\n</style>\n${frozen.root}\n`,
    'utf-8');
  console.error(`ok ${outPath} (seek ${seek}s of ${seeked.duration}s, ${ink} chars of ink)`);
} finally {
  await browser.close();
}
