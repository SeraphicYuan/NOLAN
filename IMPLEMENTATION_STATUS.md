# NOLAN Implementation Status

**Version:** 0.1.0
**Status:** Complete
**Last Updated:** 2026-02-01

## Summary

NOLAN is a CLI tool that transforms structured essays into video production packages with scripts, scene plans, and organized assets ready for video editing.

## Publish — beautiful HTML articles, a second output medium (2026-06-28)

`src/nolan/publish/` turns a URL / document / pasted text into a self-contained,
**offline single-file HTML article** — the article twin of the video pipeline,
sharing NOLAN's ingest + agent-orchestration front-half. Authoring is driven by
the NOLAN-native **`beautiful-article`** skill (reacticle themes + figure library);
the deterministic scaffold/build runs the skill's scripts via WSL.

- **CLI**: `nolan publish <source> --theme press --type explainer [--width --images
  --brand --slug --review --no-cover]` → `projects/_published/<slug>/article/article.html`.
- **WebUI**: new **Publish** tab (`/publish`) — form (theme/type/width/images/brand/cover)
  → background job (`operations.publish_article`) → progress poll → in-page preview +
  open/download. Reuses the standard `NolanJobs` job widget; result served by `/publish/file`.
- **Single source of truth**: the skill owns the scaffold-template + figure library +
  scripts; `publish/toolkit.py` references them (removed the duplicate vendored `webkit/`).
- **Project model**: `projects.py` gained a `has_article` marker (kind `article`) so
  published articles appear in the unified project list.
- **Hardening**: `source.load_source` now fails loudly on a mistyped/unsupported source
  path instead of silently treating the path string as article body.
- **Verified**: toolkit tests 6/6 (real WSL build → 2.5 MB offline HTML, screenshot,
  source guard); full `nolan publish` e2e (agent authored 3 sections → offline article);
  UI wiring (routes, validation, path-traversal containment, real article served);
  `discover_projects` picks up published articles; project tests 11/11.

## Stock providers — keys + rate-limit safeguards (2026-06-27)

Enabled three keyed stock providers (config-only) and added rate-limit handling
to `src/nolan/image_search.py`:

- **Keys** in `.env`: `PIXABAY_API_KEY` (images + video), `UNSPLASH_ACCESS_KEY`
  (images), `PEXELS_API_KEY` (images + video). Wired already — `config.py`
  maps the env vars → `ImageSourcesConfig` → `ImageSearchClient`; no code change
  to enable.
- **`_RateLimiter`** (module-level singleton, thread-safe sliding window): per-
  *account* buckets so Pexels image+video (and Pixabay image+video) share quota.
  Limits: Unsplash 50/hr, Pexels 200/hr, Pixabay 100/60s. A provider over its
  limit is skipped; an HTTP 429 cools its bucket (≤5 min) instead of erroring.
- **Tiered fan-out**: `search_assets()` queries cheap/keyless + high-limit
  providers first and only falls through to tight-budget ones (`_DEFER_LAST`,
  i.e. Unsplash) when the first tier returns `< max_results`. An explicit
  `sources=` list is honored as a single tier. Explicit single-source `search()`
  still works; 429 → `[]`, other errors propagate as before.
- **Verified**: 8 logic tests (sliding window, shared bucket, 429 cooldown,
  tier short-circuit + fallback, explicit-source behavior) + live fan-out
  (53 image results from tier-0, Unsplash not queried) + live Pexels/Pixabay/
  Unsplash image & video searches.

## Picture Library — searchable image store (2026-06-25)

`src/nolan/imagelib/` — the still-image counterpart to the video library:
persistent, deduplicated, license-aware, with **CLIP semantic search** (text→image).
Acquisition results (search providers + link extractors) can now be warehoused
instead of dumped into ephemeral `.scratch/`.

- **`catalog.py`** `AssetCatalog` (SQLite): one row/asset with `content_hash`
  (dedup), `source`, `source_url`, `license`, dims, `tags`, `query`,
  `status` (active|rejected). **`embeddings.py`** `ClipEmbedder`
  (sentence-transformers `clip-ViT-B-32`, image+text shared space).
  **`store.py`** `ImageLibrary`: file storage + catalog + ChromaDB `images`
  collection; `add_file/add_url/add_result`, `search` (active+license filtered),
  `set_status` (reject de-indexes), `search_all` (global+project merge).
- **Scopes** (in-tree, gitignored): global `_library/images/`,
  project `projects/<name>/imagelib/`.
- **CLI**: `nolan images {search,add,list,reject,stats}`; plus `image-search
  --save [--scope --project]` to ingest results tagged with the query.
- **match-broll integration**: `match_broll_v2` searches the library (global +
  project) FIRST, vision-scores candidates on the same scale, and reuses one
  scoring ≥ `library_gate` before any external provider (`from_library` in result).
  Required making `AssetCatalog` thread-safe (`check_same_thread=False` + lock)
  since match-broll searches from a thread pool.
- **Hub UI**: `/images` gallery — browse/CLIP-search, scope + license filter,
  per-tile reject; thumbnails via `/api/images/raw`.
- **Verified**: 12 unit tests (`tests/test_imagelib.py`, incl. cross-thread) +
  `tests/test_hub_images.py` (endpoints) + live CLIP ("skeleton" vs "locomotive"
  rank their own images) + functional match-broll test (scene matched from
  library, external skipped). See `docs/PICTURE_LIBRARY_v1.md`.

## Asset Extraction — link → assets (2026-06-25)

`src/nolan/extractors/` — a new acquisition channel: give it a **page URL**, it
extracts the highest-definition images embedded/linked on the page. A registry of
parsers (site-specific first, generic HTML fallback last); each emits
`ImageSearchResult` so output flows into the existing scoring/download paths.

- **Parsers**: `gutenberg` (thumbnail-links-to-full illustrations), `wikimedia`
  (map `/thumb/.../NNNpx-Name.jpg` → original), `met` (object ID → collection API
  `primaryImage`), `archive` (Internet Archive item → metadata API → original
  images), `loc` (Library of Congress item → `?fo=json` → largest rendition),
  `iiif` (**one parser for all IIIF archives** — Presentation v2/v3 manifests +
  Image API `info.json` → `full/max`), `web` (universal: `<a href>`-wraps-`<img>`
  → largest `srcset` → `src`, plus `og:image`; resolves relatives, drops
  icons/tiny/data-URIs, dedups).
- **No new dep** — stdlib `html.parser` (`html_utils.py`).
- **Surfaces**: `nolan extract-assets <url> [-n N] [-o DIR] [--no-download]`
  (downloads to `.scratch/extracted/<host>/` + manifest); hub `/extract` page +
  `POST /api/extract-assets` (synchronous preview or `download:true` job).
- **Verified live**: Gutenberg 21790 → 50 illustrations (`illus-048.jpg` full-res,
  real 750×1178 @300 DPI download); Wikimedia original; Met API; IIIF v2/v3
  manifests + info.json; Internet Archive item; LoC item. 26 unit tests
  (`tests/test_extractors.py`, network-free). Note: IIIF is a delivery standard,
  not a search API, so it lives as an extractor (not an `image_search.py` provider).
  See `docs/ASSET_EXTRACTION_v1.md`.

## Scene Iteration — review → comment/edit → re-render (2026-06-25)

`src/nolan/iterate/` adds the human-in-the-loop gate: see scenes side-by-side, edit/
comment on a few, and **re-render only those** — for **both** pipelines (the linear
orchestrator and the asset-first segment builder), which share `scene_plan.json`.

- **One engine, two adapters** (`engine.py`): `detect_pipeline()` (segment via sibling
  `segment_meta.json`, orchestrator via `.orchestrator/` or `layout_spec`); `rerender_scenes(plan, ids)`
  invalidates only the named scenes' clips and re-renders/reassembles via each pipeline's
  existing path (segment reuses the skip-guarded `build_from_plan`; orchestrator re-renders
  the selected dicts → `annotate` → silent audio → `call_assemble`). Orchestrator plans are
  handled as **raw dicts** so `layout_spec` survives (the `Scene` dataclass would drop it).
- **Apply a comment OR a direct edit** (`revise.py`): `revise_scene(scene, note, client, pipeline)`
  turns a free-text note into a whitelisted field patch; a `motion_brief` is compiled to a
  validated `motion_spec` via `nolan.motion.compile_spec`. `apply_edit()` supports note-mode
  and direct-patch-mode, and dirties `rendered_clip` so the next re-render rebuilds it.
- **Re-resolve on edit:** changing `search_query`/`visual_type` clears the scene's cached
  `matched_clip`, and re-render re-runs the match stage for just those scenes (segment reuses
  the project-local index + escalation; orchestrator re-matches b-roll via `ClipMatcher` on
  raw dicts). So editing a query actually pulls a different library clip — not just a re-render.
- **CLI:** `nolan revise-scene <plan> <id> --note "…"` (agent) or `--set field=value` (direct);
  `nolan rerender <plan> --scenes id1,id2`.
- **Web UI (`/scenes`):** the read-only viewer is now editable — per-scene **select**,
  **Comment → agent** / **Edit fields** tabs, and a **Re-render selected** bar (background job).
  Project discovery now recurses so nested segment outputs (`<project>/segment_*/`) appear;
  a `/scenes/file` route serves both `clips/` (segment) and `assets/` (linear) previews.
- **Tests:** `tests/test_iterate.py` (14) — detection, invalidation, whitelist/motion-compile,
  selective re-render for both pipelines, re-resolve on query change (+ a hub TestClient smoke
  verified end-to-end).

## Experiments

### Asset-First Scene Building (2026-06-24)
Inverted pipeline prototype: take a slice of an existing script and **build scenes
from available assets** instead of script→scenes→match. Combined three sources —
segment search (archival b-roll), renderer cards (counter/title/lower-third), and a
ComfyUI hero still + Ken Burns — synced to the original voiceover.

- **What changed:** end-to-end demo that the legacy `nolan assemble` asset-priority
  path (`rendered_clip > generated_asset > matched_asset`) composes mixed asset types
  into a final mp4. Index now supports **project-local** DBs (`projects/<name>/index.db`).
- **Usage:** `projects/US Economy/experiment_roaring20s/` — `index_source.py` →
  `build_full.py` → `nolan assemble scene_plan.json vo.m4a -o final.mp4 -r 1920x1080`.
- **Result:** `final.mp4`, 1920×1080@30, 86s, 11 scenes, all sources verified.
- **Gaps surfaced:** no compositing/overlay in assemble, no animated line-chart
  renderer, crossfade transition is a stub. See the project's `findings.md`.
- **New workflow:** registered **`flux-dev`** (`workflows/image/flux-dev-fp8.json`,
  `flux1-dev-fp8`) and **`z-image-turbo`** (8-step, `basic-z-image.json`) — large
  photoreal upgrades over the SDXL `sdxl-default` default.
  Use via `get_registry().build_client('flux-dev', config)`.

### Renderer: compositing, charts, fades (2026-06-25)
Three additions that turn the cut-sequence essay into layered video-essay grammar
(all in the renderer layer; `nolan assemble` stays a dumb concatenator):

- **Compositing** — `BaseRenderer.render_frame_rgba()` renders a scene with a
  transparent background; `renderer/composite.py::composite_over_broll(overlay,
  broll, out, duration, fade=, scrim=)` overlays a counter / lower-third / title /
  caption *on top of* moving b-roll (ffmpeg `overlay`, with optional scrim for
  text legibility). Replaces full-screen black "stat cards."
- **Animated line chart** — `renderer/scenes/line_chart.py::LineChartRenderer`
  (exported as `LineChartRenderer` / `render_line_chart`): progressive polyline,
  green-up/red-down segments, leading dot + value readout, x-labels revealed as the
  line passes. Built for the market rise→crash→rally beat.
- **B-roll fades** — `render_b_roll` honors a per-scene `fade` (seconds) for gentle
  fade in/out on cuts; `composite_over_broll` takes the same `fade`.
- **Title auto-fit** — `BaseRenderer.fit_font_size()`; `TitleRenderer` shrinks long
  titles/subtitles to fit the frame instead of clipping.
- **Loop/feedback diagram** — `renderer/scenes/loop_diagram.py::LoopDiagramRenderer`
  (`render_loop_diagram`): labelled nodes on a circle with animated curved arrows
  forming a cycle. For systemic "X feeds Y feeds Z back to X" arguments. Composites.
- **Photo montage ("photos on a table")** — `renderer/scenes/photo_montage.py::PhotoMontageRenderer`
  (`render_photo_montage`): Polaroid-framed stills (white border + drop shadow + slight
  rotation) on a textured/vignetted surface, a slow Ken Burns camera, and one **hero card
  that slides in** with a **handwritten type-on caption**. For introducing historical
  figures / archival stills. Spec id `photo-montage` (python). Test: `scripts/test_photo_montage.py`.
  Reverse-engineered from clip analysis (`projects/_clips/clip_518fb653/effect_analysis.md`).
  Cards/hero accept `frame:"polaroid"|"cutout"` — `cutout` keeps a transparent PNG's
  irregular silhouette (alpha preserved) and the drop shadow follows it.
  For the **flexible/extensible** version with per-card motion control, use the Remotion
  `PhotoMontage` composition below (spec id `photo-montage-pro`).

Demo: `projects/US Economy/experiment_roaring20s/build_v2.py` → `final_v2.mp4`.

### Curated Remotion source (2026-06-25)
Python remains the default renderer; Remotion is used **only** within its strong scope
(kinetic typography, rich animated charts, SVG annotations, maps, premium cards — see
`docs/REMOTION_EVALUATION.md`). A proper static Remotion project lives in
`render-service/remotion-lib/` (real `.tsx`, not the code-generator) with a job-JSON →
`bundle`+`renderMedia` flow (`render.mjs`).
- **Built (9 compositions across categories 1–5):** `Kinetic` (kinetic-text), `BarCompare` +
  `KShape` (rich-chart), `AnnotateOverVideo` + `AnnotateStat` (svg-annotation), `RouteMap`
  (map), `PremiumCard` (premium card). Render ~5–9s each.
- **`PhotoMontage` (photo-montage-pro)** — flexible "photos on a table" with a **per-card
  motion system**: each card declares where it rests (`x,y,scale,rotation`) and how it
  arrives (`from` edge + `enterAt`/`enterDur`/`distance`/`ease`) independently — e.g. one
  slides up to center, one in from the left to rest on the left. Frame styles
  `polaroid`/`plain`/`cutout` (cutout = bare PNG alpha + silhouette `drop-shadow`),
  handwritten type-on captions, Ken Burns camera. Multi-image staging: `render.mjs` stages
  the `cards[].src` array + `background` into `public/` (mirrors the `segments` pattern).
  **Per-card keyframe tracks** (`card.keys: [{at,x?,y?,scale?,rotation?,opacity?,ease?}]`)
  fully drive a card's transform when present — each property tweens through only the keys
  that define it, enabling **appear-then-tilt**, **fade-in-then-fade-out**, and arbitrary
  **multi-step paths**; the `from` sugar remains for one-shot entrances. Tests:
  `scripts/test_photo_montage_remotion.py` (entrances), `scripts/test_photo_montage_stress.py`
  (keyframe tracks: delayed tilt / fade-out / complex path / layered sizes). 3D pan/tilt:
  per-card `rotX`/`rotY` (+`perspective`) — `rotation` is in-plane (rotateZ), `rotX/rotY` swing
  the card in 3D space (a "pan" vs a flat tilt); demo `scripts/test_photo_montage_pan.py`.
- **`PhotoGrid` (photo-grid)** — procedural grid choreography that scales to dozens of
  images: (1) N images **fly in** to fill a `cols×rows` grid, sequenced **one-by-one / by
  row / by col** (`order`); (2) one image (`focusIndex`) **zooms to center** while the rest
  of the grid **peters out**; (3) it **zooms back** and the grid returns. All per-cell motion
  is computed from grid shape + timings, so the input is just a flat image list. Reuses the
  multi-image staging + polaroid/plain/cutout frames. Test: `scripts/test_photo_grid.py`
  (40 real library images, 8×5).
- **Style system:** shared `theme` tokens (`src/theme.ts`: dark-editorial/light/high-contrast
  or override object) on every effect + per-effect style vars (`lineStyle`, `barStyle`,
  `shapeStyle`, `routeStyle`, `cardStyle`) + shared seeded path helpers (`src/shapes.ts`).
  See `render-service/remotion-lib/README.md`.
- **Wired as a source.** `visual_router.py` has a `remotion` route (`REMOTION_VISUAL_TYPES`
  maps `kinetic-text`/`bar-compare`/`k-shape`/`annotate-video`/`annotate-stat`/`route-map`/
  `premium-card` → composition ids; `RouteDecision.remotion_comp`). Discoverable registry at
  `remotion-lib/registry.json` (each comp's visual_type + style schema). Render bridge:
  `src/nolan/remotion_source.py` (`list_compositions`, `render`, `render_scene` — shells
  `render.mjs` via Node).
- **Showcase reel:** `Showcase` composition (`<Series>` of all effects + labels) →
  `remotion-lib/output/showcase.mp4` (~27s).

### Brief layer — authoring broll/motion from intent (2026-06-26)
`src/nolan/brief/` is the agent-facing authoring surface between the broll/scene-design
stage and the render engines. Principle: **the LLM does the semantic part, deterministic
code does the mechanical part, they meet at a small validatable _brief_.** The agent
authors ~8 JSON fields; a resolver compiles them to a validated `nolan.motion` spec.
- **`TimeRef`** (`timeref.py`) — symbolic time resolved against the scene transcript:
  `3.2` | `"start"/"end"/"mid"` | `{"cue":"keyword"}` (when the VO says it) | `{"frac"}` |
  `{"after","delay"}`. Reusable by **any** timed effect, not just photo.
- **`SceneContext`** (`context.py`) — duration + word-level narration timing + warnings
  sink; `from_scene(scene, words)` builds it from a Scene (transcript for cue matching).
- **`photo-story`** (`photo_story.py`) — first brief family. `layout:"grid"` → `photo-grid`,
  `layout:"free"` → `photo-montage-pro`. Motion **verbs** (`enter/fade/tilt/pan/tilt3d/
  move/path/zoom`) compile to keyframe tracks, so the agent never writes `keys`/perspective.
- **`resolve_brief(brief, ctx)`** (`resolve.py`) → `(validated spec, messages)`; registry
  `BRIEF_REGISTRY` for new families. **Boundary:** cue→time resolves at *design time*
  (where the transcript lives); the resolved spec is persisted on the scene, render stays
  context-free. Graceful: missing cue/image/verb → warn + best-effort spec, never crash.
- **Wired into the scene-edit router** (`iterate/revise.py`): the LLM gate returns a
  `photo_brief` object for montage/grid notes, resolved against the scene's narration →
  `motion_spec`. Verified with a **real LLM + real comment** end-to-end ("6 pics, 2×3 grid,
  zoom the 4th when VO says 'keyword'" → `photo-grid`, focusIndex 3, focusAt 3.2s, rendered):
  `scripts/test_router_brief.py`. Brief-unit test: `scripts/test_brief.py`; design doc:
  `docs/BROLL_BRIEF.md`.
- **Asset binding (the input half):** each scene carries an asset **tray**
  (`scene.assets:[{id,kind,src,label?,thumb?,place?}]`). A comment references it by id/label
  ("grid of these, zoom the Knight") instead of pasting paths; the revise gate sees the tray
  and emits `images:[{ref:'<id>'}]`, dereferenced to the bound src (+ `place`/`scale`/`label`).
  UI: a `/scenes` **Assets** tab with a slide-in **picker drawer** — tabs Pictures (browse
  `/api/images/list` + CLIP search) and Videos/Clips (`/library/api/clips`, thumbnails via
  `/scenes/api/frame-thumb`), multi-select → add; tray cards show kind badge + remove + 3×3
  `place` picker. Backend op endpoint `POST /scenes/api/scene/assets` (add image/clip/path,
  remove/reorder/set_place/set_label), non-render-invalidating; resolver kind-validates (clip
  refs warn — video-in-montage is TODO C). **Spatial control** is offered only for declarative fields (place),
  never keyframes — those stay comment-driven. Tests: `scripts/test_asset_binding.py` (+ real
  LLM, hub TestClient capstone); hub/CLI cue timing fed by `iterate.scene_words` (cached VO transcript).

### Motion-spec system — natural language → render (2026-06-25)
`src/nolan/motion/` translates a one-line scene design into a precise, validated render
spec and renders it on the right backend (Python renderer or Remotion). A declarative
**registry** is the single source of truth.
- `registry.py` — 16 effects across categories/both backends; **shared params**
  (`position`/`theme`/`accent`) declared once, each effect lists its own content/style
  params + which shared params it supports. Add params here over time.
- `manifest.py` — builds the LLM capability manifest + prompt guide from the registry.
- `spec.py` — validate/normalize (effect/required/enum checks, fills defaults, coerces types).
- `compiler.py` — `compile_spec(scene, client)` (LLM + one repair retry).
- `executor.py` — `render(spec, out)` dispatches Python (`renderer.scenes`) vs Remotion
  (`remotion_source`); `position` normalized to `{x,y}` for both.
- API: `from nolan.motion import author`. Example: `examples/motion_author.py` (6 scenes,
  both backends, LLM-authored complex content like chart bars / loop nodes).
- **Solves** the "one script per location" problem: `position` (and style) are parameters
  the LLM sets. Known refinements: clamp wide content to a safe area; map `theme` onto Python
  renderers; add `timing`/motion as the next shared param; vision-grounding for placing
  annotations *on b-roll content*.
- **Integrated into the pipeline (2026-06-25):**
  - *Scene designer* — `SceneDesigner.author_motion(scenes)` + `design_full_plan(..., author_motion=True)`
    attach a `motion_spec` to graphic/text/data scenes (skips b-roll/generated). New `Scene.motion_spec`
    field (serialized). Orchestrator `render_scene` renders `motion_spec` first (Python or Remotion).
  - *Clips "Analyze effect"* — `webui/operations.py::_effect_task_markdown` now lists **both backends**
    (`_motion_catalog_md()` generated from the registry), so the recreation agent treats Remotion as a
    first-class source and is told to add a `MotionEffect(... backend=...)` row when implementing.

### build-from-segment — wrap the validated pipeline (2026-06-25)
`src/nolan/segment/` turns a segment into a ~1-min essay via the asset-first pipeline.
CLI: `nolan build-from-segment`.
- **Inputs (3):** indexed-source span (`--source --start --end`, slices VO+SRT), `--script`
  (+ optional `--vo`), or `--vo` (whisper-transcribed). → `inputs.py`.
- **Stages:** design (`SceneDesigner` + `author_motion`) → timing (`assign_timing`, proportional)
  → **resolve** (`resolver.AssetResolver`: motion for graphics, segment-search for footage above a
  threshold, else escalate to external→ComfyUI→black; records `Scene.resolved_source`) →
  render (`render.py`: motion / b-roll extract+fade / ComfyUI+KenBurns) → `nolan assemble`.
- **Modes:** `auto` (one shot) and `review` (stops after resolve with a per-scene source manifest;
  edit `scene_plan.json` then `--from-plan` to resume).
- **P2:** search threshold + escalation, external-footage hook, `suggest_spans` (LLM).
  **P3:** `--music` bed (ducked mix), `--transition` pass-through, `tts_fn` hook.
- **Tests:** `tests/test_segment_builder.py` (9, mocked — resolver routing, timing, SRT/inputs,
  both modes, suggest, external, TTS). Verified real CLI build (script → motion scenes → `final.mp4`).

## Implemented Features

### Core Pipeline
- **Essay Parser** - Extracts sections from markdown essays
- **Script Converter** - Converts essays to YouTube-style narration using Gemini API
- **Scene Designer** - Generates visual scene plans with asset suggestions

### Infrastructure
- **Configuration System** - YAML + environment variable configuration
- **Text LLM (configurable)** - `create_text_llm(config)` factory; default
  **qwen/qwen3.7-plus via OpenRouter** for all authoring tasks (script, scenes,
  clustering, inference, translation). Override via `nolan.yaml` `llm:` block,
  the Settings page, or per-run (`llm_provider`/`llm_model`). `OpenRouterLLM`
  (text) + `GeminiClient` both implement `generate(prompt, system_prompt)`.
- **Gemini LLM Client** - Async client for Gemini API
- **Video Indexer** - SQLite-backed video library indexing with visual analysis
- **Asset Matcher** - Matches scenes to indexed video library
- **Project Registry** - Organize videos by project with human-friendly slugs
  - Projects have unique IDs (internal) and slugs (CLI-facing)
  - Index videos scoped to specific projects
  - Search and filter by project

### Hybrid Indexing
- **Vision Provider** - Switchable vision models (Ollama/Gemini/OpenRouter)
  - Default: qwen3-vl:8b via Ollama
  - Configurable host/port/model
  - OpenRouter provider (OpenAI-compatible) gives access to any vision model
    on OpenRouter, e.g. `qwen/qwen3.7-plus`. Set `OPENROUTER_API_KEY` in `.env`
    and run `nolan index --provider openrouter` (model via `vision.model` in
    `nolan.yaml`). Shares the exact analyze-frame prompt + JSON parser with
    Gemini, so results are directly comparable across providers.
  - Reasoning control via `vision.reasoning_enabled` (default off) + optional
    `vision.reasoning_max_tokens`. Disabling reasoning on models like
    `qwen/qwen3.7-plus` cuts latency ~4-6x (~35s→~6s/frame) with no quality loss.
- **Smart Sampling** - 5 strategies for frame extraction:
  - FFmpeg scene detection (default - 10-50x faster, hardware accelerated)
  - Hybrid (Python-based, combines time bounds with scene detection)
  - Fixed interval
  - Scene change detection (OpenCV)
  - Perceptual hashing (skip duplicates)
- **Transcript Alignment** - SRT/VTT/Whisper JSON support (read as UTF-8, handles Chinese)
  - **Subtitle-first, Whisper-fallback**: downloads English + Chinese subtitles
    (`subtitle_langs` defaults to en + zh variants); uses a downloaded subtitle when
    present, and only transcribes with Whisper when none is found. WebUI ingest wires
    this fallback by default (`whisper_fallback`).
  - **UTF-8 mode required on Windows**: run the hub/CLI with `-X utf8` (the launcher
    does this). Otherwise ffmpeg subprocess output is decoded as cp1252, which crashes
    the reader thread and corrupts scene detection (fewer segments).
- **Segment Analyzer** - LLM fusion of visual + audio with inferred context

### Whisper Integration
- **Auto-Transcription** - Generate transcripts for videos without them
  - Uses faster-whisper (4x faster than openai-whisper)
  - Multiple model sizes: tiny, base, small, medium, large-v2, large-v3
  - GPU acceleration (CUDA) with automatic CPU fallback
  - Voice activity detection (VAD) filtering
- **Audio Extraction** - Automatic via ffmpeg
- **Caching** - Saves generated transcripts as .whisper.json files

### Hybrid Inference
- **Combined Vision+Inference** - Single API call for frame analysis (50% fewer API calls)
  - Vision model sees both image AND transcript together
  - Better inference: can recognize faces, read on-screen text
  - Returns frame_description + combined_summary + inferred_context
  - Falls back to simple description for non-Gemini providers
- **Inferred Context** - Best guesses for:
  - People (named characters, speakers, face recognition)
  - Location (setting identification from visuals and audio)
  - Story context (narrative description)
  - Objects (notable items)
  - Confidence level (high/medium/low)

### Scene Clustering
- **Segment Grouping** - Cluster continuous segments into story moments
  - Groups by shared characters/people
  - Groups by shared location
  - Groups by similar story context
  - Configurable time gap threshold
- **LLM Story Boundary Detection** - Optional refinement using LLM
  - Detects narrative beat changes
  - Splits clusters at story boundaries
- **Cluster Summaries** - LLM-generated summaries for each cluster
  - Captures what's happening in the story moment
  - Identifies key characters/elements
  - Describes emotional/narrative significance

### Semantic Search
- **Vector Database** - ChromaDB for semantic similarity search
  - Stores embeddings for segments and clusters separately
  - Persistent storage alongside SQLite database

## Recent Indexing Improvements (2026-01-17)
- **Concurrency Default** - Indexing defaults to 25 concurrent calls (configurable via `indexing.concurrency`).
- **Bulk Segment Inserts** - Segments are inserted per video in batch for faster DB writes.
- **Frame Analysis Cache** - Cached results by `(fingerprint, timestamp, transcript_hash, inference_enabled)` to reuse on reindex.
- **Transcript Alignment Cache** - Cached aligned transcript slices per `(fingerprint, transcript_hash, timestamps_hash)`.
- **Rate-Limit Backoff** - Short exponential backoff on Gemini rate-limit errors (429/resource_exhausted).
- **FFmpeg Batch Extraction** - FFmpeg scene sampler extracts frames in batches per process for fewer spawns.
- **Path Refresh** - Video path/project is updated even when reindex is skipped.

## Recent Clip Matching Improvements (2026-01-17)
- **Parallel Matching** - Scene matching runs with bounded concurrency (`clip_matching.concurrency`).
- **Rate-Limit Backoff** - Retries LLM selection on 429/resource_exhausted errors.
- **Better Selection Context** - LLM prompt now includes the merged search query.
- **Deterministic Fallback** - LLM parse failures fall back to highest-similarity candidate.
- **No-Match Logging** - Clear messages when candidates are filtered out by similarity.
- **Two-Stage Search** - Cluster-first search narrows segment results when `search_level=both`.
- **Candidate Deduping** - Removes duplicate segment candidates across sources.
- **Dominant-Match Fast Path** - Skips LLM when top similarity is clearly ahead.
- **Deterministic Tie-Breaking** - Pre-LLM ranking uses similarity, transcript presence, and duration fit.
- **LLM Selection Cache** - Per-run cache for scene+candidates avoids repeated LLM calls.

## Codebase Refactoring (2026-01-31)

### File Organization
- **Scratch Directory** - All temporary/test outputs use `.scratch/` directory
  - Updated 5 CLI commands with problematic default paths
  - Added `.scratch/` to `.gitignore`
  - Prevents test files scattering in project root

### Models Package
- **Centralized Data Models** - Extracted dataclasses to `nolan/models/` package
  - `InferredContext` - Visual + audio analysis results
  - `VideoSegment` - Indexed video segment data
  - `SceneCluster` - Grouped segments representing story moments
- **Backwards Compatibility** - Re-exports in original modules maintain API stability
- **Type Hints** - Using `TYPE_CHECKING` imports to avoid circular dependencies

### CLI Package
- **Hybrid Approach** - Created `nolan/cli/` package with backwards-compatible entry point
  - `cli_legacy.py` - Original CLI preserved (4,478 lines)
  - `cli/__init__.py` - Entry point re-exports from legacy
  - `cli/utils.py` - Shared utilities for future command modules

### Downloaders Package
- **Shared Utilities** - Created `nolan/downloaders/` package with common code
  - `sanitize_filename()` - Safe filename generation
  - `extract_lottie_metadata()` - Parse Lottie JSON metadata
  - `save_lottie_json()` - Save with minification
  - `RateLimiter` - Request rate limiting for APIs
  - `CatalogBuilder` - Generate catalog JSON files
- **Base Models** - Shared template dataclasses
  - `BaseLottieTemplate` - Common fields for all sources
  - `JitterTemplate`, `LottieflowTemplate`, `LottieFilesMetadata` - Source-specific
- **Updated Downloaders** - Jitter, LottieFiles, Lottieflow use shared utilities
- **New Tests** - 20 tests for shared downloader utilities

### HTTP Client Module
- **Shared HTTP Utilities** - Created `nolan/http_client.py` for consolidated HTTP access
  - `get_async_client()` - Pre-configured async httpx client
  - `get_sync_client()` - Pre-configured sync httpx client
  - `fetch_json_async()` / `fetch_json_sync()` - JSON fetch helpers
  - `download_file_async()` / `download_file_sync()` - File download helpers
  - `ServiceClient` - Base class for service-specific API clients
  - Default timeouts (30s read, 10s connect)
  - Default User-Agent header
  - Connection pooling support
- **New Tests** - 23 tests for HTTP client utilities

### New Test Coverage
- **test_aligner.py** - 23 tests for audio-scene alignment
  - Text normalization (unicode, punctuation, whitespace)
  - Word stream search (exact, fuzzy, case-insensitive)
  - Scene alignment algorithms
- **test_image_search.py** - 18 tests for image search
  - ImageSearchResult dataclass and scoring
  - ImageProvider base class
  - DDGSProvider implementation
- **test_clip_matcher.py** - 18 tests for clip matching
  - ClipCandidate and MatchResult dataclasses
  - Deduplication logic
  - Cache key generation
  - Project-level filtering support
- **BGE Embeddings** - BAAI/bge-base-en-v1.5 model (768 dimensions)
  - Query-document asymmetry support for better retrieval
  - Local inference (~440MB model download)
  - Combines visual descriptions, transcripts, and context
- **Search Levels** - Configurable granularity
  - `segments` - Individual video segments
  - `clusters` - Story moment clusters
  - `both` - Combined results (default)
- **Incremental Sync** - Only re-embeds changed videos
  - Uses `indexed_at` timestamps to detect re-indexing
  - Auto-triggered after `nolan index` completes
  - Use `--force` to re-embed everything
- **CLI Commands**
  - `nolan sync-vectors` - Sync SQLite index to ChromaDB
  - `nolan semantic-search <query>` - Natural language search

### Integrations
- **ComfyUI Client** - Image generation via local ComfyUI API
- **Viewer Server** - FastAPI-based local viewer for reviewing outputs
- **Library Viewer** - Web UI for browsing indexed video library (`nolan browse`)
  - Keyword and semantic search modes with toggle
  - Project filtering support
- **Scene Plan Viewer** - A/B column viewer for scene plan review (`/scenes` route)
  - Left column: Scene details (ID, timing, narration, type, query/prompt)
  - Right column: Asset preview (image/video with lightbox)
  - Section and status filters
  - Audio sync with range playback (play single scene, loop option)
  - Click timestamp to play that scene's audio range

### CLI Commands
| Command | Description |
|---------|-------------|
| `nolan script <essay.md>` | Step 1: Convert essay to narration script |
| `nolan design <script.json>` | Step 2: Design visual scenes from script |
| `nolan process <essay.md>` | Full pipeline: essay → script → scenes |
| `nolan index <video_folder>` | Index video library for snippet matching |
| `nolan export <video>` | Export indexed segments to JSON |
| `nolan cluster <video>` | Cluster segments into story moments |
| `nolan browse` | Browse indexed video library in web UI |
| `nolan serve` | Launch local viewer to review outputs |
| `nolan generate` | Generate images via ComfyUI |
| `nolan generate-test` | Quick single-image generation for testing |
| `nolan image-search` | Search for images from web/stock photo APIs |
| `nolan match-broll` | Batch search and download images for b-roll scenes |
| `nolan match-clips` | Match scenes to video library clips using semantic search |
| `nolan transcribe` | Transcribe audio/video to SRT/JSON/TXT |
| `nolan align` | Align scene plan to audio with word-level timestamps |
| `nolan render-clips` | Pre-render animated scenes to MP4 clips |
| `nolan assemble` | Assemble final video from scenes + audio |
| `nolan infographic` | Generate infographics via render-service |
| `nolan yt-download` | Download YouTube videos using yt-dlp |
| `nolan yt-search` | Search YouTube for videos |
| `nolan yt-info` | Get information about a YouTube video |
| `nolan projects create` | Create a new project with slug |
| `nolan projects list` | List all registered projects |
| `nolan projects info` | Show project details and videos |
| `nolan projects delete` | Remove a project from registry |
| `nolan sync-vectors` | Sync video index to ChromaDB for semantic search |
| `nolan semantic-search` | Semantic search across video library |
| `nolan showcase` | Launch Motion Effects Showcase UI |
| `nolan library` | Launch Video Library Viewer UI |
| `nolan hub` | Launch unified NOLAN Hub (Library + Showcase + Scenes) |

### ComfyUI Integration
- **Custom Workflows** - Load any ComfyUI workflow (API format)
- **Auto-detection** - Finds prompt nodes automatically
- **Explicit Node Selection** - `-n "node_id"` for reliable prompt injection
- **Parameter Overrides** - `-s "node_id:param=value"` for any workflow parameter
- **Config File** - `nolan.yaml` for port and other settings

### Image Search
- **Multi-Provider Support** - Extensible provider system
  - DuckDuckGo (no API key required)
  - Pexels (requires API key)
  - Pixabay (requires API key)
  - Wikimedia Commons (no API key, public domain/CC)
  - Smithsonian Open Access (requires API key, CC0)
  - Library of Congress (no API key, public domain)
- **JSON Output** - Results saved with URLs, thumbnails, dimensions, license
- **Search All** - Query multiple sources at once with `--source all`
- **Vision Model Scoring** - Score images by relevance using AI
  - OpenRouter (default: `qwen/qwen3.7-plus`, reasoning off) — used by both
    `image-search --score` and `match-broll --score`
  - Gemini vision model (cloud, fast)
  - Ollama vision model (local, requires running Ollama)
  - Scores from 0-10 with explanations
  - Results sorted by relevance

### Video Assembly Pipeline
- **Unique Scene IDs** - Section-prefixed IDs (`Hook_scene_001`, `Context_scene_002`)
  - Prevents asset file collisions across sections
  - Automatically applied during scene design
- **Timeline-Aware Assembly** - Matches video duration to audio
  - Sorts scenes by start time from audio alignment
  - Fills gaps between scenes with black frames
  - Total video duration matches voiceover exactly
- **Format Handling** - Robust image format support
  - SVG to PNG conversion (via cairosvg)
  - AVIF/HEIC detection and conversion (via Pillow)
  - Handles mismatched file extensions
- **Asset Priority** - Smart asset resolution per scene
  1. `rendered_clip` - Pre-rendered MP4 (highest priority)
  2. `generated_asset` - AI-generated image
  3. `matched_asset` - Downloaded b-roll
  4. `infographic_asset` - Rendered SVG
  5. Black frame (fallback for missing assets)

### Motion Effects Library
- **Effects Registry** - Centralized catalog of motion effects for video essays
  - Organized by category: image, quote, statistic, chart, title, map, etc.
  - Each effect maps to underlying engine (Remotion, Motion Canvas, Infographic)
  - LLM-friendly descriptions for automated scene generation
- **Effect Presets** - Ready-to-use motion patterns with sensible defaults
  - `image-ken-burns` - Classic documentary pan/zoom
  - `image-zoom-focus` - Zoom to detail reveal
  - `image-parallax` - 2.5D depth parallax layers
  - `quote-fade-center` - Elegant centered text
  - `quote-kinetic` - Kinetic typography sequences
  - `chart-bar-race` - Animated bar charts
  - `stat-counter-roll` - Number counter animation
  - `title-card` - Full-screen title cards
  - `map-flyover` - Geographic pan/zoom
  - `light-leak` - Organic light leak and film burn overlay
  - `camera-shake` - Handheld camera shake for tension/urgency
  - `compare-before-after` - Before/after slider wipe transition
  - `text-pop` - Word-by-word text reveal animation
  - `source-citation` - Citation cards for sources
  - `screen-frame` - Browser/phone/laptop mockup frames
  - `audio-waveform` - Animated audio visualization
  - `zoom-blur` - Speed zoom with radial motion blur
  - `glitch-transition` - Digital glitch with RGB split
  - `data-ticker` - CNN-style scrolling news ticker
  - `social-media-post` - Twitter/social media post mockup
  - `video-frame-stack` - Grid/stack of video thumbnails
- **Showcase UI** - Web interface for browsing and generating effects
  - Gallery view with category filtering
  - Live parameter form for each effect
  - Image upload support
  - Preview generation with render service
  - Accessible at `nolan showcase` or via unified hub
- **Unified Hub** - Single entry point at `nolan hub` combining:
  - Video Library browser (`/library`)
  - Motion Effects Showcase (`/showcase`)
  - Scene Plan Viewer (`/scenes`) with dynamic project selection
  - Landing page shows all projects as clickable cards
  - Projects auto-discovered from `--projects` directory (default: `projects/`)
  - Project dropdown in scenes viewer for quick switching
- **API Endpoints**
  - `GET /effects` - List all effects with parameters
  - `GET /effects/:id` - Get specific effect details
  - `POST /render` - Render with `{effect, params}` format
- **Full-loop webUI (v1)** — hub now operates the pipeline from the browser, not just browse:
  - **Project Studio** (`/studio`) — per-project stage view: source → script/scenes → match assets → render/assemble, each with status + action buttons
  - **Add to Library** (`/library/add`) — index a file or YouTube URL with vision provider/model/reasoning picker
  - **New from Essay** (`/process`) — essay → script → scene plan
  - **Settings** (`/settings`) — vision provider/model/reasoning, persisted to nolan.yaml
  - In-process **job manager** (`webui/jobs.py`) + `/api/jobs/{id}` polling; shared `static/` theme + nav + job widget
  - Endpoints: `/api/ingest`, `/api/process`, `/api/match`, `/api/render-clips`, `/api/assemble`, `/api/sync-vectors`, `/api/project/{name}/status`
  - See `docs/WEBUI_ROADMAP_v1.md`
- **ComfyUI / Generation page** (`/comfyui`) — manage multiple generation models, each with its own
  workflow. Backed by a **WorkflowRegistry** (`workflow_registry.py`, `workflows/registry.json`):
  named entries `{file/builtin, checkpoint, prompt_node, w/h/steps, styles}`. Page shows ComfyUI
  connection + installed checkpoints + queue, lists/adds/deletes workflows (paste/upload a
  "Save (API Format)" JSON → prompt node auto-detected), and a **sample runner** (prompt → image →
  scratch preview in `samples/`). Generation (`/api/generate`, Studio) selects a registered workflow.
  Endpoints: `/api/comfyui/status`, `/api/comfyui/workflows` (GET/POST/DELETE), `/api/comfyui/sample`.
- **One-click launcher** - `start_webui.bat` (project root) builds + starts the
  render service (`:3010`) and launches the Hub on `:8011` in its own window,
  then opens the browser. Note: Hub uses `:8011` (not the default `:8001`,
  which is reserved by SPARTA). The Showcase tab requires the render service.

### Manual Clips (2026-06-24)

Cut a snippet from any indexed video by hand, save it as a reusable **clip
asset**, and materialize it on demand for a downstream consumer.

- **Data model** — schema **v7** adds a `saved_clips` table (`indexer.py`). A
  clip is a `matched_clip`-shaped **pointer** (`source_video_path` + `clip_start`
  /`clip_end` + `label`/`tags`/`project_id`), not a file. `project_id` NULL = global
  library. Methods: `add_saved_clip` / `list_saved_clips(project_ids=…)` /
  `get_saved_clip` / `delete_saved_clip`. v6→v7 migrates in place (segments preserved).
- **Cut UI** — the Library player (`/library`) gains Set In / Set Out / Preview /
  Clear / Save controls, reusing the existing loop-preview. Saving POSTs
  `/library/api/clips`. Cut from an auto-segment **or** the whole video via the
  **✂ Cut from full video** button (free scrubbing, no segment needed). A pending
  In/Out selection is kept **per video** — it survives closing the panel and
  switching videos, and the clip is saved against the video actually in the
  player (correct even for cross-project search results).
- **Clips page** (`/clips`, `clips.html`) — cross-project search across **saved
  clips + auto-snippets (segments/clusters)** with a **project-scope multi-select**
  ("all" or pick a list). `search`/`search_clusters` gained a `project_ids` arg for
  `IN (…)` scoping. Each result can be previewed, saved, or materialized.
- **Materialize on demand** (`operations.materialize_clip`, `/library/api/clips/{id}/materialize`)
  produces the form the consumer needs and caches it under `projects/_clips/<id>/`:
  `none` (pointer → video essay), `file` (.mp4 → ComfyUI), `frames` (JPGs → Claude).
  Cached results are reused unless `force`.
- **Analyze effect via Claude agent** — the Clips page "🎬 Analyze effect" button
  (`POST /library/api/clips/{id}/analyze-effect`, `operations.analyze_effect`)
  materializes the clip's frames + file, writes a task brief to
  `projects/_clips/<id>/effect_task.md`, and dispatches it to a **selectable tmux
  Claude Code agent** (the Clips page has an agent dropdown populated from
  `GET /library/api/tmux-sessions`, defaulting to `nolan2`; dispatch via
  `tmux send-keys`, `wsl.exe tmux` from the Windows hub).
  The agent identifies the effect, **dedups against the motion library**
  (`renderer/scenes/`, `renderer/effects.py`, `render-service/src/effects/`),
  assesses replicability, and writes findings to `effect_analysis.md`
  (readable via `GET /library/api/clips/{id}/analysis`, shown by the page's
  "View findings" button).
- Clips-page result handlers are **index-based** (read paths from stored result
  objects) so Windows file paths with backslashes aren't corrupted by inline
  HTML/JS string parsing — this fixed broken Preview/Save buttons.
- Endpoints: `GET/POST /library/api/clips`, `DELETE /library/api/clips/{id}`,
  `GET /library/api/clips/search`, `POST /library/api/clips/{id}/materialize`,
  `POST /library/api/clips/{id}/analyze-effect`, `GET /library/api/clips/{id}/analysis`,
  `GET /library/api/tmux-sessions`.

  *Usage:* open `/library`, play a video, Set In/Out, Save → switch to `/clips`,
  pick a project scope, search, then "Materialize file/frames" for downstream use.

### Script Styles — transcript corpora → style guides (M1, 2026-06-25)

Learn script-writing *craft* from reference transcripts and distill a reusable
**style guide**, then later write new scripts in that voice. The writing-side
mirror of the Clips/effects (visual-craft) feature.

- **Store** (`src/nolan/script_style.py`, `ScriptStyleStore`) — file-backed under
  `script_styles/<id>/`: `manifest.json`, `corpus/<slug>.txt`, `per_transcript/<slug>.json`,
  `style_guide.md`. CRUD + `add_source` with **video_id dedup** so repeat fetches
  skip known videos.
- **Acquisition** — paste text, upload `.txt/.srt/.vtt` (parsed via `TranscriptLoader`),
  or a list of **YouTube links**: `YouTubeClient.fetch_transcript` pulls the
  **original-language transcript only** (yt-dlp `skip_download`, single best track —
  no video, no auto-translations), reusing the 429-safe language picker.
- **Analysis (hybrid, Stage B)** — `operations.analyze_style`: inline LLM
  (`create_text_llm`) extracts per-transcript features (JSON), then dispatches a
  **synthesis task to a selectable tmux Claude agent** which authors
  `style_guide.md` (Voice, Hook patterns, Narrative structure, Pacing, Rhetorical
  devices, Do/Don't, Exemplars, and a copy-pasteable "How to Apply" block).
- **UI** — `/script-styles` page: style library (left) + per-style detail (add
  transcripts → analyze → view guide), with an agent-session dropdown.
- Endpoints: `GET/POST /api/script-styles`, `GET/DELETE /api/script-styles/{id}`,
  `POST .../{id}/add-text|upload-file|add-youtube|analyze`, `POST .../{id}/remove-source/{slug}`,
  `GET .../{id}/guide`.
- **M2 (done, 2026-06-25) — apply a guide to script generation:**
  `ScriptConverter` (`script.py`) takes an optional `style_guide`; its
  `extract_style_instruction` pulls the guide's "How to Apply" block (fallback:
  whole guide) and injects it as the **system prompt**, plus a per-section
  instruction to write in that voice. `process_essay` accepts `style_id` (loads
  the guide from the library); the **New-from-Essay wizard (`/process`)** has a
  "Script style (optional)" dropdown listing styles that have a guide.
- **M3 (done, 2026-06-25) — channel acquisition:** `YouTubeClient.list_channel_videos`
  (flat enumeration of a channel's /videos tab; accepts @handle, UC… id, full URL,
  or bare handle via `channel_videos_url`) + `operations.fetch_channel`. Two modes:
  **last-N** (newest videos) and **date window** (`date_after`/`date_before`;
  newest-first with early-stop, probing per-video dates via `get_info` when flat
  entries lack them). Reuses `fetch_transcripts` for the actual fetch (dedup +
  pacing + 429 backoff). Endpoint `POST /api/script-styles/{id}/add-channel`; UI
  has a channel input with a last-N / date-range toggle on `/script-styles`.

### Script Projects — subject + style + sources → grounded script.md (2026-06-25)

The missing **front stage** of the pipeline: write a new, *source-grounded* script
from scratch (not the essay→narration adaptation in `script.py`). Output is a
normal **Director-ready project** (`projects/<slug>/` with `project.yaml` +
`script.md`), so it flows straight into `script_to_scenes → … → render` with no glue.

- **Store** (`src/nolan/scriptwriter/store.py`, `ScriptProjectStore`) — scaffolds a
  Director-ready project (same `project.yaml`/dir tree as `nolan projects init`) plus
  a `scriptgen/` workspace the Director ignores: `meta.json`, `brief.md`,
  `sources/{sources.md, raw/}`, `facts.md`, `factcheck.md`, `citations.md`. Sources
  are pasted text/files (saved to `raw/`, `status=fetched`) or bare URLs
  (`status=pending`, fetched by the agent).
- **Task brief** (`scriptwriter/tasks.py`, `write_script_task`) — the agent brief
  (mirrors `_style_synthesis_task`): fetch pending URLs via WebFetch → ground
  `facts.md` (every claim tagged `[S#]` or `[model: needs-check]`) → draft `script.md`
  using the chosen style's **How to Apply** block → fact-check. **Grounded-but-graceful**
  policy: prefer source-backed claims, allow flagged model-knowledge, never present
  unverified as certain. Output obeys the Director contract (`## ` beat headings +
  `**Total Duration:** M:SS`).
- **Dispatch** — `operations.write_script` writes the task file and dispatches to a
  tmux Claude agent (same mechanism as `analyze_style`); **standalone** — drops a
  Director-ready project, handoff to render stays a separate step.
- **Reuse, not rebuild:** voice from `ScriptStyleStore.read_guide(style_id)`; project
  shape + dir tree from `projects init`; agent dispatch from `analyze_style`. The new
  parts are only the sourcing/grounding layer + the fact-check gate.
- **UI** — `/script-projects` page: create (subject + style dropdown + angle/pivot/
  minutes) → add sources (**URL / paste / file upload** of .txt/.md/.srt/.vtt) →
  **Write script** with **live job progress** (polls `/api/jobs/{id}`) → view `script.md`
  and the **grounding artifacts** (Brief / Facts / Fact-check / Citations, plus each
  source's fetched text) in an in-page viewer.
- Endpoints: `GET/POST /api/script-projects`, `GET/DELETE /api/script-projects/{slug}`,
  `POST .../{slug}/add-source|upload-file|remove-source/{sid}|write`,
  `GET .../{slug}/script|artifact/{name}|source/{sid}`.
- Tested by `scripts/test_scriptwriter.py` (store scaffolding, source handling, artifact/
  source reads, task brief content — no LLM needed); UI verified live via headless render.
- **Note:** two distinct `style_guide.md` exist — `script_styles/<id>/style_guide.md`
  (narrative voice) vs `projects/<slug>/style_guide.md` (visual/scene, written by the
  Director). Disambiguating the project one (→ `visual_style.md`) is a recommended
  follow-up cleanup, not yet done.

### Video Styles — reference videos → visual style guide (2026-06-26)

The **visual twin of Script Styles**: distill the *production / visual* style of
reference library videos into a reusable `video_style_guide.md` so a similar look
(and visual-verbal feel) can be cloned. Mirrors the Script Styles flow — corpus →
per-video extract → agent synthesis → guide. **Descriptive-only v1** (not yet wired
into the render pipeline).

- **Module** `src/nolan/video_style/`:
  - `store.py` (`VideoStyleStore`) — file-backed `video_styles/<id>/`: `manifest.json`
    (reference videos + optional `script_style_id` pairing), `per_video/<slug>.json`,
    `frames/<slug>/`, `video_style_guide.md`. Dedups by video_path.
  - `visual_stats.py` — **deterministic** (OpenCV/NumPy, no LLM): format (aspect/fps/
    duration/orientation), color (k-means palette hex, saturation/contrast, warm↔cool),
    motion (frame-diff), graphics (edge/overlay density), pacing-from-segments
    (cuts/min, shot-length stats, tempo).
  - `pairing.py` — **script↔visual relationship** (the differentiator): per segment,
    BGE-cosine **directness** between `transcript` (said) and `combined_summary`/
    `frame_description`+`inferred_context` (shown), reusing `vector_search`'s embedder.
    Bands literal/associative/tonal, with distribution, arc variation (open/mid/close),
    and paired said↔shown samples for the agent. Needs an indexed video.
  - `tempo.py` — **video-measured** editing tempo (not the index proxy): true shot-cut
    detection (HSV-histogram diff, motion-robust), a windowed cuts/min **curve** + trend
    (accelerates/steady/decelerates/varied), and **motion-weighted energy** (intra-shot
    motion of non-cut transitions blended with cut-rate). On Liu Xiu it found 66 real
    cuts vs the index's 25 segments (~2.6× undercount). Primary pacing signal;
    `pacing_from_segments` is the cheap fallback.
  - `vision_pass.py` — style-focused vision prompt (cinematography/color/lighting/
    graphics) over sampled frames; provider injectable (defaults to **OpenRouter**, not
    Gemini, when run via `analyze_video_style`).
  - `extract.py` — samples the video once and assembles stats + pacing + pairing +
    cinematography into `per_video/<slug>.json` (+ caches frames). Graceful-degrades
    when un-indexed (no pairing) or no vision provider.
  - `tasks.py` — synthesis brief (sections incl. the **Script ↔ Visual Pairing** one).
- **Dispatch** — `operations.analyze_video_style`: per-video extract (loads segments
  from the index, runs stats+pairing+vision), then dispatches synthesis to the `nolan2`
  tmux agent (same mechanism as `analyze_style`).
- **UI** — `/video-styles` page: create → pick reference videos from the **library**
  (indexed videos flagged) → pair with a Script Style → **Analyze** (live job poll) →
  view per-video extract JSON + the guide.
- Endpoints: `GET/POST /api/video-styles`, `GET/DELETE /api/video-styles/{id}`,
  `POST .../{id}/add-video|remove-source/{slug}|pair-script|analyze`,
  `GET .../{id}/guide|extract/{slug}`.
- Reuses: `sampler`/cv2 (frames), `vector_search` BGE embedder (pairing), `vision.py`
  provider, `VideoIndex.get_segments`, the Script Styles store/UI/agent-dispatch pattern.
- Tested (no model/db needed): `scripts/test_video_style.py` (stats+store),
  `test_pairing.py`, `test_vision_pass.py`, `test_extract.py`,
  `test_video_style_synthesis.py`, `test_tempo.py`; UI verified headless.
  **End-to-end validated** on the indexed 「劉秀」 video (real BGE + OpenRouter vision +
  tempo) → `video_styles/liu-xiu-historical-narrative/`.
- Real-run fixes: non-ASCII paths broke `cv2.imwrite` (→ `imencode`+`tofile` + ASCII
  slugs); pairing bands recalibrated to **0.72/0.58** (BGE related-pairs cluster
  0.55–0.80); on-screen-text inflates said↔shown similarity (documented; future: strip
  rendered narration before embedding).
- **Open:** pairing bands still single-video-calibrated; on-screen-text confound; the
  tempo `energy` blend + cut threshold are heuristics; executable mapping (guide →
  render pipeline) is a deferred phase.

### YouTube Integration
- **Video Download** - Download YouTube videos using yt-dlp
  - Single video, batch from file, or entire playlists
  - Configurable quality formats (default: 720p)
  - Automatic subtitle download — fetches only the **video's original
    language** (detected from yt-dlp metadata) instead of all configured
    languages, avoiding YouTube's HTTP 429 subtitle rate-limit. If a subtitle
    download still fails, the video is **retried once without subtitles** so the
    download succeeds and the Whisper fallback transcribes it.
  - Progress tracking with callbacks
- **YouTube Search** - Search for videos without downloading
  - Returns video metadata (title, duration, views, channel)
  - Export results to JSON
  - Optional: download first result directly
- **Video Info** - Get detailed metadata for a single video
  - Title, description, tags, categories
  - Duration, views, upload date
  - Channel information

## Usage

```bash
# Install in development mode
pip install -e ".[dev]"

# === Video Production Workflow ===

# Step 1: Convert essay to script
nolan script path/to/essay.md -o ./output
# Outputs: script.md (human-readable), script.json (for design)

# Step 2: Design scenes from script
nolan design ./output/script.json
# Outputs: scene_plan.json

# Or run full pipeline in one command
nolan process path/to/essay.md -o ./output

# Index video library (Ollama vision - local)
nolan index path/to/videos --recursive

# Index with Gemini vision (cloud - faster, async)
nolan index path/to/videos --vision gemini

# Control concurrency for rate limits
nolan index path/to/videos --vision gemini --concurrency 3   # free tier
nolan index path/to/videos --vision gemini --concurrency 10  # pay-as-you-go (default)
nolan index path/to/videos --vision gemini --concurrency 30  # higher tiers

# Choose frame sampling strategy (ffmpeg_scene is default, 10-50x faster)
nolan index path/to/videos --sampler ffmpeg_scene  # Fast FFmpeg-based (default)
nolan index path/to/videos --sampler hybrid        # Python-based, more sensitive to gradual changes
nolan index path/to/videos --sampler fixed         # Fixed 5-second intervals

# Index with Whisper auto-transcription (GPU accelerated)
nolan index path/to/videos --vision gemini --whisper --whisper-model base

# Export indexed segments to JSON
nolan export video.mp4 -o segments.json
nolan export --all -o library.json

# Cluster segments into story moments
nolan cluster video.mp4 -o clusters.json
nolan cluster video.mp4 --refine  # Use LLM for better boundaries
nolan cluster --all -o all_clusters.json

# Browse indexed library in web UI
nolan browse

# === Semantic Search ===

# Sync index to vector database (first time or after new indexing)
nolan sync-vectors
nolan sync-vectors --project venezuela  # Only sync specific project
nolan sync-vectors --clear              # Clear and rebuild

# Semantic search with natural language
nolan semantic-search "person looking worried"
nolan semantic-search "dramatic landscape" --level clusters
nolan semantic-search "Hugo Chavez speaking" --project venezuela --level segments
nolan semantic-search "emotional moment" -n 20 -o results.json

# Launch viewer for project outputs
nolan serve -p ./output

# Generate images with custom ComfyUI workflow
nolan generate-test "a dragon" -w workflow_api.json
nolan generate-test "a dragon" -w workflow.json -n "26:24"  # explicit prompt node
nolan generate-test "a dragon" -w workflow.json -s "13:width=1536" -s "3:steps=40"

# Search for images from web/stock photos
nolan image-search "sunset mountains"
nolan image-search "sunset mountains" -s pexels -n 20  # Pexels (needs API key)
nolan image-search "sunset mountains" -s all -o results.json  # all sources

# Search public domain sources
nolan image-search "Hugo Chavez" -s wikimedia  # Wikimedia Commons
nolan image-search "Abraham Lincoln" -s loc     # Library of Congress
nolan image-search "dinosaur" -s smithsonian    # Smithsonian (needs API key)

# Score images by relevance using vision model
nolan image-search "sunset mountains" --score --vision gemini
nolan image-search "sunset mountains" --score --vision ollama -c "for a travel documentary"

# Generate infographics (requires render-service running)
nolan infographic --title "My Process" -i "Step 1:First" -i "Step 2:Second"
nolan infographic --template list --theme dark --title "Features" -i "Fast:Blazing speed"
nolan infographic --template comparison --theme warm --title "A vs B" -i "Option A:Pro A" -i "Option B:Pro B"
nolan infographic spec.json -o my_infographic.svg  # From JSON spec file

# === YouTube Operations ===

# Search YouTube for videos
nolan yt-search "python tutorial" -n 5          # Search and show top 5 results
nolan yt-search "documentary" -o results.json   # Export results to JSON
nolan yt-search "cooking tips" --download       # Search and download first result

# Download YouTube videos
nolan yt-download "https://youtube.com/watch?v=xxxxx"                      # Single video
nolan yt-download urls.txt -o ./videos                                     # From file (one URL per line)
nolan yt-download "https://youtube.com/playlist?list=xxxxx" --playlist     # Entire playlist
nolan yt-download "https://youtube.com/playlist?list=xxxxx" --limit 10     # First 10 from playlist
nolan yt-download "https://youtube.com/watch?v=xxxxx" -f "bestvideo[height<=1080]+bestaudio"  # Custom quality

# Get video info without downloading
nolan yt-info "https://youtube.com/watch?v=xxxxx"                          # Show video metadata
nolan yt-info "https://youtube.com/watch?v=xxxxx" -o video_info.json       # Save to JSON

# === Project Management ===

# Create a new project
nolan projects create "Venezuela Documentary" -d "Documentary about Hugo Chavez"
nolan projects create "My Project" -s custom-slug -p projects/my-project   # Custom slug and path

# List all projects
nolan projects list                                                         # Shows slug, name, video count

# View project details
nolan projects info venezuela                                               # Show project info and videos

# Index videos scoped to a project
nolan index path/to/videos --project venezuela                              # Associate videos with project

# Delete a project
nolan projects delete venezuela                                             # Remove from registry only
nolan projects delete venezuela --delete-videos                             # Also delete indexed videos
```

## Test Coverage

174 tests covering all modules:
- Configuration: 3 tests
- LLM Client: 2 tests
- Parser: 3 tests
- Script Converter: 5 tests
- Scene Designer: 3 tests
- Video Indexer: 5 tests
- Asset Matcher: 3 tests
- ComfyUI Client: 3 tests
- Viewer Server: 3 tests
- CLI: 4 tests
- Integration: 2 tests
- Vision Provider: 9 tests
- Sampler: 11 tests
- Transcript: 15 tests
- Analyzer: 10 tests
- Whisper: 17 tests
- Clustering: 34 tests
- Lottie: 42 tests (NEW)

## Project Structure

```
NOLAN/
├── src/nolan/
│   ├── __init__.py      # Package version
│   ├── __main__.py      # Module entry point
│   ├── cli.py           # CLI commands
│   ├── config.py        # Configuration loading
│   ├── llm.py           # Gemini client
│   ├── parser.py        # Essay parsing
│   ├── script.py        # Script conversion
│   ├── scenes.py        # Scene design
│   ├── indexer.py       # Video indexing + HybridVideoIndexer
│   ├── matcher.py       # Asset matching
│   ├── comfyui.py       # ComfyUI integration
│   ├── viewer.py        # Viewer server
│   ├── vision.py        # Vision providers (Ollama, Gemini)
│   ├── sampler.py       # Smart frame sampling
│   ├── transcript.py    # Transcript loading/alignment
│   ├── analyzer.py      # Segment analysis + inference
│   ├── whisper.py       # Whisper auto-transcription
│   ├── clustering.py    # Scene clustering
│   ├── aligner.py       # Scene-to-audio alignment
│   ├── library_viewer.py # Library browser server
│   ├── image_search.py  # Image search providers
│   ├── assets.py        # Asset management for motion effects
│   └── templates/
│       ├── index.html   # Viewer UI
│       ├── scenes.html  # Scene plan A/B viewer
│       └── library.html # Library browser UI
├── tests/               # Test suite (174 tests)
├── render-service/      # Node.js microservice for infographics/animations
│   ├── src/
│   │   ├── server.ts    # Express API server
│   │   ├── routes/      # API endpoints (health, render)
│   │   ├── jobs/        # Job queue and types
│   │   └── engines/     # Render engines (infographic, etc.)
│   └── package.json
├── assets/              # Visual assets for motion effects
│   ├── common/icons/    # Shared SVG icons (check, star, etc.)
│   └── styles/          # Style-specific assets (per EssayStyle)
├── pyproject.toml       # Package configuration
└── .env                 # API keys (not committed)
```

## Requirements

- Python 3.10+
- Gemini API key (set `GEMINI_API_KEY` in .env)
- Ollama (optional, for local vision model)
- ffmpeg (optional, for Whisper auto-transcription)
- ComfyUI (optional, for image generation)
- Node.js 18+ (optional, for Infographic & Animation Render Service)

## Documentation

| Document | Description |
|----------|-------------|
| [Fair Use Transforms](docs/FAIR_USE_TRANSFORMS.md) | Strategies for transforming third-party clips to reduce copyright detection |
| [Motion Effects](docs/MOTION_EFFECTS.md) | Motion effects library for video essays |
| [TTS Integration](docs/TTS_INTEGRATION.md) | Voiceover generation with MiniMax and Chatterbox |
| [LLM Content Authoring](render-service/docs/LLM_CONTENT_AUTHORING.md) | Guide for LLMs writing content with style markup |

## Next Steps (Backlog)

### Autonomous Quality System (Priority)

See [docs/plans/2026-01-30-autonomous-quality-system.md](docs/plans/2026-01-30-autonomous-quality-system.md) for full design.

**Goal:** Enable NOLAN to produce high-quality video clips autonomously with minimal human intervention.

**Four-Layer Approach:**
1. **Scope to Strengths** - Route visual types to appropriate pipelines (templates vs. generation)
2. **Template Library** - Expand Lottie/Motion Canvas templates for automatable content
3. **Video Generation** - Integrate LTX-Video/Runway for b-roll and cinematic content
4. **Quality Evaluation** - Vision-based scoring with retry loops and human fallback

**Phase 1 (Template System): COMPLETE**
- [x] Unified template catalog (`TemplateCatalog` class)
- [x] Semantic tagging (240+ auto-generated tags)
- [x] CLI commands (`nolan templates list/search/info/semantic-search/match-scene`)
- [x] Semantic template discovery (ChromaDB + BGE embeddings)
- [x] Scene-to-template matching (`find_templates_for_scene()`)
- [x] Visual type router (`VisualRouter` class in `visual_router.py`)
- [x] CLI: `nolan route-scenes` - show routing decisions
- [x] CLI: `nolan render-templates` - render templates to video clips
- [ ] Template library expansion (200+ templates - currently 52)
- [ ] Template schema completion for all templates (13/52 have schemas)

**Phase 2 (Quality Evaluation):**
- [ ] Quality scoring prompts (semantic fit, visual quality, style consistency)
- [ ] Quality gate integration after asset generation
- [ ] Per-video style guide system

**Phase 3 (Video Generation):**
- [ ] LTX-Video integration (self-hostable)
- [ ] Runway API integration (commercial)
- [ ] Video generation router with cost management

**Phase 4 (Human Review):**
- [ ] Review queue with priority scoring
- [ ] Review web UI for flagged scenes
- [ ] Notification system for pending reviews

---

- **Database-Backed Asset Management** - SQLite storage for large asset libraries (100+ assets)
  - Search by name, tags, category
  - Asset versioning and thumbnails
  - CLI for asset management (`nolan assets list/add/tag`)
  - Trigger: Implement when asset count justifies complexity
- **TTS Voiceover Generation** - `nolan voiceover` command with MiniMax API and Chatterbox local fallback
- **End-to-End Orchestrator** - `nolan make-video` single command for full pipeline automation
- **Fair Use Transform Presets** - Implement `--fair-use-transform` flag for automated clip transformation
- **AI Clip Regeneration** - `nolan regenerate-clips` using LTX-2 / Wan I2V to create new AI videos from key frames
- **yt-fts transcript search integration** - Use YouTube transcript search for full-text search
- **LLM infographic placement** - Detect data points in scripts and suggest infographic placement
- **HunyuanOCR integration** - Text extraction from video frames (subtitles, on-screen text, titles)
- **Image search browser display** - View image search results in web UI
- **Vision model image selection** - Auto-select best matching images using vision model
- **dotLottie Integration** ✅ COMPLETED
  - ✅ Spike completed: frame-accurate rendering with `setFrame()` works
  - ✅ No flickering observed (unlike @remotion/lottie)
  - ✅ `LottieAnimation` component added to Remotion engine
  - ✅ Python utility module: `src/nolan/lottie.py` (customize_lottie, validate, transform colors)
  - ✅ Scene plan support: `visual_type: "lottie"` with `lottie_template` and `lottie_config`
  - ✅ Asset library structure: `assets/common/lottie/` (lower-thirds, transitions, icons, etc.)
  - ✅ ThorVG engine supports: expressions, drop shadows, blur, masks, gradients, text
  - Test files: `render-service/test/dotlottie-spike/`
  - Docs: [docs/LOTTIE_INTEGRATION.md](docs/LOTTIE_INTEGRATION.md)
  - See: [ThorVG Lottie Support](https://github.com/thorvg/thorvg/wiki/Lottie-Support)
- **Lottie Template Catalog** ✅ COMPLETED (was: Motion Pattern Library)
  - ✅ LottieFiles Downloader: `src/nolan/lottie_downloader.py`
    - Rate-limited downloads (15-20 req/min), metadata extraction, duplicate detection
    - Color palette extraction, search functionality
  - ✅ Jitter.video Downloader: `src/nolan/jitter_downloader.py`
    - Playwright browser automation for Jitter's SPA
    - Category discovery, multi-artboard handling, blob content extraction
    - CLI: `python -m nolan.jitter_downloader --essential`
  - ✅ Lottieflow Downloader: `src/nolan/lottieflow_downloader.py`
    - Bulk download via network interception (no login required)
    - 21 categories of UI micro-interactions
    - CLI: `python -m nolan.lottieflow_downloader --essential`
  - ✅ 50+ production-ready animations across multiple sources:
    - LottieFiles: lower-thirds (2), title-cards (1), transitions (2), data-callouts (2), progress-bars (2), loaders (1), icons (2)
    - Jitter: text effects (glide, morph, sliding reveal), icons (rotate-scale)
    - Lottieflow: menu-nav (5), arrows (5), checkboxes (3), loaders (5), play (3), scroll-down (3), success (3), attention (3)
  - ✅ Catalogs: `catalog.json`, `jitter-catalog.json`, `lottieflow-catalog.json`
  - ✅ Template Schema System: `src/nolan/lottie.py`
    - `analyze_lottie()` - Discover customizable fields (text, colors, timing)
    - `generate_schema()` / `save_schema()` - Create `.schema.json` files
    - `render_template()` - Magicbox API with semantic field names
    - `list_templates()` - List templates with schema status
  - ✅ Curated schemas for 3 templates: magic-box, modern lower-third, simple lower-third
  - ✅ 42 tests: `tests/test_lottie.py`
  - ✅ Docs: [docs/LOTTIE_INTEGRATION.md](docs/LOTTIE_INTEGRATION.md#lottie-template-catalog)
- **Template Analysis Tool** - CLI to help document animation timing from reference
  - `nolan analyze-template <video>` to measure keyframes and timing
  - Export structured motion specs from reference videos
- **SVG Animation Import** - Parse animated SVGs (SMIL) to Motion Canvas code
  - Convert SMIL animations to Motion Canvas generator functions
  - Preserve timing, easing, and transform sequences
- **Canva Static Export** - Download Canva designs as static assets via API
  - OAuth flow for [Canva Connect API](https://www.canva.dev/docs/connect/)
  - Export PNG/SVG elements from Canva templates
  - Animate exported assets in NOLAN with custom timing
  - Note: No animation keyframe access, static export only

## Recently Completed

- ✅ **Animated Scene Renderer** - Codified animation system for generating animated video scenes
  - **nolan.renderer package** - Complete animation rendering framework:
    - `BaseRenderer` - Base class for all scene renderers with frame-by-frame rendering
    - `Element` - Scene element (text, rectangle, image) with property animation
    - `Timeline` - Global timing management for fade in/out sequences
    - `Easing` - 27 easing functions (linear, quad/cubic/quart/expo, back, elastic, bounce, spring, bezier)
  - **Composable Effects System** (46+ effects):
    - **Basic**: `FadeIn`, `FadeOut`, `SlideUp`, `SlideDown`, `SlideLeft`, `SlideRight`, `MoveTo`, `ScaleIn`, `ScaleOut`, `ExpandWidth`
    - **Text**: `TypeWriter`, `Reveal` (word/char), `CountUp` (number animation with prefix/suffix)
    - **Emphasis**: `Shake`, `Flash`, `Bounce`, `Glitch`, `Pulse`, `Hold`
    - **Rotation**: `RotateIn`, `RotateOut`, `Spin`, `Wobble`
    - **Blur/Focus**: `BlurIn`, `BlurOut`, `FocusPull`, `PulseBlur`
    - **Shadow**: `ShadowIn`, `ShadowOut`, `ShadowPulse`
    - **Glow**: `GlowIn`, `GlowOut`, `GlowPulse`, `Highlight`
    - **Color**: `ColorShift`, `ColorTint`
    - **Annotation**: `Underline` (incl. `style="highlight"` marker sweep with phrase-based `highlight_text` selection), `Strikethrough`, `CircleAnnotation`, `ArrowPoint`
    - **Cinematic**: `Letterbox`, `Scanlines`, `VHSEffect`
    - **Drawing**: `DrawLine`, `DrawBox`
    - **Sequencing**: `Loop`, `Sequence`, `Delay`, `StaggeredFadeIn`
    - Effects are stackable: multiple effects can be applied to a single element
  - **Easing Functions** (27 total):
    - Standard: `linear`, `ease_in/out/in_out_quad`, `ease_in/out/in_out_cubic`, `ease_in/out/in_out_quart`, `ease_in/out/in_out_expo`
    - Special: `ease_in/out/in_out_back` (overshoot), `ease_in/out/in_out_elastic` (spring), `ease_in/out/in_out_bounce`
    - Advanced: `spring` (physics-based), `bezier` (custom cubic bezier curves)
  - **Position/Layout System** (`layout.py`):
    - **Position System** (percentage-based): `Position` dataclass with x/y percentages (0-1)
      - 16 named presets: center, lower-third, upper-third, corners, split-screen
      - All renderers accept `position` parameter for placement control
    - **Slot/Layout System** (region-based): Cross-platform screen division
      - `Slot` - Rectangular region with x, y, width, height, padding
      - `Layout` - Divides screen into slots (columns, rows, grids)
      - `get_preset()` - Named layouts: "thirds", "golden", "split-1-2", "grid-2x2", etc.
      - JSON-serializable for Motion Canvas/Remotion integration
      - Templates can accept custom layouts as input
    - Aligns with render-service layout system for consistency
  - **Scene-Specific Renderers** (27 total):
    - **Core** (10): `QuoteRenderer`, `TitleRenderer`, `StatisticRenderer`, `ListRenderer`, `LowerThirdRenderer`, `CounterRenderer`, `ComparisonRenderer`, `TimelineRenderer`, `KenBurnsRenderer`, `FlashbackRenderer`
    - **Text Cards** (5): `DefinitionRenderer`, `SourceCitationRenderer`, `PullQuoteRenderer`, `QuestionRenderer`, `VerdictRenderer`
    - **Location/Time** (3): `LocationStampRenderer`, `ChapterCardRenderer`, `ProgressBarRenderer`
    - **Data Visualization** (4): `StatComparisonRenderer`, `PercentageBarRenderer`, `RankingRenderer`, `PieCalloutRenderer` (5-beat donut/pie: intro → scale-down → colour slice by % → eject slice → info-text reveal; controllable `pie_center`)
    - **Media Mockup** (3): `TweetCardRenderer`, `NewsHeadlineRenderer`, `DocumentHighlightRenderer` (its `highlight_text` param drives a phrase-targeted highlighter sweep)
    - **Transitions** (1): `SectionDividerRenderer`
    - **Portrait/Figure** (1): `portrait_reveal` - portrait slides aside to reveal bullet points (from video analysis)
    - **Smart Text Layout**: Automatic line wrapping with `max_width`, `max_lines`, dynamic font sizing
  - **Preset Functions** - One-line rendering for common scene types:
    - `documentary_quote()` - Dark background, red accent documentary style
    - `documentary_title()` - Near-black background, white title, red accent
    - `historical_year()` - Sepia tones, gold accents for historical content
    - `big_number()` - Statistics with modern/danger/success styles
    - `chapter_title()` - Chapter number and title combination
  - **Style Presets** - `StylePresets` class with documentary, historical, modern_clean, danger, success color schemes
  - **Frame-by-Frame Pipeline**:
    - Uses PIL for reliable text rendering (avoids MoviePy TextClip font issues)
    - Pre-renders all frames with eased properties
    - Composes into video using MoviePy VideoClip
    - Integrated with Quality Protocol for auto-validation
  - **Location**: `src/nolan/renderer/` (base.py, easing.py, effects.py, layout.py, text_layout.py, scenes/, presets.py)
  - **Test scripts**:
    - `scripts/test_all_renderers.py` - Tests core scene renderers
    - `scripts/test_venezuela_templates.py` - Tests all 15 new templates with Venezuela content
    - `scripts/test_new_effects.py` - Tests 10 advanced effects (CountUp, Shake, Rotation, Blur, Shadow, Glow, etc.)
    - `scripts/test_annotation_effects.py` - Tests 8 annotation/cinematic effects (Underline, Letterbox, Scanlines, etc.)
    - `scripts/test_highlight_sweep.py` - Tests the highlight-marker sweep (`Underline(style="highlight")`) and phrase-based selection
    - `scripts/test_pie_callout.py` - Tests the 5-beat donut callout (`PieCalloutRenderer`): slice tracks %, text reveal, controllable location

- ✅ **Quality Protocol Module** - Automated validation and fix system for rendered video content
  - **nolan.quality package** - Core quality assurance module:
    - `QualityProtocol` - Main validation class with configurable checks
    - `QAConfig` - Configuration for checks, tolerances, and auto-fix settings
    - `QAResult` / `QAIssue` - Result types with pass/fail status and issue details
  - **Validation checks**:
    - Properties: file exists, duration, resolution, file size
    - Visual: blank frame detection, brightness analysis
    - Text (optional): OCR-based text verification via pytesseract
    - Visual text comparison: reference-based text rendering quality check
  - **Auto-fix system**:
    - Font fallback chain for text rendering issues
    - Re-render with corrected parameters
    - Configurable max fix attempts
  - **Root cause discovery**: MoviePy TextClip has font rendering issues (character cutoff)
    - Solution: Use PIL direct text rendering + moviepy video encoding
    - `create_quote_frame()` function for reliable text rendering
  - **Integration**: `render_with_quality_check()` wrapper function
  - **Design document**: `docs/quality-protocol-design.md`
  - Location: `nolan/quality/` (protocol.py, types.py, checks/)

- ✅ **Video Generation Integration** - Dual-backend video generation for autonomous content creation
  - `VideoGenerator` abstract base class with unified interface
  - `ComfyUIVideoGenerator` for local video models (LTX-Video, Wan, HunyuanVideo, CogVideoX, AnimateDiff)
  - `RunwayGenerator` for commercial API (Gen-3 Alpha Turbo, Gen-3 Alpha)
  - Auto-detection of prompt nodes in ComfyUI workflows
  - Scene-to-video generation with optimized prompts: `generate_video_for_scene()`
  - CLI: `nolan video-gen check/generate/scene/batch`
  - Cost tracking for commercial API usage
  - Part of Autonomous Quality System Phase A-2
- ✅ **Visual Router** - Intelligent scene-to-pipeline routing for asset generation
  - `VisualRouter` class routes scenes to appropriate pipelines
  - Route types: template, library, generation, infographic, passthrough
  - Template types: lower-third, text-overlay, title, counter, icon, loading, lottie, ui
  - Library types: b-roll, a-roll, footage, cinematic
  - Generation types: generated, generated-image
  - Template matching with score threshold (default 0.5)
  - CLI: `nolan route-scenes`, `nolan render-templates`
  - Part of Autonomous Quality System Phase A-3
- ✅ **Template Catalog System** - Unified Lottie template management for autonomous video generation
  - `TemplateCatalog` class merges LottieFiles, Jitter, Lottieflow sources
  - 53 templates across 17 categories with auto-tagging (240+ tags)
  - `TemplateSearch` with ChromaDB vector embeddings for semantic search
  - Scene-to-template matching: `find_templates_for_scene()`, `match_scene_to_template()`
  - CLI: `nolan templates list/info/search/semantic-search/match-scene/index/auto-tag`
  - Visual type routing maps scene types to template categories
  - Part of Autonomous Quality System Phase A-1
- ✅ **Video Library Clip Matching** - `nolan match-clips` command for matching scenes to library clips
  - Semantic search using ChromaDB vector database finds relevant clips
  - LLM selection picks best candidate considering visual relevance, narrative fit, and duration
  - Smart clip tailoring algorithm: skips first 7% (avoid transitions), ratio-based centering
  - Combines `narration_excerpt + visual_description + search_query` for rich search queries
  - Configurable via `clip_matching` section in nolan.yaml:
    - `candidates_per_scene`: Top N candidates (default: 3)
    - `min_similarity`: Threshold 0-1 (default: 0.5)
    - `search_level`: segments, clusters, or both
  - Updates `matched_clip` field in scene_plan.json with video_path, clip_start, clip_end, reasoning
  - Supports --dry-run, --project filter, --skip-existing options
- ✅ **Semantic Search UI** - Toggle between keyword and semantic search in library viewer
  - Search mode toggle button (Keyword/Semantic) in web UI
  - Semantic scores displayed as percentage badges (e.g., "69.3%")
  - Fields dropdown hidden in semantic mode (not applicable)
  - `/api/search/semantic` API endpoint for programmatic access
- ✅ **Adaptive Scene Detection** - Automatic threshold tuning per video
  - Uses statistical analysis (mean + 5σ) to find significant scene changes
  - Adapts to different editing styles: fast cuts get higher threshold, slow pacing gets lower
  - Example: Fast-cut video (10.8 segments/min) vs slow video (5.1 segments/min)
  - Runs FFmpeg once to collect all scores, then filters - no repeated processing
  - Configurable sigma multiplier (default 5.0) in SamplerConfig
  - Falls back to fixed threshold if specified (for backwards compatibility)
  - **Score caching**: Saves frame scores to `video.scores.json` for instant reindexing
    - Skips FFmpeg on reindex if video unchanged (checks mtime + size)
    - ~100s savings on 40-min video reindex
  - **FFmpeg frame extraction**: Uses FFmpeg with input seeking instead of CV2
    - 3.7x faster frame extraction (190ms vs 700ms per frame)
    - Uses libdav1d for AV1 videos (faster decoder)
- ✅ **FFmpeg Scene Detection** - 10-50x faster frame sampling (new default)
  - Uses FFmpeg's hardware-accelerated scene detection filter
  - Only decodes frames at detected scene changes (vs every frame)
  - Respects min/max interval constraints for coverage
  - 30-min video: ~5 seconds (vs 3-8 minutes with Python-based hybrid)
  - Codec-aware decoder selection (libdav1d for AV1, native for others)
  - Use `--sampler hybrid` to fall back to Python-based detection
- ✅ **Combined Vision+Inference** - Single API call per frame (50% fewer calls)
  - Frame + transcript analyzed together in one vision call
  - Better inference: vision model can recognize faces, read text
  - Cost: ~$0.03-0.05 for 30-min video (vs ~$0.06-0.10 before)
- ✅ **Auto-Whisper Transcription** - Enabled by default when no subtitle exists
  - Generates transcripts automatically using faster-whisper
  - ~45 sec for 30-min video on GPU (base model)
  - Use `--no-whisper` to opt-out
- ✅ **Language-coded Subtitles** - Support for yt-dlp style .en.srt files
- ✅ **Async Batch Indexing** - ~10x faster video indexing with concurrent API calls
  - Process multiple frames in parallel using asyncio with semaphore
  - `--concurrency` CLI option to control parallelism (default 10)
  - Rate limit friendly: use 2-3 for free tier, 10-15 for pay-as-you-go
- ✅ **Project Registry** - Organize videos by project with human-friendly slugs
  - `nolan projects create/list/info/delete` commands for project management
  - Projects have internal UUIDs and CLI-facing slugs (e.g., `venezuela`)
  - `nolan index --project <slug>` scopes videos to a project
  - Auto-generated slugs from project names (URL-safe)
  - Database schema v4 with projects table
- ✅ **YouTube Video Download** - Download and organize YouTube videos with yt-dlp
  - Single video, batch, or playlist download
  - Automatic subtitle download (configurable languages)
  - Project-based folder organization
- ✅ **Video Assembly Pipeline** - Two-phase render pipeline for final video output
  - `nolan render-clips`: Pre-render animated scenes (infographics, sync_points) to MP4
  - `nolan assemble`: FFmpeg-based assembly of all assets + voiceover
  - Asset priority: rendered_clip > generated_asset > matched_asset > infographic_asset
  - Automatic scaling/padding to target resolution
  - Support for cut, fade, crossfade transitions
  - Full architecture documented in `docs/plans/2026-01-12-render-pipeline.md`
- ✅ **Scene-Audio Alignment** - `nolan align` command for word-level audio alignment
  - Transcribes audio with word-level timestamps via Whisper
  - Matches scene `narration_excerpt` to word stream using text matching
  - Updates scene_plan.json with `start_seconds` and `end_seconds`
  - Confidence scoring for alignment quality
  - Optional word timestamp export for debugging
- ✅ **Transcription Command** - `nolan transcribe` for audio/video to subtitles
  - Outputs SRT, JSON, or plain text formats
  - GPU (CUDA) with automatic CPU fallback
  - Multiple Whisper model sizes (tiny to large-v3)
- ✅ **B-Roll Image Matching** - `nolan match-broll` command for batch image search and download
  - Searches images for all b-roll scenes using search_query from scene_plan.json
  - Multiple providers: DuckDuckGo (default), Pexels, Pixabay, Wikimedia, Library of Congress
  - Optional vision model scoring (Gemini/Ollama) for relevance ranking
  - Downloads best match for each scene to assets/broll/
  - Updates scene_plan.json with matched_asset paths
  - Supports dry-run mode and skip-existing option
- ✅ **Two-Pass Scene Design** - Professional A/V script workflow based on video essay research
  - Pass 1 (`--beats-only`): Break narration into beats, assign visual categories
  - Pass 2 (default): Enrich beats with category-specific details
  - Visual categories: b-roll, graphics, a-roll, generated, host
  - Identifies "visual holes" (abstract concepts needing creative solutions)
  - Outputs A/V script format (av_script.txt) for human review
  - Based on "The Architecture of the Digital Argument" research
- ✅ **Standalone Script & Design Commands** - Split workflow into separate steps
  - `nolan script` converts essay to script.md + script.json
  - `nolan design` generates scene_plan.json from script.json
  - Script class now supports JSON export/import for workflow persistence
  - Enables review/editing between steps before committing to scene design
- ✅ **Scene Workflow Data Model** - Enhanced Scene dataclass for 5-step video pipeline
  - `SyncPoint` dataclass for word-to-action synchronization (trigger → action at precise time)
  - `Layer` dataclass for complex multi-element scenes (background, overlay, caption)
  - Scene fields for timing alignment: `start_seconds`, `end_seconds`, `subtitle_cues`
  - Animation fields: `animation_type`, `animation_params`, `transition`
  - Progressive enrichment pattern: Scene is a "holder" filled across workflow steps
  - Updated LLM prompt to request sync_points, layers, animation specs
  - Full plan documented in `docs/plans/2026-01-11-scene-workflow.md`
- ✅ **Motion Canvas Engine** - Render-service can export MP4s via Motion Canvas + FFmpeg
  - Generates a temporary Motion Canvas project (project, scene, render entry, spec)
  - Uses Vite + @motion-canvas/vite-plugin + @motion-canvas/ffmpeg for rendering
  - Launches headless Chromium to execute the render pipeline and writes MP4s to output
  - Supports basic spec fields (title, subtitle, items, width, height, duration, theme)
- ✅ **Remotion Engine** - Render-service can export MP4s via Remotion renderer
  - Bundles a temporary Remotion project for each job and renders via @remotion/renderer
  - Infographic composition supports title, subtitle, items, and theme colors
- ✅ **AntV Infographic Engine Enablement** - render-service now supports @antv/infographic via headless Chromium
  - Uses bundled `infographic.min.js` with Puppeteer for SVG extraction
  - Added template aliasing so `steps/list/comparison` map to real AntV templates
  - Added `INFOGRAPHIC_ENGINE` and `engine_mode` to force AntV vs SVG fallback
  - Added `PUPPETEER_EXECUTABLE_PATH`/`CHROME_PATH` support for local Chrome/Edge
  - Debug logging is gated behind `INFOGRAPHIC_DEBUG=1`
- ✅ **Render Service Engine Coverage** - Motion Canvas and Remotion engines now render MP4s
  - Processor wiring routes motion-canvas and remotion jobs to live engines
- ✅ **Render Service Code Quality Refactor** - Cleaned up engine and preset code
  - Extracted common utilities (`ensureDir`, `toNumber`, `toString`) to `engines/utils.ts`
  - Centralized theme definitions in `themes.ts` (used by all 3 engines)
  - Fixed inconsistent null handling: changed 70+ `||` to `??` for numeric params
  - Prevents bugs where falsy values like `0` incorrectly trigger fallbacks
- ✅ **Infographic Scene Integration** - Scene designer supports infographic suggestions
  - Prompt updated to allow infographic visual_type and spec payloads
  - Scene model stores infographic specs and rendered assets
- ✅ **Infographic Batch Rendering** - `nolan render-infographics` renders infographic scenes
  - Writes SVGs to assets/infographics and updates scene_plan.json
- ✅ **Viewer Infographic Review** - project viewer displays infographic specs and previews
  - Summary now includes infographic counts and render status

- ✅ **Infographic CLI Integration** - `nolan infographic` command for generating infographics
  - Connects Python CLI to Node.js render-service via HTTP
  - Three input modes: command-line options, JSON file, stdin pipe
  - Support for templates (steps, list, comparison) and themes (default, dark, warm, cool)
  - Configurable output size and location
- ✅ **Job Processor** - Connect infographic engine to job queue for render-service
  - Job processor polls for pending jobs and processes them through appropriate engines
  - Real-time status and progress updates during rendering
  - Error handling with detailed error messages stored in job
  - Singleton processor started with server
- ✅ **Infographic Engine** - SVG template-based rendering engine for render-service
  - RenderEngine interface abstraction for pluggable engines
  - InfographicEngine with native SVG template generation
  - Multiple templates: steps/sequence, list, comparison
  - Theme support: default, dark, warm, cool color schemes
  - SVG output with gradients, shadows, and proper styling
  - Note: Replaced @antv/infographic due to browser-only limitations
- ✅ **Public Domain Image Sources** - New providers for public domain images
  - Wikimedia Commons (100M+ images, no API key, CC licenses)
  - Library of Congress (historical photos, no API key, public domain)
  - Smithsonian Open Access (2.8M+ images, API key from api.data.gov, CC0)
- ✅ **Image Search Scoring** - Vision model scoring for image relevance
  - Score images from 0-10 with explanations
  - Support for Gemini (cloud) and Ollama (local) vision models
  - Quality scoring (0-10) based on resolution and aspect ratio
  - Combined sorting: relevance first, quality as tiebreaker
  - Fallback download: thumbnail → main URL if thumbnail fails
  - Optional context for better scoring (e.g., "for a documentary")
- ✅ **Image Search** - `nolan image-search` command for finding images from web/stock photos
  - DuckDuckGo search (no API key required)
  - Pexels and Pixabay stock photo APIs (optional, with API keys)
  - JSON output with URLs, thumbnails, dimensions
  - Extensible provider system for adding more sources
- ✅ **ComfyUI Custom Workflows** - Full workflow customization support
  - Load any ComfyUI workflow exported in API format
  - Explicit prompt node selection (`--prompt-node`)
  - Generic parameter overrides (`--set "node:param=value"`)
  - Auto-detection fallback for common workflow patterns
- ✅ **Video Index Viewer** - `nolan browse` command for browsing indexed video library
  - Browse videos and their segments in web UI
  - View frame descriptions, transcripts, inferred context
  - View clusters with summaries
  - Video preview playback at timestamps
  - Full-text search across segments
- ✅ **Scene Clustering** - `nolan cluster` command for grouping segments into story moments
  - Groups by shared characters, location, and story context
  - Optional LLM-based story boundary detection (`--refine`)
  - Cluster-level summaries for deeper narrative understanding
- ✅ **Export command** - `nolan export` for full JSON output with all fields
- ✅ **Gemini vision CLI** - `--vision gemini` option for cloud-based frame analysis (3-4x faster)
- ✅ **GPU Whisper** - CUDA acceleration with automatic CPU fallback
- ✅ **Hybrid inference** - LLM fusion of vision + transcript with inferred context (people, location, story)
- ✅ **Whisper integration** - Auto-generate transcripts using faster-whisper
- ✅ **Local VLM support** - Ollama integration with qwen3-vl:8b (switchable to other models)
- ✅ **Smart sampling** - 5 strategies (ffmpeg_scene, hybrid, fixed, scene_change, perceptual_hash)
- ✅ **Transcript support** - SRT, VTT, Whisper JSON loading and alignment
- ✅ **Essay Style System** - Consistent visual branding across video essay motion effects
  - **EssayStyle type** - Complete style definition with colors, typography, layout, motion, texture
  - **11 flagship styles** - noir-essay, cold-data, modern-creator, academic-paper, documentary, podcast-visual, retro-synthwave, breaking-news, minimalist-white, true-crime, nature-documentary
  - **Accent markup** - `**word**` syntax for emphasizing key terms in quotes and titles
  - **Auto-accent detection** - Numbers, dates, percentages, money auto-detected per style rules
  - **Style-driven presets** - All effect presets now support style parameter:
    - Title, quote, text (highlight, typewriter, glitch, bounce, scramble, gradient, pop, citation)
    - Chart (bar, line, pie, donut), statistic (counter, comparison, percentage)
    - Image (ken-burns, zoom-focus, parallax, photo-frame, document-reveal)
    - Overlay (picture-in-picture, vhs-retro, film-grain, light-leak, camera-shake, screen-frame, audio-waveform, data-ticker, social-media-post, video-frame-stack)
    - Transition (slide, wipe, dissolve, zoom, blur, glitch)
    - Progress, annotation, comparison, timeline, countdown, map
  - **Backward compatible** - Style parameter is optional; legacy color params still work
  - **Styles API** - Full REST API for styles:
    - `GET /styles` - List all available styles
    - `GET /styles/:id` - Get full style definition
    - `POST /styles/:id/resolve-accent` - Test accent resolution
    - `POST /styles/:id/preview` - Generate style preview with sample content
  - **Validation helper** - `validateSceneContent()` checks content against style accent rules
  - **LLM Authoring Guide** - Documentation for LLMs on how to write styled content (`render-service/docs/LLM_CONTENT_AUTHORING.md`)
  - **Texture rendering** - Grain, vignette, and gradient overlays rendered in Motion-Canvas engine
  - **Remotion style integration** - All 11 EssayStyles mapped to Remotion themes with texture support
  - **Font loading** - Inter, Georgia, Playfair Display loaded in Motion-Canvas for style fonts
  - **Style parameter convention** - Use `style` param when possible; use `essayStyle` when another `style` param exists (e.g., animation style, frame style)
  - **Known limitations**:
    - Motion timing (enterFrames, exitFrames, easing) not yet derived from style; uses per-effect defaults
    - Helper functions (getTextureSettings, getFontProps, getSafeArea) available but not fully utilized
- ✅ **Layout System** - Region-based positioning for effect placement
  - **Region type** - Position defined by `{ x, y, w, h, align, valign, padding }` (all percentage-based 0-1)
  - **11 layout templates** - Predefined region configurations for video essays:
    - `center` - Single centered region (default)
    - `full` - Full bleed with safe margins
    - `lower-third` - Bottom bar for names, citations
    - `upper-third` - Top bar for chapter titles
    - `split` - Left/right 50-50 comparison
    - `split-60-40` / `split-40-60` - Asymmetric left/right emphasis
    - `thirds` - Three equal columns
    - `split-with-lower` - Two columns + bottom bar
    - `presenter` - Main content + lower third
    - `grid-2x2` - Four equal quadrants
  - **Render API integration** - `POST /render` accepts `layout` parameter:
    - Template name: `{ layout: "lower-third" }`
    - Custom regions: `{ layout: { regions: { main: { x: 0.1, y: 0.8, w: 0.5, h: 0.15 } } } }`
  - **Engine integration** - Layouts resolved before bundling, passed as CSS styles to components
  - **Layouts endpoint** - `GET /render/layouts` returns all templates with region definitions
  - **Remotion CSS conversion** - `regionToRemotionStyle()` converts regions to CSS flexbox properties
  - **Motion Canvas support** - `regionToMotionCanvas()` converts to center-based coordinates
  - **Style layout merge** - `applyStyleToRegion()` merges EssayStyle.layout with region defaults
  - **Extensible architecture** - Phase 1 (templates) complete; designed for Phase 2 (composition) and Phase 3 (full CSS)
- ✅ **Asset Management System** - File-based visual assets for motion effects
  - **Folder structure** - Organized by style with common fallback:
    - `assets/styles/{style-id}/` - Style-specific assets
    - `assets/common/` - Shared assets (fallback for all styles)
  - **AssetManager API** - Python module for asset access:
    - `get_asset(style, name)` - Get path with style→common fallback
    - `get_asset_content(style, name)` - Read file content directly
    - `get_icon(style, name)` - Convenience for `.svg` icons
    - `list_assets(style, category)` - List available assets
  - **Common icons** - 9 SVG icons (24x24 viewBox, `currentColor` stroke):
    - check, star, arrow-up, trending-up, code, database, users, zap, award
  - **Design decision** - Chose file-based over database for simplicity
    - Database-backed system in backlog for future scaling (100+ assets)
  - **Documentation** - `assets/README.md` with guidelines and usage

## Local TTS + Voice Cloning (OmniVoice) — M1 (2026-06-26)

Local text-to-speech with zero-shot voice cloning via
[OmniVoice](https://github.com/k2-fsa/OmniVoice) (Apache-2.0). Fills the gap where
the orchestrator wrote *silent* audio ("TTS not yet integrated").

- **Isolated runtime:** OmniVoice runs in a dedicated CUDA conda env
  (`D:\env\omnivoice`), invoked as a **batch subprocess** so the heavy torch stack
  stays out of the lean `nolan` env and VRAM is freed when the job ends. Setup:
  `scripts/setup_omnivoice.ps1`, POC: `scripts/omnivoice_poc.py`, docs:
  `docs/OMNIVOICE_SETUP.md`.
- **Shared GPU lock:** `get_gpu_lock()` (singleton in `webui/jobs.py`) serializes
  GPU work across the hub event loop. `ComfyUIClient.generate()` and the TTS
  worker acquire the *same* lock so OmniVoice and ComfyUI never contend for the
  4090's VRAM; the TTS job can also POST ComfyUI `/free` first
  (`tts.omnivoice.free_comfyui_vram`).
- **Provider abstraction:** `src/nolan/tts.py` — `TtsProvider` ABC +
  `OmniVoiceTTS` (batch via `omnivoice-infer-batch`) + `create_tts_provider`
  (mirrors `create_text_llm`). Config: `TtsConfig`/`OmniVoiceConfig` + a `tts:`
  block in `nolan.yaml` (enabled default off).
- **Voice library:** `src/nolan/voice_library.py` — file-backed `voices/<id>/`
  (sample.wav + meta). Clone from an **uploaded clip** or from a **saved Clip's
  audio** (reuses the Clips feature). Optional reference transcript (OmniVoice
  auto-transcribes via Whisper otherwise).
- **Voiceover generation:** `operations.generate_voiceover` reads a project's
  `script.json`, batch-synthesizes per section under the GPU lock, concatenates →
  `projects/<name>/assets/voiceover/voiceover.mp3`. Run `nolan align` after for
  audio-accurate scene timings (replaces the 150-wpm estimate).
- **UI:** `/voices` page (add/clone/preview voices, generate a project's voiceover)
  + Voices nav link. Endpoints: `GET/DELETE /api/voices`, `/api/voices/upload`,
  `/api/voices/from-clip`, `GET /api/voices/{id}/sample`, `POST /api/generate-voiceover`.
- **Roadmap:** auto-wire TTS into the orchestrator (`SegmentBuilder.tts_fn` /
  `director` silent-audio replacement) + a `nolan voiceover` CLI — deferred.

### TTS Studio (`/tts`) — 2026-06-26

Interactive single-utterance TTS playground built on the OmniVoice integration.
- **Voice source** (4 modes): saved voice · upload a sample · **crop from a library
  video** (player + Set-In/Out, or click a segment/cluster to prefill the range)
  · **voice design** (`instruct` text, no cloning). Cropped/uploaded samples are
  **ephemeral** (`voices/_tmp/<token>.wav`) with an optional "Save as voice".
- **Text source**: write/paste, or load a project's script (`GET /api/project/{p}/script`).
- **Params**: num_step (16/24/32), speed, language_id, instruct.
- **Output**: inline player + wav download; runs under the shared GPU lock.
- Backend: `operations.tts_synthesize`; endpoints `POST /api/tts/sample`,
  `/api/tts/sample-from-library`, `/api/tts/synthesize`, `GET /api/tts/sample/{t}`,
  `/api/tts/output/{t}`, `POST /api/voices/save-sample`. `OmniVoiceTTS` now passes
  num_step/speed/instruct/language through.

### TTS Studio — Script Projects source + Project Voiceover modes (2026-06-26)

- TTS Studio text source now lists **Script Projects** (`/api/script-projects`),
  loading `script.md` with markdown headings/metadata stripped.
- New **Project Voiceover** panel + extended `operations.generate_voiceover`
  (source = render project's `script.json` OR a Script Project's `script.md`):
  - `script.py.parse_script_sections` splits `script.md` on `##` headings into
    `{title, timecode, body}`; `clean_tts_text` strips markdown so only bodies are
    spoken (headings/`**Total Duration**`/`---` never read aloud) — both modes.
  - **mode=full** → concatenated `assets/voiceover/voiceover.mp3`.
  - **mode=segments** → per-section `assets/voiceover/segments/<NN>_<slug>.wav` +
    `segments.json` (title, timecode, duration) for the segment pipeline.
- Endpoints: `POST /api/generate-voiceover` (now takes `script_project` + `mode`),
  `GET /api/voiceover/{project}/{path}` serves outputs. Segment-pipeline auto-wiring deferred.

### Voiceover captions (SRT/VTT + word JSON) — 2026-06-26

Hybrid word-timing for generated voiceovers: Whisper word timestamps snapped to
the KNOWN script words (correct spelling of proper nouns/numbers), no new deps.
- `src/nolan/captions.py`: `align_words` (difflib sequence-align known↔Whisper +
  gap interpolation), `group_lines`, `words_to_srt` / `words_to_vtt`.
- `operations.generate_captions(project)`: CPU Whisper `transcribe_words` per
  segment (or the full mp3), aligns to section bodies, stitches a global timeline
  via segment offsets. Writes `assets/voiceover/voiceover.{srt,vtt,words.json}`
  (full) + per-segment `<seg>.{srt,vtt,words.json}`.
- Endpoint `POST /api/generate-captions`; outputs served via `/api/voiceover/...`
  (now sends srt/vtt/json types); `/api/voiceover-info` reports a `captions` flag.
- UI: "Captions (SRT)" button in the TTS Studio Project Voiceover panel; SRT/VTT/
  word-JSON download links appear once generated.
- Word JSON ({word,start,end}) is ready for kinetic/karaoke caption effects.
