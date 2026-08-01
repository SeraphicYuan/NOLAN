# v0.4 constrained planner

v0.4 adds the first authoring-intelligence layer without weakening the v0.3
render contract. It plans a script into a complete `ProjectSpec`, but it cannot
emit arbitrary Python.

## Boundary

```text
script + aligned narration + style + assets
                     |
             decision provider
                     |
              VisualDecision
       (strict template + safe parameters)
                     |
            constrained emitter
                     |
       PlanningArtifact + ProjectSpec
                     |
       existing validate/render/review path
```

`VisualDecisionProvider` is the future model seam. A provider may select one of
the registered templates, provide a validated function expression or numeric
landmarks, explain its rationale, assign confidence, and record unsupported
intentions. It cannot return Manim code, imports, or a custom-scene block.

`HeuristicDecisionProvider` is the deterministic offline baseline. It selects:

- `equation_reveal` for authored inline/display LaTeX.
- `equation_transform` for two authored formulas plus transformation language.
- `function_plot` for a safe explicit expression plus graph language.
- `secant_to_tangent` for a safe expression plus derivative language.
- `number_line` for explicitly requested numeric landmarks.
- `title_card` when a stronger visual would require invented mathematics.

The title fallback is deliberately visible in `planning.json` and carries an
unsupported-intent warning when appropriate.

## Artifacts

The `plan` command writes:

```text
planning.json
project.json
```

`planning.json` includes the planner/provider ID, request and project hashes,
per-beat source text, selected template, rationale, confidence, formula IDs,
unsupported intentions, template counts, and custom-Python requests. The
custom-Python list is empty for the constrained planner.

## Narration

One narration utterance must correspond to each script paragraph. Existing word
timestamps and the audio path are preserved. With no alignment input, the
planner creates untimed utterance records and conservative durations. Nolan
alignment remains authoritative in production.

## Mathematical policy

The planner copies authored formulas verbatim into the ledger. It records each
one as an `assumed` claim sourced from the script. It does not mark a claim
verified merely because the formula compiled or rendered. Independent
mathematical verification is a later provider/stage.

## Benchmark

`benchmarks/unseen_prompts.json` contains 12 prompts spanning algebra,
arithmetic, geometry, calculus, functions, probability, linear algebra,
Fourier analysis, statistics, multivariable calculus, and research
mathematics.

Run compilation only:

```bash
/opt/miniconda3/envs/mas/bin/python scripts/run_planner_benchmark.py
```

Run every clip and compose the synthetic narrated film:

```bash
/opt/miniconda3/envs/mas/bin/python scripts/run_planner_benchmark.py --render
```

The acceptance threshold is 80%. The checked run selected all 12 expected
templates, compiled and rendered all 12 clips, requested no custom Python, and
passed mathematical-contract and media review. The final cold run rendered all
12 clips in 71.9 seconds and produced a 32.1-second, 640×360, 15 fps H.264 film
with 24 kHz mono AAC narration. Review reported no warnings or errors.

The first run also exposed redundant number-line typesetting and false blank
closing-frame warnings. The number-line compiler now draws only requested
labels using `Text`, and review treats the deliberate cleanup frame of a legacy
block as expected blank while probing the block's actual stable and motion
frames.

## Contract freeze and CI

`tests/golden/v0.3_contracts.json` freezes:

- Project and SceneProgram JSON Schema hashes.
- Public schema-version strings.
- The deterministic block catalog.

`tests/golden/v0.4_compiler.json` separately freezes semantic compiler output
for the equation fixture, excluding only the package-version banner. This lets
v0.4 intentionally repair rendering behavior while keeping Nolan's v0.3 public
data contract unchanged.

The local suite contains 45 passing unit/golden tests. GitHub CI runs those
tests, validates every checked-in project, compiles
the planner benchmark, and performs a native Cairo/LaTeX render smoke test.

## Deliberate limits

- The heuristic fallback recognizes a narrow, transparent vocabulary. It is a
  safe baseline, not a pedagogy model.
- Formula claims are assumed, not independently proved.
- General geometric scene planning still needs a provider capable of returning
  richer typed object/action plans.
- Automated repair is not yet enabled. The existing review evidence is ready
  for a bounded repair graph, but planning quality should be evaluated first.
- LangGraph remains deferred until remote provider calls, approvals, or repair
  retries create real orchestration state.
