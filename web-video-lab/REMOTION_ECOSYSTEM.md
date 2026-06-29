# Remotion ecosystem — effects tier + skills-repo adopt list

## Post-processing / "shader" tier — PostFX (built)
`@remotion/effects` (GLSL via `HtmlInCanvas`) first shipped at **4.0.455** and needs **Chrome
149+**; we're on **4.0.404** with an older headless Chromium and can't touch the shared
render-service. So we built the same outcomes from the browser's own GPU primitives: **SVG
filters + blend overlays** (`src/Effects.tsx` → `PostFX`). Deterministic (grain seeded by
frame), works now, zero upgrade.
- **Effects:** `grade` (`warm|cool|noir|vivid` via feColorMatrix), `bloom` (feGaussianBlur +
  brighten + merge — light bleed on bright accents), `grain` (frame-seeded feTurbulence
  overlay), `vignette` (radial darken).
- **Usage:** optional global on a narrated chapter — spec field
  `"fx": { "grade": "warm", "bloom": 0.3, "grain": 0.07, "vignette": 0.42 }` → `gen_spec`
  passes it through → `Chapter` wraps the Series in `<PostFX>`. Demo: `FXSpike` composition;
  before/after at `tailtrading/final/_postfx-before-after.png`. Verified tasteful on both
  dark-stage beats (bloom on accent numbers) and the light figure card (legible, warm glow,
  no wash-out). If we ever move render-service to ≥4.0.455 + newer Chromium, `@remotion/effects`
  becomes available for true GLSL passes — until then PostFX covers the need.

## remotion-dev/skills — verdict: ~70% redundant; cherry-pick these
It's one agent-skill (SKILL.md + 36 rule files) pinned to a Remotion release. Its core
(timing, calculate-metadata, transitions, sequencing, "CSS-transitions FORBIDDEN") just
*validates* our determinism discipline. Don't vendor it. Genuinely additive, ranked:

**Adopt now (low cost, fills a real gap):**
- ✅ **DONE — `@remotion/layout-utils` `fitText`**: wired via `src/primitives/fit.ts`
  (`fitFontSize`) into `HeroStatement` — long lines auto-shrink to fit the stage (capped at
  the design size) instead of overflowing/wrapping. Reusable on any big-type block.
- ✅ **DONE — `<Sequence premountFor={fps*0.5}>`**: added to the `Chapter` driver — each beat
  premounts ~0.5s early so fonts/Img/KaTeX/Lottie resolve before the cut (kills pop-in).
  Verified: total duration unchanged + narration sync intact (premounted `<Audio>` stays
  silent until the sequence starts).
- **`useCurrentScale()`** before ANY `getBoundingClientRect()`: Remotion scales the canvas, so
  raw rects are wrong at non-100% zoom — a silent correctness bug if a block measures the DOM.
  (Note: `fitFontSize` uses `measureText`, which is scale-independent, so it's unaffected.)
- **video-layout numeric minimums → linter rules**: safe-area (≥80px sides / ≥100px top-bottom
  at 1080-wide; scale for 1920) + min font sizes → add as pacing-linter checks. Also fold a
  `fillTextBox` overflow check into the linter (build-time "does this caption overflow N lines?").

**Worth knowing (adopt opportunistically):**
- **`@remotion/effects` + `HtmlInCanvas`** (WebGL/WebGPU post-processing) — the real shader
  package; gated on a render-service upgrade (see above). PostFX is our interim.
- **`createTikTokStyleCaptions`** (`@remotion/captions`) — token-pagination + per-word active
  highlight; cleaner than our hand-rolled caption band if we revisit it.
- **adaptive silence-trim** (ffmpeg `loudnorm`→`silencedetect`→`trimBefore/After`) — auto-tighten
  TTS dead-air per clip; pairs with the pacing linter.
- **`@remotion/sfx`** hosted whoosh/ding library (URLs) — cheap transition/reveal SFX polish.
- **`<LightLeak>` + `<TransitionSeries.Overlay>`** — themed flares over cuts; the Overlay track
  is a clean way to layer anything across a transition.
- **`useWindowedAudioData` + `visualizeAudio`** — deterministic audiograms / bass-reactive
  pulses on stat reveals.
- **`@remotion/media` engine** (`<Video>/<Audio>` with loop/pitch/volume-curve) — the
  current-release media path vs legacy `OffthreadVideo`.
- **`<AnimatedImage loopBehavior="pause-after-finish">`** — play-once-and-hold GIF/APNG.
- **the normalized-progress idiom** (one `progress = slideIn - slideOut`, derive all props) +
  three named bezier curves — a tidy authoring house-style for the 22 blocks.

**Skip:** 3d/maplibre/transparent-video/tailwind rules — not our pipeline.
