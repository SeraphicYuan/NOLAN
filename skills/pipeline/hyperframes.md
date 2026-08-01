---
id: pipeline.hyperframes
name: NOLAN HyperFrames pipeline (compose-first)
description: >
  The DOMINANT NOLAN video-essay pipeline: compose-first HyperFrames authoring →
  the `nolan hf-finish` DAG (VO-owns-duration timing, word-sync, dataset/document
  binding, timing + number-provenance gates, sound, assemble, render, QA gates) →
  incremental `hf-render` and the /hyperframes edit loop. Read this before touching
  ANY compose-first HF work (author.py, compose, blocks, sfx, finish, sync, edit) or
  running/​debugging `nolan hf-finish` / `nolan hf-render`. This SUPERSEDES the legacy
  Director/explainer/art flow for making essays. Points into the code + the umbrella
  craft skills; it does not duplicate them.
kind: methodology
purpose: >
  Orient + route any compose-first HyperFrames pipeline task — the stage map, the
  finish DAG (each step + its gate), the load-bearing invariants, and the gotchas
  that repeatedly cost renders.
status: active
version: 1
tier: primary
handoffs:
  - { process: hyperframes, stage: finish, gate: B }
uses:
  - common.motion-craft
  - common.composition-craft
  - common.sound-craft
  - common.pairing-craft
overrides:
  - explainer.flow
  - art.flow
documents:
  dag: src/nolan/hyperframes/finish.py
loaded_by: []
evals: []
---

# NOLAN HyperFrames pipeline — the compose-first spine

This is the **dominant** way NOLAN makes a video essay. It **replaces** the legacy
Director/`explainer`/`art` flow (`orchestrator/director.py`, `flows/`) for essay
production — those skills remain for legacy projects only.

A source (essay / paper / topic) becomes a **HyperFrames composition** (HTML that
renders to video): `author → compose/blocks → assets & pairing → sfx → voice →
hf-finish → render → edit-loop`. The composition is the artifact the human edits;
every stage reads and rewrites it in place.

**Renderer: HyperFrames, NOT Remotion.** HF renders the composition's HTML in a headless
browser (single paused, seek-safe timeline) with animation via **GSAP** (the default adapter;
also Lottie / Three.js / Anime / CSS / WAAPI). The finish DAG's `render` step is `npx
hyperframes render` (run via `cmd.exe`), and `nolan hf-render` does incremental re-renders.
Remotion is the LEGACY Director/FLOW renderer only (`[[organ.render]]`, `[[organ.layout-blocks]]`) —
do not reach for it on the HF path.

**This file orients; the rules live elsewhere.** Environment + invariants: `CLAUDE.md`.
Motion/composition/sound/pairing *craft*: the umbrella skills in `uses:` above.
Per-run lessons: memory (`MEMORY.md`, the `HF cold-author` + `HF *` trail).

## The load-bearing invariants (violate these and it breaks)

- **Narration owns duration.** Per-section VO wavs are THE beat anchors; the video is
  timed to the narration, never the reverse. The finish DAG derives frame durations
  FROM the VO (`sync-durations`) and places each scene on its spoken word (`word-sync`).
- **scene_plan / composition is lossless.** Unknown keys survive every round-trip.
  Never strip what you don't recognize.
- **Failures are loud.** `hf-finish` is one idempotent driver that fails LOUD on the
  first broken step (non-zero exit, error surfaced) and is safe to re-run. No silent caps.
- **Gates block, they don't warn-and-ship.** The scene-timing gate (≥6s visual lag or a
  mis-ordered scene) and the number-provenance gate (a data block whose numbers trace to
  nothing) HARD-BLOCK the render. So does the STYLE gate, which runs pre-render on the
  specs (~1s) so a contract miss costs a second, not a 20-minute render — the `revise` half
  of draft -> lint -> revise only happens if something refuses to ship. Escapes are explicit
  env vars (`HF_ALLOW_LAG=1`, `HF_ALLOW_UNSOURCED=1`, `HF_ALLOW_STYLE=1`) for a knowing
  exception only.
- **A gate must be feedable.** The dials that brief the author (`asset_density`, `video_share`,
  `block_variety`) persist to `hyperframes.json` and drive BOTH the gate and the asset-need
  derivation — a `heavy` essay derives video needs so the pool can supply the footage the gate
  demands. A gate the pipeline cannot feed is worse than no gate.

## Where the code lives

| Concern | Path | Entry |
|---|---|---|
| Finish DAG (the driver) | `src/nolan/hyperframes/finish.py` | `nolan hf-finish <comp>` |
| Word-sync / timing gate | `src/nolan/hyperframes/sync.py` | `python -m nolan.hyperframes.sync <comp> [--report]` |
| Incremental render | `src/nolan/hyperframes/incremental.py` | `nolan hf-render <comp> [--only ...]` |
| Edit loop (review→edit→re-render) | `src/nolan/hyperframes/edit.py` | `/hyperframes` hub page |
| Compose / blocks | `src/nolan/composition.py`, `compose*.py`, `layout_blocks.py` | authored `block` fields |
| SFX (design + ducked mix) | `hyperframes/sfx_design.py`, `sound.py`, `sfx_mix.py` | finish `sfx` step |
| Dataset / document binding | `hyperframes/datasets.py`, `documents.py` | finish `datasets`/`documents` steps |
| Math (Manim) binding | `hyperframes/math_source.py` → `nolan/mathanim/` | finish `math` step; `[[organ.math-animation]]` |
| Bespoke raw scene | `hyperframes/bespoke.py` | `/hyperframes` 🎨 Bespoke |

## The finish DAG — `nolan hf-finish`

One idempotent driver runs these steps IN ORDER and fails LOUD on the first break.
`--dry-run` prints the DAG without running it; `--no-render` / `--no-sound` stop early.
Each row is a real step in `finish.py`; **this table is honesty-tested against the
driver** (`tests/test_organ_skills.py`) — a step added to the DAG that isn't documented
here fails CI.

| step | what it does | gate? |
|---|---|---|
| `sync-durations` | derive frame durations FROM the VO (narration owns duration) | soft |
| `word-sync` | force-align the VO; place each scene + fire its highlight on the spoken word | — |
| *(datasets)* | materialize dataset-bound data scenes from their tables (real numbers + `value_source`) before recompose | raises on failure |
| *(documents)* | resolve document/split_view scenes to page source + region rects before recompose | raises on failure |
| *(math)* | compile every `math` scene's typed template + formula ledger into a Manim clip (essay's theme, exact narration window) and mount it as that scene's video ground | raises on failure |
| *(math-provenance gate)* | HARD-BLOCK a math scene whose displayed formula traces to nothing, or whose LaTeX is invalid — the whole set is checked before ANY of them renders (`HF_ALLOW_UNVERIFIED_MATH=1` escapes) | HARD |
| *(scene-timing gate)* | HARD-BLOCK a ≥6s visual lag or a mis-ordered scene (`HF_ALLOW_LAG=1` escapes) | HARD |
| *(number-provenance gate)* | HARD-BLOCK a data block whose numbers trace to nothing (`HF_ALLOW_UNSOURCED=1` escapes) | HARD |
| *(auto-ground)* | fill long ungrounded holds (>5s, `autoground.py`) with a relevant pool asset (image/video); leaves clean when nothing fits — never forces | soft |
| `bgm` | fetch background music from the storyboard | soft |
| `sfx` | design + fetch SFX cues (subtractive, sectional bed) | soft |
| `captions` | build the caption track from the storyboard | — |
| `assemble-index` | assemble the composition index.html from the storyboard | — |
| `assemble-media` | resolve + stage the composition's media | — |
| `layout` | layout-lint pass (caption keep-out, overlap, bounds) | soft |
| *(style gate)* | HARD-BLOCK the render while any style-contract GATE fails — scored against the essay's own `style_dials` from `hyperframes.json` (`HF_ALLOW_STYLE=1` escapes) | HARD |
| `render` | render the composition to video (`npx hyperframes render`) | — |
| `hf-qa` | freeze + audio QA (ffmpeg): frozen/silent detection | soft |
| `style-lint` | spec-dimension style contract report, same dials as the pre-render gate | soft |
| `temporal` | motion gate: frozen / static / dead-air | soft |
| `perceptual` | VLM render gate: legibility + relevance | soft |

Steps 0 (`STORYBOARD.md` guarantee) and the two binding steps run inline; the rest are
`_run(...)` sub-processes. `soft` steps warn and continue; the two HARD gates and the
un-marked steps abort the run.

## How to use this skill (routing)

- **Starting a NEW essay from text** → the **`hf-author`** skill (formerly `faceless-explainer`) orchestrates authoring
  (`hyperframes init` → pick a frame preset → write `STORYBOARD.md`/`SCRIPT.md` → `audio.mjs` for
  the VO); the scaffold entry is `hfedit.new_essay(name, script, theme=…)` in
  `src/nolan/hyperframes/edit.py`. There is NO `nolan new-essay` CLI. Then `nolan hf-finish`.
- **Running / debugging a finish** → start here, then read `finish.py` for the failing
  step; the error message names the fix. Re-run `nolan hf-finish <comp>` (idempotent).
- **A scene is late / mis-timed** → `python -m nolan.hyperframes.sync <comp> --report`,
  re-anchor the scene to the phrase where its topic OPENS, or reorder the spec.
- **Designing motion / layout / sound / b-roll for a scene** → load the matching umbrella
  craft skill (`common.motion-craft`, `common.composition-craft`, `common.sound-craft`,
  `common.pairing-craft`) — this skill routes, those carry the vocabulary.
- **Editing one rendered scene from a human note** → `nolan-scene-edit` (the /scenes agent
  path) or the `/hyperframes` edit loop; agent edits are PROPOSALS that pass a gate before
  becoming canonical.
- **A cheap re-render of a few scenes** → `nolan hf-render <comp> --only <frames>`
  (incremental; inherits bgm/sfx/theme from the last `hf-finish` assembly).

## Verify BEFORE you render (the ~1 min loop that pays for itself)

A render is ~20-25 min. Almost every defect worth catching is visible without one, so do this after
authoring and after ANY spec edit — it is how the diamond-v2 branded-hero and inverted-comparison
defects were found:

```bash
# 1. assemble + every pre-render gate, no render spend (~1 min)
python -X utf8 -m nolan.hyperframes.finish <comp> --no-render
#    runs: sync -> word-sync -> datasets/documents -> timing + number gates -> auto-ground ->
#    recompose -> sound -> captions -> assemble-index -> assemble-media -> layout -> STYLE GATE

# 2. LOOK at every clip you placed — the menu's caption is a claim, the pixels are the fact
ffmpeg -ss 1 -i <clip> -frames:v 1 -vf scale=480:-1 /tmp/f.jpg      # then read the sheet
```

What only the eye catches: a clip that is someone else's branded upload, a comparison whose sides are
swapped, footage that is on-topic but shows the wrong thing. The VLM provenance gate now flags chrome
and unverified captions in `asset-descriptions.md` (`[UNVERIFIED ORIGIN]`, `[caption unverified]`) —
treat those tags as "open this file", not as decoration.

Render mode is `auto`: `whole` on a cold comp (the canonical baseline), `incremental` once a build +
clip cache exist. Incremental also emits `compositions/frames/*.clip.mp4`, which is what `/hyperframes`
serves per frame — so the edit loop gets its cache for free. Force either with `--render whole|incremental`.

## Gotchas (these cost renders)

- Run `finish --no-sound` when iterating: the bgm step can wipe `voices[]`. (The DAG now
  raises if the sound step drops narration, but know the failure mode.)
- Render via `cmd.exe npx hyperframes render`, not a bare WSL `npx` (esbuild is win32).
- Anchor scenes to EARLY, EXACT spoken phrases; non-numeric/late anchors miss.
- Windows paths: `nolan hf-finish` runs the Windows python; use `D:/…` paths, `-X utf8`.
