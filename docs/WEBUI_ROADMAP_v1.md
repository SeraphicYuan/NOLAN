# NOLAN webUI Roadmap (v1)

Goal: make the hub **own the full loop for one project** — ingest → process → review assets →
render/assemble — on top of UI/UX improvements to the existing pages.

Date: 2026-06-14. See [Nolan_Structure_Map_v1.md](../Nolan_Structure_Map_v1.md) for the architecture.

## Principles
- Reuse existing patterns: FastAPI hub (`hub.py`), standalone HTML templates, async-job + poll (Showcase).
- CLI-backed operations run **in-process** as tracked jobs (the modules — indexer, script, scenes,
  matchers — are importable and already async/progress-aware). No subprocess sprawl.
- Surgical: add a shared static layer + a job manager; don't rewrite the existing pages.

## Foundation (Phase 0)
- `webui/jobs.py` — in-process `JobManager`: job = {id, type, status, progress, message, logs[], result, error}.
  Routes: `POST` start (per feature), `GET /api/jobs/{id}`, `GET /api/jobs`.
- `/static` mount + `nolan.css` (shared theme vars from hub.html) + `nav.js` (injected top nav) +
  `jobs.js` (reusable poll + progress widget). New pages use these; existing pages get the shared nav.
- Render-service health banner (clear "offline" state instead of raw 503).

## Features (priority order)
| Phase | Feature | Wraps | Output |
|---|---|---|---|
| 1 (B1) | Ingest / Add-to-Library | `youtube.py`, `HybridVideoIndexer`, `vision.py` | new video in library.db |
| 2 (B2) | Essay → process wizard | `parser`, `script`, `scenes` | new project + scene_plan.json |
| 3 (B3) | Asset review & curation | `clip_matcher`, `image_search`, `assets` | assets attached to scenes |
| 4 (B4) | Render + assemble + download | `renderer/`, `aligner`, `video_gen`, render-service | final video |
| 5 (B5) | Settings panel | `config.py` | nolan.yaml / per-project overrides |
| 6 (B6) | Vector index management | `vector_search.py` | embeddings synced |

## UI/UX (Phase A, woven through)
- A1 shared design system/nav (Phase 0)
- A2 Library faceting by people/location/objects (uses inferred_context)
- A3 progress feedback everywhere (job pattern)
- A4 service-down banners
- A5 settings visibility (Phase 5)

## Integration (Phase 7)
- **Project Studio** page: one project, the pipeline as stages (Ingest source ▸ Process essay ▸
  Review assets ▸ Render/Assemble), each showing status + an action that launches the matching job.
  This is where the full loop becomes visible and operable end-to-end.

## Status (updated 2026-06-14)
- [x] Phase 0 — job manager, /static, shared nolan.css + nav.js + jobs.js, render health banner
- [x] Phase 1 — Ingest UI (`/library/add`, `/api/ingest`) — verified live (job ran end-to-end)
- [x] Phase 2 — Essay wizard (`/process`, `/api/process`)
- [x] Phase 3 — Asset matching (`/api/match`, in-process `_match_broll`/`_match_clips`) wired into Studio
- [x] Phase 4 — Render/assemble (`/api/render-clips`, `/api/assemble`) via `run_cli` subprocess of proven CLI
- [x] Phase 5 — Settings (`/settings`, `/api/settings` → nolan.yaml) — verified
- [x] Phase 6 — Vector sync (`/api/sync-vectors`)
- [x] Phase 7 — Project Studio (`/studio`, `/api/project/{name}/status`) — full-loop stage view, verified vs real project
- [x] Phase A — shared nav on all pages, landing "Create & Operate" section, service-down banner, settings visibility

### Verified live (uvicorn @ :8011)
All 12 pages return 200; ingest job ran end-to-end; project status reads real data (72 scenes / 24 matched / 28 rendered).

### Remaining / follow-ups
- A2 Library faceting by people/location/objects (inferred_context) — not yet done.
- Phase 3 candidate **swap/approve** UI is v1 (trigger + coverage badge; view results in Scenes). Full per-scene
  candidate gallery with manual override is the next iteration.
- Phase 4 render/assemble are wired + plumbing-verified but not yet executed end-to-end via the UI (needs
  render-service running + a narration audio file for assemble).
