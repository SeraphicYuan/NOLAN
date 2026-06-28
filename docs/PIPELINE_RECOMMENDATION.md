# Pipeline Consolidation — Recommendation (pick one primary)

Decision requested: NOLAN has **three** pipelines that all produce `scene_plan.json` and a
final video. Pick a canonical one, make it the default UX, demote the rest. This doc
recommends the target and a phased, low-risk migration. (Companion to the 2026-06 review;
relates to review items C2 + C1.)

## The key insight: compare *layers*, not whole pipelines
Each "pipeline" is really three stackable layers. They mix and match:

| Layer | Studio (linear) | Orchestrate (director) | Segment (build-from-segment) |
|---|---|---|---|
| **Authoring** (design scenes) | `SceneDesigner` two-pass (in-proc) | **Claude CLI agent** writes the plan + checkpoints/refine | `SceneDesigner` two-pass + `author_motion` |
| **Resolve** (pick assets) | `match_broll_v2` (now library-first) | vector matcher (`_match_clips`) | **`AssetResolver`** fallback chain (motion→segment-search→**library**→external→ComfyUI→card) |
| **Render** | `PythonTemplateEngine` (regex auto-detect, **legacy**) | `orchestrator/render.py` (no ComfyUI, no fallback card) | **`segment/render.py`** (motion + b-roll + ComfyUI + card) |
| **Hub UI** | ✅ `/studio` (friendly buttons) | ✅ `/agents` (monitor/run dashboard) | ❌ **none — CLI only** |
| **`/scenes` iteration** | ❌ not supported (`detect_pipeline` gap) | ✅ | ✅ |
| **Maturity** | oldest; legacy renderer | experimental; carried 2 of the bugs we fixed | newest; cleanest code; most complete |

**Observation:** the three *render* layers and three *resolve* layers are the duplication that
caused the divergence (the counter black-frame, PATH-ffmpeg, no-ComfyUI gaps were all in the
weaker render paths). The *authoring* layer is legitimately pluggable (essay vs Claude-director
vs indexed-span/script/VO are different inputs).

## Recommendation
**Canonical core = Segment's `AssetResolver` + `segment/render.py`.** Make resolve+render a single
shared core; let authoring stay pluggable but always emit into that core.

1. **One render path.** Promote `segment/render.py`'s `render_scene` to *the* renderer
   (`motion_spec → matched_clip → layout_spec → comfyui → card`, bundled ffmpeg). Retire
   `orchestrator/render.py` and `renderer/engine.py` (legacy regex). [review C2]
2. **One resolver.** `AssetResolver` is the asset picker; fold `match_broll_v2`'s providers in as
   an `external_fn` source (it already has library-first, segment-search, ComfyUI, card).
3. **Give the canonical core a hub UI.** Today the best engine has no page. Add a "New Video"
   hub flow over the segment core (or re-point Studio's existing buttons at it) so the default
   user path uses the strong engine — and gains `/scenes` iteration for free.
4. **Demote the others to authoring front-ends / advanced:**
   - **Studio page** → keep as a friendly entry but its render/resolve buttons call the canonical
     core (not `render-clips`/`PythonTemplateEngine`). Eventually it's just "the essay→video UI."
   - **Orchestrate** → optional/advanced "Claude designs the scenes" authoring mode that writes a
     plan, then hands to the canonical resolve+render. Keep `/agents` for those who want the
     checkpoint/refine loop; stop maintaining its separate render path.

Net: **one resolve+render core, three optional authoring entries, one consistent `/scenes` edit
loop** — instead of three half-overlapping stacks.

## Why segment (not Studio or orchestrate)
- Only path that renders the full capability set (motion + b-roll trim + ComfyUI gen + fallback
  card) and uses the bundled ffmpeg.
- Cleanest, smallest code; resume-guard + one-bad-scene isolation already built.
- Already integrated with `/scenes` iteration and the picture library (library-first).
- Studio's renderer is explicitly legacy (regex `PythonTemplateEngine`); orchestrate's render
  path is the least mature (it held the bugs we just fixed).

## What this fixes
- Kills the class of "works in pipeline X, broken in pipeline Y" bugs (counter, ffmpeg, ComfyUI,
  alpha) by having **one** path.
- Removes ~3 render registries + duplicated b-roll/ffmpeg/assemble helpers (review C2/B).
- Gives users **one obvious door** instead of Studio-vs-Agents-vs-CLI.

## Phased migration (each step independently testable; no big-bang)
- **P1 — unify render dispatch (no UX change).**
  - **P1a ✅ DONE:** shared `src/nolan/ffmpeg_utils.py` (bundled-ffmpeg subclip / silent-audio /
    normalize filtergraph); segment + orchestrator both delegate to it. Fixes the orchestrator's
    bare-`ffmpeg`-on-PATH bug and normalizes its b-roll output to 1920×1080@30 (matching segment,
    so assemble concats consistently). Removed the triplicated helpers. Tests: `tests/test_ffmpeg_utils.py`.
  - **P1b ✅ DONE (routing):** shared `src/nolan/render_dispatch.py::render_one` handles the union
    (`motion_spec → matched_clip → layout_spec → comfyui → card`) for both a Scene object and a raw
    dict. `segment/render.py` and `orchestrator/render.py` both delegate to it, each keeping its own
    output-path + return convention (so `assemble` paths are byte-unchanged). The orchestrator now
    renders a **title card** for `generated-image` instead of a black frame. Routing fully
    unit-tested (`tests/test_render_dispatch.py`).
    **Render-verified (2026-06):** drove both real paths under the Windows env python — orch b-roll,
    orch generated-image→card, orch counter, and segment b-roll all produced **1920×1080 non-black**
    clips. The generated-image card and the counter both render (were black before). Per-scene render
    confirmed; full `assemble` not separately run but all clips are uniform 1920×1080@30 so concat is
    dimension-safe, and `assemble` itself was unchanged by P1.
  - **P1c — TODO (after the render pass):** decide whether to give the orchestrator a real
    ComfyUI `gen_fn` (it falls back to a card today) and retire the now-unused `render_b_roll`.
- **P2 ✅ DONE — unify resolve.** Shared `src/nolan/external_assets.py::external_match_for_scene`
  (query-variant → provider search → quality pre-filter → vision score → attach video by ref /
  download image) + `build_query_variants`. `match_broll_v2` now calls it; `AssetResolver`'s
  `external_fn` (wired in `SegmentBuilder._make_external_fn`, `BuildConfig.enable_external=True`,
  prefer-images since the segment pipeline has no materialize step) calls it too — so the resolver
  chain is the single picker: **motion → segment-search → library → external → comfyui → card**.
  Resolver `external_fn` contract updated to attach the asset itself (image or video clip) and return
  a kind. Tested: `tests/test_external_assets.py` + resolver tests + **render-verified** (external
  image → assemble → 1920×1080 non-black video).
- **P2.5 ✅ DONE — lazy motion authoring (replaces eager `author_motion`).** Instead of an eager
  design-stage pass, the resolver now authors a `motion_spec` **on demand** for graphic/text/data
  scenes that reach it with none: `ResolverConfig.enable_motion` + `AssetResolver(motion_fn=…)`,
  wired in `SegmentBuilder._make_motion_fn` (calls `nolan.motion.compile_spec`); the builder's
  eager `author_motion=True` pass is removed. So graphics are authored only when actually needed,
  and any pipeline that runs scenes through the resolver gets motion for free. **Verified end-to-end
  with the real LLM:** graphic scene → resolver authored `motion:counter` (python/CounterRenderer)
  → rendered 1920×1080 non-black. Tests in `tests/test_segment_builder.py`. This also **unblocks P3**:
  Studio no longer needs an eager `author_motion` flag — re-pointing its render at the core means
  its graphics get authored at resolve time.
- **P3 ✅ DONE (render-verified) — Studio render through the unified core.** `render-clips` (Studio's
  "Render clips" button) now has a `--unified` pass (default on): for graphic/text/data/generated
  scenes it lazily authors a motion_spec and renders via `render_one` (`_unified_render_clip`), only
  falling back to the Remotion **render-service** for what the core can't handle (`--no-unified`
  restores exact legacy behavior). It even renders graphic scenes the legacy path ignored (no
  infographic/sync/animation needed). **Render-verified:** real `nolan render-clips` on a bare
  text-overlay scene → core authored a `counter` → `assets/clips/g1.mp4` 1920×1080 non-black. Tests:
  `tests/test_render_clips_unified.py`. *Recommend a quick live Studio browser pass to confirm the
  full button flow, but the CLI path it invokes is verified.*
- **P4 ✅ DONE — retire legacy render code.** Deleted: `renderer/engine.py` (615-line
  `PythonTemplateEngine` regex renderer) + its only caller the `render-templates` CLI command (~260
  lines) + the `renderer/__init__` exports; and `orchestrator/render.py::render_b_roll` (dead — b-roll
  now via `render_dispatch`→`ffmpeg_utils.extract_subclip`). Audited first: no tests, no other
  importers, not wired into Studio/hub. **NOTE:** `orchestrator/render.py` itself is *kept* —
  `render_layout` is used by `render_one`, `render_scene`/`annotate_scene_plan`/`generate_silent_audio`
  by iterate/director. **Lottie rendering** (only reachable via the orphaned `render-templates`) is
  retired with it; reintroduce as a `render_one` branch if needed. Verified: imports clean, CLI loads,
  render-clips still renders via the core post-deletion; 105 tests green.

## C2 status: COMPLETE
P1 (one render path) · P2 (one resolve path) · P2.5 (lazy motion) · P3 (Studio→core) · P4 (retire
legacy) — all done & render-verified. One asset picker (`AssetResolver`), one renderer
(`render_dispatch.render_one` + `ffmpeg_utils`), graphics authored lazily, Studio routed through it,
legacy regex renderer deleted. Plus a Studio bug fixed (assemble `--audio-file` → positional).
Remaining follow-ups (optional): give the orchestrator a real ComfyUI `gen_fn` (currently cards);
fold `match_broll_v2`'s remaining job-shell into the resolver.

## Lottie reintroduced (post-P4, the clean way)
`src/nolan/lottie_render.py`: `render_lottie_to_mp4` (via the render-service async job API:
POST /render `{engine:"remotion", data:{lottie_path}}` → poll /render/status → /render/result),
`prepare_lottie` (customize text/colors/duration via `nolan.lottie.customize_lottie`), and
`render_lottie_for_scene`. Wired as a **branch in `render_one`** (scenes with
`lottie_asset`/`lottie_template`; falls through if the render-service is down) and a **`nolan
render-lottie`** CLI. Render-verified against the live render-service → 1920×1080 MP4. Note: the
render-service API had **changed** since the legacy `render-templates` code (was sync
`{spec:{type:lottie}}`, now async `{engine,data}`) — caught + fixed by live testing. Tests:
`tests/test_lottie_render.py`.

### E2E shakedown fixes (2026-06)
Front-to-back runs on a current-vocab plan slice (canonical visual_type = b-roll|graphics|a-roll|
generated|host) surfaced + fixed: (1) `render_one` only carded `generated-image`, not canonical
`generated` → black; now `vt.startswith("generated")`. (2) `render-clips` lazily authored motion for
generated scenes → a remotion spec that can't render locally → black; now generated skips motion
authoring (→ comfyui/card). (3) hub `/api/match` default b-roll used the legacy single-query matcher
(0 yield on specific queries) → now routes to `match_broll_v2` (query-variant fallback + multi-source +
library-first). (4) `assemble` now prints a loud final QA report of BLACK (asset-less) scenes. (5) `match_broll_v2`
gained `use_vision` (default off): the free local quality/CLIP pre-filter picks the candidate; remote
vision scoring is opt-in — b-roll match dropped from >9min to ~5s for 4 scenes (~115×). Full clean
12-scene slice now reaches 12/12 scene coverage (generated/graphics/b-roll all matched+rendered).

### Lottie API + showcase (hub)
Hub HTTP API: `GET /api/lottie` (catalog + categories, ?category/?q), `GET /api/lottie/{id}`,
`GET /api/lottie/{id}/raw` (JSON for client preview), `POST /api/lottie/render` (job →
`operations.render_lottie_preview`; schema `fields`/text/colors customization),
`GET /api/lottie/preview/{name}` (serves MP4, path-contained). Page `/lottie`
(`templates/lottie.html`): grid with **live lottie-web previews** (client-side, no render-service
needed to browse), schema field editor, **Render MP4** (render-service). Nav entry added. Backed by
`TemplateCatalog` (52 templates). Render-verified live (field override → 1920×1080). Tests:
`tests/test_hub_lottie.py`. Previews → `_library/lottie_previews/` (gitignored via `/_library/`).

## Risks / non-goals
- **Authoring stays plural** — we are NOT forcing one way to *design* scenes (essay, Claude, span
  are real different inputs); we unify *resolve+render* only.
- **Orchestrate's checkpoint/refine** is a genuine feature for some users — kept as an authoring
  mode, not deleted.
- P3 (hub UI) needs browser verification against the Windows-bound hub — gate it on a manual pass.
- Backward-compat: existing `projects/*/scene_plan.json` must still render through the unified path
  regardless of which pipeline produced them (parity tests in P1).

## Decision points for you
1. **Studio page**: re-point it at the segment core (keep the essay→video UI), or retire it once
   the new flow exists? *(Recommend: re-point — it's the friendliest entry.)*
2. **Orchestrate**: keep as an advanced "Claude-designs-scenes" authoring mode, or freeze it?
   *(Recommend: keep but stop maintaining its render path.)*
3. Start with **P1 (unify render dispatch)** — safe, testable here, immediate de-dup — yes?
