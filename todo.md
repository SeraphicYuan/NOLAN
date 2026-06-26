# NOLAN — refinement backlog

Things deliberately left to refine as we use the features. Newest first.

## build-from-segment (`src/nolan/segment/`)
- [ ] **Precise VO alignment.** `assign_timing` currently tiles the span proportional to
      narration word-count. Upgrade to per-line/word alignment: use the SRT line times
      (indexed-span case) or Whisper word timestamps to snap each scene's start/end to the
      actual spoken boundaries, so cuts land exactly on the VO.
- [ ] **External-footage provider for escalation.** The resolver's escalation chain is
      external → ComfyUI → black, but `external_fn` is a hook with no provider wired. Connect
      `image_search.py` (Pexels / Pixabay / Internet Archive / Library of Congress) so a
      below-threshold b-roll scene tries stock footage before generating.

## scene iteration (`src/nolan/iterate/`)
- [x] **Re-resolve on changed `search_query`.** Editing `search_query`/`visual_type`
      now clears the scene's `matched_clip`+`resolved_source` (`apply_patch`), and
      re-render re-runs the resolve/match stage for exactly those scenes before
      rendering — segment via `SegmentBuilder._reresolve_unresolved` (project-local
      index + escalation), orchestrator via `ClipMatcher` on raw dicts (preserves
      `layout_spec`). Skips gracefully when no index/vectors are present.
- [ ] **Orchestrator timing.** Selective re-render re-runs `annotate_scene_plan`, which
      recomputes all start/end from `duration` (overwrites SRT-precise times). Fine for
      the linear pipeline as built, but revisit if precise VO alignment lands there.

## ComfyUI generation throughput (found on McDonald's segment run)
- [ ] **z-image gens degrade under load.** First few gens are fast, then each times out
      (>240s/image) — looks like 6B-model VRAM thrashing (model reloaded per gen). Investigate
      keeping the checkpoint resident / pacing gens serially with a warmup, or detecting the
      stall. Env-side: restarting ComfyUI clears it.
- [x] **Resilience: gen failure → card fallback** (not a black hole). `render._fallback_card`
      renders a `TitleRenderer` card from the scene intent. Added `--comfyui-timeout` +
      `comfyui_retries=1` so a stuck gen fails fast and falls back.
- [ ] **Upgrade the fallback card** from a plain title to a kinetic-text / pull-quote card
      (reuse `nolan.motion`) so fallbacks match the essay style.

## Lower priority / known limitations
- [ ] **True crossfades.** `nolan assemble` is cut-only (its crossfade path is a stub).
      Real frame-blended transitions live in the Remotion path (`@remotion/transitions`).
      Either wire an ffmpeg `xfade` post-step in assemble, or route transition-heavy cuts
      through Remotion.

## motion-spec system (`src/nolan/motion/`)
- [ ] **Safe-area clamp** for wide content (e.g. `$46.6B` at `bottom-right` overflows).
- [ ] **Map `theme` onto Python renderers** (currently theme tokens are Remotion-only).
- [ ] **Add `timing`/motion as the next shared param** (same pattern as `position`).
- [ ] **Vision grounding** to place annotations *on b-roll content* (detect target → position).
