---
id: organ.sync
harness: nolan-sync
name: Word-level narration → scene sync
description: >
  How each scene lands on the spoken word. `sync-durations` pins only the 7 FRAME boundaries;
  inside a frame the cuts were author-typed open-loop, so visuals drift ahead of narration (5–25s
  measured). This organ closes that seam: align_voices (whisper aligner → per-word times in
  audio_meta.voices[].words, cached by wav mtime) + place_scenes (each scene's start/dur set to the
  moment its ANCHOR phrase is spoken, monotonic-clamped, per-frame proportional fallback) + the
  scene-timing GATE (a visual that trails narration ≥6s or is mis-ordered HARD-blocks the render).
  Read before touching word-sync, anchors, the aligner, or the timing gate — or when a scene is late.
kind: grammar
purpose: >
  Orient any narration↔scene timing task — the align→place pipeline, anchor semantics, the
  monotonic clamp + per-frame fallback, and the scene-timing HARD gate.
status: active
version: 1
tier: organ
handoffs:
  - { process: hyperframes, stage: word-sync, gate: B }
uses:
  - organ.voice
documents:
  module: src/nolan/hyperframes/sync.py
loaded_by: []
evals: []
---

# Word-level narration → scene sync (`src/nolan/hyperframes/sync.py`)

The `word-sync` step of the HF finish DAG. `audio.mjs sync-durations` pins only the 7 frame
boundaries; inside a frame the scene cuts were author-typed open-loop (audio_meta.words was empty),
so visuals drift ahead of narration. This closes that seam. Run: `python -X utf8 -m
nolan.hyperframes.sync <comp> [--report]`.

## The pipeline

1. **`align_voices`** — run the whisper aligner over each `assets/voice/0N.wav`, write per-word
   times into `audio_meta.voices[].words` (**SECTION-relative**). **Cached by wav mtime** (re-runs
   are cheap; a changed wav re-aligns).
2. **`place_scenes`** — set each `scene.start`/`dur` to the moment its **ANCHOR** (the distinctive
   SPOKEN phrase it illustrates) is said. Absent an anchor, fall back to the scene's visible text.
   **Monotonic-clamped**; if a frame's anchors don't resolve in order, warn + fall back to
   proportional spacing **for that frame only** (never silently).

## Inside a scene: the THREE cue surfaces

Placing a scene is only half of sync. What the scene REVEALS has to track the voice too, and a block
can only be pinned where its data has somewhere to write the answer. There are three surfaces, all
resolved during `word-sync`, all ABSOLUTE times bounded to the scene's own window, all idempotent:

| surface | written on | resolved by | read by |
|---|---|---|---|
| `_cue` | each ELEMENT of a list-of-dicts (chart series, stat items, table rows) | `_retime_reveals` | `_reveal_cues(items, start)` → `_reveal_times(...)` |
| `_line_cues` | `data.lines` (and a side panel's list-valued `title`) | `_retime_lines` | the block's per-line tween |
| `_field_cues` | a whole PROSE FIELD — `quote`, `title`, `caption`, … (`sync.PROSE_FIELDS`) | `_retime_prose` | `compose._prose_cue(d, field, start)` |

Two-sided blocks (`comparison`, `juxtaposition`, `split_view`) keep their prose one level down, so
`_retime_panels` runs the line and field layers again inside `left` / `right` / `paper`.

**`PROSE_FIELDS` is a field → HOLD-FRACTION map, not a list.** A quote is the beat's payload and may
wait as long as the narration takes to reach it; a *title* is the frame's anchor, and parking it 6s in
trades a lead for a hole — so a title is only nudged (0.35 of the beat), and past that bound it opens
on the beat as before. `kicker` is deliberately absent: it is design copy, not narration.

**Adding a block?** It must READ one of those three surfaces.
`tests/test_reveal_sync_contract.py` composes every block twice — once plain, once with cues injected —
and fails if the timeline does not move. A deliberate cadence (a dialogue beat, a continuous wipe) goes
in `DELIBERATE_CADENCE` with a justification, never in silence. The older
`bridge/check_reveal_sync.py` guards the neighbouring rule (no hardcoded `start + LEAD + i*STEP`); it is
syntactic, so it cannot see a block that reveals everything at one fixed offset — which is exactly how
`pull_quote` shipped a 13-word quote ~3.7s ahead of its narration while passing that check.

## The scene-timing GATE (why it HARD-blocks)

`sync_gate_report()` finds scenes whose VISUAL trails the narration — the drift the eye plainly
catches. `place_scenes` fixes what it can first; a surviving **≥6s lag** (`_HARD_LAG_S`) or a
**mis-ordered** scene is something placement could NOT resolve → it HARD-BLOCKS the render (the
finish DAG raises). Fix one of: re-anchor the scene to the phrase where its topic **OPENS**, reorder
the scenes in the spec, or split the overrunning previous scene. Knowing exception: `HF_ALLOW_LAG=1`.

## Authoring rules that make sync robust

- **Anchor to an EARLY, EXACT spoken phrase** — a late/closing anchor makes placement auto-correct
  but is fragile; a non-numeric anchor on a number-heavy line misses. (`sync --report` flags both.)
- **Number-aware matching**: 'nine hundred million' ≡ '900 million' when resolving anchors.

Part of `[[pipeline.hyperframes]]` (the `word-sync` DAG step); depends on the VO wavs the
`[[organ.voice]]` organ writes. Number-provenance + reveal-sync are adjacent gates in the same step.
