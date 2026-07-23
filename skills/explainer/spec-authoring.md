---
id: explainer.spec-authoring
name: Explainer spec authoring
kind: craft
purpose: The per-beat agent contract — choose a library block or author a bespoke one, and write the spec.json.
status: deprecated
version: 1
handoffs:
  - { process: explainer, stage: author-spec, gate: A }
uses: [explainer.block-catalog]
evals: []
---

# Spec authoring — the agent contract (library OR bespoke, per beat)

The spec author (the skill's chapter agent) turns a chaptered script into a render
spec. For each beat it makes ONE decision: **use a library block, or author a
bespoke one.** This is the closed loop — no human picks blocks or frames.

Read `block-catalog.md` (blocks, props, anchors, relation→block guide, the Raw tier).

## Per-beat decision
1. **Library first.** If a cataloged block fits the beat's relation (list / profiles /
   contrast / before-after / statement) → use it: `{ "block": "<Name>", "anchors": [...],
   "props": {...} }`. Most beats (the recurring 80%) take this path.
2. **Bespoke for a signature beat.** If it's a cold-open / one-of-a-kind diagram / a
   number that should count as it's spoken — and no library block does it justice —
   **author bespoke** instead of forcing a fit. In the spec, name a new block and attach
   a brief:
   ```json
   { "block": "NpcStrike", "anchors": ["@start"],
     "bespoke": { "brief": "Big 'I never wanted to be an NPC.' — a strike-through draws
        across 'NPC' exactly when the word 'NPC' is spoken (use the `words` timeline);
        faint scrolling daily-loop terminal backdrop. Token-faithful, Surface-wrapped." },
     "props": {} }
   ```
   The brief must say **what the visual is** and **which word(s) to sync to** (so the
   builder uses the per-word `words` timeline). Reserve bespoke for **1–2 signature beats
   per chapter** (cost discipline) — prefer library.
3. **Redraw vs lift, for a figure from a source (paper/report).** Ask: *"could I
   regenerate this exactly from symbols/numbers I have?"*
   - **Yes → redraw** (on-theme, animatable): a formula → `Formula`; a table → `DataTable`;
     a few quantities → `BarChart`; a simple box-and-arrow schematic → a bespoke diagram.
   - **No → lift** with **`PaperFigure`**: the figure is an *empirical artifact* (attention
     heatmap, plot of real data, sample output, photo) — redrawing it would **fabricate
     data**. Prep the asset with `extract_figure.py`, then point `PaperFigure` at it and add
     `highlights` (word + fractional region) so an accent box walks the figure as the
     narration names each part. Always set `source` (cite it). Don't lift what you can
     honestly redraw — redraw is cleaner and on-theme.

## Orchestration (what runs the spec)
1. Spec author → emits the spec (library steps + bespoke steps with briefs).
2. For each step with a `bespoke` brief → spawn a block-author agent that writes
   `src/blocks/raw/<Name>.tsx` per the brief + the Raw-tier contract (receives
   `revealFrames`, the per-word `words` timeline, `durationInFrames`; token-faithful;
   `<Surface>`-wrapped; no `<Audio>`), and registers it in `raw/index.ts`.
3. `gen_spec.py <spec> <job>` (resolves anchors + emits the `words` timeline).
4. Render via NOLAN Remotion.

(This is exactly the flow run by hand in test run 7 — now the spec author makes the
library-vs-bespoke call and writes the brief, instead of only flagging `_needsBlock`.)

## Promotion
A bespoke block that recurs graduates: move `raw/<Name>.tsx` → `library/`, generalize
its content into props, add a `BLOCK_CATALOG` entry. Now the spec author can *select* it.
