// Programmatic render for the curated Remotion source.
// Usage (from render-service/ as cwd, Windows node):
//   node remotion-lib/render.mjs remotion-lib/jobs/<job>.json
// Job JSON: { comp, out, durationInFrames, codec?, video?, props:{...} }
import {bundle} from '@remotion/bundler';
import {selectComposition, renderMedia} from '@remotion/renderer';
import {fileURLToPath} from 'url';
import path from 'path';
import fs from 'fs';

const here = path.dirname(fileURLToPath(import.meta.url));
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));

const publicDir = path.join(here, 'public');
const outDir = path.join(here, 'output');
fs.mkdirSync(publicDir, {recursive: true});
fs.mkdirSync(outDir, {recursive: true});

const props = {...(cfg.props || {}), durationInFrames: cfg.durationInFrames || 120};
const stage = (src, prop) => {
  const base = path.basename(src);
  fs.copyFileSync(src, path.join(publicDir, base)); // staticFile needs it in public/
  props[prop] = base;
};
if (cfg.video) stage(cfg.video, 'videoSrc');
if (cfg.image) stage(cfg.image, 'mapSrc');
if (cfg.background) stage(cfg.background, 'background'); // photo-montage table image
if (cfg.cards) {
  // photo-montage: stage each card image, keep all its motion/style fields.
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

const comp = cfg.comp || 'Kinetic';
const t0 = Date.now();
console.log('Bundling…');
const serveUrl = await bundle({entryPoint: path.join(here, 'src', 'index.tsx'), publicDir});
console.log('Selecting composition:', comp);
const composition = await selectComposition({serveUrl, id: comp, inputProps: props});
const out = path.join(outDir, cfg.out);
console.log(`Rendering ${cfg.out} (${composition.durationInFrames} frames, ${cfg.codec || 'h264'})…`);
await renderMedia({
  composition,
  serveUrl,
  codec: cfg.codec || 'h264',
  outputLocation: out,
  inputProps: props,
});
console.log(`DONE ${cfg.out} in ${((Date.now() - t0) / 1000).toFixed(1)}s -> ${out}`);
