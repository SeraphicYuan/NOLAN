// Render diagnostic STILLS (one PNG per sample frame) from a Chapter job — the cheap
// Tier-1 pre-flight that catches spatial / empty-beat defects before paying for the
// full video render. Bundles + selects ONCE, then renderStill() per frame (no encode,
// no audio mux), so the whole contact sheet costs ~seconds, not minutes.
//
// Usage: node still.mjs <job.json> <samples.json> [outDir]
//   samples.json = [{ "frame": 123, "out": "00_hook_92.png" }, ...]
import { bundle } from "@remotion/bundler";
import { selectComposition, renderStill } from "@remotion/renderer";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { stageJob } from "./stage.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const cfg = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const samples = JSON.parse(fs.readFileSync(process.argv[3], "utf-8"));
const outDir = process.argv[4] || path.join(here, "output", "chk");
fs.mkdirSync(outDir, { recursive: true });

const { compId, props, publicDir } = stageJob(cfg, here);
const serveUrl = await bundle({ entryPoint: path.join(here, "src", "index.tsx"), publicDir });
const composition = await selectComposition({ serveUrl, id: compId, inputProps: props });
console.log("comp:", compId, "frames:", composition.durationInFrames, "stills:", samples.length);

for (const s of samples) {
  const frame = Math.max(0, Math.min(composition.durationInFrames - 1, s.frame));
  await renderStill({ composition, serveUrl, output: path.join(outDir, s.out), frame, inputProps: props });
  console.log("still", String(frame).padStart(6), "->", s.out);
}
