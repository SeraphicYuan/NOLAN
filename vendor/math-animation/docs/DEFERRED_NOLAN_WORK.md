# Deferred Work for Nolan

The standalone math-animation module is ready to hand off after v0.7.1.
Collision-aware rendered review was completed before handoff. The following
four areas are deliberately deferred until Nolan owns the integration context.

## 1. Exact Nolan timing and style adapters

Replace the placeholder boundaries with Nolan's real versioned payloads:

- TTS audio and utterance identifiers.
- Word-level alignment, including punctuation/token policy.
- Style-template tokens, safe areas, typography, semantic colors, and motion.
- Media delivery settings, transparent overlays, and Nolan composition.
- Cache invalidation when narration, style, or delivery settings change.

Do not change `ProjectSpec v1` merely to mirror provider-specific fields. Add a
Nolan adapter that translates its payloads into the stable contracts.

Acceptance should include a real Nolan-authored project rendered in landscape,
square, and portrait output.

## 2. Promote successful bespoke scenes into typed templates

The `SceneProgram` IR can already express complex Manim scenes, as demonstrated
by the determinant-area stress test. That scene was deliberately authored as a
typed bespoke program rather than generated Python.

Promote recurring patterns only when production examples justify them. Strong
initial candidates are:

- `linear_map_geometry`
- `basis_vector_transform`
- `area_under_transformation`
- `orientation_flip`
- `singular_collapse`
- `graph_parameter_sweep`
- `geometric_proof`

Each template should own object construction, responsive layout, timing
defaults, assertions, and render fixtures. A provider should fill constrained
parameters, not emit Manim source.

## 3. Evaluate a live planning model

The OpenAI Responses adapters are implemented and tested using injected
clients. No claim has been made about live model quality.

Run a versioned benchmark against Nolan's selected production model:

- Template-selection accuracy.
- Formula-index and numeric grounding.
- Pedagogical-strategy quality.
- Parameter validity and unsupported-intent recognition.
- Repair/regeneration success after rendered failures.
- Cost, latency, and output stability.

Store exact model IDs, call records, benchmark prompts, and acceptance results.
Keep the deterministic validators authoritative after every model response.

## 4. Expand responsive render coverage

The base visual IR supports landscape, square, and portrait overrides, but the
new v0.7 templates and featured stateful scenes have primarily been accepted
in landscape.

Add a rendered matrix covering:

- `equation_sequence`
- `concept_comparison`
- At least one dense stateful `SceneProgram`
- Light and dark Nolan templates
- Landscape, square, and portrait
- Transparent and full-frame delivery where applicable

Acceptance must run collision-aware rendered review at every aspect ratio.

## Deliberately not deferred

Rendered collision detection is implemented now. It projects visible typed
text, MathTex, and annotation boxes at stable cue states, checks overlap and
minimum separation, and attaches evidence to the actual rendered probe.

For compatibility, the frozen `Diagnostic v1` records this as:

```json
{
  "code": "text_overflow",
  "evidence": {
    "kind": "visual_collision"
  }
}
```

A future `Diagnostic v2` may introduce a dedicated code, but Nolan must not
mutate the frozen v0.5 schema in place.
