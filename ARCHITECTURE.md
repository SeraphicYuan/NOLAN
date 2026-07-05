# NOLAN Architecture

**Core purpose:** automate the video-making process — *script → plan → asset
matching (clips, pictures, Remotion blocks, themes, charts, numbers/words,
aligned with voiceover) → rendered video.*

This document describes the consolidated architecture (2026-07, phases 0–6 of
`docs/ARCHITECTURE_CONSOLIDATION.md`). It is a living doc: update it when a
contract or pipeline changes.

## The one pipeline (Director)

`nolan orchestrate <project> [--auto]` · webUI: Project Dashboard (/studio) or
Agents page. Nine steps, each checkpointed and idempotent
(`src/nolan/orchestrator/director.py`, `PIPELINE_STEPS`):

| step | does | artifact |
|---|---|---|
| match_and_adapt_style | style template match → project style guide | style_guide.md |
| script_to_scenes | script.md → sectioned scene plan | scene_plan.json |
| tempo_enrich | energy/pacing per scene (reference-blendable) | plan (in place) |
| select_clips | **asset engine** over footage+art scenes | matched_clip/matched_asset |
| slide_designer | layout_spec for info scenes (23 templates) | plan (in place) |
| generate_assets | ComfyUI imagery for `generated` scenes (krea2 registry default) | assets/generated/*.png |
| voiceover | local TTS via the **voice pipeline** (per-beat wavs) | assets/voiceover/ |
| align_narration | beat-anchored timing (`nolan align`) | plan windows |
| render | render scenes + assemble WITH narration (or premium mode) | output/final.mp4 |

**The sync contract:** narration owns duration. Per-section VO files
(`assets/voiceover/_work/sec_NNNN.wav`) give exact audio spans; scene windows
are confined to their section's span and tiled gap-free
(`scenes.anchor_scenes_to_sections`), so video ≡ narration and sync errors
cannot cross beats.

## Contracts

- **ScenePlan is lossless + versioned** (`src/nolan/scenes.py`, schema_version 2).
  Unknown scene keys survive round-trips in `Scene.extra` (folded back flat on
  save); unknown top-level keys in `ScenePlan.meta`. Raw-dict layers round-trip
  through `ScenePlan._scene_from_dict/_scene_to_dict` safely.
- **Assemble is honest**: relative `-o` resolves against CWD; non-zero exit on
  any failure; output existence verified. Field priority at assemble:
  `rendered_clip > generated_asset > matched_asset > infographic_asset`.
- **Failures are loud**: steps record errors in state + raise; no silent
  rc-0-on-failure, no silent caps.

## One asset engine

`src/nolan/asset_engine.py` — the single per-scene resolution ladder:

```
motion_spec present → done
archival-art → exact-title museum pass → semantic fallback
footage      → vector clip search (ClipMatcher, gate 0.5)
             → operator BRIDGE on miss: tonal/conceptual metaphor queries
               (evoke_broll prompts) re-probe the search tier
generated    → comfyui_prompt
graphic/text → lazy motion authoring (LLM)
escalation   → picture-library stills (hybrid CLIP+BGE; bridged queries too)
             → external providers → generate → none(reason)
```

Every resolution writes an auditable `scene.resolved_source`.
`AssetEngine.from_config` wires the standard backends lazily; tier fns are
injectable. Thin callers: segment resolver (`segment/resolver.py` shim),
Director `select_clips`, iterate reresolve (`resolve_dicts`, lossless).
NOTE: clip-search `project_id` scopes the index and must be an id the index
knows — omit for global search; the project imagelib is discovered from
`project_path` independently.

## One render story (Remotion-first)

- **Layouts**: `render_layout` renders all 23 templates through the curated
  Remotion flow-blocks (`src/nolan/layout_blocks.py` adapters → one-step
  Chapter job via `remotion_source.render`). Python renderers
  (`renderer/scenes/`) are the automatic per-scene fallback;
  `NOLAN_LEGACY_RENDER=1` forces them.
- **Motion specs**: `src/nolan/motion/` registry is one-backend-per-intent —
  `block` (curated blocks), `remotion` (compositions), `python` (line-chart,
  loop-diagram only). Executor: `motion/executor.py`.
- **Premium mode** (`render_mode: premium` in project.yaml): every beat renders
  as ONE Remotion Chapter with per-scene VO slices baked in
  (`src/nolan/premium_render.py`) — FLOW's driver fed from the scene plan. The
  section WAV is the timing authority (frame-exact normalization); ineligible
  scenes fail the run with ids listed. Media paths must be absolute (staging
  runs with node CWD = render-service/).
- **FLOW** (`src/nolan/flows/`) remains the hand-authored premium format; its
  Chapter/blocks are the same ones premium mode and layouts use.

## One voice pipeline

`src/nolan/voice_pipeline.py` — async, GPU-locked TTS core (OmniVoice):
per-section synthesis, voice cloning from the voice library, full-mp3 or
segments packaging. The webUI voiceover op is a thin job adapter over it.
Voice resolution everywhere = `nolan.voiceover.resolve_voice_ref`
(project.yaml `voice_id` → config `tts.default_voice`). `nolan/voiceover.py`
also carries the segment builder's sync per-section core + captions + word
alignment (body dedup pending).

## Surfaces

- **Hub** (`src/nolan/hub.py`, :8011): FastAPI app; jobs run through the single
  `webui/jobs.py` JobManager; long operations live in `webui/operations.py`.
  Pages: Project Dashboard (/studio — pipeline chips + run controls +
  artifacts + final player), Agents (checkpoints/plan/feedback), Scenes,
  Voices (voice library + TTS studio + project voiceover, merged), Library /
  Add / Clips / Picture Library / Extract / Evocative B-roll, Deconstruct,
  Script Styles/Projects, Video Styles, Lottie, ComfyUI, Publish, Showcase,
  Skills, Settings. `/tts` → 307 `/voices` (transition alias).
- **CLI**: `nolan.cli` package (domain modules; `cli_legacy` is a compat shim
  for helper imports). Entry: `from nolan.cli import main`.
- **render-service** (:3010, Node): legacy HTTP engines (Lottie path) + the
  `remotion-lib/` bundle invoked via `render.mjs` CLI (NOT HTTP) for
  compositions/Chapters.

## Test nets

- `scripts/test_e2e_smoke.py` — THE regression net: fixture project through
  anchor → stamp → render (Remotion + fallback) → annotate → assemble;
  asserts video ≡ audio, losslessness, honest assemble.
- `scripts/test_director_steps.py` — step sequencing + skip paths (no GPU/LLM).
- `tests/` — pytest suites: asset engine ladder, segment builder (through the
  shim), iterate, render dispatch, hub routes, and more.
- Live acceptance pattern: copy a real project (e.g. `projects/aeneid-auto-test`),
  reset the target artifacts, run `orchestrate --auto`, verify
  |video − narration| < 1s and spot-check frames.

## Known deferred work

- hub.py APIRouter split (200 routes defined in one `create_hub_app` closure —
  needs state-to-dependency conversion; dedicated session).
- URL convention normalization (4 conventions in the wild; alias-then-remove).
- `voiceover.py` ↔ `voice_pipeline.py` body dedup; `match_broll_v2._try_library`
  onto the engine's library tier; evoke_broll operators as the retrieval query
  layer for every engine tier.
- `annotate_scene_plan` re-tiles windows from planner durations when aligned
  windows are absent — premium mode is immune; standard mode is capped by
  audio at assemble, but the re-tiling should be removed.
