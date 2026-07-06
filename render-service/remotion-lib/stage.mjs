// Shared job staging for the Chapter renderer (render.mjs) AND the still-based
// pre-flight checker (still.mjs), so a contact-sheet still is staged EXACTLY like
// the full render — same theme, same images, same props. If these ever diverged the
// contact sheet would lie, so both paths go through this one function.
import fs from "fs";
import path from "path";

const IMG_RE = /\.(jpe?g|png|webp|gif|avif)$/i;

// recursively stage ANY image-path string in a props object (src, left.src, …)
// into public/ and rewrite it to a basename so staticFile() resolves it.
function stageImages(obj, publicDir) {
  if (!obj || typeof obj !== "object") return;
  for (const k of Object.keys(obj)) {
    const v = obj[k];
    if (typeof v === "string" && IMG_RE.test(v) && fs.existsSync(v)) {
      const base = path.basename(v);
      fs.copyFileSync(v, path.join(publicDir, base));
      obj[k] = base;
    } else if (v && typeof v === "object") stageImages(v, publicDir);
  }
}

// Stage theme + audio + images into public/, assemble inputProps.
// Returns { compId, props, publicDir, theme }. Mutates cfg.props.steps in place
// (rewrites audioSrc + image paths to basenames), same as the original render.mjs.
export function stageJob(cfg, here, { stageAudio = true } = {}) {
  const publicDir = path.join(here, "public");
  fs.mkdirSync(publicDir, { recursive: true });

  const theme = cfg.theme || "bold-signal";
  let tokens = fs.readFileSync(path.resolve(here, "../../themes", theme, "tokens.css"), "utf8");
  // brief.json accent override (compiled from the style guide) — appended so it
  // wins the cascade; contact sheets share this path so they can't diverge.
  if (typeof cfg.accent === "string" && /^#[0-9a-fA-F]{6}$/.test(cfg.accent)) {
    tokens += `\n:root { --accent: ${cfg.accent}; }\n`;
  }
  fs.writeFileSync(path.join(here, "src", "styles", "_active-theme.css"), tokens);

  const steps = (cfg.props && cfg.props.steps) || [];
  for (const s of steps) {
    if (stageAudio && s.audioSrc) {
      const base = path.basename(s.audioSrc);
      if (fs.existsSync(s.audioSrc)) fs.copyFileSync(s.audioSrc, path.join(publicDir, base));
      s.audioSrc = base;
    }
    if (s.props) stageImages(s.props, publicDir);
  }

  const compId = cfg.composition || "Chapter";
  const props = compId === "Montage"
    ? { steps, transitions: cfg.transitions || [], motionBlur: !!cfg.motionBlur }
    : { steps, captions: !!cfg.captions, ...(cfg.fx ? { fx: cfg.fx } : {}) };

  return { compId, props, publicDir, theme };
}
