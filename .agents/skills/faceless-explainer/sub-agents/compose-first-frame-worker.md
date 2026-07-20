# Compose-first frame worker — faceless-explainer Step 5 (NOLAN composer path)

> You build **one** frame's composition HTML, with the **same input/output contract** as
> `frame-worker.md` — but you **prefer the NOLAN composer templates** and hand-author only
> what no template covers. **Read `frame-worker.md` first**: the shared contract (inputs, the
> "you do NOT decide" list, the frame constraints, and the self-check codes) all apply
> unchanged. This file states only the compose-first delta.

**INPUT** — everything `frame-worker.md` lists, plus:

- `BRIDGE_DIR` — absolute path to the NOLAN composer: `compose.py`, `author.py`,
  `catalog.json`, `AUTHOR_PROMPT.md`, `vendor/`.

**OUTPUT** — `compositions/frames/<frame_id>.html`, **produced by running the composer**, not
hand-written. It is the same artifact the stock worker emits (`<template>`-wrapped `#root`
carrying `data-composition-id="<frame_id>"`, one paused `window.__timelines["<frame_id>"]`) —
so the assembler, captions, transitions, and lint all treat it identically. You do not edit
`STORYBOARD.md`, mint audio, assemble, or run the renderer.

## Procedure

1. **Read** `BRIDGE_DIR/catalog.json` (the template menu + data schemas) and
   `BRIDGE_DIR/AUTHOR_PROMPT.md`, then your `## Frame N` block and `frame.md` (design truth).
2. **Map each Scene** in your time-coded shot sequence to a composer scene, preferring a
   template (`catalog.json` → `when_to_use`):
   - a number / rate / share → `stat`;  a place (state / country / "where") → `geo`;
     a words-carried claim or turn → `statement`;  an object-as-evidence → attach a
     `prop_cutout` via `data.props`;  a full-bleed ground (image dimmed+Ken-Burns / paper /
     transparent over a root video) → `data.ground`.
   - **No template fits** (a drawn line/bar chart, a custom multi-column layout, a blueprint
     signature move no template realizes) → a **`raw`** scene: hand-author its `html` +
     `tl` per the `raw` constraints in `catalog.json` (ids prefixed with the scene id,
     `class="clip"` + `data-start/duration/track-index` on every timed element, transform /
     opacity only, **no exit tween** unless you are the final frame, all content above the
     **83% caption keep-out**).
   - **Choose each templated Scene's layout `variant`.** A variant-capable block (`stat`,
     `statement`, `bullet_list`, `pull_quote`, `ledger`, `comparison_table`, `timeline`,
     `comparison`) offers arrangements *within* the theme's macro-layout. Set `data.variant`
     to the one the beat's meaning calls for — pick from the **composition-dialect brief in
     the kickoff** (`.hf_kickoff.md`), which lists the variants THIS theme sanctions with
     when-to-use. Omit it to let `author.py`/`compose.py` auto-pick (theme-constrained +
     anti-repeat) — safe but generic; setting it is how the layout says something.
   - Keep each Scene's window (`start`/`dur`) from the shot sequence; the frame `dur` is your
     block's `duration` (already synced to real voice — never change it).
   - **Do NOT set `captionBar`** on any scene — the root caption track owns the bottom band.
   - **Colours + fonts are the theme's job, applied automatically** — `author.py` injects the
     project theme's tokens on every compose (from `hyperframes.json`), so template scenes
     inherit them; do NOT hand-set palette on templated scenes. `frame.md` is the design-intent
     reference (which face carries a beat, the mood); only a `raw` scene needs explicit tokens,
     and it should reference the theme vars (`var(--accent)` / `var(--shell)` / `var(--font-display-en)`),
     not literal hexes, so it stays theme-true across a recompose.
3. **Write the per-frame spec** to `compositions/frames/<frame_id>.spec.json`:
   `{"frames":[{"id":"<frame_id>","dur":<duration>,"scenes":[ … ]}]}`.
4. **If any scene is `geo`**, make the geometry libs available: copy `BRIDGE_DIR/vendor/*`
   into `PROJECT_DIR/vendor/` (idempotent — skip if already there).
5. **Gate + build** — run the composer through its validating gate:
   `python3 <BRIDGE_DIR>/author.py --spec compositions/frames/<frame_id>.spec.json --out-dir compositions/frames`
   It validates the spec against the catalog and, on success, writes
   `compositions/frames/<frame_id>.html`. **If it exits non-zero, the spec was rejected —
   read the `✗` lines, fix the spec, and re-run** (do not hand-edit the generated HTML).
6. **Self-check** the generated HTML against `frame-worker.md`'s checklist (template
   transport, `#root` styling, clip attrs, no exit on a non-final frame, keep-out). The
   composer satisfies these by construction; verify your `raw` scenes do too. Writing the
   file is your terminal action.

## Notes

- The composer already guarantees the load-bearing frame rules: full-bleed grounds on
  `class="clip"` layers (never `#root`), `#root`-selector styling, transform-only + seek-safe
  motion, and exactly one merged paused timeline per frame.
- **Blueprints are shot-shape guides.** When a template's motion already realizes the frame's
  `blueprint:` signature move, use the template; when it doesn't, that Scene is `raw` and you
  reproduce the blueprint's move by hand.
- **Whole-frame bespoke** (no scene maps to any template) is allowed — emit an all-`raw`
  spec — but prefer per-scene `raw` so the templatable scenes in the frame still get the
  speed + consistency. If a frame is genuinely all-bespoke, deferring to the stock
  `frame-worker.md` is also valid.
