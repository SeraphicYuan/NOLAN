# Effect Analysis — clip_4d85395f

Source: `US Economy / If The Economy Is F＊cked, Why Hasn't It Crashed Yet？.mp4`
In/out: 118.41s → 119.24s (0.83s)

## Effect

A **pie/proportion chart emphasising a minuscule slice**, in a grainy documentary style.

- A large grey, paper-textured **circle (pie)** represents the whole ("...out of every
  30m..."). A **thin blue wedge/sliver** at the 3 o'clock position represents the tiny share —
  the stat text reads **"0.0017%"**. The slice is so small it's a near-invisible needle.
- **Entry:** the clip opens on an over-exposed **white light-bloom / flash** (frame 1) that
  blows out into the scene — a bright bloom transition.
- **Motion in this 0.83s window:** mostly a **slow leftward camera drift + slight zoom**
  (Ken-Burns-like) on the circle, while the **stat text fades/slides in from the right**
  ("0.0017% of 30m...", "out of every..."). The wedge itself is roughly static here.
- Aesthetic: grainy paper texture, neutral grey + single blue accent, light background.

## Dedup result

**Mostly already covered — split by engine.**

- **render-service (TS / motion-canvas): COVERED.** `chart-pie`
  (`render-service/src/effects/presets/chart.ts:422`) is an animated pie chart — segments grow
  from centre, supports `donut`, `show_percentages`, and a `documentary` style preset. A single
  tiny-value segment reproduces the clip's core visual.
- **Python (PIL) renderer: was NEW.** No pie/donut scene existed — only bar-style data viz
  (`percentage_bar`, `stat_comparison`, `ranking`). `base.py` used `draw.arc` only for the
  `CircleAnnotation` outline (`base.py:815`), not filled wedges.
- Supporting motion was already available as primitives: white-flash entry ≈ `Flash` /
  render-service transitions; slow drift/zoom ≈ `KenBurnsRenderer` or `MoveTo`+`ScaleIn`;
  text slide-in ≈ `SlideLeft/Right`+`FadeIn`.

## Replicable?

**Yes.** Two paths existed: reuse render-service `chart-pie`, or add a Python scene.

Per the user's direction this became a **richer, purpose-built motion** (not just the static
sliver in the clip): big pie → scale down → colour the slice by an input percentage → eject the
slice → reveal an info text block. Built in the **Python renderer** (engine choice), as a
**donut**, **pie-left / text-right** layout, with a **user-controllable pie location**.

## Plan

Implemented as a self-contained scene (mirrors `KenBurnsRenderer`'s `render_frame` override —
no `base.py`/`effects.py` changes), drawing the donut + annular-sector slice with PIL
`pieslice` and beat-based easing. Difficulty: **Low-Medium**.

## Promoted to NOLAN

Implemented 2026-06-24.

| Technique | Scene / API | File | Date |
|-----------|-------------|------|------|
| 5-beat donut/pie callout (intro → scale-down → colour slice → eject slice → text reveal) | `PieCalloutRenderer`, `render_pie_callout()` | `src/nolan/renderer/scenes/pie_callout.py` | 2026-06-24 |

Beats: (1) big donut fades/scales in centred; (2) scales down + slides to `pie_center`;
(3) target slice (sized by `percentage`) sweeps in, accent colour, with the value in the donut
hole; (4) slice ejects outward along its bisector; (5) `info_title` + `info_text` block slides
in from the right.

Usage:

```python
from src.nolan.renderer.scenes.pie_callout import PieCalloutRenderer

PieCalloutRenderer(
    percentage=23,                 # slice size + centre value
    info_title="23%",
    info_text="of respondents had never heard of the policy before this year.",
    slice_label="Unaware",
    pie_center=(0.30, 0.52),       # controllable resting location (default: left)
    donut=True,
).render("pie.mp4", duration=6.5)
```

- Key params: `percentage`, `info_title`/`info_text`/`slice_label`, `pie_center` (location),
  `donut`/`hole_ratio`, `slice_color`/`track_color`, `start_angle`, `explode_frac`.
- Verified by `scripts/test_pie_callout.py` (donut renders; accent slice appears and its size
  tracks the percentage — 23% paints far more accent than 0.0017%; text block appears late;
  `pie_center` moves the chart). Visual check confirmed all 5 beats.
