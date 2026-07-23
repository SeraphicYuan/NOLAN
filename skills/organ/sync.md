---
id: organ.sync
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
