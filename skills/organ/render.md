---
id: organ.render
name: Render dispatch + render modes
description: >
  How ONE scene becomes pixels — the per-scene render router shared by the segment and
  orchestrator paths. It picks the renderer by what the scene carries, in a fixed order:
  motion_spec → matched_clip (b-roll) → layout_spec → comfyui (generated) → card, and NEVER
  leaves a black hole — any failure renders a clean title card. Also the render MODES (premium =
  one Remotion Chapter per section with baked VO). Read before touching per-scene render routing,
  the never-black fallback, or premium mode — or when a scene rendered as the wrong kind / black.
  (The DOMINANT HF path renders the whole composition via the finish DAG instead — see below.)
kind: grammar
purpose: >
  Orient any render-routing task — the per-scene routing order + kinds, the resilient title-card
  fallback, the premium (Chapter-per-section) mode, and the pointer to the HF render path.
status: active
version: 1
tier: organ
handoffs: []
uses:
  - organ.asset-engine
documents:
  module: src/nolan/render_dispatch.py
loaded_by: []
evals: []
---

# Render dispatch + render modes

> **This is the LEGACY Director/segment render path — it renders scenes with Remotion.** The
> DOMINANT HF compose-first path renders the whole composition with **HyperFrames + GSAP** (see
> "The DOMINANT path renders differently" below and `[[pipeline.hyperframes]]`). Use this organ
> only for Director/segment/premium work.

## Per-scene routing (`src/nolan/render_dispatch.py`)

ONE place decides which renderer handles a scene and runs it — shared by the segment path (a Scene
**object**) and the orchestrator/iterate path (a raw **dict**, kept to preserve `layout_spec`).
Routing order, first field present wins:

    motion_spec → matched_clip (b-roll) → layout_spec → comfyui (generated) → card

Returned **kind**: `motion | broll | lottie | layout | generated | card | None`.

- **Never a black hole.** If a chosen renderer raises, `render_card()` draws a clean title card from
  the scene's intent instead of leaving black. A `card` return means a fallback fired — investigate
  the intended kind, don't ship the card silently.
- Only routing + render calls are shared; each caller keeps its own output-path / return / assemble
  conventions (segment vs orchestrator `assemble` paths are unchanged).

## Render modes

- **Standard** — scenes render to independent MP4s, assembled over the narration.
- **Premium** (`premium_render.py`) — FLOW convergence: every scene-plan SECTION is ONE Remotion
  Chapter with per-scene audio slices baked in, block visuals, and frame-exact step durations from
  the beat-anchored windows. Sections concat (hard cuts) → final.mp4; **video ≡ narration by
  construction**. Eligibility: every scene must map to a Chapter step.

## The DOMINANT path renders differently

This organ is the **Director / segment** per-scene render path. The dominant **HF compose-first**
path renders the WHOLE composition via the finish DAG's `render` step (`npx hyperframes render`) and
incremental `nolan hf-render` — not per-scene dispatch. For HF work start at `[[pipeline.hyperframes]]`;
use this organ for the Director/segment/premium path. Block prop-mapping: `[[organ.layout-blocks]]`.
