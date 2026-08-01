# Architecture

## Boundary

Math Animation is organized around a stable artifact contract:

```text
topic or script
  -> planning agent (future/provider-specific)
  -> expanded typed decision + pedagogy intent
  -> ProjectSpec / mathematical screenplay
  -> deterministic math/pedagogy validation and timing resolution
  -> legacy blocks or SceneProgram visual IR
  -> deterministic Manim compiler
  -> per-beat source and clips
  -> timeline.json
  -> Nolan composer or standalone FFmpeg composer
```

The planning model, Manim renderer, and final compositor are replaceable. The
project, style lock, timeline, and manifest remain inspectable.

## Why the screenplay is canonical

Generated Python is an implementation artifact. It is a poor product contract
because it mixes pedagogy, math, visual intent, style, timing, and renderer
details in one unrestricted language.

`ProjectSpec` instead keeps:

- User intent and script policy.
- Mathematical claims and formula definitions.
- Nolan narration and word alignment.
- Beat-level learning objectives.
- Typed visual blocks.
- Persistent scene objects and actions when a shot needs coordinated state.
- Stable timing anchors.
- Style and asset references.
- Render settings.

Editing an upstream concern can therefore invalidate only its downstream work.
A style change does not need to rediscover prerequisites. A narration change
does not need to re-check an unchanged derivation. A Manim API error does not
need to regenerate the screenplay.

## Layers

### Contracts

`contracts.py` is the public API. It uses strict Pydantic models, rejects unknown
fields, validates references, and publishes JSON Schema.

Breaking changes require a new `schema_version`. Provider-specific fields must
not leak into the canonical models; adapters translate them.

### Math validation

`math_validation.py` performs deterministic structural checks and distinguishes:

- `passed`
- `needs_review`
- `failed`

Claims explicitly record whether they are verified, assumed, or still awaiting
review. This avoids silently presenting a model-generated assertion as a
mathematical fact.

Symbolic and numeric verifiers can later be registered by domain. Their evidence
should be recorded on the same claim rather than hidden in model prose.

### Timing

`timing.py` consumes Nolan word timestamps without changing them. It resolves
project time into clip-local time and rejects narration overlaps and impossible
beat durations.

The compiler does not silently time-compress visuals that overrun narration.
It reports the exact beat and duration mismatch so the authoring stage can fix
the appropriate artifact.

### Block registry

`blocks.py` maps a typed block spec to deterministic Manim source. Built-in
blocks own:

- Object construction.
- Style-token application.
- Animation timing.
- Cleanup.
- Renderer-safe implementation details.

The registry should grow from recurring production needs. A bespoke scene that
repeats should be promoted into a typed block with fixtures and render tests.

### SceneProgram visual IR

`SceneProgram` is the stateful visual representation for shots that cannot be
expressed as isolated, self-cleaning blocks. Stateful means that a declared
object keeps the same identity across later actions; it does not mean that a
Manim runtime object or arbitrary Python value enters the public contract.

The initial v1 vocabulary supports:

- Persistent text and addressable MathTex.
- Vectorized point clouds with up to 10,000 deterministic samples.
- Ordered, safe expression bindings compiled to NumPy.
- Multiple named coordinate states per point cloud.
- Numerical projection assertions between coordinate states.
- Create, transform, fade, and 3D camera actions.
- Parallel cues with a shared clock.
- Fixed-in-frame overlays over 3D geometry.

Every object must be created before use. Object IDs, cue IDs, binding names, and
point-state IDs are validated. Coordinate expressions accept only arithmetic,
declared variables, constants, and a small approved math-function set.

A beat uses either legacy `blocks` or one `scene_program`. This preserves all
v0.1 inputs and keeps simple shots simple.

The visual IR is deliberately not implemented with LangGraph. It is a
deterministic, versioned domain artifact. A future optional LangGraph runner may
orchestrate planning, validation, rendering, review, and repair around these
artifacts without becoming necessary to compile them.

### Pedagogy evaluation

`pedagogy.py` evaluates the canonical project rather than provider prose. It
combines math validation, typed-object/action inspection, Nolan word timings,
and existing repair diagnostics into a weighted, evidence-bearing report.

The evaluator is intentionally deterministic. It can gate obvious structural
failures before render, but it cannot certify human learning. Nolan should
retain the report beside model-call, compile, and rendered-review evidence.

### Compiler

`compiler.py` emits one scene per beat. Every source file is compiled with
Python's syntax compiler before it enters the run bundle.

Per-beat output is deliberate:

- Nolan can rearrange or replace individual clips.
- Repair stays local.
- Parallel rendering becomes possible.
- Cache keys can eventually be calculated per beat.
- Alpha overlays and full-frame shots can coexist.

SceneProgram beats additionally write `visual_ir/<beat-id>.scene.json` so Nolan,
reviewers, and future repair agents can inspect the exact persistent object and
action plan without reading generated Python.

### Render and composition

The local renderer is appropriate for deterministic built-in blocks. Production
rendering should move behind a durable isolated worker.

`composer.py` is intentionally replaceable. It assembles clips and optional
external narration with FFmpeg for standalone operation. Nolan should consume
the same timeline and take over final composition.

## Custom scene threat model

The custom-scene AST checker catches common mistakes and obvious unsafe code.
It is not a sandbox: Python has too many reflective and native escape paths for
a blocklist to be a security boundary.

A production custom-scene worker must use:

- A fresh container, gVisor sandbox, or microVM.
- No outbound network by default.
- No model-provider credentials.
- A job-specific writable directory.
- Read-only application and dependency layers.
- Non-root execution.
- CPU, memory, process, disk, and wall-clock limits.
- Version-pinned Manim, FFmpeg, LaTeX, fonts, and native libraries.

## Planned extensions

1. Exact Nolan author-stage, TTS/alignment, and style-template adapters.
2. Additional typed teaching patterns driven by benchmark failures.
3. Symbolic/numeric validation plugins.
4. Model-based semantic pedagogy review as advisory evidence beside the
   deterministic rubric.
5. Durable isolated render-worker service.
6. Production learner/usability evaluation and rubric calibration.
