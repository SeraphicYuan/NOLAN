# Experiment: Asset-First Scene Building (Roaring Twenties, ~86s)

**Date:** 2026-06-24
**Source:** `If The Economy Is F＊cked, Why Hasn't It Crashed Yet？.mp4`
**Segment:** 02:15 → 03:41 (the self-contained "Roaring Twenties → 1929 crash →
rally while breadlines" arc)
**Output:** `final.mp4` (1920×1080, 30fps, 86.0s, original voiceover)

## What this tested

Instead of NOLAN's normal flow (script → scenes → match assets), we inverted it:
**pick a slice of an existing script, then build scenes from whatever the asset
sources can supply.** Three sources were combined:

1. **Segment search** — semantic search over the indexed source video for archival b-roll.
2. **Renderer / motion** — animated counter / title / lower-third cards.
3. **ComfyUI** — a generated "hero" still (live server on `127.0.0.1:8080`).

Voiceover is the original audio extracted from the source for the chosen span.

## Pipeline used

1. Indexed the source video **into a project-local DB** (`index.db` + `vectors/`,
   336 segments) — deliberately *not* the external central library, to stay inside
   the project boundary.
2. `VectorSearch` confirmed the pool was rich: the creator's own archival 1920s /
   Depression footage sits right in this span (134s–223s), covering nearly every beat.
3. Built 11 scenes (`build_full.py`) → normalized 1920×1080@30 clips/cards →
   `ScenePlan` → `nolan assemble scene_plan.json vo.m4a -o final.mp4`.

## Scene breakdown (all verified by frame extraction → `qa/`)

| Scene | Time | Source | Result |
|-------|------|--------|--------|
| b1 roaring | 0–6.5 | search clip @134.4 | 1920s street (carried creator's burned-in title) |
| b2 dow | 6.5–16 | counter | green "6×" Dow 1922–29 |
| b3 cracks | 16–27.5 | search clip @157.4 | split-screen factory assembly lines |
| b4 bets | 27.5–38 | search clip @172.0 | 1920s trading floor |
| b5a crash | 38–44 | search clip @178.1 | street strewn with discarded papers (crash) |
| b5b unemp | 44–50 | counter | red "25% · 1 IN 4 AMERICANS" |
| b6a rally | 50–57 | counter | green "+300%" 1933–37 |
| b6b title | 57–63 | title | "BUT ONLY THE STOCK MARKET" |
| b7 breadline | 63–74 | **ComfyUI** + Ken Burns | photoreal 1930s breadline (excellent) |
| b8a despondent | 74–80 | search clip @217.4 | despondent man |
| b8b close | 80–86 | lower-third | "STOCK MARKET ≠ YOUR LIFE" |

## Verdict — good experiment, and it works

All three sources rendered correctly and on-topic, synced to the original VO, with
zero timeline gaps. The strongest, slightly surprising result: **once the source
video is indexed, segment search alone supplies most of the b-roll** — the creator
had already cut topical archival footage into this exact span. ComfyUI is best used
for a *hero/gap-fill* shot (the breadline climax) rather than carrying every beat.

## Limitations discovered (honest)

- **`nolan assemble` concatenates, it does not composite.** No layered overlays
  (caption *on top of* moving b-roll); the essay is a cut sequence of full-frame
  clips and cards. True overlay needs a compositor stage.
- **No animated line-chart renderer.** The "chart up→crash→rally" was expressed as
  count-up stat cards (works well, arguably punchier). A real animated chart would
  need a new renderer or the (static) infographic route.
- **Transitions are hard cuts only** — assemble's crossfade path is a stub.
- **Reused footage carries baked-in graphics** (b1's "Roaring Twenties" title came
  from the creator's clip). Fine here; a cleanup/crop step could remove it.
- **Source is 640×360** — archival clips are upscaled to 1080p (acceptable, soft).
- Orchestrator-v1 does not wire ComfyUI/Lottie; this build used the legacy
  `nolan assemble` asset-priority path instead.

## Promoted to NOLAN (candidates)

| Technique | Status | Note |
|-----------|--------|------|
| Asset-first scene build from a script slice | Prototype (`build_full.py`) | Could become an `nolan build-from-segment` command |
| Project-local indexing (boundary-safe) | Pattern | Index into `projects/<name>/index.db` instead of central library |
| Animated line-chart renderer | **Missing — proposed** | Real gap for finance/data essays |
| FLUX.1 dev workflow | **Done** | `workflows/image/flux-dev-fp8.json`, registered as `flux-dev`. Big photoreal jump over the SDXL `sdxl-default` default; b7 hero regenerated with it |

## v2 — limitations addressed (2026-06-25)

The three honest limitations above were implemented as reusable renderer features
and demonstrated in `final_v2.mp4` (`build_v2.py`):

1. **Compositing** (`BaseRenderer.render_frame_rgba` + `renderer/composite.py`):
   counters / lower-thirds / titles now sit *over* moving b-roll instead of cutting
   to black cards. Shown: b1 title, b4 lower-third, b6a counter (over a generated
   plate), b8 lower-third over the FLUX breadline. Optional `scrim` keeps text legible.
2. **Animated line chart** (`renderer/scenes/line_chart.py`): the 1922→1929→crash→
   1933-37 arc as a real chart (green-up/red-down, moving value readout). Shown: b2, b5.
3. **Fades**: gentle fade in/out on cuts (`render_b_roll` `fade=`, and in the compositor).

Re-confirmed limitation in the wild: reused source footage carries **burned-in
graphics** (b6a first landed "+300%" over the source's burned "1922–1929"); fixed by
compositing over a clean generated plate instead. True frame-blended crossfades were
intentionally skipped (hard cuts suit this genre).

## Generation model note

First pass used `sdxl-default` (JuggernautXL/SDXL) — too weak for archival photoreal.
The ComfyUI box actually has FLUX dev, FLUX Krea (`krea2_turbo`), Ideogram4, Qwen-Image,
Z-Image Turbo — NOLAN just had no workflow for them. Built + registered **`flux-dev`**
(`flux1-dev-fp8`, all-in-one checkpoint, 1344×768, 24 steps, guidance 3.5, prompt node `6`)
and regenerated the breadline hero (`generated/b7_flux_a.png`) — far stronger. FLUX Krea
is the next step up for photoreal if needed.

## Files

- `index_source.py` — project-local indexing runner
- `search_probe.py` — segment-search sanity probe
- `extract_vo.py` — VO extraction (135.0s, 86s)
- `build_full.py` — the 11-scene asset-first build
- `scene_plan.json`, `clips/`, `cards/`, `generated/`, `qa/`, `final.mp4`
- `smoke_*` — earlier 2-scene smoke test (safe to delete)
