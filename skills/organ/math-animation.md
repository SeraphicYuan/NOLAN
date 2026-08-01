---
id: organ.math-animation
name: Math animation source (Manim)
description: >
  How NOLAN puts real mathematics on screen: a `math` scene declares a typed template plus a
  formula ledger, and the finish DAG compiles it into a Manim clip in the essay's own theme,
  mounted as that scene's video ground. Read before authoring a math/science beat, before
  touching `nolan.mathanim` or `vendor/math-animation`, or when the math-provenance gate blocks
  a render. Covers the nine templates, the ledger contract, the two-interpreter split (Manim and
  LaTeX live in a separate conda env), and what this source is deliberately NOT for.
kind: grammar
purpose: >
  Author a mathematical beat correctly the first time — pick the right template, write the
  ledger the gate demands, anchor the steps to the narration, and know when NOT to spend a
  Manim render.
status: active
version: 1
tier: organ
handoffs:
  - { process: hyperframes, stage: author, gate: A }
uses:
  - pipeline.hyperframes
documents:
  registry: src/nolan/mathanim/registry.py
  resolver: src/nolan/mathanim/resolve.py
  gate: src/nolan/mathanim/gate.py
  engine: vendor/math-animation/src/math_animation/contracts.py
loaded_by: []
evals: []
---

# Math animation — the fourth typed source

NOLAN's 50 composer blocks cover data, documents, structure and prose. A **derivation** — an
equation that changes and the viewer must follow the change — is unreachable by all of them.
This source closes that gap for maths and science essays, and for almost nothing else.

A `math` scene is a typed intent, never Manim source. The finish DAG compiles it, in the essay's
own theme, at the scene's exact narration window, and mounts the clip as that scene's video ground.

```
scene.type = "math"        →  nolan.mathanim.resolve   →  data.ground = {kind:"video", src}
  data.template                 (a finish-DAG step,        →  collect_video_grounds root-mounts it
  data.params                    beside datasets and       →  the composed frame paints only
  data.formulas                  documents)                   kicker / caption / source over it
```

## When NOT to reach for this

Every math render costs 10–60s, so this is the wrong tool more often than the right one:

| the beat shows… | use |
|---|---|
| **data** — measured quantities, a trend, shares | `chart` / `stat` with a bound dataset — themed, cheaper, provenance-gated |
| a formula as **decoration**, never reasoned about | `statement` — set it as type |
| a system, pipeline or hierarchy | `diagram` |
| a **derivation, a function's shape, a limit argument, a geometric proof** | **`math`** |

The test: does the viewer have to FOLLOW something changing? If the equation could be a still
image without losing the point, it should be.

## The scene contract

```json
{ "id": "s2", "type": "math", "start": 12.4, "dur": 9.0, "anchor": "standard form",
  "data": {
    "template": "equation_sequence",
    "objective": "Derive the vertex form",
    "formulas": [
      {"latex": "y=x^2-6x+5",        "says": "standard form"},
      {"latex": "y=(x^2-6x+9)-9+5",  "says": "add and subtract nine"},
      {"latex": "y=(x-3)^2-4",       "says": "vertex form"}
    ],
    "params": { "steps": [0, 1, 2], "at": ["complete the square", "the vertex appears"] },
    "kicker": "STEP TWO",
    "caption": "the vertex sits at x equals three",
    "source": "Euler, Introductio, 1748"
  } }
```

**`formulas` is the ledger, and it is the whole safety story.** Every formula a scene displays is
referenced BY INDEX into this list. A bespoke `scene_program` may only paint LaTeX that appears
here. The finish gate HARD-BLOCKS anything else — a formula the viewer cannot check has to trace
to one the author wrote down. Add `"verified": "<source>"` to a formula when you have a citation;
without one it is recorded as an authored assumption and listed in the run's advisories.

**Chrome vs Manim.** `kicker`, `caption` and `source` are painted in HTML, in the theme's type.
`title` is NOT painted — it names the beat in the run bundle and feeds the pedagogy report.
`params.caption` (one level down) is a different field, typeset inside the clip by the template.

**`at` anchors a step to the words that describe it** — the same "show it as you say it" contract
as an HTML block's `at` cue, resolved by the repo's own phrase matcher. Omit it and the steps
spread evenly across the beat; they are never front-loaded.

## The nine templates

Chosen from `src/nolan/mathanim/registry.py` — `catalog.json` carries a generated copy, and
`tests/test_mathanim.py` fails if this list drifts from either.

| template | for | key params |
|---|---|---|
| `equation_sequence` | **the workhorse** — a 3–6 step derivation on one persistent formula | `steps` (indices), `at` |
| `equation_reveal` | one formula written on, part by part | `formula`, `part_roles`, `caption` |
| `equation_transform` | ONE algebraic step where the change is the point | `from`, `to`, `caption` |
| `concept_comparison` | two forms side by side (stacks in portrait) | `left`, `right`, `left_label`, `right_label` |
| `function_plot` | the SHAPE of a relationship you can write | `expression`, `x_range`, `y_range`, `label` |
| `number_line` | roots, an interval, a bound, where a limit heads | `values`, `labels`, `x_range` |
| `secant_to_tangent` | the limit definition of the derivative, animated | `expression`, `x0`, `h_start`, `h_end` |
| `title_card` | a typeset title BETWEEN Manim beats | `title`, `subtitle` |
| `scene_program` | the bespoke tier: 3D surfaces, point clouds, epicycles, a determinant deforming an area | `program` (a typed `SceneProgram`) |

`scene_program` is typed, not a hole for Python. **`custom_scene` is refused by name** at the
authoring gate: the engine allows it only behind an asserted isolated renderer, and NOLAN has none.

Semantic colour roles for `part_roles` / `role`: `primary`, `secondary`, `changing`, `fixed`,
`positive`, `negative`, `foreground`, `muted`. `changing` and `fixed` are the load-bearing pair —
`nolan.mathanim.style` derives them from the theme and refuses a palette where a viewer could not
tell which term moved.

## What owns what

Narration owns duration, exactly as everywhere else in NOLAN:

- `scene.dur` becomes the beat's duration, and the engine's compiler pads the Manim scene to
  **exactly** that and **refuses to compile** when the animation needs more. The clip is
  frame-exact by construction, so the freeze-heal that rescues a short b-roll clip is skipped for
  math (its boomerang would play a derivation backwards).
- The theme drives background, type and semantic colours, so a math beat looks like the essay
  around it rather than a Manim clip spliced in.
- Manim never sees the audio, never mixes, never decides a duration.

## Two interpreters

Manim + LaTeX live in **`D:\env\mas`**; everything else runs in the pipeline env with pydantic
alone. This is not a preference — installing Manim alongside the pipeline lands numpy 2.5.1 and
Pillow 12.3.0, both outside NOLAN's pins. Setup and the deltas from upstream v0.7.1:
`vendor/math-animation/CLAUDE.md`.

```bash
D:\env\mas\python.exe -m math_animation doctor
```

`latex: missing` is the usual first failure — every equation then dies inside a Manim subprocess.
`NOLAN_MATHANIM_PYTHON` overrides the interpreter.

**Fonts are the other half of "in the essay's theme".** Colours, type sizes and semantic roles
map cleanly, but Manim asks Pango for SYSTEM fonts and cannot use the webfonts the HTML side
pulls from Google Fonts. A theme face that is not installed on the render machine falls back to
generic Sans with mangled kerning, and Pango says so only in a stderr log a successful render
never surfaces. So `nolan.mathanim.style` resolves the face against what the render env actually
sees and substitutes by the theme's `typePersonality` (geometric-sans → Century Gothic,
editorial-serif → Georgia, mono-technical → Consolas …), REPORTING every substitution. To match
the HTML exactly, install the theme's own face on the render machine — then the resolver uses it
untouched. Equations are unaffected: they are typeset by LaTeX, not Pango.

## Working on it

```bash
# build + provenance-check every math scene, no render spend
python -X utf8 -m nolan.hyperframes.math_source <comp> --gate-only

# the whole DAG (math runs after word-sync, before recompose)
python -X utf8 -m nolan.hyperframes.finish <comp> --no-render
```

Clips are content-addressed on the built project — the authored data, the theme's style tokens,
the exact duration and the sliced word timings — so an unchanged scene never re-renders. Change
any of those and only that scene rebuilds.

The gate's escape is `HF_ALLOW_UNVERIFIED_MATH=1`, for a knowing exception only.

Deferred deliberately (see `vendor/math-animation/docs/DEFERRED_NOLAN_WORK.md`): alpha-MOV
overlay delivery, promotion of recurring bespoke programs into typed templates, and a responsive
render matrix for square/portrait.
