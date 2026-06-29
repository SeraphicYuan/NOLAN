// Lab probe renderer — mirrors render-service/remotion-lib/render.mjs, adds an
// audio-staging branch. Reuses render-service/node_modules (run from there with
// Windows node). Touches no existing NOLAN file; the whole folder is removable.
import { bundle } from "@remotion/bundler";
import { selectComposition, renderMedia } from "@remotion/renderer";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const here = path.dirname(fileURLToPath(import.meta.url));
const cfg = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));

const publicDir = path.join(here, "public");
fs.mkdirSync(publicDir, { recursive: true });

const props = { ...(cfg.props || {}), durationInFrames: cfg.durationInFrames || 120 };

// stage audio into public/ and reference it by basename (staticFile resolves there)
if (cfg.audio) {
  const base = path.basename(cfg.audio);
  fs.copyFileSync(cfg.audio, path.join(publicDir, base));
  props.audioSrc = base;
}

const serveUrl = await bundle({ entryPoint: path.join(here, "src", "index.tsx"), publicDir });
const composition = await selectComposition({ serveUrl, id: cfg.comp || "ListReveal", inputProps: props });

const outDir = path.join(here, "output");
fs.mkdirSync(outDir, { recursive: true });
const out = path.join(outDir, cfg.out || "out.mp4");

await renderMedia({
  composition, serveUrl,
  codec: cfg.codec || "h264",
  audioCodec: "aac",
  outputLocation: out,
  inputProps: props,
});
console.log("rendered", out);
