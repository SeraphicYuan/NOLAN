# v0.5 Typed Repair Workflow

v0.5 adds a bounded self-repair layer without weakening the stable
`ProjectSpec` or `SceneProgram` contracts. The layer can fix presentation and
timing defects, but it refuses to invent missing inputs or alter unsupported
mathematics.

## Graph

LangGraph is used only as the control plane:

```text
START -> audit -> repair -> audit -> execute -> review -> finish
                    ^                    |
                    +--------------------+
```

The graph state contains artifact paths, status, attempt counters, and
diagnostic IDs. The mathematical/visual IR remains in versioned JSON files, so
it is usable without LangGraph and can later be handed to Nolan.

The default policy permits:

- At most two pipeline attempts.
- At most two typed repair passes.
- Content-addressed reuse of unaffected beat clips.
- No arbitrary JSON patches and no generated Python.

## Diagnostics

`Diagnostic` v1 records a stable ID, code, severity, stage, beat/object/cue
scope, evidence, suggested typed operations, and whether repair is safe.

The current vocabulary covers:

- Text overflow and illegible type.
- Blank stable frames, frozen motion, and abrupt discontinuities.
- Excessive geometry density.
- Cue/media timing drift.
- Mathematical or numeric invariant failures.
- Missing inputs and invalid LaTeX.
- Media mismatch, wrong template selection, and render failures.

Review report v2 retains the existing `warnings` and `errors` arrays for
compatibility and adds the structured `diagnostics` array. Blank-frame warnings
are evaluated only when a cue should be stable or at a non-blank closing;
opening and early `Create` frames are not mislabeled.

## Typed repairs

The deterministic executor supports:

- Repositioning an object within the active aspect safe area.
- Raising an authored responsive scale or font size.
- Adding a maximum width and line wrapping without changing words.
- Shortening a generated caption/title while leaving narration untouched.
- Scaling scene-action or legacy-block timing to the aligned beat window.
- Reducing point, trace, footprint, or surface density.
- Moving a frozen tracker to an already-authored trace endpoint.
- Swapping a title fallback to a ledger-locked equation template.

`regenerate_beat` exists as a typed provider boundary but is intentionally not
executed without an explicit future planning provider. Every applied plan:

1. Verifies the source project hash.
2. Applies only named typed operations.
3. Revalidates the complete `ProjectSpec`.
4. Verifies that changed beat hashes match the declared affected beat IDs.
5. Writes the original, plan, repaired project, before/after hashes, and graph
   state into the repair session.

## Refusal policy

The workflow refuses rather than guesses when it sees:

- Missing assets or narration files.
- A mathematically invalid ledger.
- Invalid LaTeX.
- Non-finite surfaces or failed numeric invariants without an authored safe
  domain.
- Frozen motion without an authored alternative target.
- An unclassified render failure.

## Adversarial benchmark

`scripts/run_repair_benchmark.py --render` builds and renders a 21.42-second
portrait explainer containing eight injected defects:

- Clipped generated caption.
- Tiny portrait formula.
- Frozen tracker.
- Excessive surface density.
- Cue longer than narration.
- Offscreen object.
- Unbounded long text.
- Wrong fallback template.

It separately tests three refusals: missing asset, invalid math ledger, and a
non-finite surface domain.

Cold native results:

- Repair success: 8/8 (100%).
- Correct refusal: 3/3 (100%).
- Custom Python: 0%.
- Pipeline attempts for the repaired explainer: 1.
- Review: passed with zero warnings and zero errors.
- Final media: 360x640, 12 fps, 257 H.264 frames, AAC 24 kHz mono.
- Cold end-to-end pipeline time: 32.69 seconds.
- Scoped retry: seven unaffected beats reused; only the changed caption beat
  rendered again.

Evidence:

- `artifacts/repair_benchmark.mp4`
- `artifacts/repair_benchmark_keyframes.png`
- `artifacts/repair_benchmark_report.json`
- `artifacts/repair_benchmark_review.json`
- `examples/repair_benchmark/project.defective.json`
- `examples/repair_benchmark/project.repaired.json`

## Nolan integration

Nolan can call the repair workflow after authoring and before accepting a clip
bundle. Its TTS/aligner timestamps remain authoritative, its style template
continues to enter through `StyleTemplateRef`, and only changed beat clips need
to return to the Manim renderer. The graph does not own narration, style, or
composition.

That next layer is implemented in v0.6 as a real structured-output
`VisualDecisionProvider` adapter plus typed beat regeneration. It consumes
diagnostics and returns only an allowed template decision—not Python source.
