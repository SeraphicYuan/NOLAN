---
id: pipeline.hyperframes-edit
harness: nolan-hf-edit
name: NOLAN HyperFrames edit loop (single + AI batch)
description: >
  The /hyperframes REVIEW → EDIT → RE-RENDER loop, and the AI BATCH mode that runs it
  at scale: a human stages free-text comments across many frames, one (or several)
  fleet agents turn each into a gated PROPOSAL, the human reviews the batch on one
  contact sheet and accepts. Read this before running or debugging a batch edit,
  before writing `propose_scene_edit` ops, before acquiring an asset from the edit
  loop, and before parallelising agents over a comp. Covers the proposal contract,
  the anchor rule, the verify tiers (cheapest first), scene-scoped acquisition, the
  capability-gap ledger, the mandatory closing verify, and the undo.
kind: methodology
purpose: >
  Give a batch agent everything it needs to edit an essay correctly without reading
  compose.py — the ops grammar, what each block actually consumes, how to re-anchor,
  how to verify before spending a render, how to get an asset, and how to report an
  honest miss.
status: active
version: 1
tier: primary
handoffs:
  - { process: hyperframes, stage: edit, gate: B }
uses:
  - pipeline.hyperframes
  - organ.sync
  - organ.acquire
  - common.composition-craft
documents:
  edit: src/nolan/hyperframes/edit.py
  batch: src/nolan/hyperframes/batch.py
  acquire: src/nolan/hyperframes/acquire_scene.py
  review: src/nolan/hyperframes/contact_sheet.py
loaded_by: []
evals: []
---

# The HyperFrames edit loop — single edit and AI batch mode

`pipeline.hyperframes` makes the essay. This is what happens **after** the first render, when a
human watches it and has notes. Load this before any batch edit; load
`[[pipeline.hyperframes]]` for the finish DAG itself.

## The contract (do not route around it)

An agent's edit is a **PROPOSAL**, never a write to the canonical spec:

```
comment (human)  →  proposal (agent, gated at creation)  →  human accepts  →  canonical
```

`propose_scene_edit` applies your ops to a **copy**, runs `author.py --validate-only`, and records
the result with your rationale. `accept_proposal` is what applies it for real, through the gate,
with revert-on-reject. You never call `apply_scene_edit`, never edit a `*.spec.json`, never render.

```python
from nolan.hyperframes import propose_scene_edit
propose_scene_edit(comp, frame_id="04-invent", scene_id="s3",
    ops=[{"op": "patch", "scene_id": "s3", "patch": {"data.kicker": "THE TRADITION"}}],
    rationale="the note asked for an eyebrow naming the section",
    agent="nolan1", comment_id="c7",
    requirements=[{"req_id": "r1", "status": "met", "note": "added the eyebrow"}])
```

**Op kinds** (`_apply_ops`): `patch` (scene_id, patch:{dotted: value}, deletes:[]) · `add`
(scene:{id,type,start,dur,data}, index?) · `remove` (scene_id) · `retime` (scene_id, start?, dur?) ·
`transition` (scene_id, kind, dur?).

**Dotted paths** index into lists (`data.items.0.to`) and **`+` appends** (`data.series.+`). An
out-of-range index RAISES and names the fix — it does not grow the list, because silent growth turns
a typo into blanks that validate.

## Blocks: the catalog is the truth, not compose.py

Your brief carries the catalog slice for the blocks in play. **A field not listed for a block is not
consumed by it.** Writing one used to validate and paint nothing; two classes are now refused
outright, and both refusals name the alternative:

- `data.ground` (image/paper) on a block that doesn't paint it → **CAPABILITY-GAP**. A *video*
  ground is fine on any block — `collect_video_grounds` root-mounts it (that is how a `math` scene's
  Manim clip reaches the screen).
- `at` (a reveal cue) on a block outside `CUE_BLOCKS` → INERT, refused.

**A CAPABILITY-GAP refusal is not your mistake.** The block genuinely cannot do what the note asked.
It is logged to `.hf_gaps.jsonl` as a feature request and counted across comps (`list_gaps()`).
Record the requirement `unmet`, or convert the scene and record `partial` **with the cost** — e.g.
converting a `juxtaposition` to `layout` is the documented path but loses the per-line reveal styles
and changes the typography. Say so. Three counted asks is what got `juxtaposition` a real
`data.ground`; a workaround you silently absorbed is a capability nobody ever builds.

## Anchors — copy them, never retype them

A scene's `anchor` is the spoken phrase it lands on. `sync.place_scenes` matches it as an **exact
token subsequence** of the aligned VO. A paraphrase does not score lower, it does not match: the
scene is placed by fallback and the report reads `UNRESOLVED @conf 0.0`.

The one genuine regression in a 25-edit batch was exactly this — the anchor said *"someone taught it
to you"*, the VO says *"somebody"*.

- **Copy** the anchor out of the `VO:` line in your brief.
- Anchor where the beat's topic **opens**, not a closing aside.
- Never lead with a number — Whisper writes digits, so a spelled-out number-leading anchor misses.
- An anchor edit changes **nothing** until `word-sync` runs. That is the closing step, below.

## Verify before you propose — cheapest tier that can answer the question

| cost | tool | answers |
|---|---|---|
| free | read the spec | field values, ordering, windows |
| ~1s | `recompose_frame(comp, fid)` | does it compose / gate |
| seconds | `snapshot_frame(comp, fid, at=t)` | layout, type, colour, crowding |
| seconds | `proposal_preview(comp, pid)` | what the proposal WOULD look like (canonical untouched) |
| ~30s | `render_scene(comp, fid, sid, seconds=3)` | motion, and any scene with a **video ground** |
| minutes | `render_frame(comp, fid)` | the whole beat, last resort |

Snapshot **one frame's scaffold**, never the whole comp — the comp index loads every root video and
times out. A seeked `<video>` does not decode into a still, so a footage-grounded scene previews as
an empty plate: that is what `render_scene` exists for, and the contact sheet flags those rows.

**A menu caption is a claim; the pixels are the fact.** Contact-sheet every clip you place
(`ffmpeg -ss 1 -i <clip> -frames:v 1 -vf scale=480:-1 out.jpg`) before proposing it — watermarks,
hard-subs and branded uploads are invisible to every text-level gate.

## Assets — one door, never hand-rolled

```python
from nolan.hyperframes import acquire_for_scene
acquire_for_scene(comp, frame_id, scene_id, query=None, modality="video", n=6, generate=False)
```

It derives the need from **that scene's own narration and window**, so `min_duration` is right; runs
the **full** engine (clips_library, transcript tiers, library, visuallib, stock) with relevance,
fitness, dedup and the **VLM usability floor**; dedups against every asset this essay already shows;
and **merges** into `pool.json`. Candidates land on the scene's **shortlist** — wiring one into the
block is a normal gated proposal.

- Do **not** run the whole-project pool bridge to fetch one asset.
- Do **not** write `pool.json` yourself (it is the project's catalogue; an overwrite destroys it).
- A file you dropped locally goes through `add_scene_asset` (validates the bytes, records provenance).
- `generate=True` spends the **GPU**; it queues on the machine-wide `nolan.gpu_lock`. Deliberate only.

## Honest reporting beats coverage theatre

Pass `requirements=[{req_id, status: met|partial|unmet|deferred, note}]` mapping your ops to the
checklist in the brief. `unmet` and `partial` are first-class signals — the reviewer reads them at
the top of the sheet. Never fake `met`.

**`deferred` is a real comment state**, not a way of saying "I gave up": real work, blocked on an
external resource, with the command that resumes it.

```python
resolve_comment(comp, fid, comment_id, status="deferred",
                reason="ComfyUI is down",
                retry="acquire_for_scene(comp, '04-invent', 's3', generate=True)")
```

It stays out of the open changeset but is listed by `list_deferred(comp)` and picked up by
`list_changeset(comp, include_deferred=True)`.

## Parallelism

Everything that is not GPU work parallelises: proposal construction, gate subprocesses, stock search
and download, snapshots (cap ~3, they are browser-bound), ffmpeg. **All GPU work — generation, TTS,
CLIP — must go through `nolan.gpu_lock`**, which is a machine-wide lockfile precisely because a fleet
agent is a different process from the hub and cannot see its in-process lock.

At the batch level the unit is the **frame**: `dispatch_batch_sharded(comp, ["nolan1","nolan2",…])`
gives each agent whole frames, so no two agents ever touch one `*.spec.json`. **Stay inside your
shard.** The shared surfaces are safe (proposals take a cross-process lock, the activity log is
append-only, the pool merges).

## The closing step — mandatory, once

```bash
python -X utf8 -m nolan.hyperframes.batch --verify <comp>
```

Runs the finish DAG's pre-render half: `word-sync`, the **scene-timing gate** (≥6s visual lag or a
mis-ordered scene HARD-blocks), the number/math-provenance gates and the **style gate**. None of
these run at propose or accept time, so without this a batch can be fully reviewed, fully accepted,
and only then refuse to render. Report its verdict in your final message. Under a sharded dispatch
only the first agent runs it — it covers the whole comp.

## For the human reviewing the batch

- `build_sheet(comp)` / `write_markdown(comp)` — every touched scene in **essay order** with
  before/after, rationale, coverage, gate findings, and the anchor delta. Reading `BATCH_REVIEW.md`
  as prose is the cheapest answer to "does it still hang together".
- `accept_proposals(comp, ids, all_or_nothing=False)` — one transaction, returns a `rollback_token`.
- `rollback_batch(comp, token)` — the undo. Git is **not** the safety net here (shared tree,
  concurrent agents, and `git stash` is forbidden in this repo).
- `list_gaps()` — what the essays keep asking for that the blocks cannot do.
- `prune_previews(comp)` — reclaim preview scratch.

## Shipping it — after the render is good

| step | command |
|---|---|
| what IS the deliverable, is it current, what's loitering | `python -X utf8 -m nolan.hyperframes.manifest <comp> [--clean]` |
| where every on-screen asset came from | `python -X utf8 -m nolan.hyperframes.provenance <comp> --write` |
| build `package/` (chapters, subtitles, description, titles, provenance) | `python -X utf8 -m nolan.hyperframes.package <comp>` |
| AUTO mode — judge → revise (`drafts/draft-NN` + `reviews/review-NN`) | `python -X utf8 -m nolan.hyperframes.ship <comp> --rounds 3` |
| EXPORT mode — one paste-able brief for iterating elsewhere | `python -X utf8 -m nolan.hyperframes.ship <comp> --export` |
| thumbnails, rendered in the essay's theme and judged at feed size | `python -X utf8 -m nolan.hyperframes.thumbnail <comp>` |

`renders/` has ONE deliverable, `video.mp4`, recorded in `renders/render.json` with a per-frame
fingerprint. Ask `manifest.deliverable(comp_dir)` for it — never glob for an mp4; that is how the QA
gates spent months scoring an SFX preview. Intermediates live in `renders/_work/`, one predecessor in
`previous.mp4`, and `hf-finish --tag <name>` keeps a cut you care about.

**Packaging REFUSES a stale deliverable.** Titles and thumbnails are generated from a render; if the
specs have moved since, you would be packaging a video you are not shipping. Re-run `hf-finish`, or
pass `force=True` knowingly.

## Gotchas that cost real time

- The proposal gate is a **spec** check. It does not know the VO, the assembled composition, or the
  style dials. That is why the closing verify is not optional.
- An accepted proposal rebuilds its frame's HTML; it does **not** re-run sync, so timing edits only
  land at the next `hf-finish`/verify.
- `finish --no-sound` while iterating: the bgm step can wipe `voices[]`.
- Render via `cmd.exe npx hyperframes render`, not a bare WSL `npx` (esbuild is win32).
- Windows paths: use `D:/…` and `python -X utf8`.
- A derivation is a RECORDED fact (`derived_from` on the pool entry), not a filename you can parse.
  Ask `edit.pool_original(comp, name)`. And read provenance from `edit.pool_entries` (the raw rows) —
  `asset_pool_meta` is a UI projection that drops `license`, `source_url` and `derived_from`.
