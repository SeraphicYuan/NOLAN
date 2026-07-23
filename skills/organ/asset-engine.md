---
id: organ.asset-engine
name: Asset engine (source-resolution ladder)
description: >
  The ONE per-scene source-resolution ladder shared by all pipelines. For each scene it picks the
  source that fits the scene TYPE, then escalates until something clears the bar: motion (Python/
  Remotion) for text/data/chart, an exact-title museum pass for named archival art (titles beat
  CLIP for named works), library video for footage, else stills → external providers → ComfyUI
  generation → none. Every choice is recorded on `scene.resolved_source` (no silent caps). Read
  before touching per-scene source selection, the escalation ladder, or `EngineConfig` thresholds —
  or when a scene resolved to the wrong source tier.
kind: grammar
purpose: >
  Orient any source-resolution task — the scene-type→source mapping, the escalation ladder, the
  resolved_source provenance record, and EngineConfig thresholds.
status: active
version: 1
tier: organ
handoffs: []
uses:
  - organ.acquire
documents:
  module: src/nolan/asset_engine.py
loaded_by: []
evals: []
---

# Asset engine — the source-resolution ladder (`src/nolan/asset_engine.py`)

**ONE** per-scene resolution ladder for all pipelines (promoted from the segment builder's
`AssetResolver`). Entry: `AssetEngine(cfg).resolve(scene)` (+ `resolve_all` / `resolve_dicts`).
It encodes the "source mix adapts to scene type" learning, then escalates.

## The ladder (per scene, by type, escalating)

1. **motion** (Python / Remotion) for **text / data / chart** scenes — authored on demand, not fetched.
2. **archival-art** scenes → an **exact-title museum pass FIRST** (titles beat CLIP for named works),
   then the escalation ladder.
3. **footage** scenes → **library video** search IF a match clears the threshold.
4. else **escalate**: picture-library **stills** → **external providers** → **ComfyUI generation** →
   **none** (honest failure — a scene that resolved to nothing is recorded, not hidden).

## Invariants

- **Every resolution is recorded on `scene.resolved_source`** — no silent caps. A scene that fell all
  the way to `none` says so; you can see exactly which tier answered.
- **Scene TYPE drives the first choice, not a global default** — text/data/chart want motion, named
  art wants the title pass, footage wants library video. Don't collapse to one source.
- **Titles beat CLIP for named works** — the exact-title museum pass exists because CLIP cosine can't
  discriminate named artworks (the woodcut lesson); don't route named art through generic CLIP search.

## Config + relationship to acquire

Thresholds/tiers: `EngineConfig`. This engine RESOLVES one scene from existing/known sources; the
acquisition engine (`[[organ.acquire]]`) BUILDS the over-provisioned pool the stills/footage tiers
draw from. Asset engine = per-scene pick; acquire = pool fan-out. See `[[project_asset_extraction]]`
and the HF pool (`/pool`).
