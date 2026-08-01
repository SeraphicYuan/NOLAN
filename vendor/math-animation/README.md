# Math Animation

Math Animation is an artifact-first authoring module for mathematical video.
It turns a versioned mathematical screenplay into deterministic Manim scenes,
clip-level timeline metadata, and—when the render toolchain is installed—video
clips and an optional standalone MP4.

The package is designed to become a Nolan module later without depending on
Nolan today:

- Nolan remains responsible for TTS and word alignment.
- Nolan remains responsible for its mature style-template system.
- Math Animation owns pedagogy/math artifacts, visual beats, Manim block
  compilation, rendering, and the clip handoff.
- Nolan can replace the optional FFmpeg composer while keeping the same project
  and timeline contracts.

## Current status

The current v0.7.1 implementation provides:

- Strict Pydantic contracts and exported JSON Schema.
- Nolan timing and placeholder style adapters.
- A mathematical claims/formula ledger with deterministic review checks.
- Word-, beat-, and absolute-time animation anchors.
- Six deterministic Manim blocks:
  - `title_card`
  - `equation_reveal`
  - `equation_transform`
  - `function_plot`
  - `number_line`
  - `secant_to_tangent`
- A versioned `SceneProgram` visual IR for stateful shots:
  - Persistent text, semantic MathTex, common 2D geometry, axes, graphs,
    annotations, groups, point clouds, tracked dependencies, parametric
    curves/surfaces, sampled footprints, and measured intervals.
  - Stable object and point-state IDs.
  - Sequential and parallel action cues.
  - Typed 3D camera poses and camera actions.
  - Safe NumPy-vectorized coordinate expressions.
  - Time-varying points, connectors, orbit circles, and pre-sampled traces
    driven by deterministic value trackers.
  - Move, scale, rotate, recolor, matrix, matching-equation, fade/re-entry,
    and multi-time point-cloud actions.
  - Finite, bounds, spread, projection, matrix determinant, tracked-coordinate,
    surface, footprint, and interval-width assertions.
  - Fixed-in-frame overlays over moving 3D geometry.
  - Landscape, square, and portrait overrides with aspect-correct camera
    coordinates and minimum effective type sizes.
- Syntax-checked, per-beat Manim source generation.
- Batched LaTeX compilation and local asset/audio preflight before rendering.
- An opt-in custom-scene escape hatch with a static safety gate.
- Inspectable run bundles, manifests, hashes, performance measurements,
  automatic contact sheets, and Nolan-neutral timelines.
- Content-addressed per-beat render reuse with scoped invalidation.
- Optional local Manim rendering and FFmpeg standalone composition.
- A Nolan handoff manifest containing clips, exact word timings, normalized and
  raw style payloads, alpha metadata, and checksummed external assets.
- Post-render decoder, duration, resolution, frame-rate, frame-count, audio,
  alpha, blank-frame, freeze, and discontinuity probes.
- Collision-aware stable-frame review for visible Text, MathTex, and
  annotations, including object IDs, projected boxes, minimum-separation
  evidence, and the exact rendered probe path.
- A provider-neutral constrained planner:
  - Script paragraphs become timed mathematical beats.
  - Providers return a strict visual decision, never Python source.
  - A deterministic fallback selects equation, transform, plot,
    secant-to-tangent, number-line, or conservative title templates.
  - Every selection records confidence, rationale, formula bindings, and
    unsupported visual intentions.
  - Authored formulas enter the ledger as explicit assumptions pending
    independent mathematical verification.
- A 12-domain unseen-prompt benchmark and v0.3 golden compatibility gates.
- Structured, evidence-bearing review diagnostics with stable codes and
  beat/object/cue scope.
- Typed deterministic repairs for framing, responsive type, line wrapping,
  generated-caption length, cue timing, geometry density, frozen trackers, and
  ledger-locked template swaps.
- A minimal LangGraph control plane with at most two pipeline attempts; the
  versioned project/scene artifacts remain independent of the graph runtime.
- Explicit refusal for missing inputs, invalid mathematics/LaTeX, unbounded
  numeric failures, and repairs that would require guessing.
- A rendered adversarial repair benchmark with eight successful repairs, three
  correct refusals, and scoped cache reuse.
- A provider-neutral `VisualDecisionProvider` shared by initial planning and
  rendered-beat regeneration.
- An OpenAI Responses API adapter using Pydantic structured outputs, explicit
  model configuration, latency/usage audit records, and no stored credentials.
- Source-grounding gates that prevent model-invented formulas, plot
  expressions, and number-line values.
- Executable `regenerate_beat` operations backed by separate, hashed
  `RegenerationArtifact` records while preserving the frozen v0.5 repair plan.
- A two-attempt rendered regeneration benchmark proving blank/frozen
  diagnostics, typed replacement, and unaffected-beat cache reuse.
- An expanded decision schema with two pedagogy-first reusable templates:
  - `equation_sequence` transforms one persistent, ledger-bound formula
    through three to six authored steps.
  - `concept_comparison` presents two authored formulas side by side, with
    portrait-aware stacking and optional typed labels.
- A deterministic seven-dimension pedagogy report covering mathematical
  grounding, objective/visual alignment, progressive disclosure, pacing,
  cognitive load, narration sync, and legibility.
- Optional pre-render pedagogy acceptance gates and a synthetic sensitivity
  case that correctly rejects a static, overloaded, misaligned explanation.
- A conservative script-to-project drafting fallback for exercising the full
  plumbing before an agent planner is connected.

The drafting fallback is not presented as a finished pedagogy engine. It
preserves script paragraphs, extracts inline LaTeX, and produces a reviewable
`ProjectSpec`. A later planning agent should emit the same contract.

> **Vendored into NOLAN.** This checkout is `vendor/math-animation/` inside the
> NOLAN repo. Read `CLAUDE.md` first: it records the four deltas from upstream
> v0.7.1 and the two-interpreter split. The commands below use NOLAN's envs;
> upstream's macOS paths are gone.

## Environment

Compilation and validation need **only pydantic** — install into the pipeline env:

```bash
D:\env\nolan\Scripts\pip.exe install -e .
```

The pinned renderer (Manim, Cairo/Pango, Pillow) goes in a separate env, so the
pipeline env never meets Manim's dependency stack:

```bash
D:\env\mas\Scripts\pip.exe install -e ".[render]"
```

Optional extras: `.[model]` (OpenAI decision providers) and `.[workflow]`
(the LangGraph repair control plane). NOLAN uses neither.

Manim also needs native FFmpeg, LaTeX and `dvisvgm` for equation-heavy
rendering. Check the RENDER env's toolchain with:

```bash
D:\env\mas\python.exe -m math_animation doctor
```

## Quick start

Validate and compile the included example:

```bash
python -X utf8 -m math_animation \
  validate examples/derivative_project.json

python -X utf8 -m math_animation \
  compile examples/derivative_project.json --runs-dir runs
```

The second command does not require Manim. It produces:

```text
runs/<run-id>/
  project.lock.json
  style.lock.json
  math_validation.json
  pedagogy.json
  nolan_handoff.json
  timeline.json
  cache.json
  performance.json
  manifest.json
  schemas/project.schema.json
  schemas/scene-program.schema.json
  visual_ir/<beat-id>.scene.json
  source/<beat-id>.py
  clips/
  review/
  preflight/
```

Render beat clips:

```bash
python -X utf8 -m math_animation \
  compile examples/derivative_project.json --runs-dir runs --render
```

Render and assemble a standalone MP4:

```bash
python -X utf8 -m math_animation \
  compile examples/derivative_project.json --runs-dir runs --render --compose
```

Render the persistent 3D point-cloud example:

```bash
python -X utf8 -m math_animation \
  compile examples/olin_scene_program.json \
  --runs-dir runs --render --compose
```

Render the 62-second featured stress test:

```bash
python -X utf8 -m math_animation \
  compile examples/olin_featured_project.json \
  --runs-dir runs --render --compose
```

Additional featured fixtures cover narrated algebra, Jacobian
local-versus-global behavior, Fourier epicycles, parametric surfaces, and the
ERDŐS 1038 potential landscape:

```bash
python -X utf8 scripts/build_fourier_fixture.py
python -X utf8 scripts/build_jacobian_fixture.py
python -X utf8 scripts/build_erdos_1038_fixture.py

python -X utf8 scripts/run_responsive_matrix.py --render
python -X utf8 scripts/run_nolan_handoff_smoke.py
python -X utf8 scripts/run_adversarial_suite.py
python -X utf8 scripts/run_system_matrix.py
```

Draft a review project from an existing script:

```bash
python -X utf8 -m math_animation \
  draft script.txt \
  --project-id limits-intro \
  --title "Understanding Limits" \
  --output limits.project.json
```

Plan a script through the constrained authoring layer:

```bash
python -X utf8 -m math_animation plan script.txt \
  --project-id limits-intro \
  --title "Understanding Limits" \
  --narration nolan-alignment.json \
  --style nolan-style.json \
  --output-dir planned/limits \
  --render --compose \
  --runs-dir runs
```

This writes `planning.json` and `project.json` before compilation. The planning
artifact explains every block choice and records unsupported intentions.

Plan with the expanded templates and emit pedagogy evidence:

```bash
python -X utf8 -m math_animation plan-expanded script.txt \
  --project-id algebra-comparison \
  --title "Solve and Compare" \
  --narration nolan-alignment.json \
  --style nolan-style.json \
  --output-dir planned/algebra-comparison \
  --minimum-pedagogy-score 0.9
```

The output includes `expanded-planning.json`, `project.json`, and
`pedagogy.json`. Add `--compile`, or `--render --compose`, to run the same
acceptance gate before Manim.

Evaluate any existing project without rendering:

```bash
python -X utf8 -m math_animation evaluate project.json \
  --minimum-score 0.8 \
  --output pedagogy.json
```

Audit, repair, and compile an authored project:

```bash
python -X utf8 -m math_animation repair project.json \
  --runs-dir runs
```

Run the bounded repair workflow through render and standalone composition:

```bash
python -X utf8 -m math_animation repair project.json \
  --runs-dir runs --render --compose
```

The repair session preserves the original and repaired projects, structured
diagnostics, typed plans, beat-level hash diffs, and graph state. It never
executes an arbitrary patch or generated Python.

Use a structured-output model for initial planning:

```bash
python -X utf8 -m math_animation plan script.txt \
  --project-id limits-intro \
  --title "Understanding Limits" \
  --provider openai \
  --model YOUR_MODEL_ID \
  --output-dir planned/limits
```

Or allow the same constrained provider to regenerate beats that fail rendered
review:

```bash
python -X utf8 -m math_animation repair project.json \
  --runs-dir runs --render --compose \
  --regeneration-provider openai \
  --model YOUR_MODEL_ID
```

Other commands:

```bash
python -m math_animation blocks
python -m math_animation schema -o project.schema.json
python -m math_animation schema --kind scene-program -o scene-program.schema.json
python -m math_animation schema --kind expanded-decision -o decision.schema.json
python -m math_animation schema --kind pedagogy-report -o pedagogy.schema.json
python -m math_animation validate project.json
```

## Timing model

Nolan word timestamps are authoritative when provided. A block can start at:

- Seconds relative to its beat.
- Seconds on the full project clock.
- A fraction of the beat.
- The start or end of a particular aligned word, plus an optional offset.

Each beat renders as an independent clip. The generated `timeline.json` records
its project in/out time, duration, source, expected media path, frame rate,
resolution, and alpha mode.

Legacy blocks remain sequential and self-contained. A `SceneProgram` cue can
coordinate multiple actions in parallel while preserving its named objects
across later cues. Both representations use the same Nolan anchors. A beat must
choose exactly one representation; it cannot mix blocks and a `SceneProgram`.

## Styles

`StyleTemplateRef.raw` preserves Nolan's future payload unchanged. The temporary
adapter recognizes a small canonical subset:

```json
{
  "colors": {
    "background": "#f5f0e6",
    "foreground": "#181818",
    "muted": "#66615b"
  },
  "semantic_colors": {
    "primary": "#315c8c",
    "changing": "#bd4f3a",
    "fixed": "#4f7752"
  },
  "typography": {
    "font": null,
    "title_size": 64,
    "body_size": 30,
    "math_size": 58
  },
  "motion": {
    "create_seconds": 1.0,
    "transform_seconds": 1.2,
    "beat_hold_seconds": 0.4
  }
}
```

When Nolan becomes available, only `math_animation.adapters.nolan` and
`normalize_style()` need to learn its exact schema.

Objects may also declare conservative `responsive` overrides for landscape,
square, and portrait output. These overrides change authored position, scale,
or relative layout; the compiler changes the Manim camera frame to the actual
pixel aspect instead of stretching a landscape coordinate system.

## Custom Manim

`custom_scene` is an escape hatch, not the normal authoring path:

- It is rejected unless `--allow-custom-python` is passed.
- It cannot be mixed with deterministic blocks in the same beat.
- Imports and dangerous calls receive an AST-based static check.
- Local rendering refuses it unless an isolated renderer is explicitly
  asserted.

Static checks do not make generated Python safe. A production custom-scene
renderer must run in a disposable container or microVM without network,
provider secrets, or broad filesystem access.

See [Architecture](docs/ARCHITECTURE.md) and
[Nolan integration](docs/NOLAN_INTEGRATION.md). The first real-render
evaluation is recorded in the
[v0.1 showcase benchmark](docs/V0_1_SHOWCASE_BENCHMARK.md).
The persistent visual contract is documented in
[SceneProgram v1](docs/SCENE_PROGRAM.md). The full-render acceptance result is
recorded in the
[featured Olin stress test](docs/FEATURED_STRESS_TEST.md).
The broader v0.3 evidence is recorded in
[v0.3 acceptance](docs/V0_3_ACCEPTANCE.md).
The constrained planner and benchmark are documented in
[v0.4 planner](docs/V0_4_PLANNER.md).
The bounded diagnostic and repair workflow is documented in
[v0.5 typed repair](docs/V0_5_REPAIR.md).
The model provider and executable regeneration path are documented in
[v0.6 model regeneration](docs/V0_6_MODEL_REGENERATION.md).
The expanded templates and structural teaching evaluator are documented in
[v0.7 expanded planning and pedagogy](docs/V0_7_EXPANDED_PEDAGOGY.md).
Nolan should begin with the
[handoff note](docs/NOLAN_HANDOFF.md); intentionally postponed work is listed
in the [deferred roadmap](docs/DEFERRED_NOLAN_WORK.md).

## Tests

```bash
python -X utf8 -m pytest -q
```
