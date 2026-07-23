---
id: organ.layout-blocks
name: Layout-block adapters (Remotion-first rendering)
description: >
  How a layout scene's template params become Remotion flow-block props. `render_layout` tries the
  curated Remotion blocks library FIRST (the same blocks FLOW's Chapter composition uses), falling
  back to the legacy Python renderers on any failure or unmapped template (`NOLAN_LEGACY_RENDER=1`
  forces Python). Per-block ADAPTERS map params → props and return `(block_name, props)` or None
  ("no faithful mapping — use the Python renderer", e.g. a non-numeric statistic). Read before
  touching a layout-block adapter, adding a template→block mapping, or the Remotion/Python render
  fallback — or when a layout scene rendered with the wrong/legacy block.
kind: grammar
purpose: >
  Orient any layout-block task — the Remotion-first-then-Python fallback, the adapter contract
  ((block_name, props) | None), and graceful degradation without narration timing.
status: active
version: 1
tier: organ
handoffs: []
uses:
  - common.composition-craft
documents:
  module: src/nolan/layout_blocks.py
loaded_by: []
evals: []
---

# Layout-block adapters (`src/nolan/layout_blocks.py`)

> **This is the LEGACY Remotion render path.** It maps params to **Remotion** flow-blocks (the
> Director/FLOW renderer). The DOMINANT HF compose-first path does NOT use this — it authors blocks
> directly in the HyperFrames composition and renders with GSAP (`[[pipeline.hyperframes]]`).

Remotion-first layout rendering: `render_layout(params)` tries the **curated Remotion blocks
library first** (the same blocks FLOW's Chapter composition uses) via a one-step Chapter job
(`remotion_source.render`), and falls back to the **legacy Python renderers** on any failure or
unmapped template. `NOLAN_LEGACY_RENDER=1` forces the Python path.

## The adapter contract

Each per-block adapter (`_quote`, `_statistic`, `_counter`, `_timeline`, `_ranking`, `_comparison`,
`_list`, `_lower_third`, `_title`, `_chapter_card`, `_verdict`, `_location_stamp`, …) takes template
params and returns:

- **`(block_name, props)`** — a faithful mapping to a Remotion flow-block, or
- **`None`** — "no faithful mapping for these params, use the Python renderer" (e.g. a non-numeric
  `statistic` value). None is not a failure; it's the honest hand-off to the fallback renderer.

## Graceful degradation (renders standalone)

Blocks degrade WITHOUT narration timing: `revealFrames: []` reveals at frame 0 and `words: []`
disables word-sync, so a layout scene renders standalone. The premium / FLOW path later supplies the
real word timings through the SAME blocks (so a preview and the final use one block, not two).

## Where it sits

Called by the `layout` branch of `[[organ.render]]`'s per-scene routing. This is the block
PROP-MAPPING executor; the macro LAYOUT vocabulary (archetypes) is `[[common.composition-craft]]`,
and the dominant HF path authors blocks in the composition directly (see `[[pipeline.hyperframes]]`).
This organ is the Remotion/FLOW render path (`NOLAN_LEGACY_RENDER` toggles the Python fallback).
