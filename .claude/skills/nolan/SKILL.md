---
name: nolan
description: >
  Orientation + router for working on the NOLAN codebase (turns essays/artworks into
  narrated videos). Read this FIRST on any non-trivial NOLAN task — it maps the two flows,
  the skill registry, every subsystem + where it lives, the key commands, and the
  cross-cutting runtime gotchas that repeatedly bite (Windows-python-from-WSL, the GPU lock,
  the shared-working-tree/git-index hazard with concurrent agents, the numpy/Pillow pins).
  It is a MAP that points into the code + skills/ registry — it does not duplicate them.
  Use when: starting to explore NOLAN, unsure which subsystem/skill owns a task, or hitting
  an environment/build error.
---

# NOLAN — the map

NOLAN turns a source into a narrated video. The **DOMINANT** path is compose-first
**HyperFrames** — HTML rendered in a headless browser, animation via **GSAP** (the default
adapter): author → the `hf-finish` DAG → render → edit-loop. The **LEGACY** Director path
(script → scene plan → assets → **Remotion** render → assemble) remains for legacy projects.
Don't conflate the two renderers: **HF = HyperFrames/GSAP**, **Director = Remotion**.

**This file orients; it doesn't contain the rules.** Rules live in `CLAUDE.md`. Durable facts
live in memory (`MEMORY.md`). Pipeline judgment prose lives in `skills/<domain>/*.md`. This is
the index that ties them together — read the pointed-to file for detail.

## The dominant pipeline

**Compose-first HyperFrames** (GSAP) is THE way to make an essay now. Author → the `hf-finish`
DAG → render → edit-loop. Start at the **`pipeline.hyperframes`** skill; the per-subsystem
**`organ.*`** skills go deeper. Both HITL gates still apply: **Gate A** = plan-time (authoring),
**Gate B** = render-time (per-beat edits).

## The two flows (LEGACY — Director/Remotion)

> Superseded by the HF pipeline above. Kept for legacy projects; `explainer.*`/`art.*`/`flow.*`
> skills are **deprecated**. `src/nolan/flows/` renders via `remotion-lib`. CLI: `nolan render-flow`.

- **explainer** — idea-dense text → narrated explainer (`skills/explainer/flow.md`).
- **art** — image-first; the artwork IS the subject (`skills/art/flow.md`).

## The skill system (how to find the right prose)

A **skill** = any `.md` with an `id:` in frontmatter. Two roots, one catalog:
- `skills/<domain>/*.md` — pipeline judgment prose, injected at gates via
  `handoff(skill_id)` (`src/nolan/skills/__init__.py`). Domains: `common` (cross-flow craft),
  `explainer`, `art`, `flow`, `orchestrator` (one-shot prompts), `publish`.
- `.claude/skills/*/SKILL.md` — harness-invocable Claude Code skills (this one;
  `nolan-scene-edit`; `beautiful-article`). Cataloged in place — **moving breaks invocation.**
- Catalog: `skills/index.json`. Lint/regenerate: `python -m nolan.skills`. Browse: `/skills`
  hub page (Registry / Lineage / Health). `kind` ∈ {contract, craft, grammar, prompt, methodology}.

→ To change *how the pipeline reasons* at a stage, edit the skill in `skills/<domain>/`, not code.

<!-- BEGIN AUTOGEN:skill-router (python -m nolan.skills --emit-router) -->
## Skill registry — auto-generated, do not edit by hand

_39 skills. Regenerate: `python -m nolan.skills --emit-router`. Load the skill for the subsystem you are ABOUT to touch — not preemptively._

### Primary pipeline (start here)

| skill | kind | what it's for |
|---|---|---|
| `pipeline.hyperframes` | methodology | Orient + route any compose-first HyperFrames pipeline task — the stage map, the finish DAG (each step + its gate), the load-bearing invar… |

### Organs

| skill | kind | what it's for |
|---|---|---|
| `organ.acquire` | grammar | Orient any acquisition task — the fan-out → gate → floor → dedup → generate pipeline, the two FLOORs (CLIP relevance, VLM usability), pro… |
| `organ.asset-engine` | grammar | Orient any source-resolution task — the scene-type→source mapping, the escalation ladder, the resolved_source provenance record, and Engi… |
| `organ.audio-mix` | grammar | Orient any soundtrack/mix task — the mix_soundtrack integration point, the real sidechain duck spec, music-library selection by energy ar… |
| `organ.layout-blocks` | grammar | Orient any layout-block task — the Remotion-first-then-Python fallback, the adapter contract ((block_name, props) | None), and graceful d… |
| `organ.render` | grammar | Orient any render-routing task — the per-scene routing order + kinds, the resilient title-card fallback, the premium (Chapter-per-section… |
| `organ.sync` | grammar | Orient any narration↔scene timing task — the align→place pipeline, anchor semantics, the monotonic clamp + per-frame fallback, and the sc… |
| `organ.voice` | grammar | Orient any voiceover / narration task — the per-section anchor contract, cloning, the GPU lock, the speak-ready gate, take versioning, an… |

### Labs (exploration tools)

| skill | kind | what it's for |
|---|---|---|
| `lab.deconstruct` | methodology | Orient any deconstruction task — what it recovers (beats/pairing/tempo/motion), the shared vocabularies it recovers INTO, and the recover… |
| `lab.kb` | methodology | Orient any KB task — the markdown-is-canonical / indices-are-derived rule, the ingest→distill→index→link pipeline, and hybrid retrieval (… |

### Craft (umbrella judgment)

| skill | kind | what it's for |
|---|---|---|
| `common.chapter-craft` | craft | Per-beat visual craft — the 10 principles, the content→motion decision tree, the anti-AI-look list, completion checklist. |
| `common.composition-craft` | craft | The composition umbrella — the named layout archetypes (centered-hero, split-screen, swiss-grid…), when to use each, and how a theme + be… |
| `common.editing-craft` | craft | The editing umbrella — cutting-rhythm techniques (j-cut, shot-list, transition-in), when to use each, how to author them on the plan. |
| `common.effects-craft` | craft | The effects umbrella — visual TREATMENTS (grades, grain, film damage, physical-element overlays) with when-to-use guidance; authored as a… |
| `common.motion-craft` | craft | The motion umbrella — every registered effect with when-to-use guidance; how specs are authored, validated and promoted. |
| `common.outline-format` | craft | Outline format — rhythm, step counts, info-pool extraction, the dual-source principle. |
| `common.pairing-craft` | craft | The narrative->asset pairing umbrella — every operator (literal, knowledge, tonal, conceptual, ironic, trait, relational, scale) with whe… |
| `common.script-style` | craft | Article-to-narration craft — >=60% info retention, de-AI voice, keep the source language. |
| `common.sound-craft` | craft | The sound umbrella — SFX cue-kinds (whoosh, impact, paper, data-punch, ambience beds …), when to fire each, how to author them as data on… |
| `common.theme-craft` | craft | Create/enrich themes — token philosophy, banding, font-loader constraints, the enrich/validate workflow. |

### Legacy flows

| skill | kind | what it's for |
|---|---|---|
| `art.flow` | methodology | When-to-use + grammar + palette for the image-first artwork explainer flow. |
| `explainer.block-catalog` | grammar | The authoring contract for explainer blocks — every block, its props, and anchor spec. |
| `explainer.flow` | methodology | When-to-use + grammar + palette for the paper/article explainer flow. |
| `explainer.scene-grammar` | grammar | Section scene taxonomy (Hook→Problem→Method→Results→Takeaway) + the comprehension eval. |
| `explainer.script` | craft | Author the narration from a source paper — 7 stages (extract → arc → draft → tighten → verify → gate → score). |
| `explainer.spec-authoring` | craft | The per-beat agent contract — choose a library block or author a bespoke one, and write the spec.json. |
| `flow.authoring` | craft | The plan-checkpoint craft layer — outline rhythm, dual-source, motion selection/invention — before planning or editing a flow video. |
| `flow.edit-contract` | contract | Hard rules for an agent reworking one beat of a flow video (edit the spec, reuse blocks, re-render only that beat). |
| `orchestrator.adapt-style` | prompt | Adapt a matched style template to the project's script. |
| `orchestrator.invent-style` | prompt | Invent a style guide from scratch when no template matches. |
| `orchestrator.motion-designer` | prompt | Author motion_spec on scenes where a motion effect beats the default treatment — the pass that spends the motion library. |
| `orchestrator.refine-clips` | prompt | Re-search clips after user feedback. |
| `orchestrator.refine-slides` | prompt | Adjust layout specs after QA feedback. |
| `orchestrator.refine-style` | prompt | Refine the style guide after QA feedback. |
| `orchestrator.script-to-scenes` | prompt | Turn the narration script into scene_plan.json (excerpt + visual type per scene). |
| `orchestrator.select-clips` | prompt | (deprecated) LLM clip-selection pass — superseded by the in-code semantic vector matcher. |
| `orchestrator.slide-designer` | prompt | Attach a layout_spec to text-overlay/graphic scenes. |

### Other

| skill | kind | what it's for |
|---|---|---|
| `publish.author-article` | prompt | Author the article component hierarchy from the source. |
| `scene-edit` | contract | Route a single-scene edit to the right NOLAN capability, apply, validate, re-render only that scene. |

<!-- END AUTOGEN:skill-router -->

## Subsystem map (where things live)

| Area | Path | What / entry |
|---|---|---|
| Core pipeline | `src/nolan/{parser,script,scenes,llm}.py` | essay → script → scene plan. `nolan process` |
| Orchestrator **(LEGACY)** | `src/nolan/orchestrator/director.py` | the Director linear pipeline (Remotion); `orchestrator.*` skills. Superseded by HF — see `pipeline.hyperframes` |
| Flows engine **(LEGACY)** | `src/nolan/flows/` | art/explainer flow + gates (Remotion). `nolan render-flow`. Superseded by HF |
| Scene iteration | `src/nolan/iterate/` | review/edit N scenes, re-render only those. `nolan revise-scene` / `rerender`; `/scenes` |
| Build from segment | `src/nolan/segment/` | span/script/VO → design→render→assemble. `nolan build-from-segment` |
| Picture library | `src/nolan/imagelib/` | persistent CLIP-searchable image store. `nolan images`; `/images` |
| Stock/image search | `src/nolan/image_search.py` | Unsplash/Pexels/Pixabay (rate-limited) |
| Asset extraction | `src/nolan/extractors/` | URL → hi-def images. `nolan extract-assets`; `/extract` |
| Cutout (bg removal) | `src/nolan/cutout.py` | rembg RGBA cutouts (isnet/birefnet/u2net). `nolan cutout`; `/images` "Cut out" |
| ComfyUI gen | `src/nolan/comfyui.py`, `workflows/` | image gen via ComfyUI (:8080, Windows-only) |
| Motion specs | `src/nolan/motion/` | NL scene design → validated spec → render |
| TTS / voices | `src/nolan/{tts,voice_library,voiceover}.py` | OmniVoice (separate CUDA env). `/voices`, `/tts` |
| Themes | `themes/` (25+ dirs) | video themes + `selector.json` + `scripts/select_theme.py`. See `themes/THEME-PLAYBOOK.md` |
| Renderer (HF, dominant) | HyperFrames — `npx hyperframes render` (via `cmd.exe`) | HTML → headless-browser frame render; animation via **GSAP** (default adapter, +Lottie/Three/Anime/…). Incremental: `nolan hf-render` |
| Renderer (legacy) | `render-service/remotion-lib/` | **Remotion** render (`render.mjs`/`still.mjs`/`stage.mjs`) — the Director/FLOW path only |
| Hub webUI | `src/nolan/hub.py` (FastAPI) + `templates/` + `static/` | design system in `static/nolan.css`, shell in `nav.js`. Port **8011** |
| Fleet / agents | `src/nolan/fleet.py` | dispatches to tmux Claude agents; `/agents` |
| Publish | `src/nolan/publish/` | final render/assemble + article path. `/publish` |

Full CLI: `nolan --help` (Click; commands in `src/nolan/cli_legacy.py`).

## Runtime gotchas (these cost hours if unknown)

- **Python is the Windows env**, even from WSL: `D:\env\nolan\python.exe` (WSL:
  `/mnt/d/env/nolan/python.exe`), pip `D:\env\nolan\Scripts\pip.exe`. Run with `-X utf8` on
  Windows or ffmpeg cp1252 decode crashes corrupt scene detection.
- **Rendering needs Windows node**: WSL `node` can't build (esbuild binary is win32) — use
  `/mnt/c/Program Files/nodejs/node.exe`. Bundled ffmpeg: `render-service/node_modules/@ffmpeg-installer`.
- **GPU lock**: ComfyUI + OmniVoice TTS serialize on `get_gpu_lock()`. Prefer CPU work
  (e.g. rembg cutout) so it doesn't queue behind renders/TTS.
- **Dependency pins**: keep `numpy<2.3` + `Pillow<12` (opencv/moviepy need them). rembg is the
  optional `[cutout]` extra, pinned `<2.0.76` to stay numpy<2.3-compatible.
- **Concurrent agents share ONE working tree + git index** (tmux agents). The branch can change
  under you; the index can carry another agent's staged files. **Commit with an explicit
  pathspec** (`git commit -m "…" -- <your files>`) and land on master via an **isolated worktree
  cherry-pick** — never a whole-branch fast-forward (it publishes others' WIP).
- **Hub**: port **8011** (avoid 8001 — SPARTA). Tailnet via `tailscale serve --tcp=8011`.
- **UI screenshots**: Windows Chrome headless, or puppeteer (`render-service/node_modules`) for
  device-emulated (iPhone) viewports — Chrome `--window-size` won't honor <484px CSS width.

## Where knowledge lives (keep these distinct)

- `CLAUDE.md` — **rules & conventions** you must follow.
- memory (`MEMORY.md` + files) — **durable facts** across sessions (verify paths before acting).
- `skills/<domain>/*.md` — **pipeline judgment prose** (via `handoff()`), tracked in the registry.
- `.claude/skills/*/SKILL.md` — **invocable** Claude Code skills.
- **this file** — the **map/router**. Add pointers here; put detail in the right place above.

## Conventions

- **Language layering** (don't flatten to all-English): code/ids/keys/`tags`/`mood` = English;
  product pairs = `x` + `xZh`; audience free-text (`bestFor`, narration) = Chinese; engine docs
  (`IMPLEMENTATION_STATUS`, comments) = English; skill agent-docs = Chinese, consistent per file.
- After a feature, update `IMPLEMENTATION_STATUS.md` (CLAUDE.md rule).
