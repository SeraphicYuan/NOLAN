# Constraint brief — what a NOLAN-legal bespoke block must obey

For a Claude Design **template book** that emits `raw` scenes. A `raw` scene is
`data: {html, tl}` — HTML fragment(s) plus GSAP lines merged into the frame's ONE paused timeline
(`render-service/_lab_hyperframes/bridge/catalog.json` → `scene_templates.raw`).

Bespoke is first-class, not a side door: `src/nolan/hyperframes/bespoke.py` runs the full
propose → gate → accept → render loop, and `incremental.render_one` re-renders just that frame.
So a template book is a legitimate **bespoke block factory** — provided what it emits clears the
gate.

## The one rule everything else follows from

**The frame is a single GSAP timeline, created paused, and the renderer SEEKS it frame by frame.**
It is never played. Any construct whose output depends on wall-clock time, on how many times it has
been called, or on randomness produces a different pixel on re-render and breaks determinism.

## Machine-enforced today (`author.py::_raw_seek_errors`)

These eight substrings are rejected outright. This list is exhaustive — it is a substring scan over
the joined `html` + `tl` strings:

| forbidden | why |
|---|---|
| `Math.random` | non-deterministic |
| `Date.now` | time-based |
| `new Date(` | time-based |
| `performance.now` | time-based |
| `yoyo:` / `yoyo :` | repeating tween — no defined value at an arbitrary seek |
| `repeat:-1` / `repeat: -1` | infinite repeat — same |

## Declared but NOT enforced — the honour-system half

`catalog.json` lists six constraints on `raw`; the gate checks only the determinism ones above.
**A template book that violates these will pass the gate and still be wrong**, so the brief has to
carry them:

| constraint | what it means | why it is not caught |
|---|---|---|
| `transform_opacity_only` | animate `transform` and `opacity` only — no `filter`, `blur`, `box-shadow`, `width`/`height`, `top`/`left` | not scanned; a `filter: blur()` tween renders but costs 10× and can flicker under seek |
| `caption_keep_out_83pct` | keep content out of the bottom 17% of frame height — the caption band lives there | `layout_lint` reads composed geometry, but nothing maps a bespoke fragment's boxes to the band |
| `sid_prefixed_ids` | every `id` must start with the scene id (`s3-headline`, not `headline`) | not scanned; a collision silently animates the wrong element in another scene |
| `no_exit_on_non_final` | a non-final scene must NOT animate its content out — the CUT is the transition | not scanned; this is the exact defect that produced blank frames in the math work |
| `duration_preserving` | the block must fill its authored window, not decide its own length | narration owns duration everywhere in NOLAN |

`no_exit_on_non_final` is the one most likely to be violated by a design system, because a
standalone component naturally animates in *and out*. Inside an essay the next scene is the
transition, so an exit animation leaves the frame empty. That failure has already cost this repo
real render time (`skills/organ/math-animation.md`, "A block clears itself unless you say
otherwise").

## Timing contract

- Every timed element carries `class="clip"` plus `data-start` / `data-duration` /
  `data-track-index`.
- GSAP lines in `tl` use **frame-absolute** times, not scene-relative.
- Reveals land on the spoken word. Do not hardcode a stagger — NOLAN's scheduler places them.

## Theme contract

Read tokens, never literals. `var(--text)`, `var(--shell)`, `var(--surface)`, `var(--accent)`,
`var(--text-mute)`, `var(--font-display-en)`, `var(--font-body)`, `var(--r-card)`, `var(--rule-w)`.
A hex literal in a bespoke block is a bug: it will not follow the essay's theme, and NOLAN ships 41
themes.

## Card rendering, for the Design System pane

**NOLAN blocks paused at t=0 are mostly BLANK** — almost everything animates in from nothing.
Publishing them naively yields empty cards. Render each card at a meaningful seek time (or via the
existing still/snapshot path) before publishing.

## Status of the probe

`DesignSync.list_projects` works — one project, **Modernist**, owned. `list_files` returns
**HTTP 403 `permission_denied: "access gate closed"`**, so design-system scopes are not granted for
this session; `/design-login` or an approval prompt is needed before any read or write. Nothing was
pushed.
