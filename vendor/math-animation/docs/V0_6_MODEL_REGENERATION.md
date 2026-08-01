# v0.6 Model Decisions and Typed Regeneration

v0.6 connects a real structured-output model API without allowing the model to
emit Manim code, arbitrary scene JSON, or patches. It also completes the
`regenerate_beat` path introduced in v0.5.

## Provider boundary

Every provider implements:

```python
class VisualDecisionProvider(Protocol):
    provider_id: str

    def decide(self, context: PlanningBeatContext) -> VisualDecision:
        ...
```

`VisualDecision` can select only:

- `title_card`
- `equation_reveal`
- `equation_transform`
- `function_plot`
- `secant_to_tangent`
- `number_line`

The post-provider validator enforces source grounding:

- Equation templates require authored formulas.
- A transform requires two authored formulas.
- Plot/secant expressions must exactly match a safe expression in the source.
- Number-line values must be finite values written in the source.
- Expression/value fields are forbidden on unrelated templates.
- No custom-scene or Python field exists in the schema.

These checks run after both heuristic and model decisions, so provider behavior
cannot bypass the deterministic safety layer.

## OpenAI Responses adapter

`OpenAIResponsesDecisionProvider` uses the official SDK's Responses API
structured-output parser with `VisualDecision` as its Pydantic output type. A
model ID is explicit configuration rather than a hard-coded default.

Install the optional SDK:

```bash
/opt/miniconda3/envs/mas/bin/pip install -e ".[model]"
```

Configure `OPENAI_API_KEY`, then plan:

```bash
/opt/miniconda3/envs/mas/bin/python -m math_animation plan script.txt \
  --project-id limits \
  --title "Limits" \
  --provider openai \
  --model YOUR_MODEL_ID \
  --output-dir planned/limits
```

Every call records:

- Provider/model and response ID/model.
- Exact grounded context and its hash.
- Allowed templates.
- Parsed decision and status.
- Latency and token-usage payload.
- Validation or provider errors.

The records are written to `model-calls.json`. API keys are never stored.

## Regeneration

Rendered review diagnostics for blank, frozen, or discontinuous shots can now
route back through the bounded repair graph when a provider is configured:

```text
render attempt 1
  -> structured review diagnostics
  -> regenerate_beat RepairPlan operation
  -> grounded RegenerationArtifact
  -> deterministic built-in block
  -> render attempt 2
  -> review
```

The v0.5 `RepairPlan v1` remains unchanged. The provider decision lives in the
separate `RegenerationArtifact v1`, which contains:

- Source project hash and triggering diagnostic.
- Beat ID and provider ID.
- Narration-derived context and previous representation.
- Meaningfully matched ledger formulas.
- Allowed templates and selected formula IDs.
- Strict `VisualDecision` plus decision hash.

The executor verifies the artifact against the plan and source hash, constructs
the replacement with the normal block factory, revalidates the full project,
and confirms that only declared beat hashes changed.

Run model-backed repair:

```bash
/opt/miniconda3/envs/mas/bin/python -m math_animation repair project.json \
  --runs-dir runs \
  --render --compose \
  --regeneration-provider openai \
  --model YOUR_MODEL_ID
```

Nolan can instead inject its own provider implementing the same protocol.

## Regeneration benchmark

`scripts/run_regeneration_benchmark.py --render` deliberately renders:

- An almost invisible shot that triggers `blank_frame`.
- A no-op motion cue that triggers `frozen_motion`.
- One accepted control beat.

A deterministic provider is used so the benchmark is reproducible without
network credentials. This tests the exact same provider contract and
regeneration executor as the live adapter; it is not presented as a live model
evaluation.

Acceptance requires:

- Both failures observed in rendered evidence.
- Two typed regeneration decisions.
- Exactly two pipeline attempts.
- Both failed beats replaced by ledger-locked equation blocks.
- The accepted control clip reused from cache on attempt two.
- Only regenerated beats freshly rendered.
- Final review passes without warnings or errors.
- Zero custom Python.

Cold native result:

- 2/2 rendered failures diagnosed and regenerated.
- Two pipeline attempts and two provider decisions.
- Control beat reused; two regenerated beats rendered fresh.
- Final review: passed, zero warnings, zero errors.
- Final media: 5.87 seconds, 640x360, 15 fps, H.264 plus AAC narration.
- Full two-attempt benchmark: 30.18 seconds.

Evidence:

- `artifacts/regeneration_benchmark.mp4`
- `artifacts/regeneration_benchmark_keyframes.png`
- `artifacts/regeneration_benchmark_report.json`
- `artifacts/regeneration_benchmark_first_review.json`
- `artifacts/regeneration_benchmark_review.json`
- `examples/regeneration_benchmark/project.defective.json`
- `examples/regeneration_benchmark/project.regenerated.json`

## Deliberate limits

- A live model call is not run without user-supplied credentials.
- Providers select existing templates; they do not author unrestricted
  `SceneProgram` objects.
- Formula relevance uses explicit references first, then meaningful
  title/narration overlap. Generic words such as “equation” are ignored.
- Mathematical and missing-input refusals remain non-regenerable.
- The graph still stops after two pipeline attempts.

The next expansion should add richer typed template parameters and
pedagogy-level evaluation, not a return to unrestricted generated Python.
