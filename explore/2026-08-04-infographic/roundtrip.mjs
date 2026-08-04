/**
 * Inverse parsing — recover a diagram's STRUCTURE from what actually rendered.
 *
 *   node roundtrip.mjs <frame.html> <frame-id> <authored.json> [out.json]
 *
 * The idea is SciFlow-Bench's (arXiv 2602.09809): do not grade a generated figure on visual
 * similarity, grade it on STRUCTURAL RECOVERABILITY — parse the rendered output back into a graph
 * and compare it to the intent. Their finding is that image models produce "visually plausible but
 * structurally incorrect" figures, which is exactly the failure a paper explainer cannot ship.
 *
 * They inverse-parse from PIXELS with a hierarchical multi-agent system, because they treat
 * generation as black-box image synthesis. NOLAN renders a DOM, so the same check is a DOM query:
 * read the node labels and the drawn connectors straight out of the composed frame.
 *
 * What this catches that an authoring gate cannot: the spec said six nodes and the renderer drew
 * five; a label was truncated to nothing; an edge the spec declared was never stroked.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire('D:/ClaudeProjects/NOLAN/render-service/');
const puppeteer = require('puppeteer');

const [, , framePath, frameId, authoredPath, outPath] = process.argv;
if (!framePath || !frameId || !authoredPath) {
  console.error('usage: node roundtrip.mjs <frame.html> <frame-id> <authored.json> [out.json]');
  process.exit(2);
}

const authored = JSON.parse(readFileSync(authoredPath, 'utf-8'));

// Flatten the authored hierarchy into the labels and parent->child edges it CLAIMS.
const claimNodes = [];
const claimEdges = [];
const claimSub = [];
(function walk(n, parent) {
  if (!n || !n.label) return;
  claimNodes.push(n.label);
  if (n.sub) claimSub.push(n.sub);          // authored text that is not a node label
  if (parent) claimEdges.push(`${parent} -> ${n.label}`);
  for (const c of n.children || []) walk(c, n.label);
})(authored.root, null);

// Labels REPEAT in real graphs — both Transformer stacks contain a feed-forward network. Matching
// on a Set silently merges them and under-counts the render. Compare MULTISETS instead.
const tally = (xs) => xs.reduce((m, x) => m.set(x, (m.get(x) || 0) + 1), new Map());

// `diagram` and `geo` load d3/topojson/atlases from a RELATIVE vendor/ path, which only resolves
// from the bridge directory. Rewrite those to absolute file URLs so the frame works wherever the
// temp copy lives — otherwise d3 never loads, the setup IIFE throws, and the timeline is silently
// never registered (the failure reads as "no timeline", which is deeply unhelpful).
const VENDOR = pathToFileURL(
  resolve('D:/ClaudeProjects/NOLAN/render-service/_lab_hyperframes/bridge/vendor') + '/').href;
const composed = readFileSync(framePath, 'utf-8')
  .replace(/^\s*<template>/, '').replace(/<\/template>\s*$/, '')
  .replace(/src="vendor\//g, `src="${VENDOR}`);
const tmp = resolve(framePath + '.roundtrip.html');
writeFileSync(tmp, `<!doctype html><meta charset="utf-8">
<style>html,body{margin:0;width:1920px;height:1080px;overflow:hidden}</style>\n${composed}`, 'utf-8');

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });
  await page.goto(pathToFileURL(tmp).href, { waitUntil: 'networkidle0' });

  const recovered = await page.evaluate((fid) => {
    const tl = window.__timelines && window.__timelines[fid];
    if (!tl) return null;
    tl.seek(tl.duration(), false);          // the END state: everything the frame ever draws

    // NODES: any element carrying visible text that is not a connector.
    const seen = [];                        // every visible text leaf, NOT deduped
    for (const el of document.querySelectorAll('#root *')) {
      if (el.children.length) continue;     // leaves only, so a wrapper is not counted twice
      const txt = (el.textContent || '').trim();
      if (!txt) continue;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      seen.push(txt);
    }

    // EDGES: drawn connectors. A path/line that is actually stroked and has length.
    let connectors = 0;
    for (const p of document.querySelectorAll('#root path, #root line, #root polyline')) {
      const cs = getComputedStyle(p);
      if (cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.02) continue;
      if (cs.stroke === 'none' || !cs.stroke) continue;
      const len = typeof p.getTotalLength === 'function' ? p.getTotalLength() : 0;
      // stroke-dashoffset draw-ins leave a fully-drawn path at the end of the timeline
      const dash = parseFloat(cs.strokeDashoffset || '0');
      if (len > 4 && Math.abs(dash) < len * 0.98) connectors += 1;
    }
    return { labels: seen, connectors };
  }, frameId);

  if (!recovered) {
    console.error(`no timeline "${frameId}"`);
    process.exit(1);
  }

  const want = tally(claimNodes);
  const got = tally(recovered.labels);
  const missing = [];
  let found = 0;
  for (const [label, n] of want) {
    const have = got.get(label) || 0;
    found += Math.min(n, have);
    for (let i = have; i < n; i++) missing.push(label);   // one entry per un-rendered copy
  }
  // Text the frame shows that the spec never claimed — chrome (kicker/caption) mostly, but a
  // fabricated label would surface here too.
  const claimedText = new Set([...claimNodes, ...claimSub]);
  const extra = Array.from(new Set(recovered.labels.filter((l) => !claimedText.has(l))));

  const report = {
    frame: framePath,
    claimed: { nodes: claimNodes.length, edges: claimEdges.length },
    recovered: { nodes: found, connectors: recovered.connectors },
    node_recall: +(found / Math.max(1, claimNodes.length)).toFixed(3),
    edge_recall: +(Math.min(recovered.connectors, claimEdges.length) /
                   Math.max(1, claimEdges.length)).toFixed(3),
    missing_nodes: missing,
    unclaimed_text: extra,
  };
  report.pass = missing.length === 0 && recovered.connectors >= claimEdges.length;

  if (outPath) writeFileSync(outPath, JSON.stringify(report, null, 1), 'utf-8');

  console.log(`\ninverse parse: ${report.pass ? 'PASS' : 'FAIL'}`);
  console.log(`  nodes  claimed ${report.claimed.nodes}  recovered ${report.recovered.nodes}  ` +
              `recall ${(report.node_recall * 100).toFixed(0)}%`);
  console.log(`  edges  claimed ${report.claimed.edges}  connectors drawn ${report.recovered.connectors}  ` +
              `recall ${(report.edge_recall * 100).toFixed(0)}%`);
  if (missing.length) console.log(`  MISSING FROM THE RENDER: ${missing.join(' | ')}`);
  if (extra.length) console.log(`  unclaimed text (chrome or fabricated): ${extra.join(' | ')}`);
  process.exit(report.pass ? 0 : 1);
} finally {
  await browser.close();
}
