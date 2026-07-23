---
id: organ.acquire
name: Asset acquisition engine
description: >
  The multi-source asset acquisition organ — beat-driven, over-provisioned, relevance-ranked,
  fitness-gated. For every authored NEED it fans out to EVERY source (saved library + stock /
  archival / museum providers), over-fetches, CLIP-scores for relevance, culls junk with a
  ONE-vision-call VLM usability FLOOR (judge.py), de-dups semantically, keeps the best, and
  GENERATES originals where stock is thin or off-topic. Read before touching acquisition,
  source fan-out, the relevance/usability gates, provider tiers, or `AcquireConfig` tuning —
  or when the HF pool has junk / is thin / missed a beat. NOTE: `acquire/` is actively being
  consolidated — check git before editing the code.
kind: grammar
purpose: >
  Orient any acquisition task — the fan-out → gate → floor → dedup → generate pipeline, the
  two FLOORs (CLIP relevance, VLM usability), provider tiers + curated exemption, and config.
status: active
version: 1
tier: organ
handoffs:
  - { process: hyperframes, stage: acquire, gate: A }
uses:
  - common.pairing-craft
documents:
  module: src/nolan/acquire/engine.py
loaded_by: []
evals: []
---

# Asset acquisition engine (`src/nolan/acquire/`)

**The pool is the ceiling on essay quality.** For each authored NEED, acquisition builds a
pro-sourced b-roll pool: fan out to every source, over-fetch, rank, gate, keep the best, and
generate originals to fill gaps. Entry: `acquire_pool(needs, ctx, cfg)` → per-need
`acquire_need()`. Config: `AcquireConfig` (`acquire/config.py`).

## The pipeline (per need)

1. **Fan out to every source**, over-fetch `per_need * over_provision`. Sources ranked by
   `TIERS[category]` (category ∈ **art / archival / general**) — the saved **library** and
   **clips_library** always rank first.
2. **Download + decode-gate** (concurrent; network-bound fetch parallelized, CLIP/dedup after).
3. **CLIP relevance FLOOR** — a cheap cosine gate BEFORE the VLM (`clip_lib_relevance_floor`).
   Two source classes lie about relevance and are gated. **Curated** institutional/art providers
   (`_CURATED`: artvee, met, wellcome, wikimedia, loc, smithsonian…) are EXEMPT — for evocative
   beats their value is precisely the non-literal match a low CLIP score would cull.
4. **VLM usability FLOOR** (`judge.py`) — the semantic cull CLIP can't do, FUSED with the caption
   pass (~one extra prompt, not a call). Per kept image → `{usable, flags, caption}`. It is a
   FLOOR that removes junk, NOT a re-ranker. Video + generated stills are exempt.
5. **Semantic de-dup** (avg-hash + hamming) — drop near-duplicates.
6. **Keep the best** `per_need`; **generate originals** (evocative, floor-gated) where a beat is
   thin or off-topic.

## The usability FLOOR flags (`judge.UNUSABLE_FLAGS`)

An asset FLAGGED with any of these is dropped (honesty-tested against `judge.py`):
**watermark · overlaid text · heavy text · text overlay · stock-photo graphic · logo**.
The floor removes junk on a graceful-error → KEEP basis (never empty the pool on a VLM outage) —
so the downscale-before-vision step matters (a >4k image errors the API and junk then survives).

## Design invariants

- **Two FLOORs, not re-rankers.** CLIP + tier gates ORDER what survives; the VLM only culls. Don't
  turn the floor into a ranker.
- **Over-provision then cull.** Fan-out + over-fetch is deliberate — the pool is the ceiling.
- **Generate to fill, never to diversify.** Originals fill thin/off-topic beats; model policy is
  krea2-default, vary via Fooocus styles/prompts (see `[[feedback_generation_model_policy]]`).

## Where it lives + plugs in

`acquire/`: `engine.py` (fan-out/gate/dedup/generate), `context.py` (build_context, stock client),
`judge.py` (VLM floor — pure prompt/parse, unit-testable), `art_direction.py` (VisualBrief → prompt),
`coverage.py`, `shared.py` (de-duped helpers), `config.py`. Feeds the HF pool → `/pool`; the HF
bridge does the vision call + file cull. See `[[project_acquisition_engine]]`,
`[[project_acquisition_consolidation]]`, and `[[pipeline.hyperframes]]`.
