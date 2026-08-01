# v0.7 Expanded Planning and Pedagogy

v0.7 expands the safe typed-template path without letting a planning model
emit unrestricted Python or arbitrary scene graphs. It also adds a deterministic
teaching-quality signal that can be reviewed or enforced before an expensive
render.

## Authoring order

The module treats narration and visual planning as coupled artifacts, not as a
one-way “write a script, then decorate it” process:

1. A script paragraph and learning goal define the semantic beat.
2. Nolan narration and word timestamps, when present, define its exact time
   budget.
3. A constrained decision selects a pedagogical strategy, a reusable template,
   and only authored formula references.
4. The deterministic compiler builds the Manim representation.
5. Math, pedagogy, render, and decoder review remain separate evidence layers.

This supports both practical Nolan flows:

- For a locked script, Nolan can generate TTS first and the module plans inside
  the aligned duration.
- For co-authored teaching content, the module can propose the beat/visual
  structure before Nolan commits to final speech.

The script is therefore not discarded, and animation is not free-form. The
canonical state remains the versioned project plus planning evidence.

## Expanded typed decisions

`ExpandedVisualDecision` is
`math-animation.visual-decision.v2`. It adds:

- `PedagogicalIntent`: learning goal, teaching strategy, optional
  misconception, and bounded cognitive-load intent.
- `PacingProfile`: the intended visual-action and stable-hold fractions.
- A discriminated typed plan rather than a bag of optional parameters.

The existing six v1 blocks remain available. Two new common patterns compile
to `SceneProgram`:

### `equation_sequence`

- Requires three to six distinct indices into the authored formula list.
- Keeps one MathTex object alive through every step.
- Uses ledger-bound `TransformMathAction` operations.
- Preserves the authored order selected by the provider.
- Leaves a stable inspection hold inside the narration budget.

### `concept_comparison`

- Requires two distinct authored formula indices.
- Shows both representations concurrently.
- Accepts short, typed left/right labels.
- Uses responsive overrides to stack the comparison in portrait output.

The expanded validator runs after both heuristic and model providers. It
rejects out-of-range indices, wrong parameter counts, unsupported templates,
invented expressions, and invented number-line values.

## Model adapter

`OpenAIExpandedDecisionProvider` uses Responses API structured output with
`ExpandedVisualDecision` as the parsed Pydantic type. The model receives:

- Exact beat text and ordered formulas.
- Previous template/diagnostic context when supplied.
- Only templates supported by the authored inputs.

Every call writes an audit record with context/hash, allowed templates,
response metadata, latency, usage, parsed decision, and any validation error.
The adapter stores no credentials and is client-injectable for offline tests.

Nolan can replace it with any provider implementing the same `decide(context)`
protocol.

## Pedagogy report

`evaluate_pedagogy(project)` writes
`math-animation.pedagogy-report.v1`. Its weighted dimensions are:

| Dimension | Weight | Structural evidence |
| --- | ---: | --- |
| Objective alignment | 0.20 | Requested representation versus visible typed objects |
| Progressive disclosure | 0.16 | Meaningful transformation and reveal stages |
| Cognitive load | 0.16 | Object count, concurrent actions, text volume |
| Pacing | 0.14 | Active animation versus aligned beat duration |
| Mathematical grounding | 0.12 | Existing deterministic math validation |
| Narration sync | 0.12 | Nolan word-alignment evidence and duration agreement |
| Legibility | 0.10 | Existing layout, type, and density diagnostics |

The report includes per-beat scores, structured findings, evidence, and
suggested actions. It always states its limits: these heuristics detect
structural teaching risks; they do not prove that a learner understands the
material. Human/domain review and eventual learner testing remain necessary.
Exact beat-duration agreement earns strong sync evidence; full sync credit
requires at least one explicit Nolan `WordAnchor`, so duration fitting is not
misrepresented as semantic cue-to-word alignment.

The pipeline always records `pedagogy.json`. Enforcement is opt-in:

```bash
python -m math_animation compile project.json \
  --minimum-pedagogy-score 0.85
```

This avoids breaking legacy projects while giving Nolan a deterministic
pre-render acceptance gate.

## Benchmark

`scripts/run_expanded_pedagogy_benchmark.py` exercises:

- A three-step algebra derivation.
- A side-by-side function comparison.
- Synthetic narration with word timestamps.
- Style input through the Nolan placeholder bridge.
- A deliberately overloaded, static, graph-misaligned negative case.

Compile-only acceptance currently records:

- Correct templates: `equation_sequence`, `concept_comparison`.
- Positive pedagogy score: at least 0.95, status `passed`.
- Negative synthetic score: 0.4906, status `failed`.
- Zero custom Python.

The rendered mode additionally requires decoder/review acceptance and writes a
standalone MP4 plus stable-frame contact sheet.

Final cold native result:

- Both templates selected and two clips rendered fresh; zero cache reuse.
- Pedagogy: 0.9574, `passed`.
- Synthetic negative: 0.4906, `failed`, with grounding, alignment,
  progressive-disclosure, pacing, and cognitive-load findings.
- Render review: `passed`, zero warnings and zero errors.
- Media: 11.33 seconds, 640x360, 15 fps, H.264 plus mono AAC narration.
- Total cold pipeline: 35.87 seconds.
- Zero custom Python.

Evidence:

- `artifacts/expanded_pedagogy_benchmark_compile_report.json`
- `artifacts/expanded_pedagogy_benchmark_report.json`
- `artifacts/expanded_pedagogy_benchmark_keyframes.png`
- `artifacts/expanded_pedagogy_benchmark_review.json`
- `examples/expanded_pedagogy/expanded-planning.json`
- `examples/expanded_pedagogy/project.json`
- `examples/expanded_pedagogy/pedagogy.json`
- `examples/expanded_pedagogy/synthetic-risk.pedagogy.json`

## Compatibility and deliberate limits

- v0.3–v0.6 schemas remain frozen by their existing golden hashes.
- New v0.7 schemas have a separate compatibility baseline.
- The canonical `ProjectSpec v1` and `SceneProgram v1` remain unchanged.
- The evaluator is deterministic and explainable, but semantically shallow.
- The two new templates cover common teaching structures, not all mathematics.
- Bespoke Manim remains a separately gated escape hatch, never a provider
  default.
- Live model quality is not claimed without credentials and an evaluated
  prompt set; offline tests prove request construction, parsing, grounding, and
  audit behavior.
