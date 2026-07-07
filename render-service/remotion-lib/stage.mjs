// Shared job staging for the Chapter renderer (render.mjs) AND the still-based
// pre-flight checker (still.mjs), so a contact-sheet still is staged EXACTLY like
// the full render — same theme, same images, same props. If these ever diverged the
// contact sheet would lie, so both paths go through this one function.
import fs from "fs";
import path from "path";

// Atomic write/copy: parallel section renders (premium render_workers) stage
// into the SAME src/styles + public/ — identical content, but a plain
// writeFileSync could hand a half-written file to the sibling bundler.
// tmp + rename is atomic on one volume. On WINDOWS, rename-over-existing
// throws EPERM while a sibling has the dest open (the render_workers>=2
// incident, 2026-07-07) — so: skip identical content entirely (the common
// case: every worker stages the SAME theme), retry transient errors, and
// accept a same-size dest as the sibling having won the race.
const RETRYABLE = ["EPERM", "EACCES", "EBUSY"];
function sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}
function renameWithRetry(tmp, dest, attempts = 6) {
  for (let i = 0; ; i++) {
    try { fs.renameSync(tmp, dest); return; }
    catch (e) {
      if (!RETRYABLE.includes(e.code) || i >= attempts - 1) {
        try { fs.unlinkSync(tmp); } catch {}
        throw e;
      }
      sleepSync(50 * Math.pow(2, i));
    }
  }
}
function writeAtomic(dest, data) {
  try { // identical content already staged (sibling worker) -> nothing to do
    if (fs.existsSync(dest) && fs.readFileSync(dest, "utf8") === String(data)) return;
  } catch {}
  const tmp = `${dest}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, data);
  renameWithRetry(tmp, dest);
}
function copyAtomic(src, dest) {
  const tmp = `${dest}.tmp-${process.pid}`;
  fs.copyFileSync(src, tmp);
  try { renameWithRetry(tmp, dest); }
  catch (e) {
    // sibling staged the same source concurrently: same-size dest = success
    try {
      if (fs.statSync(src).size === fs.statSync(dest).size) return;
    } catch {}
    throw e;
  }
}

const IMG_RE = /\.(jpe?g|png|webp|gif|avif)$/i;
const VID_RE = /\.(mp4|mov|webm|m4v)$/i;

// recursively stage ANY media-path string in a props object (src, left.src, …)
// into public/ and rewrite it to a basename so staticFile() resolves it.
// Videos join images since render story v2 (Video steps + hosted comps with
// videoSrc); an already-staged copy is reused, not re-copied.
function stageImages(obj, publicDir, missing) {
  if (!obj || typeof obj !== "object") return;
  for (const k of Object.keys(obj)) {
    const v = obj[k];
    if (typeof v === "string" && (IMG_RE.test(v) || VID_RE.test(v))) {
      if (fs.existsSync(v)) {
        const base = path.basename(v);
        // ALWAYS copy: public/ accumulates staged files across projects and
        // basenames collide (homer's scene_016.jpg vs aidc's — the Homer
        // montage rendered a POWER SUBSTATION). Skipping "already staged"
        // files reused another project's image silently.
        copyAtomic(v, path.join(publicDir, base));
        obj[k] = base;
      } else if (path.isAbsolute(v) || v.includes("/") || v.includes("\\")) {
        // a path that names a file that isn't there would surface as a
        // cryptic staticFile() crash mid-render — fail HERE, by name.
        // (bare basenames are assumed already staged and left alone)
        missing.push(`${k}: ${v}`);
      }
    } else if (v && typeof v === "object") stageImages(v, publicDir, missing);
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
  const accentOverride =
    typeof cfg.accent === "string" && /^#[0-9a-fA-F]{6}$/.test(cfg.accent) ? cfg.accent : null;
  if (accentOverride) {
    tokens += `\n:root { --accent: ${accentOverride}; }\n`;
  }
  // language-aware display face (the font-drift fix, part 2): blocks read
  // --font-display; an English job aliases it to the EN face, everything
  // else keeps the CN face (the blocks' historical default).
  const lang = cfg.lang === "en" ? "en" : "cn";
  tokens += `\n:root { --font-display: var(--font-display-${lang}); }\n`;
  writeAtomic(path.join(here, "src", "styles", "_active-theme.css"), tokens);

  // One theme system (SOTA #3): the hosted motion comps style via theme.ts
  // (inline hex — they concat alpha suffixes, so CSS vars won't do). Resolve
  // the ACTIVE theme's token values into a JSON theme.ts imports; without
  // this the comps rendered dark-editorial no matter what the brief picked.
  const tok = {};
  for (const m of tokens.matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/g)) tok[m[1]] = m[2].trim();
  // first-choice family per font token — theme-fonts.ts loads these in the
  // bundle so the theme's typography actually renders (the font-drift fix)
  const fam = (v) => String(v || "").split(",")[0].trim().replace(/^["']|["']$/g, "");
  const fonts = [...new Set(
    ["font-display-en", "font-display-cn", "font-body", "font-mono"]
      .map((k) => fam(tok[k])).filter(Boolean),
  )];
  writeAtomic(
    path.join(here, "src", "styles", "_active-theme.json"),
    JSON.stringify({
      theme,
      bg: tok["surface"], fg: tok["text"], muted: tok["text-2"],
      accent: accentOverride || tok["accent"],
      fontFamily: (lang === "en" ? tok["font-display-en"] : tok["font-display-cn"])
        || tok["font-display-en"] || tok["font-body"] || "",
      fonts,
    }, null, 1),
  );

  const steps = (cfg.props && cfg.props.steps) || [];
  const missing = [];
  for (const s of steps) {
    if (stageAudio && s.audioSrc) {
      const base = path.basename(s.audioSrc);
      if (fs.existsSync(s.audioSrc)) copyAtomic(s.audioSrc, path.join(publicDir, base));
      s.audioSrc = base;
    }
    if (s.props) stageImages(s.props, publicDir, missing);
  }
  if (missing.length) {
    throw new Error(`stage: ${missing.length} media path(s) do not exist:\n  ` + missing.join("\n  "));
  }

  const compId = cfg.composition || "Chapter";
  const props = compId === "Montage"
    ? { steps, transitions: cfg.transitions || [], motionBlur: !!cfg.motionBlur }
    : { steps, captions: !!cfg.captions, ...(cfg.fx ? { fx: cfg.fx } : {}) };

  return { compId, props, publicDir, theme };
}
