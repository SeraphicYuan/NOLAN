// Unified Remotion render for NOLAN — handles BOTH job shapes from one bundle:
//   • MOTION (per-scene motion path, src/nolan/remotion_source.py):
//       { comp, out, durationInFrames, codec?, video?, image?, cards?, background?, segments?, props }
//       -> renderMedia(comp) with inline video/image/card staging.
//   • FLOW (chapter-block flow engine, src/nolan/flows):
//       { composition:"Chapter"|"Montage", out, theme, props:{steps}, captions?, fx?, transitions? }
//       -> stageJob() (theme + audio + image staging) -> renderMedia(Chapter).
// Run from render-service/ with Windows node:  node remotion-lib/render.mjs <job.json>
import {bundle} from '@remotion/bundler';
import {selectComposition, renderMedia} from '@remotion/renderer';
import {fileURLToPath} from 'url';
import path from 'path';
import fs from 'fs';
import {stageJob} from './stage.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));

const publicDir = path.join(here, 'public');
const outDir = path.join(here, 'output');
fs.mkdirSync(publicDir, {recursive: true});
fs.mkdirSync(outDir, {recursive: true});

// A flow job carries a Chapter/Montage composition (or props.steps); everything else is motion.
const isFlow = !!(cfg.composition || (cfg.props && cfg.props.steps));

let compId, inputProps, audioCodec;
if (isFlow) {
  const staged = stageJob(cfg, here);            // theme + audio + images -> public/, builds props
  compId = staged.compId;
  inputProps = staged.props;
  audioCodec = 'aac';
  console.log('theme:', staged.theme);
} else {
  const props = {...(cfg.props || {}), durationInFrames: cfg.durationInFrames || 120};
  const stage = (src, prop) => {
    const base = path.basename(src);
    fs.copyFileSync(src, path.join(publicDir, base)); // staticFile needs it in public/
    props[prop] = base;
  };
  if (cfg.video) stage(cfg.video, 'videoSrc');
  if (cfg.image) stage(cfg.image, 'mapSrc');
  if (cfg.background) stage(cfg.background, 'background'); // photo-montage table image / still-motion base
  if (cfg.foreground) stage(cfg.foreground, 'foreground'); // still-motion parallax subject cutout
  if (cfg.cards) {
    props.cards = cfg.cards.map((c) => {
      const base = path.basename(c.src);
      fs.copyFileSync(c.src, path.join(publicDir, base));
      return {...c, src: base};
    });
  }
  if (cfg.segments) {
    props.segments = cfg.segments.map((s) => {
      const base = path.basename(s.video);
      fs.copyFileSync(s.video, path.join(publicDir, base));
      return {src: base, label: s.label, category: s.category};
    });
  }
  compId = cfg.comp || 'Kinetic';
  inputProps = props;
}

const t0 = Date.now();
console.log('Bundling…');
const serveUrl = await bundle({entryPoint: path.join(here, 'src', 'index.tsx'), publicDir});
console.log('Selecting composition:', compId);
const composition = await selectComposition({serveUrl, id: compId, inputProps});
const out = path.join(outDir, cfg.out || 'out.mp4');
console.log(`Rendering ${cfg.out} (${composition.durationInFrames} frames, ${cfg.codec || 'h264'})…`);
await renderMedia({
  composition,
  serveUrl,
  codec: cfg.codec || 'h264',
  ...(audioCodec ? {audioCodec} : {}),
  outputLocation: out,
  inputProps,
});
console.log(`DONE ${cfg.out} in ${((Date.now() - t0) / 1000).toFixed(1)}s -> ${out}`);
// flow callers print/inspect this line; keep the _lab_chapter-compatible form too:
if (isFlow) console.log('rendered', out, 'frames:', composition.durationInFrames);
