# v0.1 Showcase Benchmark

Date: 2026-07-29

Follow-up: Math Animation 0.2 now implements the first Olin-oriented vertical
slice—persistent objects, vectorized point-cloud states, parallel camera and
geometry actions, and checked projection assertions. See
[SceneProgram v1](SCENE_PROGRAM.md) and
`examples/olin_scene_program.json`. Time-varying clouds and the Erdős surface
vocabulary remain future work.

This benchmark compares the deterministic v0.1 block library with three
reference films from
[HarleyCoops/Math-To-Manim](https://github.com/HarleyCoops/Math-To-Manim):

1. `derivatives-as-slopes.gif`, used as a control because v0.1 already has a
   `secant_to_tangent` block.
2. `ERDŐS 1038: THE POTENTIAL LANDSCAPE`, a stress test for mathematical 3D
   surfaces, level sets, distributions, and proof structure.
3. `OLIN: THE SPACE INSIDE A TWEET`, a stress test for vectorized point clouds,
   coordinate transforms, projection, and camera choreography.

The benchmark deliberately separates three questions:

- Can the installed Manim engine render the visual?
- Can the typed v0.1 blocks describe the visual?
- Can the standalone pipeline compile, render, and compose the result?

## Verified toolchain

The project uses `/opt/miniconda3/envs/mas/bin/python` and Manim Community
`0.20.1`. The render worker can resolve:

- Conda FFmpeg `7.1.1`
- Homebrew TeX Live `2026`
- Homebrew `dvisvgm 3.6`
- Cairo and Pango

`math-animation doctor` passes. The repository test suite passes with 15
tests.

The render environment explicitly keeps Homebrew's `latex` and `dvisvgm`
together. Mixing Conda's partial TeX package with Homebrew's `dvisvgm` caused
format and font-map failures during the first benchmark attempt.

## Results

| Reference | Engine result | Typed v0.1 result | Approximate built-in coverage |
| --- | --- | --- | --- |
| Derivatives as slopes | Pass | Credible simplified version | 55–70% |
| Erdős 1038 | Reference film inspected | Signature visual cannot be expressed | 15–20% |
| Olin | Exact 69.6-second source rendered at 854×480, 15 fps | Signature visual cannot be expressed | 10–15% |

The percentages estimate coverage of the explainer's teaching visuals, not
lines of code or renderer capability.

### Derivatives as slopes

The included `derivative_project.json` rendered and composed successfully:

- 11.07 seconds
- 1920×1080
- 30 fps
- H.264
- two independently rendered clips

v0.1 captures the central teaching motion: a moving point brings the secant
line toward the tangent. It does not yet reproduce the reference film's
simultaneous graph-plus-equation layout, braces, `h` labels, slope quotient,
or persistent objects across symbolic stages.

Verdict: v0.1 can make a useful derivative explainer today, but not a close
reproduction of the showcase composition.

### Erdős 1038

The film's six beats require:

1. Root configurations on a number line.
2. A genuine logarithmic-potential surface and translucent zero plane.
3. The below-zero footprint representing \(E_f\).
4. Atomization and distribution morphs.
5. An endpoint atom plus a continuous one-cut density.
6. A raised parameter valley, certified interval, and endpoint maximizer.

v0.1 can supply titles, formulas, a number line, and a basic two-dimensional
function plot. It cannot express the terrain, level-set footprint,
distribution morph, raised density, or 3D camera moves. Those missing objects
carry the proof, so replacing them with equations would defeat the explainer.

Verdict: the engine is capable, but the deterministic block vocabulary is not.
Using unrestricted custom Python would bypass the architecture rather than
validate it.

### Olin

The repository's self-contained `OlinOffWhite3DSpace` scene was rendered
locally with the installed toolchain:

- 69.60 seconds
- 854×480
- 15 fps
- H.264
- 105 Manim animations

This proves that Manim `0.20.1`, NumPy, TeX, `dvisvgm`, and FFmpeg can execute
the reference workload. The scene depends on capabilities absent from v0.1:

- a vectorized 10,000-point static cloud;
- a deterministic 5,000-point animated subset;
- time-varying NumPy coordinate functions;
- morphing from the 2D shadow to the exact lift \(E\);
- morphing from \(E\) to the cylindrical interpretation \(C\);
- orthographic projection checks;
- persistent 3D objects and camera orbits;
- fixed-in-frame formulas and captions over 3D geometry.

Verdict: renderer pass, typed-authoring fail. This is the cleanest evidence
that the next work belongs in reusable blocks, not in dependency installation.

## Recommended v0.2 slice

The next release should not attempt to encode the whole showcase. A coherent
vertical slice is:

1. Add a 3D scene mode and typed camera shots.
2. Add persistent named objects and action tracks so geometry can survive
   across transformations instead of every block fading itself out.
3. Add `vectorized_point_cloud` with deterministic sampling, safe coordinate
   expressions, precomputation, and hard point/render budgets.
4. Add `coordinate_transform_3d` with explicit source, target, projection, and
   morph semantics.
5. Add `surface_with_level_set` for a surface, translucent plane, and shaded
   sublevel footprint.
6. Add `distribution_morph` for atoms, densities, and barycentric collapse.
7. Add `parameter_valley` for a raised curve, tracked minimizer, and certified
   interval annotation.
8. Add render QA: MathTex preflight, missing-font detection, representative
   frames, text-bound checks, black-frame detection, and performance metrics.

Olin should be the first v0.2 acceptance target because its mathematics and
source scene are self-contained and its reusable primitive is clear:
point-cloud coordinate transforms. Erdős should follow as the second target
after surfaces, sublevel sets, and distribution morphs exist.

## Architectural conclusion

The v0.1 boundary is sound:

- The screenplay, narration timestamps, style lock, math ledger, timeline, and
  run manifest worked as intended.
- The Manim and FFmpeg backend worked end to end.
- The custom-Python escape hatch remains useful for research, but it should not
  be counted as block coverage.

The main limitation is now the visual intermediate representation. v0.2 needs
stateful 3D composition and several high-value typed primitives; it does not
need a different renderer or a return to unrestricted scene generation.
