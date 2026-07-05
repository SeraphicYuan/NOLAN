# NOLAN Code Review — 2026-06

Deep review of Scenes, Script Projects, Script Styles, Clips, Studio, Motion Effects,
Picture Library, Video Library + their modules and the hub/web layer. Findings below;
**Status** column tracks remediation.

## Cross-cutting themes
1. **Fragmented project model** — "a project" means 4–5 different things (filesystem
   `projects/<slug>/` seen through 3 scans, the index-DB `projects` table, the
   scriptwriter slug store, per-name imagelib scope). The FS and DB never reference
   each other; the pages show different project lists. *Root cause #1.*
2. **Triplicated pipelines & catalogs** — 3 scene pipelines (webui-linear, orchestrator,
   segment), 3 render dispatchers, 4 effect catalogs, 3 Remotion entry points, 4 search endpoints.
3. **Silent-failure class** — errors swallowed everywhere; failures show as black frames / cards.
4. **Dead/broken parallel code** — 3 legacy standalone apps duplicating hub routes; obsolete matcher.
5. **Copy-paste frontend / god-files** — no base template (16/16 inline `<style>`), hub.py 104-route
   closure, indexer.py 2176-line god-module.

## Phase A — confirmed bugs & security  →  FIXED + tested (tests/test_review_phase_a.py)
| Issue | Location | Status |
|---|---|---|
| Orchestrator NameError at select_clips (`result` unassigned) | director.py:1424-1440 | ✅ fixed |
| Every "counter" scene renders black (`CountUp` Effect vs `CounterRenderer`) | orchestrator/render.py:96 | ✅ fixed |
| Empty-query match crash (`[]` vs 3-tuple) | clip_matcher.py:176 | ✅ fixed |
| `NameError: re` in `_parse_json_object` | webui/operations.py:1234 | ✅ fixed |
| Path traversal in `scenes_serve_asset` | hub.py:1519 | ✅ fixed (containment) |
| Stored XSS (unescaped user data) | script_projects.html, scenes.html | ✅ fixed (`esc()`) |
| Transparent-alpha compositing ghosts toward bg | renderer/base.py | ✅ fixed (`_alpha_color`) |

## Phase B — delete dead/broken  →  DONE (core)
- ✅ Deleted standalone apps `library_viewer.py`, `showcase.py`, `viewer.py` + CLI commands
  `serve`/`browse`/`showcase`/`library` (hub already serves all). `library_viewer` was broken
  (called hub API prefix → 404) and defaulted to SPARTA's port 8001.
- ✅ Deleted obsolete `matcher.py` (`AssetMatcher`, superseded by `ClipMatcher`) + its test.
- ⏳ **Deferred:** prune `renderer/effects.py` (~30 unused classes + 7 unconsumed-prop) — needs the
  render suite to verify nothing is string-referenced; do as a dedicated render-tested pass.
- ⏳ **Deferred (trivial):** dead `scenes.py` PASS2 per-category prompts + `_parse_json_object`,
  `ScriptProjectStore.target_words`, `remotion_source.render_scene`.

## Phase C — structural consolidation
| Item | Status |
|---|---|
| Dedup `_MEDIA_TYPES` (was defined 2×) | ✅ done (with Phase-A traversal fix) |
| C1 Unify the project model (slug-keyed `Project`, FS↔DB link) | ◑ **in progress** — `src/nolan/projects.py` + `GET /api/projects` + `nolan projects status/backfill` + FS↔DB link on script-create DONE & tested (`docs/PROJECT_MODEL_DESIGN.md`, `tests/test_projects.py`). Migrating the 4 legacy listing endpoints onto it deferred (needs web render-testing). |
| C2 One render path (merge 3 dispatchers, shared ffmpeg/registry) | ⏳ deferred — needs render testing |
| C3 Decide script contract (script.json vs script.md; `style_guide.md` name collision) | ⏳ deferred |
| C4 Split hub.py into APIRouters; split indexer.py | ◑ **hub half done (2026-07)** — hub.py 3,361→286 lines; the ~200 routes moved verbatim into 18 `src/nolan/webui/routes/*.py` modules (`register(app, ctx)` per section; `ctx` = SimpleNamespace of the old closure locals). Route-surface parity verified (207 before = 207 after), hub tests green, live hub restarted + smoked. indexer.py split still deferred. |
| C5 Shared base template + adopt NolanJobs everywhere | ⏳ deferred — large frontend pass |
| C6 Collapse 4 search endpoints; factor duplicate FileResponse handlers | ⏳ deferred (partial: media-types) |
| C7 Shared helpers (`dispatch_agent_task` ×3, `slugify` ×3, vector_search upsert ×2) | ⏳ deferred |
| C8 FTS5 for indexer.search() O(N) scan | ⏳ deferred |

## Phase D — smaller gaps
| Item | Status |
|---|---|
| Hub default port 8001 → 8011 (SPARTA owns 8001) | ✅ done (hub.py + CLI) |
| Iteration UI dead for classic Studio (linear) projects (`detect_pipeline`) | ⏳ deferred — needs render testing |
| Hardcoded `C:/Windows/Fonts/...` in renderer/base.py | ⏳ deferred (centralize + bundled fallback) |
| Motion validation errors silently dropped | ⏳ deferred |
| ffmpeg: orchestrator uses bare PATH `ffmpeg` vs bundled imageio_ffmpeg | ⏳ deferred (folds into C2) |

## Why items are deferred (not skipped)
The remaining C/D items are either (a) **large blast-radius refactors** touching the whole app
(project model, render path, hub/indexer split, frontend base template), or (b) require the
**render/web runtime** to verify (effects prune, linear re-render, ffmpeg unification) which can't
be exercised reliably from WSL against the Windows-bound hub/renderer. Each should be its own
focused, individually-tested pass rather than a rushed batch.

## Pre-existing test failures (NOT introduced here)
`test_clustering` (stale `detect_boundary` API), `test_config`/`test_sampler` (stale defaults,
comfyui 8002→8080), 3 errors from missing `draft-20260104-110039.md` fixture, and `test_hub.py`
(a manual `uvicorn.run` smoke script that hangs pytest). Unrelated to this review's changes.
