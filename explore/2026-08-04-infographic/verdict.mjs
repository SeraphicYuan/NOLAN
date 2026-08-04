/**
 * Test D verdict — score a composed frame against the six measurable criteria.
 *
 *   node verdict.mjs <frame.html> <frame-id> <narration.json> [out.json]
 *
 * Measurement is DOM-based, not pixel-based: at each sampled time the timeline is seeked and every
 * subject's computed opacity and bounding rect are read. That is exact where a pixel diff is a
 * guess, and it tells us WHICH subject was late rather than only that something was.
 *
 * The checks:
 *   1 anchor      each subject's first visible frame within +/-150ms of its spoken noun
 *   2 no-exit     visible ink is monotonically non-decreasing (nothing animates out)
 *   3 keep-out    nothing visible below 83% of frame height (the caption band)
 *   4 never-blank ink is above a floor from the first entry onward
 *   5 all-present every subject is visible at the end
 *   6 seek-safe   two independent passes over the same times agree exactly
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire('D:/ClaudeProjects/NOLAN/render-service/');
const puppeteer = require('puppeteer');

const [, , framePath, frameId, narrationPath, outPath] = process.argv;
if (!framePath || !frameId || !narrationPath) {
  console.error('usage: node verdict.mjs <frame.html> <frame-id> <narration.json> [out.json]');
  process.exit(2);
}

const narration = JSON.parse(readFileSync(narrationPath, 'utf-8'));
const anchors = narration.anchors;                 // {assetStem: {noun,start,end}}
const DUR = narration.duration_s;
const TOL = 0.15;                                   // +/-150ms
// Sampling must be FINER than the tolerance or the check cannot pass by construction. The first
// run used 40 samples over 9.04s = 232ms resolution and failed every anchor by +0.16..0.31s — a
// harness artefact, not a block defect. 0.04s resolution puts quantisation well under the bar.
const STEP = 0.04;
const KEEPOUT = 0.83;
// "Visible" means the entry has BEGUN, not that it is half-done. Waiting for opacity>0.5 measures
// the midpoint of a ~0.4s entry tween and reports every subject as systematically late.
const VISIBLE = 0.02;

const composed = readFileSync(framePath, 'utf-8')
  .replace(/^\s*<template>/, '').replace(/<\/template>\s*$/, '');
const tmp = resolve(framePath + '.verdict.html');
writeFileSync(tmp, `<!doctype html><meta charset="utf-8">
<style>html,body{margin:0;width:1920px;height:1080px;overflow:hidden}</style>\n${composed}`, 'utf-8');

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });
  await page.goto(pathToFileURL(tmp).href, { waitUntil: 'networkidle0' });

  const sweep = async () => {
    const rows = [];
    const N = Math.ceil(DUR / STEP) + 1;
    for (let i = 0; i < N; i++) {
      const t = Math.min(i * STEP, DUR);
      rows.push(await page.evaluate((fid, tt, keys, ko) => {
        const tl = window.__timelines && window.__timelines[fid];
        if (!tl) return null;
        tl.seek(tt, false);                          // suppressEvents:false — onUpdate must fire
        const H = 1080, W = 1920;
        const vis = (el) => {
          let o = 1, n = el;
          while (n && n !== document.body) {
            const cs = getComputedStyle(n);
            if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
            o *= parseFloat(cs.opacity);
            n = n.parentElement;
          }
          return o;
        };
        // Ink proxy: sum of (visible area x opacity) over every image and text-bearing leaf.
        let ink = 0, below = 0; const belowWho = new Set();
        for (const el of document.querySelectorAll('img, [class*="clip"], svg')) {
          const o = vis(el);
          if (o <= 0.01) continue;
          const r = el.getBoundingClientRect();
          if (r.width <= 0 || r.height <= 0) continue;
          ink += (r.width * r.height * o) / (W * H);
          // Keep-out governs CONTENT, not grounds. A backdrop or scene container is full-frame by
          // definition and spans the caption band harmlessly — the first run flagged the collage's
          // own `clgbg`/`clgworld`, which is a false positive, not a layout defect. Anything
          // covering essentially the whole frame is a ground.
          const fullFrame = r.width >= W * 0.98 && r.height >= H * 0.98;
          if (!fullFrame && r.bottom > H * ko && r.top < H) {
            below += 1;
            belowWho.add((el.getAttribute('src') || el.className || el.tagName).toString().split('/').pop());
          }
        }
        const subjects = {};
        for (const k of keys) {
          const el = Array.from(document.querySelectorAll('img'))
            .find((im) => (im.getAttribute('src') || '').includes(k));
          subjects[k] = el ? vis(el) : -1;           // -1 = element absent from the DOM entirely
        }
        return { t: tt, ink, below, belowWho: Array.from(belowWho), subjects };
      }, frameId, t, Object.keys(anchors), KEEPOUT));
    }
    return rows;
  };

  const pass1 = await sweep();
  if (pass1.some((r) => r === null)) {
    console.error(`no timeline "${frameId}" in ${framePath}`);
    process.exit(1);
  }
  const pass2 = await sweep();

  // --- 6 seek-safe: identical seeks must give identical readings ---
  const drift = pass1.reduce((m, r, i) =>
    Math.max(m, Math.abs(r.ink - pass2[i].ink)), 0);

  // --- 1 anchor ---
  const anchorRows = [];
  for (const [asset, a] of Object.entries(anchors)) {
    const first = pass1.find((r) => r.subjects[asset] > VISIBLE);
    const absent = pass1.every((r) => r.subjects[asset] === -1);
    anchorRows.push({
      asset, noun: a.noun, expected: a.start,
      actual: first ? +first.t.toFixed(3) : null,
      delta: first ? +(first.t - a.start).toFixed(3) : null,
      ok: !!first && Math.abs(first.t - a.start) <= TOL,
      absent,
    });
  }

  // --- 2 no-exit: ink never falls (allow 2% jitter for sub-pixel layout) ---
  let worstDrop = 0, dropAt = null;
  for (let i = 1; i < pass1.length; i++) {
    const d = pass1[i - 1].ink - pass1[i].ink;
    if (d > worstDrop) { worstDrop = d; dropAt = +pass1[i].t.toFixed(2); }
  }
  const noExit = worstDrop <= 0.02 * Math.max(...pass1.map((r) => r.ink));

  // --- 3 keep-out ---
  const violations = pass1.filter((r) => r.below > 0).length;

  // --- 4 never-blank, from the first entry onward ---
  const firstEntry = Math.min(...anchorRows.filter((a) => a.actual !== null).map((a) => a.actual));
  const after = pass1.filter((r) => r.t >= firstEntry);
  const minInk = after.length ? Math.min(...after.map((r) => r.ink)) : 0;

  // --- 5 all present at the end ---
  const last = pass1[pass1.length - 1];
  const missingAtEnd = Object.keys(anchors).filter((k) => !(last.subjects[k] > 0.5));
  const belowWho = Array.from(new Set(pass1.flatMap((r) => r.belowWho)));

  const report = {
    frame: framePath, frameId, duration: DUR, samples: pass1.length, step_s: STEP,
    checks: {
      anchor: { pass: anchorRows.every((a) => a.ok), tolerance_s: TOL, rows: anchorRows },
      no_exit: { pass: noExit, worst_drop: +worstDrop.toFixed(4), at_s: dropAt },
      keep_out: { pass: violations === 0, frames_with_content_below_83pct: violations, offenders: belowWho },
      never_blank: { pass: minInk > 0.01, min_ink_after_first_entry: +minInk.toFixed(4) },
      all_present_at_end: { pass: missingAtEnd.length === 0, missing: missingAtEnd },
      seek_safe: { pass: drift < 1e-9, max_ink_drift_between_passes: drift },
    },
  };
  report.score = Object.values(report.checks).filter((c) => c.pass).length;
  report.total = Object.keys(report.checks).length;

  if (outPath) writeFileSync(outPath, JSON.stringify(report, null, 1), 'utf-8');

  console.log(`\n${framePath}  ->  ${report.score}/${report.total}`);
  for (const [name, c] of Object.entries(report.checks)) {
    console.log(`  ${c.pass ? 'PASS' : 'FAIL'}  ${name}` + (name === 'keep_out' && !c.pass ? ` -> ${c.offenders.join(', ')}` : ''));
  }
  console.log('\n  subject      noun     expected   actual    delta');
  for (const a of anchorRows) {
    const act = a.actual === null ? (a.absent ? 'ABSENT' : 'never') : a.actual.toFixed(2);
    const d = a.delta === null ? '   -  ' : (a.delta >= 0 ? '+' : '') + a.delta.toFixed(2);
    console.log(`  ${a.ok ? 'ok  ' : 'FAIL'} ${a.asset.replace('_00', '').replace('_01', '').padEnd(13)}` +
                `${a.noun.padEnd(8)} ${a.expected.toFixed(2).padStart(7)}  ${act.padStart(7)}  ${d.padStart(7)}`);
  }
  process.exit(report.score === report.total ? 0 : 1);
} finally {
  await browser.close();
}
