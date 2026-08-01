# Math Animation implementation roadmap

Status: implemented and acceptance-tested in v0.3. The tranche descriptions
below are retained as the dependency rationale and regression contract.

This roadmap turns the successful Olin vertical into a reusable Nolan-facing
mathematical authoring subsystem. Work is intentionally sequenced by dependency:
each tranche adds a small typed capability, validates it, and uses it in a
rendered acceptance film before the next tranche begins.

## Principles

- `ProjectSpec` and `SceneProgram` remain the durable editing contracts.
- Common work compiles from typed data; custom Python remains an audited escape
  hatch.
- Nolan owns narration generation, word alignment, house style, and final
  author-stage orchestration. This module can simulate those inputs locally.
- Rendering successfully is not acceptance. Mathematical checks, decoder
  checks, stable-frame review, and legibility checks are required.
- New workflow infrastructure is added only when the artifact pipeline needs
  retries, resumability, or provider coordination. The visual IR does not
  become a LangGraph state object.

## Tranche 1: common persistent teaching grammar

Add persistent:

- Dots, lines, arrows, circles, rectangles, polygons, and polylines.
- Axes, function graphs, and parametric curves.
- Groups and annotations.
- Relative placement, alignment, stacks, and screen-safe sizing.
- Move, rotate, scale, recolor, highlight, and opacity actions.
- Matching equation transforms with stable source and destination IDs.

Acceptance:

- Existing projects compile unchanged.
- Reference and lifetime validation rejects invalid targets and transforms.
- A narrated algebra/derivative film uses no custom Python.
- The same film renders in landscape, portrait, and square layouts.

## Tranche 2: validation and visual review

Add:

- Finite-coordinate, bounds, spread, and projection invariants sampled over
  declared times.
- Pre-render text/layout safe-area checks.
- Automatic stable/mid-transition frame extraction.
- Post-render checks for blank frames, unexpected freezes, decoder failures,
  and suspicious frame discontinuities.
- Machine-readable review artifacts linked from the run manifest.

Acceptance:

- An adversarial fixture fails for each invariant with object/state/time detail.
- The historical multiline defect is detected before or after rendering.
- Olin passes the automated review without suppressing real errors.

## Tranche 3: Nolan handoff simulation

Add:

- Synthetic narration audio and exact word timestamps.
- A multi-beat project with word-anchored cues.
- Audio/video composition with deterministic duration policy.
- Transparent-overlay and mixed external-clip handoff fixtures.
- Content-addressed compilation/render cache records.
- Determinism and targeted invalidation reports.

Acceptance:

- Word-triggered visuals are correct to one output frame.
- Multiple Manim clips plus a Nolan/GSAP placeholder compose with audio.
- Repeating identical inputs reports cache eligibility.
- Changing one beat invalidates that beat without changing unrelated source.

## Tranche 4: Jacobian acceptance film

Add only the primitives required to show:

- A square/cube grid.
- A matrix-driven local deformation into a parallelogram/parallelepiped.
- Basis arrows and determinant/area or volume annotation.
- A camera pullback separating local invertibility from global behavior.

Acceptance:

- Matrix coordinates are checked numerically.
- The local/global distinction is stated and visually staged.
- No custom Python.

## Tranche 5: dependency-driven motion and Fourier acceptance film

Add:

- Numeric trackers independent of point clouds.
- Object dependencies such as an arrow endpoint following another endpoint.
- Path tracing and updater cleanup.
- Repeatable linear and angular motion.

Acceptance:

- Chained rotating vectors remain connected within tolerance.
- The traced endpoint agrees with the declared Fourier sum.
- Time animation, camera motion, and captions remain synchronized.

## Tranche 6: surfaces and Erdős landscape

Add:

- Typed parametric surfaces.
- Planes and surface opacity.
- Sampled scalar fields and level/sublevel footprints.
- Root markers and one-dimensional interval measurements.

Acceptance:

- Surface values are finite over the sampling grid.
- The zero-plane intersection and sublevel footprint are numerically checked.
- Width annotations agree with the declared mathematical packet.
- The film distinguishes an attained extremum from an approached infimum.

## Final matrix

The completed suite must cover:

- Cairo at low and production-like quality.
- OpenGL smoke compatibility where the environment supports it.
- 720p and 1080p; 16:9, 9:16, and 1:1.
- Light and dark palettes, long captions, and font fallback.
- Dense and continuously updated geometry.
- Missing fonts, malformed LaTeX, invalid domains, excessive coordinates,
  failed invariants, render timeouts, and absent audio/assets.
- Full FFmpeg decode, frame count, duration, and audio presence.
- Reproducible source/IR/timeline hashes and scoped cache invalidation.

## Exit condition

The module is Nolan-ready when it can accept a script, word timings, assets,
and a normalized style payload; produce independently editable Manim clips;
and return a timeline, validation evidence, and review artifacts without Nolan
needing to understand generated Python.
