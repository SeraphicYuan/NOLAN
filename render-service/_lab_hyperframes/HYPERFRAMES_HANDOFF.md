# HyperFrames — internals handoff for the next agent

**Purpose:** get you productive on HeyGen's HyperFrames *framework itself* fast — not
just the authoring skills. Written 2026-07-08 after a full read of the `main` source
(`github.com/heygen-com/hyperframes`) + the docs + this NOLAN lab. Companion docs in this
folder: `REPORT.md` (the NOLAN eval + bridge program), `TASK.md` (the original eval brief),
`bridge/compose.py` (NOLAN's build-time composer). Read this first, then those.

All `file:line` anchors below are **repo-relative** (e.g. `packages/core/src/runtime/init.ts:2498`),
stable on `main`. They are NOT in this repo — see "Getting the source" — but the paths are
what you cite once you have it.

---

## 0. TL;DR mental model

HyperFrames **renders video from HTML, deterministically, by seeking a paused timeline
frame-by-frame.** A composition is an HTML doc where the DOM declares *timing* (`data-*`
attributes) and a **single paused GSAP timeline** declares *motion*. The renderer never
"plays" anything: for each output frame `N` it computes `t = N/fps`, calls one global
`window.__hf.seek(t)` to position the whole DOM+timeline at exactly `t`, captures the pixel
buffer with Chrome's `beginFrame` API, and FFmpeg-encodes the frames + separately-mixed
audio into MP4. Same input → same frames. That's the entire bet.

Three ideas do all the work:
1. **Timing is declarative** (`data-start`/`data-duration`/`data-track-index` + `class="clip"`), owned by the runtime — *scripts must never play/pause/seek media or toggle clip visibility.*
2. **Motion is one paused, seekable timeline** per composition, registered at `window.__timelines[<data-composition-id>]`.
3. **Determinism is a contract**, statically linted (no `Date.now`/`Math.random`/`rAF`/`repeat:-1`, no animating `display`/`visibility`, transforms/opacity only).

If you internalize those three, everything else is detail.

---

## 1. Getting the source (the scratchpad clone is ephemeral)

The next session won't have the clone I read. To get it:

```bash
# Full source (bun monorepo). LFS baselines are ~240MB of test mp4s — skip them:
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/heygen-com/hyperframes.git
```

You do NOT need to build it to *use* it — `npx hyperframes <cmd>` downloads the published CLI.
You only need the clone to *read internals* or hack on the framework. Build (if hacking):
`bun install && bun run build` (bun, NOT npm/pnpm; oxlint/oxfmt, not eslint/prettier).

The **skills** are already installed in this repo (`.agents/skills/hyperframes*`, symlinked into
`.claude/skills/`) — they're the authoring contract. This note is the layer *under* the skills.

---

## 2. Monorepo map (what each package is)

| Package | Role | Read it for |
|---|---|---|
| `packages/core` | **Types, parsers, generators, linter re-exports, the RUNTIME, frame adapters, the scoping compiler** | the composition contract + how seek actually works |
| `packages/parsers` | dependency-free data types + DOM/GSAP parsing (`TimelineElement`, `htmlParser`) | the parsed composition model |
| `packages/lint` | browser-safe rule engine (depends on `parsers`, NOT `core`) | the full lint-rule gate |
| `packages/engine` | seekable page→video capture (Puppeteer + FFmpeg): the render loop, BeginFrame, video-frame extraction/injection, audio mix, encode, workers | how a render runs |
| `packages/producer` | render *orchestrator* (stages) + runtime injection + sub-comp inlining | end-to-end render job |
| `packages/sdk` | headless composition **editing** engine (the DOM *is* the model) | programmatic edits / Studio parity |
| `packages/studio` + `studio-server` | browser timeline/canvas editor + source write-back | the human edit surface |
| `packages/player` | embeddable `<hyperframes-player>` web component | preview embedding |
| `packages/cli` | the `hyperframes` command (citty subcommands) | every command + flags |
| `packages/aws-lambda`, `gcp-cloud-run` | distributed render adapters | cloud render |
| `packages/shader-transitions` | WebGL transitions | shader FX |
| `registry/` | 109 blocks + 25 components + examples (installed via `hyperframes add`) | reusable scenes |

Dependency direction: `parsers` → `lint` → `core` → (`engine`, `producer`, `sdk`, `cli`).

---

## 3. The authored composition contract (what valid HTML must provide)

A composition is an HTML doc with:
- A **root** element carrying `data-composition-id` + `data-width` + `data-height`; on the root, `data-duration` = **total render length in seconds** (see the lock below).
- Timed elements marked `class="clip"` with `data-start` (+ `data-duration`), grouped by `data-track-index`.
- **Exactly one paused GSAP timeline** built synchronously and registered at `window.__timelines["<root data-composition-id>"]` (key MUST equal the id). One per sub-composition too.

```html
<div id="root" data-composition-id="root" data-width="1920" data-height="1080" data-duration="30">
  <video class="clip" data-start="0" data-duration="6" data-track-index="0" src="a.mp4" muted playsinline></video>
  <h1 id="title" class="clip" data-start="1" data-duration="4" data-track-index="1">Hi</h1>
  <audio data-start="0" data-duration="6" data-track-index="2" data-volume="0.5" src="m.wav"></audio>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3/dist/gsap.min.js"></script>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.from("#title", { opacity: 0, y: 40, duration: 0.8 }, 1);
    window.__timelines = window.__timelines || {};
    window.__timelines.root = tl;
  </script>
</div>
```

### `data-*` reference (the ones that bite)
| Attribute | Meaning / gotcha |
|---|---|
| `data-start` | seconds, OR a clip-id ref for **relative timing** (`"intro"`, `"intro + 2"`, `"intro - 0.5"` for crossfade). **Element discovery keys off `[data-start]`**, not `class="clip"`. |
| `data-duration` | clip length. On a **clip**: re-read from the *live DOM after scripts run* (so a script/variable can set it). On the **root**: read **once at compile time**, before scripts — a script/variable CANNOT change render length. Author it directly. |
| `data-track-index` | **Temporal only** — groups clips into timeline rows; same-track clips **cannot overlap** (lint error `overlapping_clips_same_track`). It does **NOT** set z-order. |
| **Z-order** | Runtime forces every root-level clip to `position:absolute; inset:0; 100%×100%` (`init.ts:382-488`) and stacks by **DOM order** (later sibling paints on top). Use CSS `z-index` for explicit layering; author DOM order deliberately. (The skill docs' "higher track = in front" is a simplification — don't trust it.) |
| `data-media-start` | media trim/offset (seconds). `data-volume` (0–1). `data-has-audio="true"` for a video whose audio you want mixed. |
| `data-hidden` | hard `display:none` regardless of playhead (Studio's eye toggle; reversible). |
| `data-no-timeline` | on a comp host that's driven purely by CSS/rAF — opts it out of the 45s "timeline not registered" poll. |

### Variables (parameterize + reuse)
- Declare on `<html data-composition-variables='[{id,type,label,default}, ...]'>` (types: string/number/color/boolean/enum/font/image).
- Override per sub-comp instance via `data-variable-values='{...}'` on the host; override at top level via `hyperframes render --variables '{...}'`.
- Read at runtime with `window.__hyperframes.getVariables()`. Precedence: declared default < host `data-variable-values` < CLI `--variables`.
- Media `src`, and even a clip's `data-duration`, can come from a string variable — the producer re-probes the live DOM after your script runs. **Root dimensions + root duration + fps + codec cannot** (compile-time / CLI-only).
- Tooling: `extractCompositionMetadata(html)` from `@hyperframes/core` reads declared variables without rendering (this is what Studio's variables panel uses).

---

## 4. How a render actually runs (engine + producer)

Orchestrator stages (`producer/src/services/renderOrchestrator.ts`, `executeRenderJob`):
**compile → probe → extractVideos → audio-mix → capture → encode → assemble (mux + faststart).**

- **Compile** flattens sub-comps referenced by `data-composition-src` into the live top-level DOM (`producer/src/services/htmlCompiler.ts` `inlineSubCompositions`), and injects the runtime (§6).
- **Per frame** (`engine/src/services/frameCapture.ts`): `t = quantizeTimeToFrame(N/fps)` → `page.evaluate(window.__hf.seek(t))` (the *only* call into the composition runtime, `:1869`) → `onBeforeCapture` paints video frames (§5) → capture.
- **Capture** is deterministic two ways:
  - **BeginFrame** (Linux + chrome-headless-shell): one `HeadlessExperimental.beginFrame` CDP call does layout→paint→composite **and** returns the screenshot atomically at virtual tick `base + N·interval` — no wall clock. Uses `--deterministic-mode`, `--run-all-compositor-stages-before-draw`, etc. (`browserManager.ts:688-700`).
  - **Screenshot fallback** (macOS/Windows): `Page.captureScreenshot`. Still deterministic because state comes from `__hf.seek(t)`, not from timing.
- **Encode** (`chunkEncoder.ts:31-35`): quality tiers → x264 `draft=ultrafast/CRF28`, `standard=medium/CRF18`, `high=slow/CRF15`. `webm`→VP9(alpha), `mov`→ProRes4444(alpha), HDR→h265 10-bit. `-bf 0`. **fps and resolution are independent of the tier.**
- **Workers**: auto ≈ `min(cpu-2, mem-based, frames/30)`, cap 24 (`parallelCoordinator.ts`). Linux parallel workers get isolated Chrome procs (BeginFrame can't be shared); streaming encode reorders out-of-order frames.
- **Determinism / Docker**: byte-identical output needs Linux + chrome-headless-shell + `--deterministic-mode` (what `--docker` gives you). Without it, renders are **visually identical (SSIM ~0.9999) but not byte-identical** — GPU rasterizer + encoder vary per host. This exactly matches NOLAN's REPORT §6 finding.

---

## 5. Media playback is framework-owned (critical mental model)

The composition **never** plays `<video>`/`<audio>`. Instead:
- **Video**: `videoFrameExtractor.ts` pre-extracts frames with FFmpeg (`-ss mediaStart -t duration`, resampled to render fps). Per output frame, `screenshotService.ts injectVideoFramesBatch` (`:593`) does `getElementById(videoId)` on the **top-level document**, paints the seeked frame onto an adjacent absolutely-positioned `<img class="__render_frame__">`, and hides the native `<video>` (`visibility:hidden`, so GSAP opacity on the video still composites).
- **Audio**: `audioMixer.ts` extracts each track to 48k WAV, then FFmpeg `atrim → volume → adelay(data-start) → apad → amix → aac`. `data-volume` becomes a sample-accurate PCM envelope. Muxed at the end.

**⇒ Why `<video>`/`<audio>` MUST be a direct root child, never inside a raw `<template>`:** both the FFmpeg extractor (`querySelectorAll("video[src]")`) and the runtime injector (`getElementById`) operate on the **top-level document and do not descend into `<template>.content`**. A media element in an un-inlined template subtree is invisible to both → renders blank / first-frame-frozen. Properly-referenced `data-composition-src` sub-comps are *flattened into the top-level DOM at compile time*, so their media IS found. Lint enforces this: `media_in_subcomposition` (E). NOLAN's `inject_root_video.py` exists precisely to mount b-roll `<video>` at the index HOST ROOT for this reason (archetype B).

---

## 6. The runtime + the global surface

- The runtime is one bundle (`build:hyperframes-runtime` → `hyperframe.runtime.iife.js`, sha256-pinned). The producer injects it at render/preview time in 3 layers (`producer/src/services/fileServer.ts:704-715`): an early stub at head-start, the verified runtime IIFE in `<head>`, and a body bridge that maps `window.__player` → **`window.__hf = {duration, seek}`**. Persisted HTML ships *without* the runtime; the producer/FE own injection.
- Stable globals: `window.__timelines`, `window.__player` (`.seek`/`.renderSeek`), `window.__hf`, `window.__playerReady`, `window.__renderReady`, `window.__hyperframes.getVariables()`, `window.__clipManifest`.
- **Seek core** (`init.ts:2498 seekTimelineAndAdapters`): GSAP is always paused; each tick does `tl.totalTime(t)` (preferred; includes nesting) else `tl.seek(t)`, clamped to `totalDuration()` (seeking past the end holds the final frame instead of reverting `from()` tweens). Sub-comp timelines are GSAP-*nested* into the master at their resolved `data-start` (`init.ts:850-882`), so seeking one master drives the whole tree.

### Frame adapters — "what should the screen look like at frame N?"
Any runtime that can answer that plugs in. Live adapter registry order (`init.ts:2227-2242`):
`waapi, css, animejs, lottie, three, mapbox, leaflet, google-maps, maplibre, d3, typegpu, gsap`.
Each implements `{discover, seek({time}), pause, getReadyPromise?, getInferredDurationSeconds?}`.
GSAP is driven directly (skipped in the generic loop). Lottie → `goToAndStop(ms)`; CSS/WAAPI →
`animation.currentTime=ms; pause()`; Three/TypeGPU → set `window.__hfThreeTime` + dispatch a
`"hf-seek"` CustomEvent your rAF loop listens to. `getReadyPromise()` gates `__renderReady`
(async asset loads). The static tooling adapter (`core/src/adapters/gsap.ts`) is a separate,
simpler surface used outside the live runtime.

---

## 7. ⭐ The multi-instance crux (reconciles NOLAN's REPORT Addendum 5)

**NOLAN's lab concluded** you cannot mount the same animated block twice (2nd renders blank →
hence `bridge/compose.py` stamps modules at build time). **The framework source on `main` says
multi-instance IS supported — through the sub-composition scoping path.** Both are "right"; the
distinction is *how* you mount:

- Mounting via `data-composition-src` (or an inline `template#<id>-template`) triggers
  `assignRuntimeCompositionIds()` (`compositionLoader.ts`): a duplicate `data-composition-id`
  is renamed to `<id>__hf1`, `__hf2`, … AND the block's script is wrapped by
  `wrapScopedCompositionScript` (`compiler/compositionScoping.ts`), which installs a **Proxy over
  `window.__timelines`** remapping the authored key → the runtime key, and scopes
  `getElementById`/`querySelector`/GSAP string targets to that instance's own root. So two
  instances get distinct timelines and distinct element lookups automatically — even if the block
  hardcodes `window.__timelines["stat-lockup"]` and `#num`. (This is exactly how the docs'
  `card-pro`/`card-enterprise` from one `card.html` works — `docs/concepts/variables.mdx`.)
- The failure NOLAN hit happens when the scoping path is **bypassed** — e.g. the same raw block
  pasted inline twice (no `data-composition-src`, no `template#<id>-template`): `shouldAssignRuntimeCompositionId`
  is false → no rename, no Proxy → the 2nd `window.__timelines["foo"]=tl` **overwrites** the 1st,
  and both `getElementById("num")` resolve to the **first** DOM match. 2nd instance renders blank.
  A partial rename without the wrapper causes the *other* symptom: the engine polls
  `window.__timelines["foo__hf1"]`, never finds it, and hits the **45000ms timeout**.

**Action for the next agent:** before assuming the build-time composer is the *only* path,
**empirically re-test multi-instance on current `main`**: two hosts, each `data-composition-src`
pointing at the same block file, distinct host `data-composition-id`s, distinct `data-variable-values`.
If it works (it should, per the code), then NOLAN has **two** viable reuse strategies:
1. **Build-time composer** (`compose.py`) — instant, deterministic, one merged timeline, full control; the proven path today. Best when you want to stamp many scenes from a compact spec.
2. **Runtime multi-instance registry blocks** — author blocks that (a) mount as real sub-comps and (b) scope all DOM lookups to their own root; then reuse via `data-variable-values`. This is the framework-native path and keeps blocks Studio-editable + catalog-installable.
Caveat: NOLAN's original test may have run an older published CLI than `main`; version-check before drawing conclusions.

---

## 8. The gate: lint / validate / inspect (what generated HTML must pass)

Run order (all `--json`-able except render/preview/play): **`lint` → `validate` → `inspect` →
`snapshot` (if sub-comps) → `preview` → `render`**. Lint is advisory by default; `--strict`
(errors) / `--strict-all` (+warnings) block render.

- **`lint`** (`packages/lint`, ~70 rules) — static HTML. Highest-value error classes:
  - Contract: `root_missing_composition_id`, `root_missing_dimensions`, `missing_timeline_registry`, `timeline_id_mismatch`, `timed_element_missing_clip_class`, `overlapping_clips_same_track`, `standalone_composition_wrapped_in_template`, `head_leaked_text`.
  - Determinism: `non_deterministic_code` (`Math.random`/`Date.now`/`new Date`/`performance.now`/`crypto.getRandomValues`), `gsap_infinite_repeat` (`repeat:-1`), `requestanimationframe_in_composition`, `gsap_non_transform_motion` (animating `left/top/margin/fontSize`…), `gsap_animates_clip_element` (tweening `visibility`/`display`).
  - Media: `media_in_subcomposition`, `video_missing_muted`, `video_nested_in_timed_element`, `base64_media_prohibited`, `placeholder_media_url`.
  - Scene hygiene: `gsap_exit_missing_hard_kill`, `scene_layer_missing_visibility_kill`, `unscoped_gsap_selector`, `gsap_from_opacity_noop`.
  - Studio: `studio_missing_editable_id` (W — add a stable human `id` to every timed clip).
  - Deprecations: `deprecated_data_layer` (use `data-track-index`), `deprecated_data_end` (use `data-duration`).
- **`validate`** — loads in headless Chrome: runtime console/page errors, failed requests (≥400), clip-vs-source duration fit, and a **WCAG AA contrast audit** across 5 seeked samples.
- **`inspect`** (alias of `layout`) — seeks a grid and runs a **layout audit** (`clipped_text`, `text_box_overflow`, `canvas_overflow`, `container_overflow`, `content_overlap`, `text_occluded`) + **motion-intent** verification against an optional `*.motion.json` sidecar (`appearsBy`/`before`/`staysInFrame`/`keepsMoving`).
- **`snapshot --at t1,t2,...`** — the ONLY gate that mounts `index.html` sub-comps the way render does; use it to catch cross-file mount failures (`<style>` left in `<head>`, host-id ≠ template-id → 45s timeout).

---

## 9. Programmatic build API (directly relevant to expanding the composer)

`@hyperframes/core` exposes a **model → HTML** builder (`packages/core/src/generators/hyperframes.ts`):
- `generateHyperframesHtml(elements: TimelineElement[], totalDuration, options)` → full HTML doc.
- `generateHyperframesStyles(...)`, `generateGsapTimelineScript(...)` — the pieces.
- `TimelineElement` = media | text | composition, per `packages/parsers/src/types.ts`. Generate↔parse round-trips (`htmlParser.parseHtml`).

**Caveat:** this generator targets the **Studio/legacy attribute set** — it emits `data-layer`
(deprecated) and a single centered `#stage` layout, so its output trips `deprecated_data_layer`/
`deprecated_data_end` in lint. NOLAN's `bridge/compose.py` deliberately does **not** use it — it
emits the *current* authored contract (`data-track-index`, scoped CSS, one merged timeline) as
strings. So: the core generator is available but is not the newest contract; `compose.py`'s
hand-rolled string emission is the better base to extend today. If you want SDK-grade editing of
generated output, go through `@hyperframes/sdk` instead (next section).

---

## 10. Editing model (SDK + Studio) — why it matters for reuse

- **The DOM *is* the model.** `@hyperframes/sdk` `openComposition(html)` stamps `data-hf-id` on
  every element (content-hashed, stable) and parses to a linkedom `Document` it mutates in place,
  then `serialize()`s back to HTML. No separate JSON model.
- Ops: `setStyle/setText/setAttribute/setTiming/setHold/moveElement/addElement/removeElement/
  reorderElements/setVariableValue/setCompositionMetadata` + a GSAP tween/keyframe family; each
  emits forward+inverse RFC-6902 patches; undo/redo built in. `setTiming` writes the `data-*`
  **and** shifts the matching GSAP tween (timeline is source-of-truth at playback).
- **Two id conventions — don't conflate:** `data-hf-id` (auto-minted machine key for SDK/Studio
  addressing + source write-back) vs. a **stable human `id`** (what `studio_missing_editable_id`
  asks for, so Studio's timeline/canvas controls have a legible target). Programmatically-generated
  comps ARE Studio-editable afterward (shared `data-hf-id` + `sourceMutation.ts` write-back), but
  emit a human `id` on every timed clip for clean editing.

---

## 11. Registry format (blocks vs components)

- `registry/registry.json` = thin index (`{name, type}` only). Per-item metadata in
  `registry/<blocks|components|examples>/<name>/registry-item.json`.
- **Block** = standalone sub-composition (own `dimensions` + `duration`), a full `<!doctype html>`
  with a scoped `<style>` + a paused-timeline `<script>`; installs to `compositions/<name>.html`;
  wired via `data-composition-src`. Optional `params[]` = CSS-var overrides.
- **Component** = fragment/snippet (no dimensions/duration); installs to
  `compositions/components/<name>.html`; pasted by hand into a host.
- `hyperframes add <name>` resolves deps (topological), remaps targets per `hyperframes.json`
  `paths`, fetches from `raw.githubusercontent.com/heygen-com/hyperframes/main/registry`, prepends
  a `<!-- hyperframes-registry-item: <name> -->` provenance marker, copies a wiring snippet to
  clipboard. `add` is blocks/components only; examples install via `init --example`.
- The catalog already ships **maps** (`us-map`, `us-map-bubble/hex/flow`, `world-map`, `spain-map`),
  **`data-chart`**, `flowchart`, many `code-*`, lower-thirds (`lt-*`), `transitions-*`, `vfx-*`,
  social cards (`reddit-post`, `x-post`, `spotify-card`) — relevant to NOLAN's `geo_map`/`chart`
  composer work (don't reinvent; either install or study these first).

---

## 12. NOLAN ↔ HyperFrames (where our code meets theirs)

Everything lives in `render-service/_lab_hyperframes/` (see `REPORT.md` for the full program):
- **`bridge/compose.py`** — the build-time "block kit": `BLOCKS = {stat, statement, geo, timeline, raw}` +
  modules `media_ground`, `prop_cutout`. Takes a compact `scenes_spec.json`, stamps `<template>`-wrapped
  frame sub-comps with per-scene id prefixes + one merged timeline. THE expansion surface (add a
  `def block(sid, sc)->(frag, tl)`, register in `BLOCKS`, document in `bridge/catalog.json` or the
  `check_catalog.py` honesty test fails). Gated for agent-routing by `bridge/author.py` (draft→validate→accept)
  + `bridge/AUTHOR_PROMPT.md`. `raw` is the bespoke escape hatch (agent hands `{html,tl}`). Open gap: a
  `chart` template — must be **GSAP+SVG/CSS, not d3/Chart.js** (framework bans chart libs for seek-safety).
  - **Text-reveal vocabulary** (`reveal:` on `statement`, built 2026-07-09, ref gsapify.com "Text &
    Typography" saved to `bridge/_ref_reveals/gsapify_animations.js`): `char`/`word`/`flip` (transform
    staggers, seek-safe verbatim) + `typewriter`/`scramble`/`decode`/`glitch` (progress-driven — gsapify's
    `Math.random`/`setTimeout` versions rewritten as pure fns of timeline progress so they don't flicker/
    desync under frame-seek) + `gradient`, plus the unchanged `rise` default. Registry `compose.REVEALS`
    mirrored in `catalog.json`'s `reveals` section, honesty-tested by `check_catalog.py` (keys must match).
    Units split at BUILD into `.rv-u` spans; the operative yellow sweep still fires after the text lands for
    every style (`.hlwrap` got `isolation:isolate` so its negative-z highlight block stays in the split
    line's stacking context). Verified with `render-service/reveals_verify.mjs` (Puppeteer: `seek(t,false)`
    fires the onUpdate reveals, then proves each frame byte-identical on re-seek) → `videos/reveals-demo/
    snapshots/rv-*-at-*.png`. THE altitude for future text-effect additions: an option on a text block, not a new block.
    - **Robustly reusable** (2026-07-09 pass 2): the whole reveal is behind ONE entry point `reveal_text(el,text,style,
      start,cue,dur,operative?,base?) -> (inner_html, css_class, style_attr, tl_lines)` that EVERY text block calls;
      blocks never branch on the concrete style. Wired into `statement` (lines), `newshead` (headline — overrides the
      word-cascade), `comparison` (per-panel `text` titles), `stat` (labels; numerals keep count-up). Simple transform
      staggers live in the `_RV_STAGGER` data table, so adding a new stagger reveal = ONE table row; a new JS-driven one =
      one `_rv_entrance` branch + REVEALS/catalog entry — zero block edits either way. Wired-block demo:
      `videos/reveals-blocks/` (out/reveals-blocks-reel.mp4). Statement refactor is byte-identical to the inline version
      (determinism hashes unchanged). Reels via `render-service/render_reel.mjs` (frame-seq → ffmpeg, manifest-driven).
  - **`linedraw` block** (built 2026-07-09, gsapify "Line Drawing" cluster): a self-drawing LINE-ART SVG — each
    stroke's `stroke-dashoffset` animates length→0 in order at a **constant pen speed** (per-path time ∝ its
    `getTotalLength()`), so a line drawing renders as if hand-drawn (logos, blueprints, maps/routes, signatures,
    hand-drawn icons/schematics). No external lib: a setup IIFE measures each path ONCE at load and adds the draw
    tweens; `strokeDashoffset` is the framework's blessed seek-safe draw (same as geo/diagram/timeline). Input:
    `data.svg` (raw) | `paths[+viewBox]` | `src`; draw mode forces a uniform stroke (register-themed) + no fill,
    `keepStyle` respects the SVG's own styling, `ink` fades fills in after each stroke. `order` = dom | length-asc |
    length-desc. Demo `videos/linedraw-demo/` (signature + lightbulb, out/linedraw-reel.mp4); all seek-safe (verified
    byte-identical on re-seek). **Vector line-art is the slam-dunk.**
  - **Raster→line-art SPIKE** (`bridge/trace_spike.py`, 2026-07-09): raster PNG → `skimage.skeletonize` centerline →
    walk the 1px skeleton into polylines between endpoints/junctions → RDP-simplify → SVG paths → `linedraw`. Proven
    end-to-end + seek-safe (`videos/linedraw-demo/ld-traced`). **Verdict: feasible but rough** — closed loops (a sun
    circle) can break into an arc, thin strokes wobble, junctions fragment a continuous line into segments. Good enough
    for simple/forgiving art; NOT crisp enough for clean icon/logo work. To productionize: closed-loop handling,
    junction-aware path merging, spur pruning, bezier smoothing (or a real centerline tracer — `autotrace --centerline`;
    potrace traces OUTLINES not pen strokes). Kept as an OPTIONAL human-run preprocessor, not wired into the block.
  - **`timeline` block** (built 2026-07-08, ref YouTube XoC62NDH4aw "Vox stylized timeline"): drawing
    yellow spine + camera pan event-to-event + circular image cutouts (stroked ring draws) + big
    year/kicker. Two axes via `data.axis`: **`horizontal`** (default — spine L→R, camera pans X,
    alternating up/down elbow callouts) and **`vertical`** (spine top↔bottom, camera pans Y via
    `dir:"down"|"up"`, branches alternate left/right; **`solo:true`** = one graph on screen at a
    time at a fixed focus/playhead, previous slides out as next slides in, opposite side stays free
    for companion content — `solo_side` sets which side, default right). Seek-safe (transforms/opacity/strokeDashoffset).
    Demos: `videos/timeline-demo/` (horizontal, `out/timeline_demo_images.mp4`) + `videos/timeline-vertical/`
    (vertical, `out/timeline_vertical.mp4`); specs in `bridge/timeline_*_spec.json`; ref clip `_ref_timeline/ref.mp4`.
  - **`newshead` block** (built 2026-07-09, ref YouTube _HU37rX4G1U "Vox newspaper animation"): a
    newspaper headline card — dot-grid paper, red date tag, bold serif headline whose words cascade
    in with a yellow highlighter sweep, serif subhead (optional highlight), blackletter source
    masthead + drawn rule, optional framed grayscale photo sliding in + optional red hand-drawn
    arrow. `data:{date?,headline:[lines]|str,highlight?,subhead?,subhighlight?,source?,image?,caption?,arrow?,tilt?,image_tilt?}`
    (`tilt`=small card rotation°; `image_tilt`=extra photo rotation° relative to the card — "pinned askew").
    Two image modes: default framed grayscale photo, or **`cutout:true`** = a transparent-PNG subject
    (grayscale + red outline via 8-way drop-shadow) bleeding off the card's right edge (a card sibling, so
    the card's clip can't crop it). Make the PNG with `nolan cutout <img> -m birefnet -o <out>` then trim
    the alpha bbox / drop the product-shot reflection (PIL). Cutout demo: `videos/newshead-cutout/`
    (`out/newshead_cutout.mp4`, spec `bridge/newshead_cutout_spec.json`).
  - **`collage` block** (built 2026-07-09, ref clip `clip_985f7653` = a cut from "Samurai in Venice",
    fetched from the live hub `GET /api/library/clips`, DB `~/.nolan/library.db`): a kinetic COLLAGE —
    cut-out subjects (people/objects, transparent PNGs) scale/slide in **staggered** and assemble into a
    layered tableau on a backdrop, then hold (optional `camera:"push"` Ken-Burns). **Collage ≠ montage**:
    borderless cutouts composited into one scene, not framed photos on a table. Placement is explicit
    `x/y/scale` per subject OR a `layout` preset (`row`/`heroes`/`heroes-tight`/`cluster`/`scatter`);
    explicit overrides the preset (`heroes-tight` = close/big flanking subjects + an overlapping cast row →
    `videos/collage-heroes/`). `backdrop` is an input (color, default `#fff`; texture path; or `transparent`)
    + optional `vignette`. Subjects are `nolan cutout` PNGs (trim the alpha bbox — quality lives on cutout
    quality; isnet fragmented some objects, birefnet cleaner). Demo: `videos/collage-demo/`
    (`out/collage_demo.mp4`, spec `bridge/collage_demo_spec.json`); ref frames `_ref_collage/`.
    **Deferred options** (add in-place when a beat asks — don't fork a template; see the code comment in
    `collage()`): `parallax` (depth-driven idle drift tied to the camera push, still seek-safe) and
    `edge:"torn"` (ragged mask + paper lip). A FULL paper-craft look (tape/halftone/kraft/handwriting) is a
    different identity → its own `scrapbook` template, not a `collage` option.
    Demo: `videos/newshead-demo/` (`out/newshead_demo.mp4`); spec `bridge/newshead_demo_spec.json`;
    ref clip `_ref_newsheadline/ref.mp4`. Added Lora weights + UnifrakturMaguntia to the shared FONTS.
  - **`gallery` block** (built 2026-07-09, refs gsapify "Image & Gallery" `masonry-cascade` (035) +
    `staggered-grid-reveal`): a grid/masonry of FRAMED rectangular images (white-matte cards) that
    reveal in a deterministic staggered cascade (`from:center|start|edges|end`), then can **spotlight
    one** image — the hero scales up + lifts (raised z), the others dim + `filter:blur` = the
    "highlight a picture, background blurred" beat. Distinct identity from `collage` (borderless
    cut-outs) + `newshead` (single clipping). The gsapify recipes were re-expressed seek-safe: dropped
    `gsap.utils.random`/`from:'random'` (→ deterministic per-index tilt + center-out order) and the
    Ken-Burns `repeat:-1`; reveal is transform/opacity-only, the spotlight's blur is a deterministic
    seek-safe hold. `layout:masonry` column-packs varied heights + fit-scales into the grid box.
    `data:{images:[{src,caption?}|str], cols?, layout?, gap?, frame?, backdrop?, vignette?, from?,
    title?, titleHi?, captions?, highlight?, highlight_at?, highlight_caption?}`. Demo:
    `videos/gallery-demo/` (spec `bridge/gallery_demo_spec.json`; verified via `hyperframes snapshot`
    at 5 beats — `snapshots/contact-sheet.jpg`). **Deferred** (build in-place, don't fork): `highlight_zoom`
    (Ken-Burns push toward the hero), polaroid per-card resting tilt, multi-spotlight swap, a
    one-at-a-time `slideshow` mode (gsapify 037, un-looped).
    ⚠ Lint note: the shared `comparison` CSS comment contains a literal `<video>`, which the naive
    `hyperframes lint` HTML parser mis-tokenizes inside `<style>` → false `media_in_subcomposition` +
    `root_missing_*` on EVERY compose.py frame. Real Chrome parses `<style>` as raw text, so
    snapshot/render are unaffected; fix = de-literal the `<video>` token in that CSS comment.
  - **`carousel` block** (built 2026-07-09, refs gsapify "Carousels & Sliders" `parallax-slider` +
    `coverflow-3d`): the TEMPORAL cousin of `gallery` — steps through an ordered image set, one in
    focus (gallery = all-at-once grid; carousel = advance-through). Two `style`s: **`slider`**
    (full-bleed one-at-a-time; `transition:kenburns`(default, crossfade + slow alternating zoom drift)
    `|crossfade`) and **`coverflow`** (a 3D coverflow in a `perspective`+`preserve-3d` stage — centre
    card forward+scaled, neighbours angled back in Z; depth occlusion is by `translateZ`, NOT z-index).
    This retires the "deferred slideshow mode" that was parked under `gallery` — sequential lives here.
    Seek-safe re-expression of the gsapify recipes: dropped `repeat:-1` (the `infinite-loop` marquee)
    and click/Draggable advance (→ time-driven focus steps). `data:{images:[{src,caption?}|str], style?,
    transition?, hold?, backdrop?, vignette?, title?, titleHi?, captions?}`. Demos: `videos/carousel-slider/`
    + `videos/carousel-coverflow/` (specs `bridge/carousel_{slider,coverflow}_spec.json`; both
    snapshot-verified — `snapshots/contact-sheet.jpg`). Gotcha fixed in build: slider slides carry
    positive `z-index` for the crossfade, so `.carcap` needs `z-index:7` (above slides, below the
    `z-index:8` title) or captions render behind the slides.
    Iter-2 (feedback, 2026-07-09): `slider` gained **`layout:"cards"`** — a horizontal CARD SCROLL (a
    `.cartrack` of framed `.carcarditem`s translating X so the active card centres, neighbours peek,
    active scales up / rest dim); **coverflow** got a smooth distance **`fade`** (opacity `1-|off|*fade`,
    no hard cut) + **inputs for card size/position** (`card_w`/`card_h`/`spacing`/`depth`/`y`); and
    `.cartitle` got a `text-shadow` (legible over bright images; the yellow `.hl` opts out via
    `text-shadow:none`). Demos: `videos/carousel-cards/` (`out/carousel_cards.mp4`) + re-rendered
    `carousel-{slider,coverflow}` mp4s, all frame-verified from the ENCODED files. A static Linux
    ffmpeg/ffprobe (johnvansickle 7.0.2) is staged at `~/.local/hfbin` so `hyperframes render` now
    encodes mp4 IN WSL (~13s per 10s clip) — export it onto PATH.
    **Deferred** (build in-place, don't fork): `transition:"push"`/parallax-bg, `style:"strip"` (marquee
    — ONE linear x tween over a cloned track, NOT `repeat:-1`), `style:"deck"` (card toss), `focus`/dwell.
  - **Phase-1 Tier-1 converters** (built 2026-07-10, from `kb/registry-conversion-map.md` — HF catalog
    families → NOLAN blocks) — all four DONE + frame-verified:
    - **`lower_third`** — collapses HF's 12 lower-third profiles → 1 block + `style` (bar/box/underline…).
      BESPOKE-sized (not tokenised: fixed % geometry is the identity); tokenises only accent/text.
    - **`chart`** — the drawn GSAP+SVG bar/line chart `stat` never covered (`data-chart` family). Tokenised
      (bars = `--accent`, grid/labels = `--text`/`--rule`). Bar + line `kind`.
    - **`code`** — **29 native → 1** (5 code effects + 24 syntax-theme profiles). Python tokenises at BUILD
      time → pre-coloured spans (no browser highlighter); reveal is transform/opacity. **HYBRID theming**:
      syntax palette is a FIXED code-`theme` (monokai/vs-dark/vs-light/github-dark/dracula — identity), scene
      backdrop `--shell` + kicker/title NOLAN-themed. modes typing · highlight. Demos `videos/code-*`.
    - **`social_card`** (X · Reddit · Spotify; instagram/tiktok/yt/macos = deferred branches) — a post /
      now-playing overlay + `platform` param. **BRAND-FIXED palette** (Reddit `#ff4500` · X `#1d9bf0` ·
      Spotify `#1db954`, inline — identity, NOT NOLAN tokens: a Reddit card is always Reddit); only the
      scene backdrop is `--shell`-themed. Card slides+scales in; Spotify progress bar fills (`scaleX`).
      Demos `videos/soc_{x,reddit,spotify}/` — all frame-verified, seek-safe (0 Math.random/rAF/repeat).
    Theme-convention: **adaptive** blocks (stat/statement/chart…) read NOLAN tokens; **identity** blocks
    (code syntax, social brand) keep their signature palette and only theme the surrounding scene. The
    `theme_layout_audit` fit-warning is advisory for identity blocks (brand-fixed fonts can't overflow).
  - **Scene-transition primitive** (built 2026-07-10, the deferred "CSS transitions" track — HF
    cover/push/scale/dissolve family). NOT a block: an optional `transition_out: {kind, dur?, color?}`
    on the DEPARTING scene. `compose.TRANSITIONS` registry — `crossfade` · `slide_left`/`slide_right`/
    `slide_up` · `scale_out` · `fade_through` (dip-to-colour). An OUTGOING effect over the overlap window
    `[b, b+T]` after the scene boundary: `compose_frame` wraps each scene in a z-ordered `.scenewrap`
    (earlier scene ON TOP), extends the departing scene's boundary clips by `T` (`_extend_clip_dur`) so it
    stays mounted through the overlap, and animates the wrapper away (transform/opacity — **seek-safe**,
    literal CSS `transition:`/@keyframes stay banned) while the next scene does its own entrance underneath.
    Registry-driven like REVEALS: keys = `catalog['transitions']` (check_catalog enforces) + `author.py`
    gate validates `transition_out.kind`. **Backward-compatible**: a frame with no `transition_out`
    composes byte-identical (no wrappers). Verified `videos/trans_demo/` (crossfade + slide seams looked
    at mid-transition) + `videos/ft/` (fade-through dip). Wrapping `.clip` in a `<div>` does NOT break the
    runtime's mount/z (pitfall #5: z is DOM-order/z-index, not track-index) — confirmed by render.
- **`bridge/resolve_inject.py`** — NOLAN krea2/ComfyUI or stock → project `assets/` + ledger.
- **`bridge/pool.py`** — NOLAN acquisition fan-out → qwen-VL-captioned inventory HyperFrames selects from.
- **`bridge/inject_root_video.py`** — mounts stock b-roll `<video>` at the index HOST ROOT (archetype B) — the only legal path for motion footage (see §5).
- **`bridge/motion-palette.md`** — maps video-essay beat archetypes → HyperFrames' full vocabulary (36 rules · 15 blueprints · 24 text effects · 7 adapters).
- **`presets/highlighter-editorial/`** — a custom Vox-lineage frame preset; **`--preset-dir` is the confirmed custom-style seam.**
- Cuts: `videos/data-center-economics{,-vox,-final,-kit}/out/*.mp4` (the A/B ladder).

The agnostic NOLAN↔HF seams (from the skill-tree audit): the project **`assets/<basename>`** landing
dir + the **hyperframes-core clip-mount contract**. HyperFrames has NO single shared asset spine —
per-workflow plan dialects differ; a thin per-workflow "plan-writer" adapter bridges them.

---

## 13. Pitfalls that will actually bite you

1. **`<style>`/`<script>` must live INSIDE the `<template>`** for a sub-comp — the runtime only clones `<template>.content`; anything outside is discarded (tiny unstyled text top-left = this).
2. **Host slot `data-composition-id` must EXACTLY equal the sub-comp's inner `data-composition-id`** and the `window.__timelines` key — no `-mount`/`-slot` suffix, or you get the 45s timeout.
3. **`<video>`/`<audio>` at the root only** (§5). Never in a raw template subtree.
4. **Root needs a sized box**; a full-screen fill goes on a full-bleed *child* (`position:absolute;inset:0`), not the root — the producer can drop the root element's own `background` (frame renders black) even though preview looks fine. `lint`/`validate`/`inspect` do NOT catch these two — `snapshot` does.
5. **`data-track-index` ≠ z-order** (§3). Layer with DOM order / CSS `z-index`.
6. **Root `data-duration` is compile-time-locked** — scripts/variables can't change render length.
7. **Determinism bans are linted, not silent** — no `Date.now`/`Math.random`/`rAF`/`repeat:-1`, no tweening `display`/`visibility`, transforms+opacity only.
8. **Byte-reproducibility needs `--docker`** (Linux/headless-shell/deterministic-mode). Otherwise visually-identical, not SHA-identical — expected, not a bug.
9. **`captions.mjs` ships without the skin's font `@import`** (recurring NOLAN nit) — add a Google-Fonts `@import` to generated `captions.html`.
10. **Version skew**: `npx hyperframes` (published) can lag the `main` you're reading. If behavior contradicts the source, check the installed CLI version first.
11. **⚠ FFmpeg version → SILENT audio.** Rendering audio needs a MODERN ffmpeg on PATH. The bundled `render-service/node_modules/@ffmpeg-installer/win32-x64/ffmpeg.exe` is **from 2018** — the video encodes fine but the audio mix (`apad=whole_dur=…`) fails with `Audio mix failed — output will be video-only`, so you get a silent MP4 with **no error exit**. Stage a recent ffmpeg instead (e.g. `imageio_ffmpeg`'s v7.1: `D:\env\nolan\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe`) + the 2023 `@ffprobe-installer` ffprobe, both on PATH. Always `ffprobe` the output for an audio stream after a narrated render.

## 15. Proven end-to-end: a narrated essay beat (`videos/beat1-narrated/`)

Beyond isolated card demos, one **real script beat + real VO** runs the whole path: `inputs/script.md`
beat 1 ("The boom is real", 67.76s, `inputs/sec_0000.wav`) → 6 scenes authored to the narration
(`bridge/beat1_spec.json`: 3 `stat` + 2 `statement` + 1 `newshead` for the "Loudoun County cashes in"
citation) → validated by the `author.py` gate (6 templated, 0 bespoke) → composed → `index.html` mounts
the frame (track 1) with the **VO as a root `<audio>`** (track 10; media must live at the host root) →
rendered WITH audio → `out/beat1.mp4` (67.8s, h264 + aac 48k, verified: audio stream present, mean −23.6 dB).
Scene-level timing follows the narration (from the eval's whisper-tuned start/durs); within-scene cues
(count-ups, highlight sweeps) are hand-set — tight word-sync would want whisper word timings. This is the
"cards → actual narrated video" proof; the next step is the same via the compose-first faceless Step-5 worker.

---

## 14. Fast orientation checklist for the next agent

1. Read this note + `REPORT.md` + skim `bridge/compose.py`.
2. `GIT_LFS_SKIP_SMUDGE=1 git clone …/hyperframes` if you need internals; else just `npx hyperframes`.
3. Mental model = §0. Contract = §3. Render = §4–5. Gate = §8.
4. If the task is **reuse/scaling scenes** → resolve §7 first (empirically test multi-instance on `main`); pick composer vs. runtime-block path.
5. If **adding a scene type** → extend `compose.py` `BLOCKS` (§12) or author a registry block (§11); keep it GSAP+SVG/CSS, seek-safe, lint-clean (§8/§13).
6. Always: `lint` → `validate` → `inspect` → `snapshot` → look at frames → `render`. Verify like an editor (extract frames from the *encoded* mp4, not just preview).
