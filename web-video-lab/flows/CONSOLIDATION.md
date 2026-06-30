# Scope: defragment into ONE shared flow engine (multi-type, not art-specific)

Today the auto-mode pipeline spans **6 folders × 4 runtimes**: `src/nolan/flows/` orchestrates,
but the real logic lives in `web-video-lab/*.py` (subprocessed) and `render-service/_lab_chapter/`
(node), plus a block duplication between `_lab_chapter` and `remotion-lib`.

**The reframe:** this is a *multi-type* workflow (art, explainer/paper-video, book, …) with a
**shared engine** and routing at **one step — ingest**. Almost everything is already flow-agnostic;
the `art_` naming hides it. So consolidation = (1) move the shared logic in-process under
*flow-generic* names, and (2) make **ingest** an explicit per-type adapter slot. Done right, it
consolidates **explainer too** — explainer plugs into the same engine by adding one ingest adapter
+ a registry row.

```
src/nolan/flows/
  base.py        run_flow(flow, …)            # SHARED engine: ingest → gate → render → deliver
  __init__.py    get_flow(id) -> Flow         # routes by descriptor (registry.json)
  ingest/                                      # ← the ONLY per-type fork (routing point)
    art.py        assemble (byo-everything)    # ports art_ingest
    explainer.py  generate (paper→video)       # ports gen_spec + wires NOLAN TTS/Whisper/figure  [when promoted]
  gate/          run_gate(job, flow)          # SHARED (flow-agnostic; was art_check/validate/…)
    validate.py · pacing.py · contact.py · montage.py
  render.py      chapter-block                 # SHARED (art/explainer/book)
  scene_view.py · edit.py · project.py · authoring.py   # SHARED
```

Everything below the **job JSON** (gate → render → deliver → view → edit) is **identical for every
video type** — no routing. The router only picks the **ingest adapter** + the **profile/palette**
(config in `registry.json`). That's the "proper routing on certain steps" the workflow was designed
for, made structural.

---

## THREE deliverables — harden the mechanics, KEEP the skill a skill

Consolidation is NOT "absorb the skill into code." The skill (`web-video-lab/skill/`) is a full
**design methodology + collaboration workflow** (4 phases, two human checkpoints, CHAPTER-CRAFT /
SCRIPT-STYLE / OUTLINE-FORMAT / THEMES / ANTI-AI rules / EXAMPLES). That soft layer is where the
flexibility lives — invent-as-needed motion, the plan/authoring craft, minimum-edit. We HARDEN
only the mechanical engine and PRESERVE the skill, with explicit hand-offs.

| Layer | Form | Detail |
|---|---|---|
| ingest/gate/render **mechanics** | **code** (`src/nolan/flows/`) | the only part that hardens — stable, deterministic |
| palette / themes / profiles | **config** (`registry.json`, `themes/`) | evolves, editable |
| **plan / authoring** (Checkpoint-Plan: which motion, which assets, design the chapter) | **skill + agent** | *the most flexible layer* — `CHAPTER-CRAFT` + `ANTI-AI` + `SCRIPT-STYLE` + the `[Checkpoint Plan]` |
| edit / **invent new block (RAW)** / minimum-edit | **skill** (`FLOW_EDIT` + `CHAPTER-CRAFT`) | open-ended, agent reasoning — the escape hatch |

**The wiring principle:** the engine runs the mechanical happy-path deterministically (fast,
reproducible, gated), but **at the authoring/plan checkpoint and at edit/invent it hands to an
agent reading the skill.** That keeps both the determinism *and* the PhotoGrid-moment flexibility.

**Deliverable 3 — preserve the skill:** port the methodology into a **flow skill** the engine
references — `FLOW_EDIT.md` (edit contract, done) + an authoring/craft guide carrying the
`[Checkpoint Plan]`, CHAPTER-CRAFT, SCRIPT-STYLE, OUTLINE-FORMAT, ANTI-AI principles, and EXAMPLES.
Don't leave them stranded in `web-video-lab/skill/` to rot.

---

## Track 1 — port the SHARED engine in-process (safe, high-value, multi-type)

Replace the subprocess hops (`base.py` shelling to `web-video-lab/*.py`) with in-process imports,
under **one canonical interpreter (the nolan env python** — has Pillow/FastAPI, what the WebUI/CLI
already use, what CLAUDE.md mandates). `_localize` already makes paths interpreter-agnostic. Node +
ffmpeg stay subprocess (Remotion is node-only — irreducible).

### Shared gate (flow-agnostic — the `art_` prefix was misleading)
| from `web-video-lab/` | to `src/nolan/flows/gate/` | note |
|---|---|---|
| `art_check.py` | `__init__.py` (`run_gate(job, flow)`) | orchestrator |
| `art_validate.py` | `validate.py` | structural + palette (takes flow id) |
| `pacing_lint.py` | `pacing.py` | takes profile id — **already used by explainer** |
| `art_contact.py` | `contact.py` | still subprocesses node `still.mjs` + ffmpeg |
| `_montage.py` | `montage.py` | Pillow, now in-process (kills the 2nd interpreter) |

### Per-type ingest (the routing point)
| from `web-video-lab/` | to `src/nolan/flows/ingest/` | type |
|---|---|---|
| `art_ingest.py` | `art.py` (`ingest_art`) | art — assemble |
| `gen_spec.py` (+ `synth_omnivoice`, `word_timestamps`, `extract_figure`) | `explainer.py` | explainer — generate **[when promoted]** |

**Stays in `web-video-lab/`** (config/data, not logic): `flows/` (registry + docs), `skill/themes/`
(CSS read by node), `art/` (specs). Optional thin CLI shims so standalone use + docs still work.

### Phases (each independently testable, byte-identical render as the bar)
1. `flows/gate/` — move + refactor each `main()`→function; `base.run_gate` imports it. Test: gate
   green, identical to subprocess.
2. `flows/ingest/art.py` — `art.INGEST` calls `ingest_art()` in-process. Test: job byte-identical.
3. De-subprocess `base.py`. Test: full auto render byte-identical; re-render-one still ~20s.
4. Shims + docs.

### Risk: **low–medium** (path handling under nolan env python — covered by `_localize`, proven via
the TestClient runs). One behavior change: the flow no longer runs under bare WSL `python3` (lacks
Pillow) — fine, the nolan env IS NOLAN's interpreter.

---

## How explainer (paper/article → video) consolidates too

After Track 1, promoting explainer is **one adapter + one registry row** — the engine is already
shared:
1. **`flows/ingest/explainer.py`** — the generate adapter: wires NOLAN's existing **TTS**
   (OmniVoice), **Whisper** (word timing), **figure extraction**, then `gen_spec` (anchors→frames)
   → writes the same `flow.job.json`. (This adapter *imports NOLAN's `src/nolan/` TTS/Whisper/vision*
   — not the `web-video-lab` scripts — so it's natively integrated.)
2. **`registry.json`** — explainer row already exists (palette = charts/kinetic/PaperFigure/…,
   profile = punchy, `render_mechanism: chapter-block`).
3. **Reused for free:** `gate/` (with `--profile explainer`), `render.py` (chapter-block),
   `deliver`, `scene_view`, `edit`, the authoring mode, the Scene-page wiring, the flow-aware
   dispatch — **zero new code**.

So explainer becomes a video *type*, not a second pipeline. Adding "book" later = same: one ingest
adapter (only if a new acquisition mode) + a registry row.

---

## Track 2 — unify the two Remotion bundles ✅ DONE

There were two bundles: the temporary lab `_lab_chapter/` (Chapter-step blocks, 40) and the
NOLAN-integrated `remotion-lib/` (standalone `<Composition>` effects, used by the per-scene motion
path). **`_lab_chapter` was folded INTO `remotion-lib`** (the canonical NOLAN bundle) and retired:
- _lab_chapter's `blocks/` + `Chapter`/`Montage` + `stage.mjs`/`still.mjs` moved into `remotion-lib/src/`.
- Its deps (@visx/katex/lottie/flubber/roughjs/d3) merged into `render-service/package.json` (+ `react`
  pinned `^18.3.1` to satisfy both Remotion and @visx); `npm install`.
- `remotion-lib/render.mjs` **unified** — branches on job shape: flow `Chapter` (stage + steps) vs
  motion single-comp. `Root.tsx` registers 13 comps (10 effects + Chapter + Montage + FXSpike).
- Flow wiring re-pointed (`flows/base.py`, `render.py`, `gate/contact.py`, `gate/validate.py`).
- **Verified:** gate green, flow beat render, AND the motion path (`remotion_source.render`) all
  render through `remotion-lib`. `_lab_chapter/` deleted.
Result: **ONE render bundle, ONE block library** — no dupes, no temp folder, agents see one place.

---

## Sequencing & out-of-scope
1. **Track 1** — establishes the shared multi-type engine in-process (do first).
2. **Explainer promotion** — `ingest/explainer.py` + registry row (cheap, *after* Track 1).
3. **Track 2-C** — in place; **Track 2-B** — deferred.

**Out of scope:** node render bundle stays node; themes stay CSS. **Net after Track 1:** the
pipeline for *any* video type is `src/nolan/flows/` (python) + `_lab_chapter/` (node) +
`projects/<slug>/` (data) — 3 folders / 2 runtimes, routed only at ingest.
