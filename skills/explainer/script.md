---
id: explainer.script
name: Explainer script authoring
kind: craft
purpose: Author the narration from a source paper — 7 stages (extract → arc → draft → tighten → verify → gate → score).
status: active
version: 1
handoffs:
  - { process: explainer, stage: author-script, gate: A }
uses: [explainer.scene-grammar, common.script-style]
evals: [paper-quiz]
---

# Script skill — source (paper/article) → video transcript

A structured, multi-stage process for writing the NARRATION (the `segments.json`) — the
weakest link once the visual library got strong. Replaces the old single-shot agent pass.
Mirrors the publishing skill's discipline, but for *spoken video* narration, where the script
must be written FOR the visual and FOR the ear, not as prose we anchor afterward.

## The one rule that matters most: front-load the visual keyword
Each beat's block reveals a payload on a specific spoken word (a number, a name, a term — the
`anchor`). **That word must land in the FIRST sentence of the beat**, so the visual fires
early and the stage is never dead. The black-screen bug came from a StatCount beat whose
number ("thousand") was spoken 15s into a 23s beat — 15s of empty stage. Write the payload
first, the explanation second. (Skeleton-rendering blocks soften this, but the script is the
real fix.)

## Stages
1. **EXTRACT** — from the source, pull: the core thesis (one sentence), the 5–10 key
   claims/numbers (each with the source line for VERIFY), the must-show figures (which are
   empirical → lift, which are synthetic → redraw), and the single most surprising hook.
2. **ARC** — structure into the scene taxonomy (`Hook → Problem → Key idea → Method →
   Results → Payoff → Close`; see scene-grammar.md). **One insight per beat.** 6–12 beats.
   Assign each beat a block (apply the redraw-vs-lift rule) and its anchor word(s).
3. **DRAFT** — write each beat's narration, 2–4 spoken sentences. **Front-load the anchor**
   (rule above). Conversational, concrete, active voice. Numbers as spoken words ("two
   thousand four", "one point nine five").
4. **TIGHTEN** — cut preamble and filler; vary sentence length (a short punch after a long
   build); read it aloud in your head for rhythm. Target **130–165 WPM**.
5. **VERIFY** — every claim/number checked against the source line. **No fabrication** — if
   it's not in the paper, cut it or caption it as illustrative.
6. **GATE** — emit the spec, run `gen_spec.py`, then `python web-video-lab/pacing_lint.py
   <job>.json`. **It must pass with zero FAILs** (no late-payload/empty-stage beats, WPM in
   band). Revise any failing beat (usually: move the anchor word earlier) and re-check.
7. **SCORE** — rate 1–5 on: **accuracy** (vs source), **hook** (does the open grab?),
   **pace** (linter green + reads well), **visual-sync** (anchor front-loaded every beat?),
   **density** (one idea/beat?), **voice** (distinctive, not generic-explainer). Iterate the
   weakest dimension.

## Why this is enforceable (not vibes)
We have exact word timestamps + reveal frames, so stages 6–7 are *measured*: the pacing
linter is the gate, and "front-loaded anchor" is literally `first-reveal < 3s` per beat. A
script that passes the linter cannot ship the black-screen class of bug.

## Integration
The chapter agent runs these stages instead of a single pass; the linter is wired as a
mandatory gate before render. Output is still `segments.json` + `spec.json` — same contract,
higher quality.
