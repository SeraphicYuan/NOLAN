# Nolan Handoff: Math Animation v0.7.1

## Outcome

This repository contains a standalone, artifact-first Manim authoring module
designed to become a Nolan author-stage capability.

The module has been exercised from mathematical screenplay through:

- Strict project and stateful visual IR validation.
- Nolan-neutral narration timing and style inputs.
- Deterministic Manim source compilation.
- Per-beat rendering and content-addressed cache reuse.
- Standalone FFmpeg composition.
- Mathematical and structural pedagogy evidence.
- Decoder, timing, blankness, motion, discontinuity, and collision review.
- Bounded typed repair and model-backed typed regeneration.

The public contracts do not depend on Nolan, LangGraph, a particular model, or
the standalone compositor.

## Start here

Read these in order:

1. `README.md`
2. `docs/ARCHITECTURE.md`
3. `docs/NOLAN_INTEGRATION.md`
4. `docs/V0_7_EXPANDED_PEDAGOGY.md`
5. `docs/DEFERRED_NOLAN_WORK.md`

Primary code:

- `src/math_animation/contracts.py` — stable public project and visual IR.
- `src/math_animation/planning.py` — frozen v1 constrained planner.
- `src/math_animation/expanded_planning.py` — v2 typed pedagogy/templates.
- `src/math_animation/scene_compiler.py` — stateful IR to Manim.
- `src/math_animation/pipeline.py` — compile/render/compose/review bundle.
- `src/math_animation/review.py` — rendered evidence and collision checks.
- `src/math_animation/workflow.py` — bounded LangGraph repair control plane.
- `src/math_animation/handoff.py` — current Nolan-neutral clip handoff.

## Environment and verification

This checkout currently uses:

```text
/opt/miniconda3/envs/mas/bin/python
/opt/miniconda3/envs/mas/bin/pip
```

Install:

```bash
/opt/miniconda3/envs/mas/bin/pip install -e ".[dev,render,model]"
```

Verify:

```bash
/opt/miniconda3/envs/mas/bin/python -m pytest -q
/opt/miniconda3/envs/mas/bin/python scripts/validate_examples.py
/opt/miniconda3/envs/mas/bin/python -m math_animation doctor
```

Compile without native rendering:

```bash
/opt/miniconda3/envs/mas/bin/python -m math_animation compile \
  examples/expanded_pedagogy/project.json \
  --runs-dir runs
```

Render and compose:

```bash
/opt/miniconda3/envs/mas/bin/python -m math_animation compile \
  examples/determinant_area_stress/project.json \
  --runs-dir runs \
  --render --compose --no-cache
```

## Nolan integration boundary

Nolan should provide:

- Script/topic, audience, and authoring policy.
- Final narration audio.
- Exact word timestamps.
- Style-template reference and payload.
- Approved assets and delivery settings.

The module returns:

- `project.lock.json`
- `style.lock.json`
- `math_validation.json`
- `pedagogy.json`
- `timeline.json`
- `nolan_handoff.json`
- Per-beat Manim clips
- `visual_ir/<beat-id>.scene.json`
- Rendered-review evidence and contact sheets
- Hashes, performance, cache, and manifest records

Nolan should replace `compose_standalone()` with its compositor while retaining
the timeline and clip contracts.

## Collision-aware rendered review

The last pre-handoff improvement addresses the two human-visible defects found
during featured renders: formula crowding and cramped annotations.

At each stable rendered cue, `review.py` now:

1. Simulates visibility and typed layout state for Text, MathTex, and
   annotations.
2. Applies responsive position/scale, relative layout, moves, scaling, planar
   rotation, matrices, fades, groups, and MathTex transformations.
3. Projects label boxes into the rendered frame.
4. Detects overlap and unsafe horizontal/vertical separation.
5. Records object IDs, boxes, overlap ratio, gap, cue, and rendered frame path.
6. Deduplicates persistent collisions across later stable probes.

The native smoke fixture deliberately renders one colliding comparison and one
corrected comparison:

```bash
/opt/miniconda3/envs/mas/bin/python \
  scripts/run_layout_collision_smoke.py \
  --runs-dir /tmp/math-animation-layout-collision
```

Expected:

- The cramped beat emits one `visual_collision` evidence record.
- The corrected beat emits none.
- Overall smoke report is `passed`.

Evidence is written to:

- `artifacts/layout_collision_smoke_report.json`

## Strongest end-to-end evidence

### Expanded template benchmark

- `artifacts/expanded_pedagogy_benchmark.mp4`
- `artifacts/expanded_pedagogy_benchmark_report.json`
- `examples/expanded_pedagogy/project.json`

### Completing-the-square featured explainer

- `artifacts/vertex_form_featured.mp4`
- `artifacts/vertex_form_featured_report.json`
- `examples/vertex_form_featured/project.json`

### Stateful determinant-area stress test

- `artifacts/determinant_area_stress.mp4`
- `artifacts/determinant_area_stress_report.json`
- `examples/determinant_area_stress/project.json`

The determinant fixture uses persistent groups, word anchors, parallel cues,
matrix assertions, polygon deformation, orientation reversal, singular
collapse, annotations, and `TransformMatchingTex` without custom Python.

## Compatibility rules

- `ProjectSpec v1`, `SceneProgram v1`, and v0.3–v0.6 artifacts are frozen by
  golden hashes.
- v0.7 expanded planning and pedagogy schemas have a separate baseline.
- Do not add Nolan/provider fields directly to the canonical contracts.
- Do not replace typed templates with unrestricted model-generated Python.
- Do not broaden LangGraph until evaluated workflow requirements justify it.
- Custom Python remains an isolated-worker escape hatch only.

## Deferred work

The remaining four items are intentionally handed to Nolan:

1. Exact Nolan timing, style, and media adapters.
2. Promotion of successful bespoke scenes into typed templates.
3. Live production-model planning evaluation.
4. Responsive render coverage for new templates and stateful scenes.

See `docs/DEFERRED_NOLAN_WORK.md` for acceptance guidance.
