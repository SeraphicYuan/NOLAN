---
id: lab.deconstruct
name: Video deconstruction (inverse Director)
description: >
  The inverse Director — given an ingested library video, RECOVER its editorial plan: beats, the
  script↔asset pairing rationale (in the evocative-b-roll operator vocabulary), the tempo curve
  (tempo_plan energy/transition/motion_speed terms), and the motion applied to assets (motion
  registry treatment vocabulary), assembled into a draft `recovered_plan.json` in the SAME
  scene_plan schema the forward pipeline consumes. A LAB (feeds artifacts via handoff, never writes
  pipeline artifacts directly). Read before touching deconstruction, the /deconstruct page, or
  recovering a plan/visual-facts from a reference video.
kind: methodology
purpose: >
  Orient any deconstruction task — what it recovers (beats/pairing/tempo/motion), the shared
  vocabularies it recovers INTO, and the recovered_plan.json handoff into the forward pipeline.
status: active
version: 1
tier: lab
handoffs: []
uses:
  - common.pairing-craft
  - common.motion-craft
documents:
  module: src/nolan/deconstruct/__init__.py
loaded_by: []
evals: []
---

# Video deconstruction — the inverse Director (`src/nolan/deconstruct/`)

Given an ingested library video, recover its editorial plan and express it in the SAME
vocabularies the forward pipeline authors in — so a reference video becomes a studyable,
reusable draft plan. Output: `recovered_plan.json` in the `scene_plan` schema. Surface:
the `/deconstruct` page.

## What it recovers (into shared vocabularies)

- **beats** — the segmentation + what each beat is doing.
- **pairing rationale** — why each asset illustrates its line, in the evocative-b-roll OPERATOR
  vocabulary (`[[common.pairing-craft]]`) — literal / knowledge / tonal / conceptual / …
- **tempo curve** — in `tempo_plan`'s energy / transition / motion_speed terms.
- **motion** — the treatment applied to each asset, in the motion registry vocabulary
  (`[[common.motion-craft]]`).
- **visual_facts** — a shots table (what is actually on screen), the evidence layer.

## Invariants

- **A LAB, not a spine step.** It FEEDS artifacts through an explicit handoff (the recovered plan
  is a *draft* a human promotes), and never writes canonical pipeline artifacts directly.
- **Recover INTO the shared vocabularies**, not ad-hoc labels — so a recovered plan is directly
  comparable to (and editable like) an authored one. If a recovered term isn't in the registry,
  that's a gap to close in the registry, not a new private vocabulary.

Mirrors the two style flows in its layering; validated on the Odyssey deconstruction. See
`[[project_video_deconstruction]]`. The forward pipeline it inverts is `[[pipeline.hyperframes]]`.
