# NOLAN Flows — the multi-type video engine (design reference)

This package turns a **source (transcript / paper / artwork + assets)** into a **final video**
you can then **review and edit per beat** in the Scene page. It is a *multi-type* workflow (art,
explainer/paper-video, book, …) built as **one shared engine with routing at a single step —
ingest.** Read this before changing anything here.

> If you're an agent **editing a beat** of a flow video, read **`skills/flow/edit-contract.md`**
> (the edit contract). If you're **planning/authoring**, read **`skills/flow/authoring.md`**
> (the craft). This file is the *architecture*. Skills are cataloged in `skills/` (run
> `python -m nolan.skills` to lint).

## The one idea
A "flow" (video type) is a **descriptor**, not a pipeline. Everything below the **job JSON** is
identical for every type; the router only forks at **ingest** + picks the **profile/palette**
(config). So adding a video type = one ingest adapter + one registry row — no engine change.

```
source ──► INGEST (per-type) ──► job.json ──► GATE ──► RENDER ──► DELIVER ──► SCENE VIEW ──► (edit loop)
            ▲ the only fork        └──────────────── all SHARED, flow-agnostic ─────────────────┘
```

## Layers (what's code vs config vs skill)
| Layer | Form | Where |
|---|---|---|
| ingest/gate/render **mechanics** | **code** (deterministic) | `src/nolan/flows/` (this package) |
| palette (blessed/shared motions) · pacing profile · theme/fx defaults | **config** | `web-video-lab/flows/registry.json`, `themes/` |
| **plan/authoring** craft · **edit/invent** craft | **skill** (agent reads it) | `skills/flow/authoring.md`, `skills/flow/edit-contract.md` (+ `skills/common/` references) |

**Principle:** the engine runs the mechanical path deterministically, but **at the plan checkpoint
and at edit/invent it hands to an agent** reading the skill. That keeps determinism *and* the
freedom to do something new (e.g. invent a new block). Don't rigidify the edges into code.

## File map (this package)
| File | Role |
|---|---|
| `__init__.py` | `Flow` descriptor + `get_flow(id)` — the router (reads `registry.json`) |
| `project.py` | `load_flow_spec(project)` — a project owns its plan at `projects/<slug>/flow.spec.json` |
| `base.py` | `run_flow` / `run_flow_for_project` — the **shared engine**; `render_chapter`, `deliver`, `_win` |
| **ingest** | `ingest.py` (`ingest_art` — art = assemble byo-everything) · `art.py` (the art tenant names it). *Explainer adds `ingest/explainer.py` when promoted.* |
| **gate/** | `run_gate(job, flow)` → `validate.py` (structural + palette) · `pacing.py` (wpm/reveal/gap/density) · `contact.py` (1–2 stills/beat → labeled sheet, subprocesses node `still.mjs` + ffmpeg) · `montage.py` (Pillow sheet, in-process) |
| `render.py` | **chapter-block** mechanism: each beat → single-step `remotion-lib` job → clip; concat |
| `scene_view.py` | `build_scene_plan(project)` — projects beats into the `scene_plan.json` the Scene page reads |
| `edit.py` | `patch_beat` / `patch_focus` / `set_beat_asset` — edits write to `flow.spec.json` (source of truth) |
| `authoring.py` | Gate-A plan-time HITL: `draft_plan`, `plan_status`, `accept_draft`, `run(mode=auto\|semi-auto)`, `dispatch_refine` (to a tmux agent) |
| `run.py` | `python -m nolan.flows.run --flow art <spec>` |

## Runtimes (post-consolidation)
The engine runs **in-process under the nolan env python** (`D:\env\nolan\python.exe`) — what the
WebUI/CLI use; has Pillow + FastAPI. Only two things are subprocessed because they're external
runtimes: **Windows node** (the Remotion render: `remotion-lib/render.mjs`, `still.mjs`) and
**ffmpeg** (concat/faststart/blackframe). `base._win` + `ingest._localize` make paths work for the
Windows node/ffmpeg regardless of how the python is launched. **Heads-up:** that console is cp1252
— keep `print()`s ASCII or cp1252-safe (`· × —` are fine; `✓ → ⏸` are not).

## End-to-end (auto mode)
`nolan render-flow <project> --mode auto` (`cli_legacy.render_flow_cmd`) → `authoring.run` →
`base.run_flow_for_project` → `load_flow_spec` → **ingest** (`flow.ingest` → `ingest_art`, writes
`projects/<slug>/flow.job.json`) → **gate** (`run_gate` in-process: validate+palette, pacing,
contact) → **render** (`render.py` per-beat clips via node `remotion-lib/render.mjs` + the 39-block
library + theme `tokens.css`; concat) → **deliver** (ffmpeg faststart → `projects/<slug>/video/`) →
**scene view** (`build_scene_plan` → `scene_plan.json`).

## Review + edit (Scene page — `src/nolan/hub.py`, `templates/scenes.html`)
- `/scenes/api/scenes/flat` refreshes the view (`build_scene_plan`) and serves beats as scene rows.
- `/scenes/api/scene/revise` (direct field patch) → `edit.patch_beat` → `flow.spec.json` → re-ingest.
- `/scenes/api/scene/assets` add → `edit.set_beat_asset` binds into the beat's block prop.
- `/scenes/api/rerender` → `iterate/engine.py::_rerender_flow` (dispatched by `detect_pipeline → "flow"`)
  → re-renders **only** the selected beats (`render.render_beats`) + re-concats. ~20s for one beat.
- `/scenes/api/flow/refine` → `authoring.dispatch_refine` (sends a per-beat plan to a tmux agent).
- `/scenes/api/flow/accept` → `authoring.accept_draft` (promote a refined draft → `flow.spec.json`).
- Agent edits are dispatched **flow-aware** (`fleet.build_flow_dispatch_prompt`): carries flow id,
  theme, palette, per-beat tray/wishlist, the edit contract, points to `skills/flow/edit-contract.md`.

## Why a beat re-renders independently
Each beat's `durationInFrames` is **pinned to its voiceover segment**, so a visual edit (swap
block, change asset, nudge a focus) never reflows the timeline → the beat is a standalone clip,
re-rendered and re-concated alone. This is what makes per-beat HITL cheap.

## Adding a video type (e.g. explainer / book)
1. `flows/ingest/<type>.py` — the ingest adapter (explainer = generate: wire NOLAN's TTS + Whisper
   + figure extraction + `gen_spec`; book = its own acquisition). Output: the same `job.json`.
2. `registry.json` — a type row: `palette` (blessed motions) + `common_palette` shared + `pacing`
   profile + `defaults` + `render_mechanism: chapter-block`.
3. Register the tenant in `get_flow`'s `tenants` map.
Everything else — gate, render, deliver, scene_view, edit, authoring, Scene-page wiring, flow-aware
dispatch — is **reused unchanged**. (Explainer's row already exists in `registry.json`.)

## Gotchas / open items
- **One bundle, two component shapes** — `remotion-lib/` is now the single render bundle (the temp
  `_lab_chapter/` was folded in + retired, Track 2 in `web-video-lab/flows/CONSOLIDATION.md`). It hosts both
  `src/blocks/library/` (40 Chapter-step blocks, the flow library) and `src/*.tsx` standalone
  `<Composition>` effects (the per-scene motion path). `render.mjs` branches on job shape. Reuse the
  one library; never rebuild (`skills/flow/edit-contract.md` rule 3). Minor residual dup: PhotoGrid/PhotoMontage
  exist as both a block and an effect-Composition — eventually mergeable, not urgent.
- **cp1252 prints** (above).
- **Standalone shims**: `web-video-lab/{art_ingest,art_check,…}.py` are thin CLI wrappers re-exporting
  this package (kept for standalone runs + the docs).

## See also
`web-video-lab/flows/`: `INTEGRATION.md` (why a flow path, not the motion registry) ·
`web-video-lab/flows/EDITOR.md` (the per-beat HITL design) · `web-video-lab/flows/CONSOLIDATION.md` (this defrag) · `skills/flow/edit-contract.md` /
`skills/flow/authoring.md` (the skill layer) · `registry.json` (the type config).
