# Flow-edit contract — for an agent reworking a beat of a flow video

You were dispatched to edit one beat of a **flow** video (art, …). A flow project is NOT a
segment/orchestrator project — these rules override the generic `nolan-scene-edit` skill.

## The 7 rules

1. **Edit the source of truth: `projects/<slug>/flow.spec.json`.** The Scene page shows
   `scene_plan.json`, but that is a **generated view** rebuilt from the spec — edits to it are
   lost. Make your change in `flow.spec.json` (the `beats[]` entry for your beat), then it
   re-ingests + re-renders.

2. **Choose blocks from the flow's PALETTE** (the blessed motions). See the flow's `palette` in
   `web-video-lab/flows/registry.json`, or run `python web-video-lab/art_validate.py
   --show-palette <flow>`. Out-of-palette blocks warn at the gate.

3. **REUSE before you rebuild — never rebuild a block that already exists.** Before authoring a
   new block, check, in order:
   (a) the flow palette; (b) the full library `render-service/_lab_chapter/src/blocks/library/`
   (39+ blocks); (c) **`render-service/remotion-lib/src/`** — NOLAN's other Remotion bundle, which
   already has many blocks (PhotoGrid, PhotoMontage, BarCompare, RouteMap, …). If it exists in
   remotion-lib but not `_lab_chapter`, **PORT it** (copy + adapt to the block contract
   `{...props, revealFrames, words, durationInFrames}`) rather than rebuild from scratch. Only
   author a genuinely new block if none exists anywhere.

4. **Use the assets already attached.** The beat may already have a bound asset (`src`/`cards`/
   `left`/`right`) and the human may have **added assets to its tray** (`scene.assets[]`) or left
   a **wishlist**. Prefer those; source new ones from the picture library / clips only if needed.

5. **Re-render ONLY your beat** via the chapter-block mechanism:
   `python -c "from nolan.iterate.engine import rerender_scenes; rerender_scenes('<scene_plan.json>', ['<beat_id>'])"`.
   This renders the single beat clip and re-concats; neighbor clips stay byte-identical.

6. **Keep the theme/fx** the project declares (`flow.spec.json` `theme`/`fx`) unless asked to
   change it.

7. **Report** to `.nolan/agents/<agent>.json`: `state` working→done|error, `scene_ids`, a
   `message`, and a `result` list. Start by writing `state: "working"`.

## Quick orientation
- The spec/palette/render design: `web-video-lab/flows/INTEGRATION.md`, `EDITOR.md`, `art.md`.
- One beat = one block over one voiceover segment; its duration is pinned to that segment, so a
  visual edit never reflows the timeline — that's why a single beat re-renders independently.
