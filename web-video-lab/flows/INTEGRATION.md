# Scope: integrating the Art flow into NOLAN (#29)

Goal (from the user's decision): the art flow is **all-Remotion**; wire it into NOLAN's
**workflow/skill** so an art-explainer video can be produced *through NOLAN*, not just the
standalone `web-video-lab` scripts. "PIL renderers are OK to keep for other workflows, but
not this one."

## Current state (verified, with refs)
- **NOLAN's motion path is per-SCENE**: `render_dispatch.render_one(scene)` → one short mp4 per
  scene → `nolan assemble` concats via ffmpeg. Motion effects are registered per-scene
  (`motion/registry.py` `MotionEffect{ id, backend: python|remotion, target, ... }`), routed by
  `motion/executor.py` (`backend=="python" → _render_python` else `_render_remotion`), bridged by
  `remotion_source.render(comp, props, …)` which is **hardcoded** to `remotion-lib/render.mjs`.
- **The art flow is whole-TIMELINE**: the entire video is ONE `_lab_chapter` `Chapter`
  composition — a Remotion `<Series>` of beat-blocks with per-beat `<Audio>`, word-sync reveals,
  in-composition hard-cuts/premount. Output is the whole mp4 in one render. No per-scene mp4, no
  concat.
- **Two SEPARATE Remotion bundles** under `render-service/`: `remotion-lib/` (9 curated
  single-comp effects, root deps) and `_lab_chapter/` (Chapter/Montage + the 39-block LIBRARY +
  its OWN `package.json`/node_modules: visx, flubber, katex, lottie, roughjs). Different job
  schemas, different `render.mjs`.
- **`flows/registry.json` is metadata-only** — not wired to any Python dispatch. NOLAN has **no
  multi-scene timeline concept**; `_lab_chapter` is the only thing that does whole-video assembly.

## Key finding — do NOT route the art flow through the motion registry
The motion registry/executor is a **per-scene** abstraction (one effect → one ~4s clip). The art
flow is a **whole-video** renderer. Forcing it through that seam means either:
- (a) decompose the video into per-beat mp4s + ffmpeg concat — **regression**: loses
  in-composition premount/cross-beat timing, re-introduces concat seams, fragments the per-beat
  audio mix; or
- (b) register one "art-chapter" mega-effect whose `content` is the entire `steps[]` array — a
  whole-video renderer masquerading as a scene effect, and it still needs `remotion_source` to
  target a different bundle.

Both fight the grain. **The art flow is a new *flow* (video-type that owns its whole render), not
a scene effect.** This is also the least invasive option — it touches **zero** of
`motion/registry.py`, `executor.py`, `visual_router.py`, `render_dispatch.py`, or the PIL scenes.

## Recommended architecture — a parallel "flow" path (additive)
```
nolan render-flow <project> --type art
        │
        ▼
src/nolan/flows/art.py  ── run(project) ──►  ingest → gate → render → deliver
        │                                      │        │       │        │
        │        (reuse web-video-lab)         │        │       │        └─ projects/<slug>/video/<slug>.mp4 (faststart)
        │                              art_ingest  art_check   _lab_chapter
        ▼                              (job JSON)  (V/P/C gate)  render.mjs
src/nolan/flows/__init__.py:get_flow(type_id)  ◄── flows/registry.json (now code-wired)
```
- **NEW `src/nolan/flows/` package** — `art.py` orchestrates the existing, tested
  `web-video-lab` steps (ingest → `art_check` gate → chapter render → deliver). `__init__.py`
  exposes `get_flow(type_id)` reading `flows/registry.json` (promote it from metadata to a
  registry the code consults).
- **NEW `render_chapter(job_path)` helper** (own function — NOT an overload of
  `remotion_source.render()`, whose schema is the single-comp one): invokes
  `node _lab_chapter/render.mjs <job>` and returns the output path. This is the only "bundle
  selection" needed; remotion-lib stays untouched.
- **Project model**: a `video_type` marker on the project so NOLAN knows to dispatch to a flow;
  an entry point (CLI `render-flow`, later a WebUI button + skill).

## What we explicitly do NOT touch
`motion/registry.py`, `motion/executor.py`, `visual_router.py`, `render_dispatch.py`, the PIL
`renderer/scenes/*`, and `remotion-lib/`. PIL stays the backend for every existing scene-based
workflow. The art flow simply never enters that path. ("Replace the PIL ones" is already true
*within* the art flow — its 39-block library is the all-Remotion superset; it never calls PIL.)

## Risks / open items
- **Dual-Python env** surfaces here: `art_ingest`/gate (WSL `python3`) + `_montage` (nolan env
  python, Pillow) + Windows node. **Decision: defer normalization, match the lab precedent** —
  WSL `python3` orchestrates and subprocess-outs to Windows node (+ nolan-python for the one
  Pillow step). A single interpreter is impossible anyway (Remotion is Node-only); the only real
  wrinkle is the Pillow step, trivially removable later. The runner therefore runs under `python3`
  like the rest of the lab orchestration; the `nolan render-flow` CLI bridge is a follow-up.
- **`_lab_chapter` paths**: `stage.mjs` reads themes from `../../web-video-lab/skill/themes` and
  render.mjs assumes cwd=`render-service`. Keep that contract (no change) — the flow runner just
  shells out with the right cwd.
- **Bundle duplication**: two node_modules. Acceptable (separation is deliberate); a later
  consolidation is possible but out of scope.

## Generic flow runner — how art vs paper/article-video differ
Both flows are the **same pipeline shape** and render through the **same** `_lab_chapter`
`Chapter` composition + the **same** 39-block library, so they **converge on the job JSON**:
everything downstream (gate-structure → render → deliver) is identical. A "flow" is *not* a second
pipeline — it's a **descriptor** carrying the **five** things that genuinely differ, over one
shared engine. (art = the explainer engine **extended** with an assemble-ingest + a new
camera-tour block class + contemplative defaults.)

```python
@dataclass
class Flow:
    id: str
    ingest:   Callable   # CODE    — generate (paper) | assemble (art/byo)        → job.json
    authoring: str       # PROCESS — skill + docs: how beats are written (idea→block vs region→camera)
    palette:  Palette    # config  — { blessed LIBRARY subset, shared-common set, RAW policy }
    profile:  str        # config  — pacing thresholds (punchy vs contemplative)  [registry.json]
    defaults: dict       # config  — theme / transitions / fx
```
```
run_flow(flow, project, opts):           # the shared ENGINE (flow-agnostic)
  job = flow.ingest(project, opts)        #  ← the one heavy CODE fork
  gate(job, flow)                         #  shared structure; profile + palette come from flow
  mp4 = render_chapter(job)               #  shared: _lab_chapter render.mjs
  deliver(project, mp4)                   #  shared
```

**The five divergence axes** (the rest is shared substrate):

| axis | explainer (workflow 1) | art (workflow 2 — extends 1) | where it lives |
|---|---|---|---|
| **ingest** | **generate**: extract_figure + OmniVoice TTS + Whisper + gen_spec | **assemble**: read project segments + picture-library images | CODE (adapter) |
| **authoring grammar** | idea → visual block (redraw-synthetic / lift-empirical) | image *region* → camera move + spotlight + wall-label | skill + docs |
| **block palette** | text/data + RAW bespoke (charts, tables, kinetic, PaperFigure, StatCount; AttentionFlow/SelfFeedingCurve…) | image/camera class (ArtworkStage, DetailLoupe, ImageCompare, PhotoMontage) | descriptor + gate check |
| **pacing profile** | punchy: WPM 130–165, dead-air FAIL ≥9s, first-reveal FAIL ≥6s | contemplative: WPM 95–140, gap-check OFF, min-hold warn 2.5s | registry.json |
| **theme/fx defaults** | by-topic, hard-cut, optional fx | museum-neutral, cross-fade, grade+vignette | registry.json |
| *job JSON · gate structure · render engine · 39-block library · deliver* | **shared** | **shared** | — |

### Palette as a real flow characteristic (not just a JSON comment)
Today the block pools are **one flat merged namespace** — `BLOCKS = { ...LIBRARY, ...RAW }`
(`blocks/index.ts`); the renderer and `art_validate` are **flow-blind** (they only ask "does this
block exist?"). The `palette` in `registry.json` is declared but **enforced nowhere**. We wire the
motion-pool preference in at two points, weighted toward authoring:
- **Authoring (primary)** — each flow's skill/docs surface *its* palette as the blocks to reach
  for: art → ArtworkStage/DetailLoupe/ImageCompare/PhotoMontage; explainer → charts/tables/
  kinetic/PaperFigure **+ RAW as the bespoke escape hatch**. This is where the preference belongs;
  it's a creative guardrail, not a runtime lock.
- **Gate (soft backstop)** — `art_validate --flow <id>` **warns** (never fails) when a job uses a
  block outside its flow's palette, with two carve-outs: a shared **common set** (ChapterCard,
  EndCard, Timeline, PullQuote — legit in both) is exempt, and **RAW blocks are always allowed but
  flagged** ("bespoke, not cataloged"). Soft because blocks legitimately cross-pollinate (an art
  *Timeline* for historical context; a paper using an image block).

Adding a third video-type later = one ingest adapter (only if a new acquisition mode) + one
registry row (palette + profile + defaults) + its authoring skill. The engine never changes.

## Phased plan
1. **Palette wiring** — common-set + RAW policy in `registry.json`; soft `--flow` palette check in
   `art_validate.py`; surface each flow's palette for authoring.
2. **`flows/` package** — `base.run_flow(flow, project)` engine + `get_flow()` (reads
   `registry.json`) + art tenant + `render_chapter()` helper. Runs under `python3`, subprocess-out.
3. **Integration test** — render Dance of Death *through* the runner; QA against `art/final/`.
4. (Follow-up) `nolan render-flow` CLI bridge + project `video_type` marker + WebUI/skill surface;
   promote art status "scoping"→"solid".

## Bottom line
The art flow is ~90% built and production-grade. Integration is **routing glue, not a port**, and
the right glue is a new flow path — not the per-scene motion registry. ~2 new files + 1 helper +
a project marker; **no NOLAN core scene/motion code is modified.**
