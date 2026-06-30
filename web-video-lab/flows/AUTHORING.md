# Flow authoring & craft — the skill layer (read before planning or editing a flow video)

The deterministic engine (`src/nolan/flows/`) renders; **this is where the judgment lives** —
how to plan a video, write its script, choose/invent its motions, and avoid the "AI look." It is
ported from the `web-video-presentation` skill (`web-video-lab/skill/`); the **methodology
transfers, only the old web-page scaffolding (Vite/React `narrations.ts`) is superseded** by the
flow's block + `flow.spec.json` model. Read the linked skill references for depth — this doc maps
them to the flow form and is the agent's contract at the plan / edit / invent hand-offs.

## The plan/authoring checkpoint (Gate A) — the most flexible layer
The skill's `[Checkpoint Plan]` ("align 5 things: script / outline / theme / assets / dev-mode")
maps to the flow's **authoring mode / semi-auto** (`flows/authoring.py`). At this checkpoint the
agent drafts a per-beat **plan**, the human tweaks it, and only then does it render. Plan ≠ visual
design:
- **`outline`/plan plans RHYTHM + INFO-DENSITY + which motion (from the palette) + the asset
  wishlist** — NOT the final animation. (skill: `OUTLINE-FORMAT.md`)
- **Dual-source** (`OUTLINE-FORMAT` / `CHAPTER-CRAFT` principle 10): **`script` decides the BEATS**
  (split by `---`, 1–2 reveals each, timed by the word-aligned VO); **the source article decides
  VISUAL INFO-DENSITY** (the info pool — numbers, quotes, cases — to draw per beat).

## The craft bottom line — "this is video, not PPT" (`CHAPTER-CRAFT.md`)
Every beat must **demonstrate**, not text-dump:
- **Each beat shows something *move/animate*** — a diagram, a reveal, a camera move. *A beat that
  is only text fails review.* (This is why "invent a motion if needed" exists.)
- **Reveal progressively** — don't dump all elements at once; key elements advance with the VO.
- **No header/footer chrome; a clear hero element; comfortable color/type/rhythm.**
- **On-screen language = the source's language** (declared in the spec/plan; don't drift).

## Script style (`SCRIPT-STYLE.md`) — when the flow *generates* the script (explainer)
For the byo-everything art flow the script is the user's; for generate-from-source (explainer)
the three bottom lines hold: **(1) info-retention ≥ 60%** (rephrase, don't summarize — keep
facts/data/argument-chains), **(2) de-AI voice** (no fake empathy/depth/self-promotion/templated
parallelism — "spoken AI-feel is worse than written"), **(3) keep the source language**.

## Motion selection & invention (ties to `FLOW_EDIT.md`)
1. **Reach for the flow's palette first** (the blessed motions) + the shared/common set.
2. **Reuse before building** — check the full `_lab_chapter` library AND `remotion-lib/` and PORT;
   never rebuild an existing block (see `FLOW_EDIT.md`).
3. **Invent (RAW) only when nothing fits** — then design it per the craft bottom line above; a
   bespoke one-off lives in `blocks/raw/` (allowed, flagged). This is the escape hatch that keeps
   the system open-ended.
4. **Minimum edit** — change only the beat asked for; leave neighbors untouched (the chapter-block
   re-render makes one beat independently re-renderable).

## The hand-off principle
The engine runs the mechanical path deterministically (ingest → gate → render → deliver), but
**at the plan checkpoint and at edit/invent it hands to an agent reading this doc + `FLOW_EDIT.md`.**
That is how the flow keeps both determinism *and* the freedom to do something new.

## Canonical skill references (depth)
`web-video-lab/skill/SKILL.md` (workflow + checkpoints) · `references/CHAPTER-CRAFT.md` (motion
craft) · `references/SCRIPT-STYLE.md` (de-AI script) · `references/OUTLINE-FORMAT.md` (plan format)
· `references/THEMES.md` + `THEME-GAP-ANALYSIS.md` (theme) · `references/AUDIO.md` · `RECORDING.md`
· `references/EXAMPLES/` (worked beats). These remain the source of truth for the methodology;
this doc is the flow-form bridge to them.
