# v0.3 acceptance report

Math Animation v0.3 is a self-contained mathematical authoring and rendering
module with a Nolan-neutral boundary. It accepts mathematical screenplay data,
aligned narration, a style payload, and assets; emits typed visual IR and
deterministic Manim; renders independent clips; optionally composes a narrated
film; and returns validation and review evidence.

## Featured films

| Film | Main risk exercised | Result |
| --- | --- | --- |
| Olin | 10,000-point density, time-varying 3D projection | Pass |
| Narrated algebra | word anchors, semantic equation transforms, three-beat audio edit | Pass |
| Jacobian | checked matrix area scaling and local/global distinction | Pass |
| Fourier epicycles | dependency graph, trackers, connected arrows, derived path | Pass |
| Surface/infimum | finite sampled surfaces, zero plane, footprint, open interval | Pass |
| ERDŐS 1038 | potential landscape, submerged footprint, approached vs attained widths | Pass |

The checked-in videos and contact sheets are under `artifacts/`.

## System evidence

- 37 unit tests pass.
- Three complete algebra films pass at 1280×720 landscape, 720×720 square,
  and 540×960 portrait.
- The style matrix covers light and dark palettes plus a deliberately missing
  font, which Manim safely falls back from.
- A 1920×1080, 30 fps Cairo render passes.
- Two independent renders have identical generated-source, visual-IR,
  timeline, and decoded-frame hashes.
- The local macOS worker cannot create a headless OpenGL/EGL context. The
  attempted failure is recorded as an environment capability limitation;
  Cairo is the supported production renderer here.
- A transparent Nolan overlay passes as QuickTime RLE with ARGB alpha. The
  handoff also contains a checksummed opaque synthetic GSAP asset.

Exact hashes and the OpenGL diagnostic are in
`artifacts/system_matrix_report.json`. Expected-failure evidence is in
`artifacts/adversarial_report.json`.

## Validation layers

1. Pydantic rejects malformed schemas, references, lifetimes, action types,
   width assertions, and unsafe expressions.
2. The math ledger locks displayed formulas and rejects unbalanced or unsafe
   LaTeX.
3. Batched real-LaTeX compilation runs before any Manim scene render.
4. Generated scenes assert finite coordinates, bounds, spread, projections,
   matrix determinant expectations, connected tracker samples, surface grids,
   footprint occupancy, and screen-safe typography.
5. Local inputs are existence- and checksum-checked.
6. FFmpeg verifies full decode, resolution, frame rate, duration, frame count,
   narration presence, and alpha format.
7. Cue-aware probes detect blank stable frames, missing motion, and suspicious
   discontinuities, and produce contact sheets for human review.

The adversarial suite deliberately confirms rejection of incorrect interval
widths, illegible responsive type, malformed LaTeX, a non-finite surface,
missing assets, missing narration, and render timeout.

## Performance

Every run writes `performance.json` with compilation, LaTeX preflight,
per-beat rendering, composition, review, cache reuse, and total wall time.
The ERDŐS acceptance run completed in about 30 seconds on the development
machine: roughly 8.5 seconds of preflight before batching optimization, 18.9
seconds of rendering, 0.5 seconds of composition, and 1.8 seconds of review.
Subsequent LaTeX preflight uses one batch compiler invocation on the passing
path.

Fourier initially exposed a pathological live `TracedPath` implementation.
Changing the typed trace to a pre-sampled `ParametricFunction` derived from the
same endpoint function reduced the full narrated render from repeated timeouts
to 11.6 seconds and made the path mathematically identical by construction.

## Nolan boundary

`nolan_handoff.json` contains:

- Canvas, frame rate, duration, and alpha policy.
- Per-clip paths and project in/out times.
- Exact narration words and timestamps.
- Style template identity, normalized tokens, and the untouched raw payload.
- External assets with checksums and attribution.
- Links back to each editable `SceneProgram`.

Nolan can replace the standalone composer without understanding generated
Python. Its TTS, aligner, style schema, and GSAP author stage remain the source
of truth.

## Workflow-engine decision

LangGraph is intentionally not a runtime dependency in v0.3. Durable
`ProjectSpec`, `SceneProgram`, run manifests, cache records, and failure states
already provide the required statefulness for this deterministic local
pipeline. A small orchestration graph becomes justified when Nolan integration
adds remote model/provider calls, resumable human approvals, or repair loops.
At that point nodes should wrap the existing artifact stages; the visual IR
must remain independent of the graph implementation.

## Remaining product work

- Bind the temporary style adapter to Nolan's real versioned template schema.
- Replace synthetic tone narration with Nolan TTS/alignment in integration
  tests.
- Exercise OpenGL on a Linux worker with a real EGL context if OpenGL delivery
  matters; Cairo is sufficient for the current contract.
- Add planner and repair-agent evaluation. v0.3 validates authored plans but
  does not claim autonomous pedagogy quality.
- Define production color, loudness, caption, and alpha-codec policies with
  Nolan.
