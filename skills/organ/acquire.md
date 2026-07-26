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
   The transcript library is reached by TWO indexes over one corpus, interleaved (never concatenated —
   `c.rank` comes from list position and feeds the score, so the second tier would be systematically
   demoted): **transcript_lib** = what is SAID (transcript segments), **transcript_frames** = what is
   SHOWN (gemma-captioned keyframes, `content_kind=broll` only). The SHOWN tier exists because a segment
   anchors where the narrator *says* the topic — measured on diamond-v2, that put the super-pit
   documentary at 0.0s, its title card, while the frames held the shovel (62.0s), the controls (66.2s)
   and the Komatsu truck (97.4s). It also gives a TRUE single-shot range (keyframe → next keyframe: 3.1s
   / 8.3s / 11.6s measured) where `_clip_window` can only take a flat ≤5s guess from a segment start —
   the "shots table" its own docstring names as the missing piece. It reaches only CAPTIONED rows, so it
   is ADDITIVE to the segment tier and the captioned/total split is printed per run.
2. **Download + decode-gate** (concurrent; network-bound fetch parallelized, CLIP/dedup after).
   A **transcript_lib** or **transcript_frames** hit is materialised by pulling JUST its RANGE from the source URL,
   then **cleaned** (`shared.clean_media_inplace` — a same-aspect crop that removes the burned-in
   watermark/chyron + caption band). These are BROADCAST sources; pooling them raw puts another
   channel's brand in the essay. The same helper serves the human clip-review route, so the two
   paths can't drift.
3. **CLIP relevance FLOOR** — a cheap cosine gate BEFORE the VLM (`clip_lib_relevance_floor`).
   Two source classes lie about relevance and are gated. **Curated** institutional/art providers
   (`_CURATED`: artvee, met, wellcome, wikimedia, loc, smithsonian…) are EXEMPT — for evocative
   beats their value is precisely the non-literal match a low CLIP score would cull.
4. **VLM usability FLOOR** (`judge.py`) — the semantic cull CLIP can't do, FUSED with the caption
   pass (~one extra prompt, not a call). Per kept image → `{usable, flags, caption}`. It is a
   FLOOR that removes junk, NOT a re-ranker. Video + generated stills are exempt.
5. **Semantic de-dup** (avg-hash + hamming) — drop near-duplicates. Clips de-dup by RANGE instead:
   the **claim ledger** (`capture/_claims.json`, `shared.record_claim` / `range_is_claimed`) is the
   one dedup channel between the PRECISION pool (keyassets heroes, which runs first and claims what
   it pulled) and this RECALL pool. Ranges are exact and known at search time — better than hashing,
   which two crops of one shot defeat.
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
- **A retrieval score is not a topic gate.** The segment text-embedding compresses cosine into a
  narrow band (~0.65-0.75 for ANYTHING), so `clip_lib_min_sim` is a tail-trim only — measured live,
  "Lightbox Jewelry" retrieved free LIGHTNING stock at 0.680 and "2004 court proceedings" retrieved
  WATERGATE footage at 0.660. Discrimination is the downstream CLIP frame gate + VLM's job. Where
  this tier feeds the HERO pool (`keyassets/resolve.py`) the VLM is the ONLY real gate, so there it
  demands a POSITIVE confirmation rather than merely surviving — a wrong hero beats no hero never.
- **The pool must be able to feed the gate.** The essay's `video_share` dial reaches
  `derive_asset_needs`, which sets a floor on how many needs are video; without it a `heavy` essay
  derived 24/24 image needs and the style contract's motion gate became unsatisfiable.
- **ONE resolution policy, and it is not the preview policy.** Pool-asset downloads take
  `min(available, 1080)` via `nolan/media_quality.py`; preview/captioning deliberately stays low-res
  (`pick_derivative(purpose='caption')`, `clipper.preview_frames`). Conflating them is how every video
  provider ended up with its own conservative heuristic — pexels took the first `>=720`, pixabay
  preferred `medium` over `large`, archive took the median file by byte size, and library INGEST
  capped at `height<=720` with no `ffmpeg_location`, so failed merges fell through to 360p. The
  library's source quality is the ceiling on every clip trimmed from it, so that one cap put 46 of 48
  library clips in the diamond pool at 360p. Any yt-dlp call that may merge MUST pass
  `ffmpeg_location` — without it the degrade is silent (you still get a file).
- **No silent caps on quality.** Clips carry probed `width`/`height` into `pool.json` (read off
  `ffmpeg -i`, since imageio_ffmpeg ships no ffprobe), and the author's menu marks sub-720p pulls as
  ground-only and copyrighted pulls as excerpt-only. YouTube is externally 360p-capped here —
  a STALE yt-dlp, not YouTube: pinned at 2026.01.31 vs 2026.07.04 current, the old extractor
  couldn't reach the adaptive formats and fell back to format 18 (360p) while emitting a SABR
  warning that read like an external block. Upgrading yt-dlp (+ yt-dlp-ejs) restored up to 4K;
  the snippet path now returns 1920x1080. `deno` is a red herring (identical with/without).
  KEEP YT-DLP CURRENT — a stale extractor degrades silently and blames upstream.
- **A pool rebuild releases its own claims.** `clear_claims(project, 'pool')` at the head of each
  acquisition — the ledger is append-only, so otherwise a re-acquire skips every range the last build
  took and looks like the source went dry. Hero claims survive by design.

## Where it lives + plugs in

`acquire/`: `engine.py` (fan-out/gate/dedup/generate), `context.py` (build_context, stock client),
`judge.py` (VLM floor — pure prompt/parse, unit-testable), `art_direction.py` (VisualBrief → prompt),
`coverage.py`, `shared.py` (de-duped helpers), `config.py`. Feeds the HF pool → `/pool`; the HF
bridge does the vision call + file cull. See `[[project_acquisition_engine]]`,
`[[project_acquisition_consolidation]]`, and `[[pipeline.hyperframes]]`.
