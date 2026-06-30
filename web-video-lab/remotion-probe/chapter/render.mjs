// Lab probe — render a whole CHAPTER (a Series of step-blocks, each with its own
// narration + word-timestamp reveals) to mp4 via NOLAN's Remotion. Stages the
// theme + each step's audio. Run from render-service/ with Windows node.
import { bundle } from "@remotion/bundler";
import { selectComposition, renderMedia } from "@remotion/renderer";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const here = path.dirname(fileURLToPath(import.meta.url));
const cfg = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));

const publicDir = path.join(here, "public");
fs.mkdirSync(publicDir, { recursive: true });

const theme = cfg.theme || "bold-signal";
fs.copyFileSync(
  path.resolve(here, "../../../themes", theme, "tokens.css"),
  path.join(here, "src", "styles", "_active-theme.css"),
);
console.log("theme:", theme);

const steps = (cfg.props && cfg.props.steps) || [];
for (const s of steps) {
  if (s.audioSrc) {
    const base = path.basename(s.audioSrc);
    fs.copyFileSync(s.audioSrc, path.join(publicDir, base));
    s.audioSrc = base;
  }
}
const props = { steps };

const serveUrl = await bundle({ entryPoint: path.join(here, "src", "index.tsx"), publicDir });
const composition = await selectComposition({ serveUrl, id: "Chapter", inputProps: props });

const outDir = path.join(here, "output");
fs.mkdirSync(outDir, { recursive: true });
const out = path.join(outDir, cfg.out || "chapter.mp4");

await renderMedia({
  composition, serveUrl, codec: "h264", audioCodec: "aac",
  outputLocation: out, inputProps: props,
});
console.log("rendered", out, "frames:", composition.durationInFrames);
