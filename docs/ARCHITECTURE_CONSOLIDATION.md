# NOLAN Architecture Consolidation Plan

**Date:** 2026-07-04 · **Status:** proposed (decisions pending, see §6)
**Basis:** full-surface + redundancy audits, plus the-aeneid end-to-end production run
(which required manual CLI/python driving and surfaced 7 wiring defects, all since fixed).

## 0. North star

> Automate video making: **script → plan → asset matching (clips, pictures, remotion,
> theme, charts, numbers/words, VO alignment) → render** — one pipeline, one contract,
> every stage drivable from the UI, resumable, and honest about failure.

Everything in this plan is judged against that sentence. Features that serve it stay
(possibly relocated); duplicates converge; dead ends are removed.

---

## 1. Current state (audited census)

### Pipelines — FOUR content→video paths + a re-render layer over three of them
| Path | Stages | Scene schema | Audio | Renderer |
|---|---|---|---|---|
| **Orchestrator/Director** | match_style → script_to_scenes → tempo → select_clips → slide_designer → render | raw dicts | **silent** (assemble w/ silent.wav) | render_dispatch → python layouts + motion |
| **Segment builder** | design → timing → resolve → **voiceover** → render → assemble | `Scene` dataclass | **full VO** + music duck + align | same render_dispatch |
| **FLOW** | spec→job → gate → chapter-block render → concat | own `flow.job` steps | **baked into composition** | Remotion `blocks/library` (40) |
| **iterate/rerender** | re-implements all three as `_rerender_{flow,segment,orchestrator}` | dicts (deliberately) | inherits | inherits |

### Renderers — FOUR stacks, one conceptual catalog (17+ capabilities exist 2–4×)
1. Python/MoviePy `renderer/scenes/` — 29 classes (layout_spec templates render ONLY here)
2. Remotion curated `Root.tsx` — ~17 comps (the `nolan.motion` registry targets)
3. Remotion `blocks/library/` — 40 blocks (FLOW-only; the most complete stack)
4. render-service `effects/presets/` — 40 TS presets (HTTP-only; + a motion-canvas engine with no python caller)

Registry knowingly ships duplicate intents (`counter`/`stat-over`, `title`/`premium-card`,
`photo-montage`/`photo-montage-pro`). Orphaned python renderers: KenBurns, Flashback, PieCallout.

### Asset matching — FOUR front doors writing the same 2–3 scene fields
ClipMatcher (video vectors) · external_assets (semantic/external, incl. describe+ingest)
· evoke_broll (8 LLM operators) · art_sourcing (exact-title museums) — wired together
twice, independently (match_broll_v2 and segment `AssetResolver`). The **AssetResolver
escalation ladder** (search → library → external → motion → generate) is the best skeleton.

### Audio/alignment — three models, three aligner implementations
Orchestrator silent · segment full-VO · FLOW baked-in. Alignment exists in
`voiceover.align_scenes_from_words`, `aligner.py`/`nolan align` (now beat-anchored), and
captions/whisper word-timing. **Beat-anchored sync (per-section VO files = exact spans)
is proven and should be THE timing contract.**

### Scene schema — forked
`Scene` dataclass vs raw dicts, forked historically because round-trips dropped
`layout_spec` (root cause FIXED 2026-07-04 — `layout_spec` is now a real field).
`render_dispatch.field()` and iterate's throwaway-Scene hacks paper over the fork.
`ScenePlan` still silently drops any unknown key.

### Surface
- **Hub:** 3,344 lines, **199 routes**, zero APIRouters, **4 URL conventions**
  (`/api/X`, `/library/api/X`, `/scenes/api/X`, `/showcase/api/X`), 3 async-job idioms,
  mixed REST verbs, hardcoded agent default (`nolan4`) in a route.
- **Pages:** 23 templates; 4 orphaned (`/process`, `/extract`, `/images`, `/library/add`);
  1 nav entry with no template (`/tonal-broll/`); TTS Studio ⟂ Voices duplicate cloning;
  Studio ⟂ Scenes overlap as plan front-ends. Pages organized by module, not by workflow.
- **CLI:** `cli_legacy.py` = 5,256 lines, ~61 commands; `cli/` package is a dead stub whose
  docstring describes a split never executed.
- **Dead code:** infographic_client/icons, video_gen, lottie/jitter downloaders,
  motion_select (superseded by `nolan.motion`), visual_router (superseded by
  render_dispatch), render-service motion-canvas engine + `.cache` artifacts.

---

## 2. Diagnosis — five structural diseases

1. **The pipeline has no owner.** The end-to-end chain exists only as operator knowledge.
   The official Director cannot produce a narrated video (silent by design); VO, align,
   generate, assemble have no UI. Proven: the-aeneid required hand-written drivers.
2. **Contracts are unenforced.** The scene plan — the constitution of the system — is an
   unversioned dict; stages read it blindly and write it back lossily. Every seam crossed
   in production had a silent failure (7 found in one project).
3. **The best components are not where the pipeline looks.** VO/align/resolve excellence
   lives in the segment builder; the richest renderer (Remotion blocks) is FLOW-only;
   beat-sync existed as a docstring philosophy until a defect forced the wiring.
4. **Multiplicity without selection.** Four renderers, four matchers, three audio models,
   two schemas, two motion selectors, two layout-template concepts — accretion where
   there should have been replacement.
5. **UI mirrors modules, not the workflow.** 12+ parallel worlds; no page answers "where
   is my project on the arc, and what do I click next?"

---

## 3. Target architecture

```
                    ┌────────────────────────────────────────────────┐
                    │           PROJECT DASHBOARD (one page)         │
                    │  script ─ plan ─ assets ─ voice ─ render       │
                    │  status per stage · next action · deep links   │
                    └────────────┬───────────────────────────────────┘
                                 │ drives
   ┌─────────────────────────────▼──────────────────────────────────┐
   │                    THE PIPELINE (one conductor)                │
   │ script.md → scene_plan.json → assets → VO → beat-anchored      │
   │ align → render (Remotion-first) → assemble(narrated)           │
   │ · every stage idempotent + resumable + validated               │
   │ · agent steps and API steps behind the same step interface     │
   └────┬───────────────┬────────────────┬───────────────┬──────────┘
        │               │                │               │
   ┌────▼────┐   ┌──────▼──────┐   ┌─────▼─────┐   ┌─────▼─────┐
   │ SCENE   │   │ ASSET ENGINE│   │ VOICE     │   │ RENDER    │
   │ PLAN    │   │ one ladder: │   │ one model:│   │ Remotion  │
   │ contract│   │ operators → │   │ per-beat  │   │ blocks =  │
   │ (schema │   │ library →   │   │ VO files =│   │ canonical;│
   │ versioned,  │ external →  │   │ exact beat│   │ python =  │
   │ lossless)   │ museums →   │   │ anchors   │   │ legacy    │
   └─────────┘   │ generate    │   └───────────┘   │ fallback  │
                 └─────────────┘                   └───────────┘
   Specialist tools (deconstruct, video/script styles, broll lab, clips,
   showcase, skills, library) = feeders and inspectors of the pipeline.
```

Key commitments:
- **Scene plan is a versioned, lossless contract** (unknown keys preserved; per-stage validators).
- **Beat is the atomic sync unit**: per-beat VO → exact spans → tiling within beats.
  FLOW's chapter-block rendering (beat = composition with baked audio) is the natural
  v2 render of this model — convergence, not a third pipeline.
- **One asset engine**: AssetResolver ladder, operator-aware (evoke bridges are the
  query layer), all UIs and Director step 4 call it.
- **Remotion-first**: blocks library is canonical; slide_designer templates map onto
  same-named blocks; python renderers become flagged fallback, then retire.
- **One job model, one router layout, one agent-picker** across the hub.

---

## 4. Phased plan

Each phase is independently shippable; no big-bang. Effort in focused sessions (S).

### Phase 0 — Safety net (≈1–2 S) — do first, blocks nothing
- **E2E smoke test**: tiny fixture project (3 beats, stub assets, 20s TTS or fixture VO)
  through script→plan→assets→VO→align→render→assemble; asserts video≡audio duration,
  no black frames, plan round-trip lossless. THE regression net for everything below.
- **Contract hardening**: `ScenePlan` preserves unknown keys + `schema_version`; add
  per-stage `validate_plan()`; sweep pipeline seams for swallowed exceptions and
  rc-0-on-failure (assemble `-o` class); absolute-path discipline helper.
- Acceptance: smoke test green in CI-able script; a fuzz round-trip test proves losslessness.

### Phase 1 — One pipeline, narrated (≈2 S) — highest user value
- Director gains first-class steps: **generate (ComfyUI) → voiceover (per-beat) →
  align (beat-anchored) → render → assemble(narrated)**. Retires the silent-audio design
  and the need for hand drivers. Segment builder's `_voiceover_stage` and beat-anchoring
  become the shared `voice` module; one aligner implementation survives.
- iterate/engine's three `_rerender_*` branches collapse onto the unified steps.
- Acceptance: `nolan orchestrate <project> --auto` = narrated, sync-exact final.mp4;
  Agents page runs it; the-aeneid reproducible with zero custom scripts.

### Phase 2 — One asset engine (≈1–2 S)
- Promote segment `AssetResolver` to `nolan/assets/engine.py`; tiers = ClipMatcher →
  imagelib/external (semantic+ingest) → art_sourcing exact-title → stock → generate;
  evoke_broll operators become the query/bridge layer feeding every tier.
- Director step 4, Studio match, `/scenes` super-search, match_broll_v2 → thin callers.
- Acceptance: four front doors reduced to one module + adapters; parity test on a
  fixture plan (same or better match rate than each retired path).

### Phase 3 — One renderer story (≈3–4 S, largest) — needs Decision D1/D2
- Canonical stack: **Remotion blocks library**. Map slide_designer's 22 layout templates
  to same-named blocks (Timeline, Ranking, PullQuote, TweetCard, NewsHeadline,
  LocationStamp, ProgressBar, PercentBar, SourceCitation, ChapterCard, LineChart,
  LoopDiagram… mostly 1:1); `render_layout` targets Remotion; python renderer behind
  `NOLAN_LEGACY_RENDER=1`, then deleted.
- Motion registry: one backend per intent (drop py `counter`/`title`/`photo-montage`).
- Retire render-service `effects/presets` + motion-canvas engine (keep the remotion engine
  + lottie/infographic only if used); delete orphaned python renderers.
- FLOW convergence (D2): beat = Chapter composition with baked VO becomes the pipeline's
  render mode for "premium" projects; `flow.spec.json` becomes a scene-plan-derived view,
  not a competing source of truth.
- Acceptance: a new project renders 100% via Remotion; visual spot-diff on fixture
  scenes; python stack unreferenced.

### Phase 4 — Surface consolidation (≈2 S)
- **hub.py → APIRouters** per subsystem; single `/api/<domain>/…` convention (aliases for
  old URLs during transition); one job model (generic jobs API absorbs showcase trio);
  one shared agent-picker + job-status web component; kill hardcoded agent defaults;
  DELETE verbs for deletions.
- **CLI**: execute the `cli/` split (pipeline.py, library.py, assets.py, render.py,
  voice.py, styles.py…); `cli_legacy` becomes re-export shim; delete dead helpers with it.
- Merge **TTS Studio into Voices** (voice library + project VO + text sandbox as tabs).
  Adopt orphans: `/images`, `/extract`, `/library/add` become Library/Assets tabs;
  retire `/process` (superseded by Script Projects + pipeline).
- Acceptance: route census ≤ today with one convention; all pages keep working via aliases.

### Phase 5 — Project Dashboard (≈2 S) — the UX capstone
- One project-centric page: the arc (script → plan → assets → voice → render) with live
  per-stage status (from pipeline state), next-action buttons, and deep links into
  specialist tools; **replaces Studio**; Agents page refocuses as runs/logs/feedback.
- Nav regrouped by workflow: Create (dashboard, script styles/projects, deconstruct,
  video styles) · Assets (library, clips, broll, images) · Voice · Render (scenes,
  showcase) · System (agents, skills, settings).
- Acceptance: a new user produces a narrated video end-to-end from the dashboard
  without touching a CLI.

### Phase 6 — Cleanup & living docs (≈1 S)
- Delete audited dead code; clear `.cache` artifacts; `docs/ARCHITECTURE.md` (current-state,
  maintained); update IMPLEMENTATION_STATUS with the consolidation; memory notes.

**Sequencing rationale:** 0 protects everything; 1 delivers the core promise fastest and
exercises the contract; 2–3 shrink the machine; 4–5 present it honestly; 6 sweeps.
Phases 2 and 4 can interleave with 3 if renderer work stalls on decisions.

---

## 5. What is already done (this cycle, committed)
- `layout_spec` as a real Scene field (schema-fork root cause healed)
- Narration-owns-duration at all render sites; window tiling; **beat-anchored alignment**
- Tempo→motion stamping (reference-blended energy → Remotion still-motion)
- Archival-art sourcing engine + krea2 as default generation workflow
- Reference-guided production (deconstruct → clone/attach → pinned templates → blended tempo)

## 6. Decisions needed (owner: you)
- **D1 — Canonical renderer = Remotion blocks?** (recommended). Consequence: python
  renderer retirement path; layout templates re-homed.
- **D2 — FLOW absorbed as the pipeline's premium render mode?** (recommended) vs kept as
  a separate pipeline. Absorption makes beat-anchored VO + chapter compositions the one
  story; keeping it preserves today's art-flow independence.
- **D3 — Studio replaced by the Project Dashboard?** (recommended).
- **D4 — URL breakage tolerance:** alias old routes for N weeks (recommended) vs hard cut.
- **D5 — Phase order confirmation** (or UX-first: swap 4–5 before 2–3).
