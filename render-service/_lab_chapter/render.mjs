// Lab probe — render a whole CHAPTER (a Series of step-blocks, each with its own
// narration + word-timestamp reveals) to mp4 via NOLAN's Remotion. Staging (theme +
// audio + images) lives in stage.mjs, shared with the still-based checker so a
// pre-flight still is staged identically. Run from render-service/ with Windows node.
import { bundle } from "@remotion/bundler";
import { selectComposition, renderMedia } from "@remotion/renderer";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { stageJob } from "./stage.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const cfg = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));

const { compId, props, publicDir, theme } = stageJob(cfg, here);
console.log("theme:", theme);

const serveUrl = await bundle({ entryPoint: path.join(here, "src", "index.tsx"), publicDir });
const composition = await selectComposition({ serveUrl, id: compId, inputProps: props });

const outDir = path.join(here, "output");
fs.mkdirSync(outDir, { recursive: true });
const out = path.join(outDir, cfg.out || "chapter.mp4");

await renderMedia({
  composition, serveUrl, codec: "h264", audioCodec: "aac",
  outputLocation: out, inputProps: props,
});
console.log("rendered", out, "frames:", composition.durationInFrames);
