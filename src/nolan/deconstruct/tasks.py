"""Synthesis brief for the deconstruction agent.

Mirrors ``video_style.tasks`` / ``scriptwriter.tasks``: a self-contained
markdown brief a dispatched Claude agent reads and executes. The API layer
(extract.py) has already computed all facts and classifications; the agent's
job is the interpretive write-up (breakdown.md) and refining the draft
recovered plan — grounded in the extract, never contradicting measured facts.
"""

from __future__ import annotations


def deconstruction_synthesis_task(slug: str, title: str, video_path: str) -> str:
    base = f"video_deconstructions/{slug}"
    return f"""# NOLAN video deconstruction synthesis: "{title}"

The measurement passes are done. Your job is the **editorial write-up**: turn the
extract into a breakdown a video producer can learn from, and refine the draft
recovered plan so it reads as a replayable recipe.

## Inputs
- **Extract (facts + classifications):** `{base}/extract.json`
  — per-shot facts (camera/subject motion, treatment hints, asset types,
  on-screen text, identity hints), editorial beats, pairing operators with
  confidence, recovered tempo (energy / pace_dir / transition / motion_speed).
- **Evidence frames:** `{base}/frames/beat_NN.jpg` — one per beat. LOOK at them.
- **Draft plan:** `{base}/recovered_plan.json` — deterministic draft in
  scene_plan schema.
- Source video (only if you need to check something specific): `{video_path}`

## What to write

### 1. `{base}/breakdown.md` — the editorial breakdown
- **Overview** — one paragraph: what this video is, its editorial signature.
- **Beat sheet** — one section per beat, in order. For each:
  `## Beat N — <title> [m:ss–m:ss] · <function>` then:
  - *Says:* the narration's job in this beat (quote a key line).
  - *Shows:* the assets used (types, named works from identity hints,
    what the evidence frame confirms).
  - *Pairing:* the operator + WHY (from extract; refine the rationale with
    what you see in the frame — you may override a low-confidence call, but
    say you did and why).
  - *Rhythm & motion:* cuts/min, energy, the dominant treatment — one line on
    how the rhythm serves the beat.
- **Asset inventory** — table of identified/notable assets: what it is,
  where it appears, how to source or regenerate it. For assets a forward
  build would GENERATE, write a ready **ComfyUI prompt** (subject, medium,
  style, palette, composition, era — one line, comma-separated).
- **Editorial patterns** — 3–6 recurring techniques worth stealing, each tied
  to beats as evidence.
- **Replay notes** — what the recovered plan can/can't reproduce, and any
  fact the measurements likely got wrong (say why).

### 2. Refine `{base}/recovered_plan.json` (edit in place, keep the schema)
- Improve `visual_description` on scenes where frames/identity hints tell you
  more than the draft says.
- For scenes whose asset a forward build would generate, fill `comfyui_prompt`.
- Fix obviously wrong `visual_type` calls. Do NOT invent scenes, retime
  anything, or change `narration_excerpt`.

## Rules
- Ground every claim in the extract or a frame you actually opened; cite beat
  indices. Never contradict a measured fact (timings, cut counts, motion) —
  interpret it.
- Asset identities carry an `identity_source`: `narration-confirmed` /
  `narration-named` may be stated as fact (the narration names them);
  `vision-claim` is UNVERIFIED — where you have web access, verify
  vision-claims with a quick search before asserting them, else keep the
  "likely / unverified" framing. Never upgrade a claim without evidence.
- Operator vocabulary is fixed (literal / knowledge / tonal / conceptual /
  ironic / trait / relational / scale / text-graphic / unclear) — no new labels.
- Keep it specific and example-driven; a producer should be able to apply the
  patterns to a new video tomorrow.
"""
