# NOLAN Implementation Status

**Version:** 0.1.0
**Status:** Complete
**Last Updated:** 2026-07-05

## SFX search + fetch — pluggable provider layer wired into audio_mix (2026-07-05)

Automated the manual "search + download a sound effect" step. New `sfx_search.py`
mirrors `image_search.py`: an `SFXResult` + `SFXProvider` registry with two providers —
**FreesoundProvider** (official APIv2, token auth, CC-licensed, HQ-preview download; needs
`FREESOUND_API_KEY`) and **MixkitProvider** (best-effort scrape of mixkit.co category
pages; no API). Results cache into `projects/_library/sfx/` with an `sfx.json` manifest
(license + attribution recorded). `config.py` gains `freesound_api_key`.

Wired into `audio_mix.py`: a scene may declare an `sfx` cue (string / dict `{query,at,
volume}` / list); `author_soundtrack` sources it via the provider and adds a content event
that lands AT the beat (`lead 0.0`), distinct from transition whooshes (`lead 0.45`
pre-roll). `sfx_provider` threads through `mix_soundtrack` / `resolve_music_config` /
director (`project.yaml sfx_provider: freesound|mixkit`, default freesound). Backward-
compatible (old specs default lead 0.45); opt-in (scenes without `sfx` unchanged).

Verified live: Freesound + Mixkit search→download→valid-MP3→manifest→idempotent, plus the
audio_mix authoring integration (cues parsed, sourced, placed, correct leads). Example:
`examples/sfx_search.py`. Deferred (see `todo.md`): an **auto-cue pass** that decides which
beats get an effect — the decision layer feeding this placement layer.

## Asset-library curation UX + shortlist→essay bridge (2026-07-05)

Reworked the Picture / Video / Clip library pages from per-card "button soup"
into a **curate → select → act** model, and added a per-project **shortlist**
that bridges the libraries to a project's scenes.

**What changed**
- Shared components: `static/select.js` (`NolanSelect` — multi-select +
  contextual bottom action bar; click / shift-click / hover-checkbox; call
  `refresh()` after a re-render) and `static/shortlist.js` (`NolanShortlist` —
  project switcher + floating tray + "Send to essay"); shared CSS in
  `nolan.css` under the `ns-` prefix.
- **Pictures** (`images.html`): clean tiles; a **Select** mode reveals
  multi-select; verbs moved to the action bar — **Cut out** (1 → preview modal,
  N → batch), Reject, Promote, **Add to shortlist**.
- **Videos** (`library.html`): real poster thumbnails on the sidebar rows
  (via `/api/scenes/frame-thumb`); the per-row **Deconstruct**/**Embed**
  buttons moved into the **header** for the selected video (the list is
  single-select, so a per-row button soup / multi-bar didn't fit).
- **Clips** (`clips.html`): real poster thumbnails; the 5 per-card buttons
  replaced by the action bar — Materialize file/frames, Analyze effect,
  **Add to shortlist**, Delete.
- **Bridge (Option A — project pool):** `nolan/shortlist.py` +
  `routes/shortlist.py` persist `projects/<slug>/shortlist.json`; items are
  stored in the exact `op:add` payload shape the `/scenes` picker consumes, so
  the picker's new **Shortlist** tab feeds scenes through the existing
  `POST /api/scenes/scene/assets` seam — no pipeline fork. `/studio` shows a
  `shortlisted` count. "Send to essay" opens `/scenes?project=…&shortlist=1`.

**Usage:** library page → **Select** → pick assets → **Add to shortlist**
(target set by the "Essay" switcher) → tray **Send to essay** → on `/scenes`,
a scene's **＋ Add from library → Shortlist** tab adds them to the scene.

**Verified:** in-process TestClient + live hub — all pages 200, shortlist CRUD
+ dedup + bad-project 404, frame-thumb returns JPEG, studio status carries
`shortlist`; all inline template JS + both modules syntax-clean.

## Architecture Consolidation — Phase 6 (2026-07-05) — CONSOLIDATION COMPLETE

- `ARCHITECTURE.md` — the living map of the consolidated system (pipeline,
  contracts, engines, surfaces, test nets, deferred work).
- Dead code removed: jitter/lottiefiles/lottieflow scraper downloaders (zero
  callers; downloaders/ keeps models+utils). Kept with rationale:
  infographic_client/icons, video_gen, visual_router (live CLI commands),
  python renderer classes (Remotion fallback until bake-in), motion_select
  (evoke_broll), node-side effects/presets + motion-canvas engine (deletion
  needs a render-service rebuild — deferred).
- Test infra: `tests/test_hub.py` (a manual server script whose os._exit(0)
  silently killed every full-suite pytest run at ~38%) moved to
  scripts/hub_smoke_manual.py; stale expectations fixed (sampler default,
  visual_router fallback); missing-fixture tests now skip. FIRST-EVER clean
  full-suite run: 674 passed / 0 failed.
- /tts→/voices alias intentionally KEPT (created this phase; remove later).

## Architecture Consolidation — Phases 4–5 (2026-07-05)

**Phase 4 — surface consolidation:**
- CLI split: the 5,263-line `cli_legacy.py` is now 17 domain modules under
  `src/nolan/cli/` (process/index/generate/render/assets/library/audio/youtube/
  projects/search/hub/templates/video_gen/orchestrate/iterate/publish + _root);
  every moved section byte-identical, `nolan --help` unchanged (39 commands),
  `cli_legacy.py` is an 89-name compat shim for external helper imports.
- TTS Studio merged into Voices (one voice page; /tts 307→/voices alias).
- Orphan pages adopted into nav: /process, /library/add, /images, /extract.
- One job model verified: everything runs through `webui/jobs.JobManager`.
- Deferred (documented in ARCHITECTURE.md): hub APIRouter split, URL renames.

**Phase 5 — Project Dashboard replaces Studio (D3):** /studio is Director-
centric — 9-step pipeline chips + Run next/Run all, artifact badges
(script/scenes/matched/rendered/voiceover/final/voice/premium), inline final
player (`GET /api/project/{p}/final`); manual stage jobs collapsed to an
override section.

Known test-infra note: `tests/test_hub.py` calls `os._exit(0)` and silently
kills full-suite pytest runs at ~38% — run suites in groups or fix in Phase 6.

## Architecture Consolidation — Phase 3 (2026-07-05)

**Remotion-first rendering + FLOW absorption.**

- `render_layout` is Remotion-first: all 23 layout templates render through the
  curated flow-blocks library (`src/nolan/layout_blocks.py` adapters, one-step
  Chapter jobs); Python renderers remain the automatic per-scene fallback and
  the only path under `NOLAN_LEGACY_RENDER=1`.
- Motion registry: one backend per intent — counter/title/lower-third/comparison
  now on the "block" backend (same ids/params); python photo-montage removed.
- **Premium render mode** (`src/nolan/premium_render.py`, D2): every beat renders
  as ONE Remotion Chapter with per-scene VO slices baked in — FLOW's driver fed
  from scene_plan + beat anchors. The section WAV is the timing authority
  (windows normalized, frame-exact boundaries), so video ≡ narration by
  construction. Opt in with `render_mode: premium` in project.yaml; the Director
  render step dispatches; ineligible scenes fail the run with ids listed.
- Acceptance: the-aeneid copy premium-rendered end-to-end — 427.8s vs 427.4s
  narration (0.44s), 8 beat Chapters, 54 block scenes, frames visually verified.

## Architecture Consolidation — Phase 2 (2026-07-05)

**One asset engine**: `src/nolan/asset_engine.py` — the single scene→asset
resolution ladder (motion → archival-art exact-title → footage vector search →
picture-library stills → external providers → generate), promoted from the
segment builder's proven `AssetResolver`. Every resolution writes an auditable
`resolved_source`; scene *dicts* resolve losslessly via `resolve_dicts` (Phase 0
contract). `AssetEngine.from_config` wires the standard backends lazily.

Thin callers now: segment resolver (compat shim; the builder's four duplicate
tier factories are deleted), Director `select_clips` (footage + art through the
engine, honest `none(<reason>)` on misses), iterate's b-roll reresolve.
Parity verified on real plans (venezuela 25/25 vs old 8 matches, football
134/134 vs 16 — same matcher/gate, fuller index). Tests: `tests/test_asset_engine.py`.

## Architecture Consolidation — Phases 0–1 (2026-07-04)

**Phase 0 — safety net** (`bab7c50`): `ScenePlan` is a lossless, versioned contract
(schema_version 2; unknown scene keys survive in `Scene.extra`, top-level keys in
`ScenePlan.meta`); `nolan assemble -o` resolves relative paths against CWD and exits
non-zero on failure; `scripts/test_e2e_smoke.py` runs a fixture project through
anchor→stamp→render→annotate→assemble and asserts video ≡ audio duration + losslessness.

**Phase 1 — one narrated pipeline**: the Director now runs
`… slide_designer → generate_assets (ComfyUI, registry workflow + style suffix)
→ voiceover (local TTS, shared core) → align_narration (beat-anchored) → render
(assembles with the narration)`. `nolan orchestrate <project> --auto` produces a
narrated, sync-exact final.mp4 with zero custom scripts.

- VO core extracted to `src/nolan/voice_pipeline.py`; the webUI Voices op is a thin
  adapter over it (no drift possible). Voice resolution everywhere =
  `nolan.voiceover.resolve_voice_ref` (project.yaml `voice_id` → `tts.default_voice`).
- Voice-less projects still work: voiceover step skips with a clear note and the
  final is silent — set `voice_id:` in project.yaml to narrate.
- Scene iteration (`rerender_scenes`) keeps the narration in final.mp4 instead of
  replacing it with silence.
- Tests: `scripts/test_director_steps.py` (step sequencing + skip paths),
  `scripts/test_e2e_smoke.py`, plus a live `orchestrate --auto` acceptance run.

## Summary

NOLAN is a CLI tool that transforms structured essays into video production packages with scripts, scene plans, and organized assets ready for video editing.

## Video Deconstruction — the inverse Director (2026-07-04)

Reverse-engineer an **ingested library video** into its editorial plan, emitting the
FORWARD pipeline's vocabularies so the result is comparable/replayable:
beats → per-beat **pairing operator** (evoke_broll vocabulary: literal/knowledge/tonal/
conceptual/ironic/trait/relational/scale/text-graphic), **tempo** (tempo_plan's
energy/pace_dir/transition/motion_speed via `_levers` run in reverse), **motion treatment**
(motion-library vocabulary: hold/ken-burns-*/as-is/subtle-push), and a draft
`recovered_plan.json` in scene_plan schema.

- **Tier 1 — visual facts** (`src/nolan/visual_facts.py`, no LLM for motion): shot
  detection (reuses the sampler's `.scores.json` cache, falls back to HSV cut detection),
  **optical-flow motion classification** (Farneback; median flow → pan/tilt, radial
  divergence → push-in/pull-out, camera-speed-adaptive moving-pixel fraction → subject
  motion), optional **structured vision facts** per shot (asset_type/framing/
  on_screen_text/identity_hint — same providers as ingestion). Persisted to the new
  **`shots` table (library schema v8)** with `facts_version` for incremental re-runs;
  accessors `add_shots_bulk/get_shots/clear_shots/update_shot_vision_facts`.
  Deterministic rows persist BEFORE the vision pass; vision runs **concurrently**
  (semaphore, 5) and writes through per row — observable mid-run, crash-safe, and a
  motion-only run can be **vision-backfilled** later without recompute.
- **Tier 2 — interpretation** (`src/nolan/deconstruct/`): editorial **beats** (text-LLM,
  single call, gap/overlap repair, deterministic fallback), **operator classification**
  (batched text-LLM with a BGE said↔shown directness prior from `video_style.pairing`;
  band fallback), deterministic **tempo recovery**, evidence frame per beat, draft plan
  assembly (montage beats >8 shots collapse to one scene). Artifacts in
  `video_deconstructions/<slug>/` (extract.json, recovered_plan.json, frames/,
  synthesis_task.md).
- **Engines:** ~95% API-layer like ingestion (OpenCV + vision API + `create_text_llm`,
  i.e. OpenRouter qwen/gemini per config); ONE tmux Claude-agent dispatch at the end
  writes `breakdown.md` (beat sheet, asset inventory with ComfyUI prompts, editorial
  patterns) and refines the plan — mirrors `analyze_video_style`.
- **Hub:** `/deconstruct` page (library picker, agent selector, beat timeline colored by
  function with energy fill, per-beat cards with evidence frames, artifact viewers);
  routes `GET/POST /api/deconstruct*`; nav entry under Create.
- Tests: `scripts/test_visual_facts.py` (classifier + E2E on a generated 3-scene video +
  v7→v8 migration), `scripts/test_deconstruct.py` (mock-LLM beats/operators, extract E2E,
  plan schema, task brief, hub wiring).

### Hardening + pipeline integrations (2026-07-04, round 2)

**Quality fixes** (all Odyssey-run-evidenced): recovered plans now emit **per-shot scenes
with `montage_group` tags** (no more >8-shot collapse — internal cut rhythm is replayable);
**transcript identity cross-check** (`deconstruct/identity.py`, batched text-LLM) grades every
asset identity `narration-confirmed | narration-named | vision-claim` (narration wins; the
agent brief says web-verify remaining vision-claims); **beat-boundary snapping**
(`beats.snap_beats`) moves LLM beat starts to nearby chapter/text-card delimiter shots.

**UI**: per-beat **shot drill-down table** (camera/subject/treatment/asset/on-screen-text/
identity+source), minimal **markdown renderer** for breakdown.md, `?video=` deep-link, and a
**🔬 Deconstruct** button on every Library video row. Smoke-tested over HTTP on a test-port
hub against the real Odyssey deconstruction (page, list, meta, artifacts, frames, 400s).

**Creation-pipeline integrations**:
- **Template export** (`deconstruct/export.py` + `POST .../export-template` + UI): recovered
  beat structure → `assets/templates/scene_plans/decon-<slug>-v1/` (meta+skeleton+template.md)
  in the exact shape `orchestrator.template_match` scores — verified the matcher loads and
  ranks it. The real Odyssey structure is exported.
- **Clone mode** (`deconstruct/clone.py` + `POST .../clone` + UI): seeds a NEW script project
  whose `scriptgen/beatmap.md` is the recovered structure (constitution directive, per-beat
  pace tags from measured energy, word budgets scaled to target minutes, sponsor beats noted
  but excluded, provenance in meta + `reference_structure.json`). The v3 scriptwriter flow
  continues unchanged — this is the deconstruct→write bridge.
- **Video-style case studies**: `analyze_video_style` now passes any existing deconstruction
  breakdowns of corpus videos into the synthesis brief as citable beat-level evidence.
- **Retrieval enrichment**: `VideoIndex.get_shots_overlapping` + evoke_broll library
  candidates carry measured `shot_facts` (asset_type/camera/subject/treatment/framing), which
  surface in the library score prompt and the motion-pick prompt.
- **Roadmap**: `docs/NARRATIVE_ASSET_PAIRING.md` gains the **masterwork raid** operator row
  (evidence: Odyssey breakdown) + notes deconstruction as the operator-space evidence engine.
- Tests: `scripts/test_deconstruct_integrations.py` (runs against the REAL Odyssey extract:
  template export + matcher scoring, clone budgets/ad-exclusion/provenance, case-study brief,
  overlap lookup + prompt surfacing, new routes).

### Full-video chain fixes — timing, motion, krea2 default (2026-07-04, round 5)

Found while producing the first end-to-end reference-guided video (the-aeneid,
7:07 final.mp4 = cloned structure + tempo + 21 masterworks + 15 krea2 paintings +
18 layout cards + cloned-voice narration):

- **Narration owns duration** (three sites): `render_scene` and
  `stamp_tempo_motions` now prefer the ALIGNED window over the planner's "Ns"
  estimate, and `annotate_scene_plan` no longer overwrites aligned times with
  cumulative estimates (it was destroying `nolan align`'s work after every render).
- **`nolan align` now TILES scene windows** (`scenes.tile_scene_windows`): align
  gives each scene only its matched-words span, so pauses belonged to no scene and
  video ran ~25% shorter than audio; each scene now extends to the next scene's
  start (last → audio end), so total video ≡ narration.
- **Tempo→motion stamping** (`render.stamp_tempo_motions`, wired into the Director
  render step): image-backed scenes get a validated `still-motion` spec — treatment
  from the (reference-blended) energy via `motion_for_tempo`, duration from the
  aligned window. 36 Aeneid stills rendered via Remotion at the cloned rhythm.
- **`layout_spec` is a real Scene field** (parse + serialize): previously it
  survived only until the next `ScenePlan.load/save`, which silently wiped all
  slide_designer output (bit the-aeneid; restored via refine + feedback file).
- **krea2 is the default generation workflow**: `nolan generate` resolves
  `config.comfyui.workflow` (default `krea2-style-select`) through the workflow
  registry with `config.comfyui.style` (default "Dark Moody Atmosphere", leading
  comma handled) applied to the style-selector node; an explicit `--workflow`
  keeps manual control; falls back to the built-in SDXL workflow on registry errors.
- Voice cloning from a library video needs ONE segment:
  `VoiceLibrary.create_from_clip(video_path, t0, t1, ref_text=<segment transcript>)`.

### Archival-art sourcing — the masterwork-raid step (2026-07-04, round 4)

`src/nolan/art_sourcing.py` — scenes typed `archival-art` (named paintings/manuscripts/
statues) get REAL public-domain images. Deliberately a THIN ROUTER over existing
subsystems: museum/PD providers already in `image_search.py` (Commons/Met/ArtIC/
Cleveland/Rijksmuseum/Wellcome/LoC/+keyed) via a new `ART_SOURCES` preset;
`external_assets.semantic_match_for_scene` (library-first → ingest → CLIP) with a new
`img_sources` passthrough; `imagelib` for license-aware persistence/dedup/reuse.

- **Exact-title pass first**: the scene query usually NAMES the work — candidates are
  ranked by fuzzy title-token overlap (generic medium words stripped, which also fixes
  zero-recall long queries on Commons search). CLIP cannot tell Bernini's Aeneas group
  from any other marble; title text can. Semantic CLIP path is the fallback.
- **Download hardening**: verify the download RETURN VALUE and temp-then-move (a stale
  file at dest must never be blessed — found live); **curl fallback** for Wikimedia's
  upload edge, which TLS-fingerprint-blocks python-httpx regardless of User-Agent.
- Wired into **Director step 4** (after the video vector matcher; report line added) and
  standalone via `POST /api/source-art`. Stamps `scene.matched_asset`
  (project-relative — rendered by `nolan assemble` as a Ken-Burns still) +
  `resolved_source = "art:exact|library|ingest:<provider>"`.
- **Live validation (the-aeneid): 21/21 archival-art scenes matched**, named works
  verified by hash/inspection: the actual Vergilius Vaticanus, Bernini's Aeneas group
  (10.8MB Commons original, CC0), Augustus of Prima Porta, the Virgil mosaic,
  'Virgil Reading the Aeneid' (ArtIC), Delacroix's Barque de Dante.
- Tests: `scripts/test_art_sourcing.py` (title matching, stale-file regression,
  img_sources threading, exact-pass stamping).

### Reference-guided production (2026-07-04, round 3)

A deconstruction-referenced project now flows coherently through the whole pipeline —
the reference shapes structure, scenes, and tempo, not just the script's beatmap:

- **Attach to existing project** (`clone.attach_reference` + `POST
  /api/script-projects/{slug}/attach-deconstruction` + a Reference row on
  `/script-projects`): seeds the same artifacts clone mode creates on ANY existing
  project; refuses to overwrite an existing `beatmap.md` without `replace_beatmap`
  (409 → confirm in the UI). Badge shows the attached reference.
- **Tempo cloning** (`tempo_plan.blend_with_reference` + Director `tempo_enrich`
  wiring): the reference video's MEASURED energy curve (ads excluded, position-
  normalized) blends 50/50 with the script-derived curve; transition/motion_speed/
  shots re-derived via `_levers`, pace_dir recomputed, source = `…+reference`.
  Deterministic; degrades to current behavior with no reference.
- **Scene-planning hints**: the Director's `script_to_scenes` prompt injects
  `reference_structure_path` (per-beat operator / dominant_treatment / asset_types)
  when present; `skills/orchestrator/script-to-scenes.md` §3c explains how the agent
  leans on the reference's choices within the style guide's vocabulary.
- **Send recovered plan → project** (`POST /api/deconstruct/{slug}/send-plan` + UI):
  copies `recovered_plan.json` (scene_plan schema, per-shot scenes) into a project's
  `scene_plan.json` — the `/scenes` page and Director steps 3–6 operate on it.
  Existing plan requires `confirm` and is backed up to `scene_plan.json.bak`.
- HTTP-smoke-tested end-to-end on a test-port hub (attach fresh/409/replace,
  send-plan fresh/409/confirm+bak, 47-scene Odyssey plan landing on disk, UI controls).
  Tests extended in `test_deconstruct_integrations.py` (attach, blend, wiring).

## Showcase previews wired (2026-07-03)

**What changed.** The `/showcase` page ("Motion Effects Showcase") was fully built and wired but
every thumbnail was blank: (1) the effect card `<video>` src double-prepended the `/previews/`
path (`/showcase/preview//previews/x.mp4` → 404), and (2) no preview clips had ever been rendered
(`render-service/public/previews/` was empty). Fixed the URL by stripping to the basename
(`effect.preview.split('/').pop()`), and added `scripts/gen_showcase_previews.py` which batch-renders
a short clip for every effect from the render service (`:3010`) using each effect's `defaults`,
copying the output into `public/previews/<name>.mp4`.

**Usage.** `D:\env\nolan\python.exe -X utf8 scripts/gen_showcase_previews.py` (optionally pass
effect ids to render a subset). **Result:** 52/53 effects render (only `audio-waveform` fails —
needs an audio asset). Thumbnails load and animate on hover; verified via a real-browser screenshot
of `/showcase`.

## Script v3 — style-fidelity upgrade: craft-vs-clothing + voice pass (2026-07-02)

**What changed.** The v3 pipeline honored the style guide's *skeleton* (structure) but was losing its
*muscle* (rhetorical devices / sentence-level style) and *color* (vivid anchors) to draft-time recall,
and was blindly copying *channel-identity furniture* (sponsor reads, persona catchphrases like "I'm
literally a stickman"). Root cause: only structure was committed to an artifact; everything else
depended on recall. Fixed in the shared task-brief generator (`src/nolan/scriptwriter/tasks.py`), so
`prep_task` / `draft_task` / `v3_task` and every future project inherit it:

- **`_STYLE_KERNEL` (the four layers).** A guide mixes SKELETON + MUSCLE + SKIN (honor fully) and
  CLOTHING (channel identity). Rule: **skip** sponsor/coded-URL reads; **adapt-or-skip** persona
  labels / catchphrase sign-offs / recurring-segment names (take the *function*, never copy the
  literal identity); use the guide's **Exemplar Lines** only as a cadence tuning-fork.
- **Facts legend** now preserves vivid comparators, **bundles each claim's rebuttal on the same line**
  (so in-beat steel-manning survives), and orders hook facts **concrete-first**.
- **Beat line commits BONE + MUSCLE + COLOR:** every `beatmap.md` beat now carries `devices:` (named
  from the guide's Rhetorical-Devices/Sentence-level catalog) + `anchors:` (the exact facts/quotes to
  deploy), and a top-of-file **clothing-decisions** block.
- **New "voice pass" step → `stylecheck.md`** — the style twin of the fact-check: verify every
  `[universal]` device landed, revise flattened beats toward the guide's exemplars, confirm no
  identity content leaked. The device budget is a **floor, not a quota** (a device may be withheld
  when a beat reads better without it).

**Validation.** Re-ran all three script projects (three distinct guides — great-books braid, stickman
both-sides argument, art-stories mystery — plus both the supplied-angle and no-angle paths and the
⚠ LARGE chunk-read path). A blind agent driven only by the regenerated `v3_task.md` matched or beat
the hand-tuned inline runs *and* fixed the clothing handling those runs themselves got wrong (e.g.
adapted "I'm literally a stickman" → a neutral equivalent; skipped the sponsor). Prior outputs are
preserved under each project's `scriptgen/ab/`. Guard test `scripts/test_scriptwriter.py` stays green.

## Script Projects — v3 pipeline + new source types (2026-07-02)

Reworked the grounded script writer (`src/nolan/scriptwriter/`, `/script-projects`). The writer is
still agent-native (a task brief dispatched to a `nolan2` tmux Claude agent) but is now **v3**.

- **New source types** (`add_source` + hub routes + UI): **YouTube** link → subtitles fetched at
  add-time (`youtube.py:fetch_transcript`, no video download); **Library video** → its transcript
  concatenated from indexed segments (a picker); **MinerU book** (.md) → stored **uncapped** (no
  truncation anywhere in the source→writer path; large sources are flagged ⚠ LARGE + chunk-read).
- **v3 = the default pipeline** (`tasks.v3_task`; auto in one pass, or semi via `prep_task`→gate→
  `draft_task`). The design principle: **the style guide is the constitution.** v3 (1) grounds facts
  with a rich taxonomy (`src·purpose·beat·conf·role`), (2) **infers the spine *type* from the guide**
  (human/mystery/argument/… — not hardcoded) and picks a **resonant, right-type angle** scored on
  resonance + evidence + style-fit, (3) **beat-maps** it onto the guide's own Hook/Structure/Pacing/
  DON'T sections (retention comes from the guide, not a boilerplate), (4) drafts, fact-checks, and
  writes a run **report**. A supplied brief angle is **honored** (short-circuits the gate).
- **Persistence / A/B:** every run keeps `facts.md`, `angles.md`, `beatmap.md`, versioned
  `drafts/`, `factcheck.md`, `citations.md`, `report.md`; the legacy one-shot writer (`/write`) is
  retained as an A/B baseline; drafts are promoted to `script.md` (not clobbered). Modes: auto/semi;
  per-project narrative style is now editable in the detail panel.
- **Cemented (2026-07-02):** now that the A/B favored v3, the intermediate **v2 auto path was
  retired** (`auto_task` + its `_angles_block`/`_draft_block` helpers; the `phase="auto"` route
  option; the UI's dead `auto` label). v3 (auto via `phase=v3` + semi via `prep`→`draft`) is the
  **sole grounded pipeline**; the **v1 one-shot** (`write_script_task`, `/write`, the "⧗ Baseline"
  button) is kept as the only A/B comparator. `/run` accepts `prep|draft|v3` (v3 default). WebUI:
  `runControls`/`btnV3` (was `v2Controls`/`btnAuto`). Test: `scripts/test_scriptwriter.py` covers
  the v3 briefs (spine-infer, beat-map, resonance scoring, honored supplied angle) + v2 retirement.
- **Agent selector fix:** `/script-projects` now has an **Agent** dropdown (populated from
  `/library/api/tmux-sessions`, mirroring `/script-styles`); `runPhase`/`writeScript` send the
  chosen `session` in the POST body. Previously no selector existed and the frontend sent no
  `session`, so every run silently defaulted to `nolan2`. The `/library/api/tmux-sessions`
  endpoint was also **moved out of the `if db_path` library gate to top-level** (it only runs
  `tmux ls`), so the agent selector works regardless of library state; path kept for back-compat.
- **Validated by A/B across 3 subjects × 3 guide types** (Great Books = biographical spine,
  art-stories = mystery spine, stickman = data-grounded-argument spine): v3 inferred all three
  spine types correctly and was **≥ the baseline everywhere** — a large win where the angle is blank
  and there's an under-exploited resonant framing (Homer), converging with the baseline where the
  guide is prescriptive and/or the angle is supplied (Holbein, AI-data-centers).

## Evocative (tonal) b-roll search (2026-07-01)

`/broll` page + `src/nolan/evoke_broll.py` — find b-roll that carries a line's **emotion**,
not a literal illustration. Pipeline: LLM **metaphor bridge** → **stock** (cheap tiers) or
**library** (BGE vectors) retrieval → **vision scoring + period/locale gate** (nature/abstract =
universal) → **listwise "would an editor cut this?" accept**, returning matched picks or
**UNMATCHED(reason)** (precision over coverage). UI: Stock↔Library toggle, per-provider
checkboxes, literalness slider, mood steer. Endpoints `GET/POST /api/broll/*`.

This is **operator #1** of a general **narrative→asset pairing engine**. The full operator
space (conceptual/isomorphic, scale, ironic counterpoint, trait-embodiment, relational, rhythm…)
and how each extends to ComfyUI generation + Remotion/motion composition is mapped in
**`docs/NARRATIVE_ASSET_PAIRING.md`** (design roadmap).

### Scale / tangibility operator — count-up over footage (2026-07-02)

Operator #6 on `/broll` (**Approach: Scale**). A big number is made tangible by counting it
up over a body-sized referent. Bridge: **quantity extraction** (derives a defensible number
even when only implied — "a vast fleet" → 1,200) + a **period-safe / timeless tangible
referent** ("100 billion stars" → grains of sand; hard periods avoid modern-scale clichés).
The referent b-roll is scored for *scale + calm negative space*, then the **`StatOver`**
Remotion composition renders the count-up over the still/footage. Abstains (**UNMATCHED**)
when there's no number or stock lacks a clean referent (precision > coverage).

**Theme-aware** (the key requirement): the count-up number + caption are styled entirely by
the video **theme** via `resolveTheme` in `render-service/remotion-lib/src/theme.ts` (same as
counter / kinetic-text — `th.fontFamily / th.fg / th.accent / th.bg`), **not hardcoded**.
Theme is selectable on `/broll` (dark-editorial | light | high-contrast + optional accent
override) and via `nolan broll --theme`.

- **Composition**: `StatOver.tsx` (registered in `Root.tsx`) — count-up via `interpolate`,
  comma formatting, tabular-nums, theme-keyed legibility scrim; still (`background`) or live
  footage (`videoSrc`) backdrop.
- **Motion registry**: `stat-over` `MotionEffect` (`src/nolan/motion/registry.py`); executor
  routes it to `nolan.still_motion.render_stat_over` (shared params `theme`, `accent`).
- **Endpoints**: `POST /api/broll/stat` → `operations.preview_stat`. CLI `nolan broll -op scale
  [--theme] [--render]`. Usage: `nolan broll "…100 billion stars…" -op scale --render`.

**Example:** *"There are a hundred billion stars in our galaxy alone."* → bridge derives
100,000,000,000, picks the grains-of-sand referent, retrieves stock, and renders the number
counting up over falling sand in the chosen theme's accent.

## Rhythm/tempo + full-script context (ScriptContext) (2026-07-02)

Three pipeline-agnostic modules that give asset/motion/tempo decisions the whole-script context
they lack today (every current stage decides from one line in isolation). Built after running the
real orchestrator on the Homer script to scope the gaps empirically.

- **`script_context.py`** — `ScriptContext.load(project)` assembles the `scriptgen/` workspace:
  `script.md` beats + timecodes, `beatmap.md` `pace:a|d` tags + coverage, `facts.md` clusters,
  meta/spine. `brief()` + `beat_context(i)` are the prompt-ready digests.
- **`tempo_plan.py`** — `design_tempo(ctx, llm)` runs ONE whole-script Editorial Arc pass →
  per-beat energy curve + render levers (transition cut/dissolve/fade, motion_speed, shots),
  toward the per-flow pacing profile (punchy/contemplative); rule-based fallback from the pace
  seed. `apply_to_plan(plan, tempo)` writes `transition`/`energy`/`motion_speed` onto every scene
  (mapped by section=beat). `motion_for_tempo(bt)` → (motion_id, duration) is the renderable lever.
  Scene model gained `energy` + `motion_speed` (round-tripped).
- **`knowledge_query.py`** — `expand_queries(ctx, beat, llm)` taps the model's knowledge to name
  SPECIFIC era-correct assets (artist+title) + derives period/locale; `build_scene_lead_map` feeds
  `match_broll_v2(knowledge=True)` (via `build_query_variants(lead_queries=…)`), replacing the
  proper-noun-stripping fallback.

**Validated on the real Homer plan (57 scenes):** flat all-hard-cuts → arc-driven fade/dissolve/cut;
knowledge queries retrieved the genuine Turner *Ulysses Deriding Polyphemus* + a Blinding-of-
Polyphemus sculptural group. Preview: `scripts/tempo_gallery.py` → `/broll-gen/tempo_homer.html`.
Design + gap analysis in `docs/NARRATIVE_ASSET_PAIRING.md`. Tests: `tests/test_tempo_context.py` (13).

**Architecture note:** keep `nolan orchestrate` (a strong agent spine — its `script_to_scenes`
agent already paces via per-section duration+cut-density and writes semi-specific queries). These
modules layer on as deterministic post-passes (own the empty fill levers: transition/energy/motion
+ query depth) + a future context-injection of `ScriptContext` into the agent prompts. Not a rewrite.

## Vector embedding status + auto-reconcile (2026-07-01)

Indexing a video populates SQLite segments but embedding into the vector store was a
best-effort afterthought (CLI auto-synced but swallowed failures; the hub didn't at all),
so videos could be indexed-but-unsearchable and drift silently. Now:

- **Live embedding status** (`VectorSearch.get_embedding_status()`): per-video state —
  `synced` / `stale` (re-indexed since embed) / `unembedded` — computed from the vector
  store + SQLite (no stored flag that can lie). Plus a summary (`needs_embedding`).
- **Single-video embed** (`VectorSearch.sync_video(id)`, shared `_embed_video` helper) and
  op `operations.embed_video`.
- **Hub API:** `GET /library/api/embedding-status`, `POST /library/api/videos/{path}/embed`,
  `POST /library/api/reconcile-vectors`. Hub **startup auto-reconciles** (incremental → cheap
  if nothing to do; non-blocking background job) so stragglers get embedded automatically.
- **Library UI:** per-video badge (searchable / stale / not embedded), a manual **Embed**
  button, and an **Embed all** banner when any video isn't searchable.

Verified: status / single-embed / unembedded-detection and all endpoints (incl. 404) pass.

## Background removal (cutout) — rembg (2026-07-01)

Turn any image/frame into a transparent RGBA cutout for compositing over scenes.
CPU-based, runs **off the GPU lock** (no contention with ComfyUI/OmniVoice), always available.

- `src/nolan/cutout.py` — `remove_background(img, model) -> PIL RGBA` + `cutout_file(src, dst, model)`.
  Lazy import, per-model session cache. Models: **isnet** (default, fast), **birefnet** (best
  edges/hair, ~1GB, slower), **u2net** (baseline) + extras (u2netp, isnet-anime, birefnet-portrait, silueta).
  Optional `alpha_matting` for soft/hairy edges.
- CLI: `nolan cutout IMAGE [-m isnet|birefnet|u2net] [-o out.png] [--alpha-matting] [--to-library]`.
- Hub: `POST /api/images/{id}/cutout {model,scope,project}` → adds the cutout back as a new
  library asset (source="cutout", tags=["cutout", model]); "Cut out" button + model selector on `/images`.
- Verified: all 3 models produce clean RGBA cutouts on a real image (birefnet tightest edges;
  isnet ≈ u2net; isnet ~1–2s/img CPU).
- **Dependency caveat**: `pip install rembg[cpu]` upgrades numpy/pillow past what opencv/moviepy
  pin. Fix: keep `numpy<2.3` + `pillow<12` (satisfies opencv+moviepy; rembg still runs fine at
  runtime despite its stricter declared pins). Verified opencv+moviepy+rembg all import together.

## Skill registry — manage the hybrid pipeline's prose units (2026-06-30)

NOLAN is now a **hybrid** pipeline: a deterministic engine that hands off to an agent at judgment
points (plan / author / invent / edit), where a *skill* (markdown) carries the craft. Code has a
compiler + tests; prose rots silently. `nolan.skills` gives skills the two things they lacked —
a **verifiable binding** and an **identity/lineage** — so drift becomes a failing check.

- **`src/nolan/skills/`**: manifest frontmatter schema (`id/kind/purpose/status/version/handoffs/
  uses/overrides/loaded_by/documents/evals`); `load_skills()`, `build_index()` → `skills/index.json`,
  `lint_skills()`. Run `python -m nolan.skills` to regenerate + lint (exit 1 on errors).
- **Linter** (the "test" prose never had): unique ids · valid kind · `uses`/`overrides` resolve ·
  `loaded_by` paths still reference the skill (dead-binding) · **grammar staleness** scoped to a
  flow's palette (`documents: {palette: <flow>}`) · malformed-manifest (a `---`-fenced doc with no
  valid id, e.g. a YAML `": "` trap, is flagged not silently dropped). It immediately caught a real
  bug — `EndCard` was in the explainer + common palettes but no `EndCard.tsx` exists — now removed.
- **Two roots**: `skills/` is the consolidated home; `.claude/skills/` (harness-invoked) is
  cataloged in place. A `.md` is a skill iff its frontmatter has an `id`, so migration is incremental.
- **13 skills consolidated** into `skills/{common,flow,explainer,art}/` with a resolved lineage graph
  (e.g. `flow.authoring` → `common.{script-style,outline-format,chapter-craft}` + `explainer.script`).
  The `web-video-presentation` skill was split: shared craft → `common/`, web-page scaffold retired,
  theme tokens kept at `themes/` (render hardcodes that path).
- **Phase 2 — `handoff()` seam**: `handoff(skill_id, ctx)` resolves a skill, returns its body
  (frontmatter stripped) for prompt injection, and logs the invocation to
  `.nolan/skills/invocations.jsonl` (lineage becomes observable; the log feeds Phase 3). The 8
  `orchestrator/` + 1 `publish/` prompts moved into `skills/{orchestrator,publish}/` and
  `director.py`/`builder.py` now call `handoff()` instead of `read_text()` — verified
  byte-identical to the originals. `fleet.py`'s CITE-style reference resolves via `skill_path()`.
  `select-clips` (the LLM pass the vector matcher replaced) is cataloged `deprecated`. 22 skills,
  lint 0/0.
- **Phase 3 — feedback ledger**: `record_feedback(skill_id, note, ctx)` logs a human gate
  correction against the skill VERSION that produced the artifact (`.nolan/skills/feedback.jsonl`);
  `skill_health()`/`health_report()` surface the **revision queue** (skills with the most *open*
  corrections — those against the current version). Bumping a skill's `version` retires its open
  feedback (the corrections were about the prior version) while `feedback_total` persists — so the
  ledger is the changelog for the next revision. Wired at the two real HITL gates: the orchestrator
  refine dispatcher (`run_refine_step` → the producing skill) and the flow Scene-page edit
  (`fleet.dispatch`'s human note → `flow.edit-contract`/`scene-edit`). `python -m nolan.skills
  health` prints the queue. Verified end-to-end incl. the version-reset semantics.
- **`/skills` UI** (hub page): three views over the registry — **Registry** (skills grouped by
  domain: kind/status badges, purpose, an "N open" correction badge; click → detail drawer with
  forward+reverse lineage chips, health stats, the correction ledger, and the rendered doc),
  **Lineage** (an SVG graph — nodes by domain column, `uses`/`overrides` edges, hover-to-highlight,
  click → detail), and **Health** (the lint result + the revision queue). Backed by
  `nolan.skills.ui_index/ui_detail/ui_graph` and `/api/skills[/{id}|/graph]` in `hub.py`; linked in
  the sidebar (System group). The skill-management system (Phases 1–3 + UI) is complete.

## WebUI + iPhone design-system overhaul (2026-06-30)

Hardened the hub webUI (FastAPI, 21 templates + `static/nolan.css` + `nav.js`) and its mobile
experience, guided by the ui-ux-pro-max skill (validated the existing dark-studio + cyan theme
as correct for a creative video tool — kept, didn't re-theme). Verified with headless-Chrome /
puppeteer screenshots at desktop + true iPhone (390px).

- **Design system v2** (`static/nolan.css`, additive/backward-compatible): token scales
  (type/spacing/radius/shadow/motion), base `h1–h6`, consolidated components (`.btn` sizes+
  variants, `.field` hint/error, `.chip`, `table.nolan`, `.skeleton`/`.spinner`/`.inline-error`/
  `.empty-state`, layout utilities). All pages inherit it.
- **iPhone / shell** (`nav.js` + css): mobile **bottom-tab bar** (SVG icons, active state,
  thumb-reach) + content spacer, 44px touch targets, `dvh`, `prefers-reduced-motion`,
  `aria-current`/labeled nav, focus rings.
- **Page refits**: hub (denser tiles 300→240, **title ellipsis + 2-line desc clamp**, trimmed
  56px→34px hero), clips (same tile fix). Truncation added to dynamic names across library,
  agents, showcase, lottie, extract, script_styles, script_projects, video_styles; showcase
  grid 280→240. scenes left conservative (concurrent edits).
- Deleted legacy `templates/index.html` (dead: unrouted, depended on non-existent APIs).

## New theme — `neubrutalism` (25th theme) (2026-06-30)

Second gap-driven theme (the cheap, render-safe candidate from the gap analysis). Internet-
native neubrutalism: bright white canvas, thick 3px black borders (`--bw-1: 3px`), hard
offset solid-black shadows (`--card-shadow: 7px 7px 0`, no blur), hot-magenta accent (no
glow), chunky Space Grotesk, 8px rounded corners, faint black dot grid, bouncy motion.

- `themes/neubrutalism/{tokens.css,theme.json}` + `selector.json` entry
  (ranks #1 for bold/indie/dev-tool/design briefs, well clear of bauhaus-bold).
- Deliberately distinct from its cousin **bauhaus-bold** (cream-on-dark-shell, primary-blue,
  0-radius, Archivo Black, black stage frame, modernist-restrained): neubrutalism is
  white/light, magenta, rounded, dot-grid, no stage frame, playful.
- Verified by real `still.mjs` renders (hero / cards / table / bar) — flat hard look, all
  accent-driven (magenta bars, pink table-highlight, no glow). Light theme + flat color =
  zero banding risk, no dither needed.

## Theme metadata enrichment + health check (2026-06-30)

Phase 3 of the theme-system work. Each `theme.json` now carries two **derived** fields, and
the system has a validator that guards its invariants as themes grow.

- `themes/scripts/enrich_themes.py` — writes per-theme `fonts`
  `{displayEn,body,cjk,mono}` (parsed from that theme's `tokens.css` — CSS stays source of
  truth) + `avoidFor` (anti-pattern tags promoted from `selector.json`). Idempotent;
  `--check` reports drift without writing. Applied additively to all 24 theme.json (no
  reformatting of the hand-crafted files).
- `themes/scripts/validate_themes.py` — health check: every theme has
  theme.json + tokens.css, valid 4-key #hex preview, a selector entry (no orphans), tone
  agrees with mood, and enrichment is current. Exit 1 on any failure. Run: `OK — 24 themes
  valid`.
- Wired `avoidFor` into SKILL.md Checkpoint-Plan prep step 1 (agent excludes a theme when
  content hits its anti-patterns). Documented in `references/THEMES.md`.
- **Deferred (YAGNI)**: per-theme chart-pairing hints — overlaps the separate data-shape→
  chart-type picker idea and was speculative; left out rather than guessed.

## New theme — `aurora-mesh` (24th theme) (2026-06-30)

Gap-driven theme expansion (Phase 2 of the theme-system work). Gap analysis
(`themes/THEME-GAP-ANALYSIS.md`) found the 23 themes already cover
most of ui-ux-pro-max's style taxonomy; the strongest true whitespace was an **aurora /
gradient-mesh** AI-era look. Built end-to-end:

- `themes/aurora-mesh/{tokens.css,theme.json}` — deep indigo-black
  canvas; signature = soft 4-blob radial gradient mesh (violet/magenta/teal/indigo, `screen`
  blend) with a center scrim for text legibility. Space Grotesk + Manrope (both already
  loaded in `_lab_chapter/src/index.tsx`), electric-violet accent. Color seeds video-adapted
  from the skill's NFT/Web3 + Generative-Art palettes. No code registration needed — themes
  are staged by `stage.mjs` copying `tokens.css` → `_active-theme.css`.
- `selector.json` entry added → ranks #1 for AI/LLM and web3 briefs.
- **Verified by real render**: `still.mjs` via **Windows node** (WSL node's esbuild binary is
  win32-only) on a text-centric job; legibility + signature confirmed at 1080p.
- **Banding tested + fixed**: rendered a 6s h264 mp4, extracted frames with the bundled
  ffmpeg. 1:1 clean; 6× shadow-lift showed mild 8-bit banding (platform re-encode risk).
  Fix: a faint SVG-fractalNoise dither layer added to `--surface-pattern` (desaturated,
  alpha 0.12). Re-render under the same 6× lift → contours gone, grain invisible at 1:1.
- Best for: AI/大模型发布, 生成式艺术, web3/NFT, 现代 SaaS keynote, 未来科技/概念解读.

## Theme selector — explainable theme recommendation (2026-06-30)

Checkpoint-Plan 选主题 used to be ad-hoc: the agent eyeballed 23 `theme.json` files and
guessed from Chinese-only `bestFor`. Added a deterministic, **explainable** scorer.

- Reasoning table: `themes/selector.json` — adds the matching layer
  the raw themes lack: per-theme English `tags`, `tone`/`energy`/`formality` axes, and
  `avoid` anti-patterns (+ a synonym map for EN/中文 topic terms). `mood`/`bestFor` stay
  source of truth. Pattern borrowed from the ui-ux-pro-max skill's `ui-reasoning.csv`,
  re-authored for video themes on the content-topic axis.
- Scorer: `themes/scripts/select_theme.py` (stdlib) — scores a brief against
  `tags` + `mood` + `bestFor` (Chinese substring) + tone, returns top-N with the exact
  signals that fired. `--tone` (soft nudge), `--top`, `--json`. Falls back to safe
  defaults on no match; warns on stderr if a theme has no selector entry.
- Usage: `python scripts/select_theme.py "<brief>" [--tone dark] [--top 3]`. Wired into
  SKILL.md Checkpoint-Plan prep step 2 and documented in `references/THEMES.md`.

## Flow art block — `PhotoGrid` (2026-06-30)

New `_lab_chapter` library block **`PhotoGrid`** for the art flow: a full `cols×rows` wall
of image tiles that builds **column-by-column**, settles into the complete grid, then
**pulses a couple of named tiles** (each fades IN → holds → fades OUT, accent ring +
caption, the rest dim back) on their narration cues. Pure function of frame + grid shape,
so 40 tiles is just data.

- Block: `render-service/_lab_chapter/src/blocks/library/PhotoGrid.tsx` (registered in
  `library/index.ts`; added to the **art palette** in `web-video-lab/flows/registry.json`).
- Ingest passthrough: `cols` / `rows` / `order` / `highlight` added to the `art_ingest.py`
  prop whitelist. Contract: `revealFrames[0]` = fill start; `revealFrames[1..]` pair with
  `highlight[]` tile indices.
- First use: holbein-dance-of-death `beat_02` — a 5×8 grid of all 40 Dance-of-Death
  woodcuts, filling col-by-col, then highlighting *the abbot* and *the knight* as the
  voiceover names them ("hauls an abbot away… skewers a knight").

## Scenes page — asset preview, drag-drop, @-mention comments (2026-06-30)

Three human-in-the-loop upgrades to the Scene Plan Viewer (`templates/scenes.html`),
all additive — existing tap-to-add/select flows are unchanged.

- **Preview on add (pictures + clips)**: a ⤢ button on every picker result and tray
  card opens a modal — full image for pictures; for clips a `<video>` seeked to the
  clip's in-point and JS-bounded to its out-point (loops the segment). Backed by a new
  range-enabled `GET /scenes/api/source-video` (Starlette FileResponse honours `Range`,
  verified `206 + content-range`), so clips play without being materialized.
- **Drag & drop (desktop)**: tray cards are draggable to reorder the montage (persists via
  the existing `op:"reorder"`); dropping local image/video files onto a scene row uploads
  them (`POST /scenes/api/scene/upload` → project `assets/uploads/`) and attaches via the
  existing `op:"add", source:"path"`. Desktop-only by design (no native touch DnD); mobile
  keeps the picker.
- **@-mention in comments**: typing `@` in a scene's comment box autocompletes that scene's
  bound assets (thumbnail + id + label). The note keeps `@a1` tokens, which
  `revise.resolve_asset_mentions()` expands server-side to `[asset a1 "label" (kind, in-out)]`
  for **both** the revise-LLM (`revise_scene`) and the dispatched Claude agent
  (`fleet.dispatch`) — so instructions point precisely at a picture/clip.

## ComfyUI — style-selector workflows (2026-06-30)

Registered ComfyUI workflows can now expose an in-graph **style selector**
(ComfyUI-Easy-Use `easy stylesSelector`) as a pickable dropdown in the Sample runner.

- **WorkflowEntry** gained `style_node` / `style_input` (default `select_styles`) /
  `style_group` / `default_style` (`workflow_registry.py`). `build_client(..., style=…)`
  emits `node_overrides=["<style_node>:select_styles=<style>"]` so the chosen style is
  applied without touching the prompt chain.
- **Auto-detect**: `find_style_node()` (`comfyui.py`) finds the selector node + its group +
  default; the `POST /api/comfyui/workflows` handler fills the style fields automatically.
- **Style list**: served by `GET /api/comfyui/styles?workflow=<slug>` from a local
  `workflows/styles/<group>.json` (ComfyUI's `object_info` does NOT expose Easy-Use styles).
- **UI**: the `/comfyui` Sample runner shows a Style dropdown only for workflows that have a
  selector; it threads `style` through `comfyui_sample` → `build_client`.
- **First workflow added**: `krea2-style-select` (Krea 2 Turbo t2i; prompt node 80, style
  node 77, 275 Fooocus styles). Prompt → node 80 (PrimitiveStringMultiline, NOT the
  style-fed CLIPTextEncode). Verified by a real generation (1600×904, sai-cinematic applied).
- **Adding more**: drop the API-format JSON via `/comfyui` → "Add workflow"; any
  `easy stylesSelector` is detected automatically (add a `workflows/styles/<group>.json`
  for its dropdown list).

## Art explainer flow + pre-render QA gate (2026-06-29)

The `web-video-lab` art flow (image-first explainer) is proven end-to-end and hardened
with a tiered pre-render QA gate.

- **Dance of Death, all-Remotion**: the full 8-beat Holbein *Dance of Death* (6:23, 11508
  frames) renders entirely in Remotion from real NOLAN voiceover word-timestamps (no
  TTS/Whisper — `art_ingest.py` assembles the job). Blocks `ArtworkStage` (camera tour +
  spotlight + wall-label), `DetailLoupe` (crop-beside-whole), `ImageCompare` (two artworks +
  drift). Delivery: `web-video-lab/art/final/dance-of-death.mp4` (faststart).
- **Pre-render QA gate** (`art_check.py`, cheapest-first, fail-fast) — *check per beat before
  the full render, never after*:
  - Tier 0 `art_validate.py` — structural (image/audio paths resolve, focus rects in-frame,
    reveal-slot count vs block arity, block name in `LIBRARY` registry). ~1s.
  - Tier 0 `pacing_lint.py` — temporal (WPM, first-reveal, gap, density). ~1s.
  - Tier 1 `art_contact.py` + `still.mjs` + `_montage.py` — spatial: 1–2 `renderStill` per beat
    through the **shared `stage.mjs`** (so stills match the real render), a labeled **contact
    sheet**, and an auto black/empty-beat flag. ~25s for the whole video vs ~7min full render.
- **Usage**: `python web-video-lab/art_check.py art/<name>.job.json --profile art` → GREEN gates
  the full render. Negative-tested (bad path + out-of-bounds rect → blocked at Tier 0).
- **Benefit**: the two defects found this build (DetailLoupe clipped off-frame; ImageCompare
  single-panel) are Tier-1 catches surfaced in ~25s on one sheet, not at minute 7 of a render.
  Per-beat gating is also the prerequisite for safe parallel (subagent) beat rendering.

### NOLAN flow integration (`src/nolan/flows/`)

The art flow is now invokable *through NOLAN* as a **flow** — a descriptor over one shared
engine, not a per-scene motion effect (see `web-video-lab/flows/INTEGRATION.md` for why the
per-scene motion registry was the wrong seam). No NOLAN core scene/motion code touched.

- **`src/nolan/flows/`**: `base.run_flow(flow, spec)` = the shared engine (ingest → gate →
  render → deliver); `get_flow(id)` builds a `Flow` from the tenant's ingest adapter + the
  registry config; `art.py` is the first tenant (assemble-ingest). `render_chapter()` drives the
  `_lab_chapter` Remotion bundle. Runs under `python3`, subprocess-out to Windows node (matches
  the lab precedent; CLI bridge deferred).
- **Flow = descriptor, 5 divergence axes**: ingest (code) · authoring grammar (skill/docs) ·
  block palette · pacing profile · theme/fx defaults. Everything else (job schema, gate, render
  engine, 39-block library, delivery) is shared. art = the explainer engine extended with an
  assemble-ingest + the camera-tour block class + contemplative defaults.
- **Palette differentiation wired** (was declared-but-unenforced): `registry.json` gains a
  `common_palette`; `art_validate.py --flow <id>` soft-**warns** on blocks outside the flow's
  palette (RAW bespoke allowed-but-flagged, shared set exempt); `--show-palette <flow>` lists the
  blocks to reach for (authoring aid). Caught a real gap (`PhotoMontage` missing from the art
  palette).
- **pacing_lint gap-FAIL**: `dead_gap_fail_s` is now enforced (was warn-only) — explainer hard-
  fails ≥9s of dead air; art's 99s threshold keeps long contemplative holds legal.
- **Integration test**: `python -m nolan.flows.run --flow art .../dance.spec.json` rendered the
  whole Dance of Death through the runner → **byte-identical** to the standalone `art/final/`
  render (147,322,164 bytes, 11508 frames). Delivered to `projects/holbein-dance-of-death/video/`.

### Explainer tenant promoted in-process (2026-06-30)

The **second** flow tenant is now first-class. `web-video-lab/gen_spec.py` (the explainer's
byo-script ingest — anchor-based chapter spec + per-step Whisper word-timestamps → render job)
is ported into `flows/ingest.py::ingest_explainer`, wired through `flows/explainer.py`
(`INGEST`) and registered in `get_flow`'s tenants (`{"art", "explainer"}`).

- **Interpreter-agnostic**: the lab `gen_spec` only ran under WSL `python3` (its `wavDir`/
  `wordsCache`/`segments` are `/mnt/...` POSIX paths). The port runs `_localize` on those reads
  and `_to_win` on `audioDir` (node-side `audioSrc`), so it now runs **in-process under the nolan
  env Windows python** like the WebUI/CLI — same as `ingest_art`.
- **Parity verified**: `ingest_explainer` on `specs/tailtrading.spec.json` produces a job
  **byte-identical** (canonical-JSON diff) to `gen_spec`'s — 6 steps, 5001 frames
  (HeroStatement/StatCount/ListReveal/PaperFigure/DataTable), with computed `revealFrames` and
  script-relabeled `captionWords`.
- **Helpers ported**: `_NUM` (number-word↔digit so anchor "two" matches whisper "2"), `_canon`,
  `_wav_seconds`, `_relabel_captions` (difflib carries authoritative script spelling onto whisper
  timing), `_resolve_explainer_anchor` (`word` | `@start` | `@<sec>` | `@f<frac>`).
- Both tenants now share the same engine below the job JSON (gate → render → deliver → scene
  view → edit).

### Explainer generate-from-source asset-prep promoted (2026-06-30)

The explainer's **second ingest mode** (`generate-from-source`, registry.json) is now promoted
in-process as `flows/source.py` — the *deterministic* half: turning a source paper into the
chapter spec's input assets. (Spec authoring — pick figures, write script, place anchors — stays
a skill handoff to the agent; `ingest_explainer` then assembles.) Exposed on the tenant as
`explainer.PREPARE`.

- **`figure_catalog` / `extract_figure`** (PIL) — catalog a MinerU `content.md` or arXiv HTML's
  figures, then lift one (trim near-white margins, optional matte→transparent) for the
  `PaperFigure` block (lift-empirical, don't fabricate). Port of `extract_figure.py`.
- **`synthesize_segments`** (`nolan.tts`) — narration wavs via OmniVoice local voice-cloning;
  `<chapter>_<step>.wav` → the spec's `wav` assets. Port of `synth_omnivoice.py`.
- **`word_timestamps`** (`nolan.whisper`) — per-wav word timings → the `wordsCache` shape
  `ingest_explainer` reads. Port of `word_timestamps_batch.py` (loads whisper once).
- **Interpreter-agnostic + lazy heavy imports**: `_localize` on path args; tts/whisper/PIL
  imported inside the functions so importing the module stays cheap. The lab probes couldn't even
  run under WSL `python3` (no PIL); these run in-process under the nolan env python.
- **Parity verified**: `figure_catalog` is byte-identical to `extract_figure.py --list` on
  tailtrading's `content.md` (38 figs) and Transformer's `paper.html` (8 figs); `extract_figure`
  lifts+trims a real figure (894×528 RGBA). TTS/Whisper verified by import + signature (a live
  run needs the CUDA/model env).

### Per-beat human-in-the-loop editor — 5 phases (`src/nolan/flows/`)

Per-beat editing of a flow video through NOLAN's existing Scene-page iteration system. Two HITL
stages on one shared `projects/<slug>/flow.spec.json`; autonomy = which gate blocks. Full design
in `web-video-lab/flows/EDITOR.md`. Backends built + tested; some frontend UX needs in-browser
verification (marked ⚠ in EDITOR.md).

- **P1 Persistence** (`project.py`) — project-owned, beat-addressable spec; `load_flow_spec`,
  `run_flow_for_project`, `run_flow(render=False)`.
- **P2 chapter-block render** (`render.py`) — per-beat clip → concat, dispatched by
  `Flow.render_mechanism` (no per-type branch). Full 8-beat run = 11508 frames (== whole-comp).
- **P3 Scene-page wiring** (`scene_view.py` + `iterate/engine.py` `flow` pipeline + `edit.py`) —
  beats → scene rows; **selective single-beat re-render ~20s vs ~7min**; edit→re-render-one.
- **P4 Sub-beat** (`edit.patch_focus`) — edit one focus (`beat_NN.fJ`) independently.
- **P5 Authoring mode + autonomy** (`authoring.py`) — `draft_plan` (palette = motion menu) +
  asset wishlist (have/find/generate) + `run(mode=auto|semi-auto)` (Gate A off/on).

## WebUI — iPhone-friendly + unified theme (2026-06-28)

The hub WebUI is now responsive across the whole site and visually consistent.

- **Responsive nav** (`static/nav.js` + `static/nolan.css`): the 16-link top bar
  collapses into a tap-to-open hamburger drawer on phones (≤768px); horizontal
  bar with wrap on desktop. Touch-sized links, iPhone safe-area (notch) insets.
- **Mobile base layer** (`nolan.css`): `@media (max-width:640px)` — 16px inputs
  (no iOS zoom-on-focus), full-width modals, fluid `img/video/canvas`, roomier buttons.
- **Per-page responsiveness**: every content page (19 templates) got a
  `@media (max-width:768px)` block — multi-column/master-detail layouts collapse
  to one column, headers/toolbars stack, controls go full-width, no horizontal scroll.
- **Theme unification**: 8 pages (clips, library, scenes, script_projects,
  script_styles, tts, video_styles, voices) were on an off-brand purple/pink palette
  (`#2a2a3a` bg, `#e94560` accent). Migrated their hardcoded hexes to the shared
  `nolan.css` CSS variables (slate `--bg-*`, sky-blue `--accent`, semantic
  `--success/--warning/--danger`) — removing redundant hardcoded colors and making
  the whole app match the nav. Multi-color status legends intentionally preserved.
- **Verified**: screenshotted all 20 pages at 390×844 (puppeteer) — nav drawer,
  column collapse, and the unified theme confirmed; desktop layout unchanged.
- **Tailscale**: `start_webui.bat` now runs `tailscale serve --tcp=8011` so the Hub
  is reachable on the tailnet at `http://<tailscale-ip>:8011` (loopback proxy, no
  Windows Firewall change needed).

### Design system — Linear shell + Frame.io media (2026-06-28)

Reworked the shell and visual language toward Linear (calm console) + Frame.io
(media-forward), keeping every page and function identical.
- **Left-sidebar app shell** (`nav.js` + `nolan.css`): replaced the top nav with a
  grouped left rail (Create / Assets / Produce / Share / System), active item marked
  by an accent bar, render-status pinned at the bottom. `nav.js` wraps each page's
  existing content in `<main>` (preserving its padding) so no page markup changed.
  On phones the rail becomes an off-canvas drawer (hamburger top bar + scrim).
- **Linear base layer** (`nolan.css`): thin quiet scrollbars, accent focus rings,
  input focus-glow, button press, plus `.card` / `.media-card` (16:9 `.thumb`) primitives.
- **Per-page polish** (all 21 templates, via 4 agents): Linear type scale
  (h1 ~26px/650/-0.02em, 16–18px section heads, 12–13px meta), 8px spacing rhythm,
  12px card radius, 1px `--border`, tidy controls — styling only, JS/ids/layout intact.
- **Frame.io media cards**: Clips and Showcase are now 16:9 gallery grids (thumbnail +
  play affordance + duration badge); Scenes asset previews are framed with hover;
  Library keeps its 3-pane list (refined rows + ▶ affordance, media-forward detail).
- **Verified**: puppeteer screenshots of the whole site at 1280 + 390 — sidebar,
  drawer, media galleries, and per-page polish confirmed; functions preserved.

## Publish — beautiful HTML articles, a second output medium (2026-06-28)

`src/nolan/publish/` turns a URL / document / pasted text into a self-contained,
**offline single-file HTML article** — the article twin of the video pipeline,
sharing NOLAN's ingest + agent-orchestration front-half. Authoring is driven by
the NOLAN-native **`beautiful-article`** skill (reacticle themes + figure library);
the deterministic scaffold/build runs the skill's scripts via WSL.

- **CLI**: `nolan publish <source> --theme press --type explainer [--width --images
  --brand --slug --review --no-cover]` → `projects/_published/<slug>/article/article.html`.
- **WebUI**: new **Publish** tab (`/publish`) — form (theme/type/width/images/brand/cover)
  → background job (`operations.publish_article`) → progress poll → in-page preview +
  open/download. Reuses the standard `NolanJobs` job widget; result served by `/publish/file`.
- **Single source of truth**: the skill owns the scaffold-template + figure library +
  scripts; `publish/toolkit.py` references them (removed the duplicate vendored `webkit/`).
- **Project model**: `projects.py` gained a `has_article` marker (kind `article`) so
  published articles appear in the unified project list.
- **Hardening**: `source.load_source` now fails loudly on a mistyped/unsupported source
  path instead of silently treating the path string as article body.
- **Verified**: toolkit tests 6/6 (real WSL build → 2.5 MB offline HTML, screenshot,
  source guard); full `nolan publish` e2e (agent authored 3 sections → offline article);
  UI wiring (routes, validation, path-traversal containment, real article served);
  `discover_projects` picks up published articles; project tests 11/11.

## Stock providers — keys + rate-limit safeguards (2026-06-27)

Enabled three keyed stock providers (config-only) and added rate-limit handling
to `src/nolan/image_search.py`:

- **Keys** in `.env`: `PIXABAY_API_KEY` (images + video), `UNSPLASH_ACCESS_KEY`
  (images), `PEXELS_API_KEY` (images + video). Wired already — `config.py`
  maps the env vars → `ImageSourcesConfig` → `ImageSearchClient`; no code change
  to enable.
- **`_RateLimiter`** (module-level singleton, thread-safe sliding window): per-
  *account* buckets so Pexels image+video (and Pixabay image+video) share quota.
  Limits: Unsplash 50/hr, Pexels 200/hr, Pixabay 100/60s. A provider over its
  limit is skipped; an HTTP 429 cools its bucket (≤5 min) instead of erroring.
- **Tiered fan-out**: `search_assets()` queries cheap/keyless + high-limit
  providers first and only falls through to tight-budget ones (`_DEFER_LAST`,
  i.e. Unsplash) when the first tier returns `< max_results`. An explicit
  `sources=` list is honored as a single tier. Explicit single-source `search()`
  still works; 429 → `[]`, other errors propagate as before.
- **Verified**: 8 logic tests (sliding window, shared bucket, 429 cooldown,
  tier short-circuit + fallback, explicit-source behavior) + live fan-out
  (53 image results from tier-0, Unsplash not queried) + live Pexels/Pixabay/
  Unsplash image & video searches.

## Picture Library — searchable image store (2026-06-25)

`src/nolan/imagelib/` — the still-image counterpart to the video library:
persistent, deduplicated, license-aware, with **CLIP semantic search** (text→image).
Acquisition results (search providers + link extractors) can now be warehoused
instead of dumped into ephemeral `.scratch/`.

- **`catalog.py`** `AssetCatalog` (SQLite): one row/asset with `content_hash`
  (dedup), `source`, `source_url`, `license`, dims, `tags`, `query`,
  `status` (active|rejected). **`embeddings.py`** `ClipEmbedder`
  (sentence-transformers `clip-ViT-B-32`, image+text shared space).
  **`store.py`** `ImageLibrary`: file storage + catalog + ChromaDB `images`
  collection; `add_file/add_url/add_result`, `search` (active+license filtered),
  `set_status` (reject de-indexes), `search_all` (global+project merge).
- **Scopes** (in-tree, gitignored): global `_library/images/`,
  project `projects/<name>/imagelib/`.
- **CLI**: `nolan images {search,add,list,reject,stats}`; plus `image-search
  --save [--scope --project]` to ingest results tagged with the query.
- **match-broll integration**: `match_broll_v2` searches the library (global +
  project) FIRST, vision-scores candidates on the same scale, and reuses one
  scoring ≥ `library_gate` before any external provider (`from_library` in result).
  Required making `AssetCatalog` thread-safe (`check_same_thread=False` + lock)
  since match-broll searches from a thread pool.
- **Hub UI**: `/images` gallery — browse/CLIP-search, scope + license filter,
  per-tile reject; thumbnails via `/api/images/raw`.
- **Verified**: 12 unit tests (`tests/test_imagelib.py`, incl. cross-thread) +
  `tests/test_hub_images.py` (endpoints) + live CLIP ("skeleton" vs "locomotive"
  rank their own images) + functional match-broll test (scene matched from
  library, external skipped). See `docs/PICTURE_LIBRARY_v1.md`.

## Asset Extraction — link → assets (2026-06-25)

`src/nolan/extractors/` — a new acquisition channel: give it a **page URL**, it
extracts the highest-definition images embedded/linked on the page. A registry of
parsers (site-specific first, generic HTML fallback last); each emits
`ImageSearchResult` so output flows into the existing scoring/download paths.

- **Parsers**: `gutenberg` (thumbnail-links-to-full illustrations), `wikimedia`
  (map `/thumb/.../NNNpx-Name.jpg` → original), `met` (object ID → collection API
  `primaryImage`), `archive` (Internet Archive item → metadata API → original
  images), `loc` (Library of Congress item → `?fo=json` → largest rendition),
  `iiif` (**one parser for all IIIF archives** — Presentation v2/v3 manifests +
  Image API `info.json` → `full/max`), `web` (universal: `<a href>`-wraps-`<img>`
  → largest `srcset` → `src`, plus `og:image`; resolves relatives, drops
  icons/tiny/data-URIs, dedups).
- **No new dep** — stdlib `html.parser` (`html_utils.py`).
- **Surfaces**: `nolan extract-assets <url> [-n N] [-o DIR] [--no-download]`
  (downloads to `.scratch/extracted/<host>/` + manifest); hub `/extract` page +
  `POST /api/extract-assets` (synchronous preview or `download:true` job).
- **Verified live**: Gutenberg 21790 → 50 illustrations (`illus-048.jpg` full-res,
  real 750×1178 @300 DPI download); Wikimedia original; Met API; IIIF v2/v3
  manifests + info.json; Internet Archive item; LoC item. 26 unit tests
  (`tests/test_extractors.py`, network-free). Note: IIIF is a delivery standard,
  not a search API, so it lives as an extractor (not an `image_search.py` provider).
  See `docs/ASSET_EXTRACTION_v1.md`.

## Scene Iteration — review → comment/edit → re-render (2026-06-25)

`src/nolan/iterate/` adds the human-in-the-loop gate: see scenes side-by-side, edit/
comment on a few, and **re-render only those** — for **both** pipelines (the linear
orchestrator and the asset-first segment builder), which share `scene_plan.json`.

- **One engine, two adapters** (`engine.py`): `detect_pipeline()` (segment via sibling
  `segment_meta.json`, orchestrator via `.orchestrator/` or `layout_spec`); `rerender_scenes(plan, ids)`
  invalidates only the named scenes' clips and re-renders/reassembles via each pipeline's
  existing path (segment reuses the skip-guarded `build_from_plan`; orchestrator re-renders
  the selected dicts → `annotate` → silent audio → `call_assemble`). Orchestrator plans are
  handled as **raw dicts** so `layout_spec` survives (the `Scene` dataclass would drop it).
- **Apply a comment OR a direct edit** (`revise.py`): `revise_scene(scene, note, client, pipeline)`
  turns a free-text note into a whitelisted field patch; a `motion_brief` is compiled to a
  validated `motion_spec` via `nolan.motion.compile_spec`. `apply_edit()` supports note-mode
  and direct-patch-mode, and dirties `rendered_clip` so the next re-render rebuilds it.
- **Re-resolve on edit:** changing `search_query`/`visual_type` clears the scene's cached
  `matched_clip`, and re-render re-runs the match stage for just those scenes (segment reuses
  the project-local index + escalation; orchestrator re-matches b-roll via `ClipMatcher` on
  raw dicts). So editing a query actually pulls a different library clip — not just a re-render.
- **CLI:** `nolan revise-scene <plan> <id> --note "…"` (agent) or `--set field=value` (direct);
  `nolan rerender <plan> --scenes id1,id2`.
- **Web UI (`/scenes`):** the read-only viewer is now editable — per-scene **select**,
  **Comment → agent** / **Edit fields** tabs, and a **Re-render selected** bar (background job).
  Project discovery now recurses so nested segment outputs (`<project>/segment_*/`) appear;
  a `/scenes/file` route serves both `clips/` (segment) and `assets/` (linear) previews.
- **Tests:** `tests/test_iterate.py` (14) — detection, invalidation, whitelist/motion-compile,
  selective re-render for both pipelines, re-resolve on query change (+ a hub TestClient smoke
  verified end-to-end).

## Experiments

### Asset-First Scene Building (2026-06-24)
Inverted pipeline prototype: take a slice of an existing script and **build scenes
from available assets** instead of script→scenes→match. Combined three sources —
segment search (archival b-roll), renderer cards (counter/title/lower-third), and a
ComfyUI hero still + Ken Burns — synced to the original voiceover.

- **What changed:** end-to-end demo that the legacy `nolan assemble` asset-priority
  path (`rendered_clip > generated_asset > matched_asset`) composes mixed asset types
  into a final mp4. Index now supports **project-local** DBs (`projects/<name>/index.db`).
- **Usage:** `projects/US Economy/experiment_roaring20s/` — `index_source.py` →
  `build_full.py` → `nolan assemble scene_plan.json vo.m4a -o final.mp4 -r 1920x1080`.
- **Result:** `final.mp4`, 1920×1080@30, 86s, 11 scenes, all sources verified.
- **Gaps surfaced:** no compositing/overlay in assemble, no animated line-chart
  renderer, crossfade transition is a stub. See the project's `findings.md`.
- **New workflow:** registered **`flux-dev`** (`workflows/image/flux-dev-fp8.json`,
  `flux1-dev-fp8`) and **`z-image-turbo`** (8-step, `basic-z-image.json`) — large
  photoreal upgrades over the SDXL `sdxl-default` default.
  Use via `get_registry().build_client('flux-dev', config)`.

### Renderer: compositing, charts, fades (2026-06-25)
Three additions that turn the cut-sequence essay into layered video-essay grammar
(all in the renderer layer; `nolan assemble` stays a dumb concatenator):

- **Compositing** — `BaseRenderer.render_frame_rgba()` renders a scene with a
  transparent background; `renderer/composite.py::composite_over_broll(overlay,
  broll, out, duration, fade=, scrim=)` overlays a counter / lower-third / title /
  caption *on top of* moving b-roll (ffmpeg `overlay`, with optional scrim for
  text legibility). Replaces full-screen black "stat cards."
- **Animated line chart** — `renderer/scenes/line_chart.py::LineChartRenderer`
  (exported as `LineChartRenderer` / `render_line_chart`): progressive polyline,
  green-up/red-down segments, leading dot + value readout, x-labels revealed as the
  line passes. Built for the market rise→crash→rally beat.
- **B-roll fades** — `render_b_roll` honors a per-scene `fade` (seconds) for gentle
  fade in/out on cuts; `composite_over_broll` takes the same `fade`.
- **Title auto-fit** — `BaseRenderer.fit_font_size()`; `TitleRenderer` shrinks long
  titles/subtitles to fit the frame instead of clipping.
- **Loop/feedback diagram** — `renderer/scenes/loop_diagram.py::LoopDiagramRenderer`
  (`render_loop_diagram`): labelled nodes on a circle with animated curved arrows
  forming a cycle. For systemic "X feeds Y feeds Z back to X" arguments. Composites.
- **Photo montage ("photos on a table")** — `renderer/scenes/photo_montage.py::PhotoMontageRenderer`
  (`render_photo_montage`): Polaroid-framed stills (white border + drop shadow + slight
  rotation) on a textured/vignetted surface, a slow Ken Burns camera, and one **hero card
  that slides in** with a **handwritten type-on caption**. For introducing historical
  figures / archival stills. Spec id `photo-montage` (python). Test: `scripts/test_photo_montage.py`.
  Reverse-engineered from clip analysis (`projects/_clips/clip_518fb653/effect_analysis.md`).
  Cards/hero accept `frame:"polaroid"|"cutout"` — `cutout` keeps a transparent PNG's
  irregular silhouette (alpha preserved) and the drop shadow follows it.
  For the **flexible/extensible** version with per-card motion control, use the Remotion
  `PhotoMontage` composition below (spec id `photo-montage-pro`).

Demo: `projects/US Economy/experiment_roaring20s/build_v2.py` → `final_v2.mp4`.

### Curated Remotion source (2026-06-25)
Python remains the default renderer; Remotion is used **only** within its strong scope
(kinetic typography, rich animated charts, SVG annotations, maps, premium cards — see
`docs/REMOTION_EVALUATION.md`). A proper static Remotion project lives in
`render-service/remotion-lib/` (real `.tsx`, not the code-generator) with a job-JSON →
`bundle`+`renderMedia` flow (`render.mjs`).
- **Built (9 compositions across categories 1–5):** `Kinetic` (kinetic-text), `BarCompare` +
  `KShape` (rich-chart), `AnnotateOverVideo` + `AnnotateStat` (svg-annotation), `RouteMap`
  (map), `PremiumCard` (premium card). Render ~5–9s each.
- **`PhotoMontage` (photo-montage-pro)** — flexible "photos on a table" with a **per-card
  motion system**: each card declares where it rests (`x,y,scale,rotation`) and how it
  arrives (`from` edge + `enterAt`/`enterDur`/`distance`/`ease`) independently — e.g. one
  slides up to center, one in from the left to rest on the left. Frame styles
  `polaroid`/`plain`/`cutout` (cutout = bare PNG alpha + silhouette `drop-shadow`),
  handwritten type-on captions, Ken Burns camera. Multi-image staging: `render.mjs` stages
  the `cards[].src` array + `background` into `public/` (mirrors the `segments` pattern).
  **Per-card keyframe tracks** (`card.keys: [{at,x?,y?,scale?,rotation?,opacity?,ease?}]`)
  fully drive a card's transform when present — each property tweens through only the keys
  that define it, enabling **appear-then-tilt**, **fade-in-then-fade-out**, and arbitrary
  **multi-step paths**; the `from` sugar remains for one-shot entrances. Tests:
  `scripts/test_photo_montage_remotion.py` (entrances), `scripts/test_photo_montage_stress.py`
  (keyframe tracks: delayed tilt / fade-out / complex path / layered sizes). 3D pan/tilt:
  per-card `rotX`/`rotY` (+`perspective`) — `rotation` is in-plane (rotateZ), `rotX/rotY` swing
  the card in 3D space (a "pan" vs a flat tilt); demo `scripts/test_photo_montage_pan.py`.
- **`PhotoGrid` (photo-grid)** — procedural grid choreography that scales to dozens of
  images: (1) N images **fly in** to fill a `cols×rows` grid, sequenced **one-by-one / by
  row / by col** (`order`); (2) one image (`focusIndex`) **zooms to center** while the rest
  of the grid **peters out**; (3) it **zooms back** and the grid returns. All per-cell motion
  is computed from grid shape + timings, so the input is just a flat image list. Reuses the
  multi-image staging + polaroid/plain/cutout frames. Test: `scripts/test_photo_grid.py`
  (40 real library images, 8×5).
- **Style system:** shared `theme` tokens (`src/theme.ts`: dark-editorial/light/high-contrast
  or override object) on every effect + per-effect style vars (`lineStyle`, `barStyle`,
  `shapeStyle`, `routeStyle`, `cardStyle`) + shared seeded path helpers (`src/shapes.ts`).
  See `render-service/remotion-lib/README.md`.
- **Wired as a source.** `visual_router.py` has a `remotion` route (`REMOTION_VISUAL_TYPES`
  maps `kinetic-text`/`bar-compare`/`k-shape`/`annotate-video`/`annotate-stat`/`route-map`/
  `premium-card` → composition ids; `RouteDecision.remotion_comp`). Discoverable registry at
  `remotion-lib/registry.json` (each comp's visual_type + style schema). Render bridge:
  `src/nolan/remotion_source.py` (`list_compositions`, `render`, `render_scene` — shells
  `render.mjs` via Node).
- **Showcase reel:** `Showcase` composition (`<Series>` of all effects + labels) →
  `remotion-lib/output/showcase.mp4` (~27s).

### Brief layer — authoring broll/motion from intent (2026-06-26)
`src/nolan/brief/` is the agent-facing authoring surface between the broll/scene-design
stage and the render engines. Principle: **the LLM does the semantic part, deterministic
code does the mechanical part, they meet at a small validatable _brief_.** The agent
authors ~8 JSON fields; a resolver compiles them to a validated `nolan.motion` spec.
- **`TimeRef`** (`timeref.py`) — symbolic time resolved against the scene transcript:
  `3.2` | `"start"/"end"/"mid"` | `{"cue":"keyword"}` (when the VO says it) | `{"frac"}` |
  `{"after","delay"}`. Reusable by **any** timed effect, not just photo.
- **`SceneContext`** (`context.py`) — duration + word-level narration timing + warnings
  sink; `from_scene(scene, words)` builds it from a Scene (transcript for cue matching).
- **`photo-story`** (`photo_story.py`) — first brief family. `layout:"grid"` → `photo-grid`,
  `layout:"free"` → `photo-montage-pro`. Motion **verbs** (`enter/fade/tilt/pan/tilt3d/
  move/path/zoom`) compile to keyframe tracks, so the agent never writes `keys`/perspective.
- **`resolve_brief(brief, ctx)`** (`resolve.py`) → `(validated spec, messages)`; registry
  `BRIEF_REGISTRY` for new families. **Boundary:** cue→time resolves at *design time*
  (where the transcript lives); the resolved spec is persisted on the scene, render stays
  context-free. Graceful: missing cue/image/verb → warn + best-effort spec, never crash.
- **Wired into the scene-edit router** (`iterate/revise.py`): the LLM gate returns a
  `photo_brief` object for montage/grid notes, resolved against the scene's narration →
  `motion_spec`. Verified with a **real LLM + real comment** end-to-end ("6 pics, 2×3 grid,
  zoom the 4th when VO says 'keyword'" → `photo-grid`, focusIndex 3, focusAt 3.2s, rendered):
  `scripts/test_router_brief.py`. Brief-unit test: `scripts/test_brief.py`; design doc:
  `docs/BROLL_BRIEF.md`.
- **Asset binding (the input half):** each scene carries an asset **tray**
  (`scene.assets:[{id,kind,src,label?,thumb?,place?}]`). A comment references it by id/label
  ("grid of these, zoom the Knight") instead of pasting paths; the revise gate sees the tray
  and emits `images:[{ref:'<id>'}]`, dereferenced to the bound src (+ `place`/`scale`/`label`).
  UI: a `/scenes` **Assets** tab with a slide-in **picker drawer** — tabs Pictures (browse
  `/api/images/list` + CLIP search) and Videos/Clips (`/library/api/clips`, thumbnails via
  `/scenes/api/frame-thumb`), multi-select → add; tray cards show kind badge + remove + 3×3
  `place` picker. Backend op endpoint `POST /scenes/api/scene/assets` (add image/clip/path,
  remove/reorder/set_place/set_label), non-render-invalidating; resolver kind-validates (clip
  refs warn — video-in-montage is TODO C). **Spatial control** is offered only for declarative fields (place),
  never keyframes — those stay comment-driven. Tests: `scripts/test_asset_binding.py` (+ real
  LLM, hub TestClient capstone); hub/CLI cue timing fed by `iterate.scene_words` (cached VO transcript).

### Motion-spec system — natural language → render (2026-06-25)
`src/nolan/motion/` translates a one-line scene design into a precise, validated render
spec and renders it on the right backend (Python renderer or Remotion). A declarative
**registry** is the single source of truth.
- `registry.py` — 16 effects across categories/both backends; **shared params**
  (`position`/`theme`/`accent`) declared once, each effect lists its own content/style
  params + which shared params it supports. Add params here over time.
- `manifest.py` — builds the LLM capability manifest + prompt guide from the registry.
- `spec.py` — validate/normalize (effect/required/enum checks, fills defaults, coerces types).
- `compiler.py` — `compile_spec(scene, client)` (LLM + one repair retry).
- `executor.py` — `render(spec, out)` dispatches Python (`renderer.scenes`) vs Remotion
  (`remotion_source`); `position` normalized to `{x,y}` for both.
- API: `from nolan.motion import author`. Example: `examples/motion_author.py` (6 scenes,
  both backends, LLM-authored complex content like chart bars / loop nodes).
- **Solves** the "one script per location" problem: `position` (and style) are parameters
  the LLM sets. Known refinements: clamp wide content to a safe area; map `theme` onto Python
  renderers; add `timing`/motion as the next shared param; vision-grounding for placing
  annotations *on b-roll content*.
- **Integrated into the pipeline (2026-06-25):**
  - *Scene designer* — `SceneDesigner.author_motion(scenes)` + `design_full_plan(..., author_motion=True)`
    attach a `motion_spec` to graphic/text/data scenes (skips b-roll/generated). New `Scene.motion_spec`
    field (serialized). Orchestrator `render_scene` renders `motion_spec` first (Python or Remotion).
  - *Clips "Analyze effect"* — `webui/operations.py::_effect_task_markdown` now lists **both backends**
    (`_motion_catalog_md()` generated from the registry), so the recreation agent treats Remotion as a
    first-class source and is told to add a `MotionEffect(... backend=...)` row when implementing.

### build-from-segment — wrap the validated pipeline (2026-06-25)
`src/nolan/segment/` turns a segment into a ~1-min essay via the asset-first pipeline.
CLI: `nolan build-from-segment`.
- **Inputs (3):** indexed-source span (`--source --start --end`, slices VO+SRT), `--script`
  (+ optional `--vo`), or `--vo` (whisper-transcribed). → `inputs.py`.
- **Stages:** design (`SceneDesigner` + `author_motion`) → timing (`assign_timing`, proportional)
  → **resolve** (`resolver.AssetResolver`: motion for graphics, segment-search for footage above a
  threshold, else escalate to external→ComfyUI→black; records `Scene.resolved_source`) →
  render (`render.py`: motion / b-roll extract+fade / ComfyUI+KenBurns) → `nolan assemble`.
- **Modes:** `auto` (one shot) and `review` (stops after resolve with a per-scene source manifest;
  edit `scene_plan.json` then `--from-plan` to resume).
- **P2:** search threshold + escalation, external-footage hook, `suggest_spans` (LLM).
  **P3:** `--music` bed (ducked mix), `--transition` pass-through, `tts_fn` hook.
- **Tests:** `tests/test_segment_builder.py` (9, mocked — resolver routing, timing, SRT/inputs,
  both modes, suggest, external, TTS). Verified real CLI build (script → motion scenes → `final.mp4`).

## Implemented Features

### Core Pipeline
- **Essay Parser** - Extracts sections from markdown essays
- **Script Converter** - Converts essays to YouTube-style narration using Gemini API
- **Scene Designer** - Generates visual scene plans with asset suggestions

### Infrastructure
- **Configuration System** - YAML + environment variable configuration
- **Text LLM (configurable)** - `create_text_llm(config)` factory; default
  **qwen/qwen3.7-plus via OpenRouter** for all authoring tasks (script, scenes,
  clustering, inference, translation). Override via `nolan.yaml` `llm:` block,
  the Settings page, or per-run (`llm_provider`/`llm_model`). `OpenRouterLLM`
  (text) + `GeminiClient` both implement `generate(prompt, system_prompt)`.
- **Gemini LLM Client** - Async client for Gemini API
- **Video Indexer** - SQLite-backed video library indexing with visual analysis
- **Asset Matcher** - Matches scenes to indexed video library
- **Project Registry** - Organize videos by project with human-friendly slugs
  - Projects have unique IDs (internal) and slugs (CLI-facing)
  - Index videos scoped to specific projects
  - Search and filter by project

### Hybrid Indexing
- **Vision Provider** - Switchable vision models (Ollama/Gemini/OpenRouter)
  - Default: qwen3-vl:8b via Ollama
  - Configurable host/port/model
  - OpenRouter provider (OpenAI-compatible) gives access to any vision model
    on OpenRouter, e.g. `qwen/qwen3.7-plus`. Set `OPENROUTER_API_KEY` in `.env`
    and run `nolan index --provider openrouter` (model via `vision.model` in
    `nolan.yaml`). Shares the exact analyze-frame prompt + JSON parser with
    Gemini, so results are directly comparable across providers.
  - Reasoning control via `vision.reasoning_enabled` (default off) + optional
    `vision.reasoning_max_tokens`. Disabling reasoning on models like
    `qwen/qwen3.7-plus` cuts latency ~4-6x (~35s→~6s/frame) with no quality loss.
- **Smart Sampling** - 5 strategies for frame extraction:
  - FFmpeg scene detection (default - 10-50x faster, hardware accelerated)
  - Hybrid (Python-based, combines time bounds with scene detection)
  - Fixed interval
  - Scene change detection (OpenCV)
  - Perceptual hashing (skip duplicates)
- **Transcript Alignment** - SRT/VTT/Whisper JSON support (read as UTF-8, handles Chinese)
  - **Subtitle-first, Whisper-fallback**: downloads English + Chinese subtitles
    (`subtitle_langs` defaults to en + zh variants); uses a downloaded subtitle when
    present, and only transcribes with Whisper when none is found. WebUI ingest wires
    this fallback by default (`whisper_fallback`).
  - **UTF-8 mode required on Windows**: run the hub/CLI with `-X utf8` (the launcher
    does this). Otherwise ffmpeg subprocess output is decoded as cp1252, which crashes
    the reader thread and corrupts scene detection (fewer segments).
- **Segment Analyzer** - LLM fusion of visual + audio with inferred context

### Whisper Integration
- **Auto-Transcription** - Generate transcripts for videos without them
  - Uses faster-whisper (4x faster than openai-whisper)
  - Multiple model sizes: tiny, base, small, medium, large-v2, large-v3
  - GPU acceleration (CUDA) with automatic CPU fallback
  - Voice activity detection (VAD) filtering
- **Audio Extraction** - Automatic via ffmpeg
- **Caching** - Saves generated transcripts as .whisper.json files

### Hybrid Inference
- **Combined Vision+Inference** - Single API call for frame analysis (50% fewer API calls)
  - Vision model sees both image AND transcript together
  - Better inference: can recognize faces, read on-screen text
  - Returns frame_description + combined_summary + inferred_context
  - Falls back to simple description for non-Gemini providers
- **Inferred Context** - Best guesses for:
  - People (named characters, speakers, face recognition)
  - Location (setting identification from visuals and audio)
  - Story context (narrative description)
  - Objects (notable items)
  - Confidence level (high/medium/low)

### Scene Clustering
- **Segment Grouping** - Cluster continuous segments into story moments
  - Groups by shared characters/people
  - Groups by shared location
  - Groups by similar story context
  - Configurable time gap threshold
- **LLM Story Boundary Detection** - Optional refinement using LLM
  - Detects narrative beat changes
  - Splits clusters at story boundaries
- **Cluster Summaries** - LLM-generated summaries for each cluster
  - Captures what's happening in the story moment
  - Identifies key characters/elements
  - Describes emotional/narrative significance

### Semantic Search
- **Vector Database** - ChromaDB for semantic similarity search
  - Stores embeddings for segments and clusters separately
  - Persistent storage alongside SQLite database

## Recent Indexing Improvements (2026-01-17)
- **Concurrency Default** - Indexing defaults to 25 concurrent calls (configurable via `indexing.concurrency`).
- **Bulk Segment Inserts** - Segments are inserted per video in batch for faster DB writes.
- **Frame Analysis Cache** - Cached results by `(fingerprint, timestamp, transcript_hash, inference_enabled)` to reuse on reindex.
- **Transcript Alignment Cache** - Cached aligned transcript slices per `(fingerprint, transcript_hash, timestamps_hash)`.
- **Rate-Limit Backoff** - Short exponential backoff on Gemini rate-limit errors (429/resource_exhausted).
- **FFmpeg Batch Extraction** - FFmpeg scene sampler extracts frames in batches per process for fewer spawns.
- **Path Refresh** - Video path/project is updated even when reindex is skipped.

## Recent Clip Matching Improvements (2026-01-17)
- **Parallel Matching** - Scene matching runs with bounded concurrency (`clip_matching.concurrency`).
- **Rate-Limit Backoff** - Retries LLM selection on 429/resource_exhausted errors.
- **Better Selection Context** - LLM prompt now includes the merged search query.
- **Deterministic Fallback** - LLM parse failures fall back to highest-similarity candidate.
- **No-Match Logging** - Clear messages when candidates are filtered out by similarity.
- **Two-Stage Search** - Cluster-first search narrows segment results when `search_level=both`.
- **Candidate Deduping** - Removes duplicate segment candidates across sources.
- **Dominant-Match Fast Path** - Skips LLM when top similarity is clearly ahead.
- **Deterministic Tie-Breaking** - Pre-LLM ranking uses similarity, transcript presence, and duration fit.
- **LLM Selection Cache** - Per-run cache for scene+candidates avoids repeated LLM calls.

## Codebase Refactoring (2026-01-31)

### File Organization
- **Scratch Directory** - All temporary/test outputs use `.scratch/` directory
  - Updated 5 CLI commands with problematic default paths
  - Added `.scratch/` to `.gitignore`
  - Prevents test files scattering in project root

### Models Package
- **Centralized Data Models** - Extracted dataclasses to `nolan/models/` package
  - `InferredContext` - Visual + audio analysis results
  - `VideoSegment` - Indexed video segment data
  - `SceneCluster` - Grouped segments representing story moments
- **Backwards Compatibility** - Re-exports in original modules maintain API stability
- **Type Hints** - Using `TYPE_CHECKING` imports to avoid circular dependencies

### CLI Package
- **Hybrid Approach** - Created `nolan/cli/` package with backwards-compatible entry point
  - `cli_legacy.py` - Original CLI preserved (4,478 lines)
  - `cli/__init__.py` - Entry point re-exports from legacy
  - `cli/utils.py` - Shared utilities for future command modules

### Downloaders Package
- **Shared Utilities** - Created `nolan/downloaders/` package with common code
  - `sanitize_filename()` - Safe filename generation
  - `extract_lottie_metadata()` - Parse Lottie JSON metadata
  - `save_lottie_json()` - Save with minification
  - `RateLimiter` - Request rate limiting for APIs
  - `CatalogBuilder` - Generate catalog JSON files
- **Base Models** - Shared template dataclasses
  - `BaseLottieTemplate` - Common fields for all sources
  - `JitterTemplate`, `LottieflowTemplate`, `LottieFilesMetadata` - Source-specific
- **Updated Downloaders** - Jitter, LottieFiles, Lottieflow use shared utilities
- **New Tests** - 20 tests for shared downloader utilities

### HTTP Client Module
- **Shared HTTP Utilities** - Created `nolan/http_client.py` for consolidated HTTP access
  - `get_async_client()` - Pre-configured async httpx client
  - `get_sync_client()` - Pre-configured sync httpx client
  - `fetch_json_async()` / `fetch_json_sync()` - JSON fetch helpers
  - `download_file_async()` / `download_file_sync()` - File download helpers
  - `ServiceClient` - Base class for service-specific API clients
  - Default timeouts (30s read, 10s connect)
  - Default User-Agent header
  - Connection pooling support
- **New Tests** - 23 tests for HTTP client utilities

### New Test Coverage
- **test_aligner.py** - 23 tests for audio-scene alignment
  - Text normalization (unicode, punctuation, whitespace)
  - Word stream search (exact, fuzzy, case-insensitive)
  - Scene alignment algorithms
- **test_image_search.py** - 18 tests for image search
  - ImageSearchResult dataclass and scoring
  - ImageProvider base class
  - DDGSProvider implementation
- **test_clip_matcher.py** - 18 tests for clip matching
  - ClipCandidate and MatchResult dataclasses
  - Deduplication logic
  - Cache key generation
  - Project-level filtering support
- **BGE Embeddings** - BAAI/bge-base-en-v1.5 model (768 dimensions)
  - Query-document asymmetry support for better retrieval
  - Local inference (~440MB model download)
  - Combines visual descriptions, transcripts, and context
- **Search Levels** - Configurable granularity
  - `segments` - Individual video segments
  - `clusters` - Story moment clusters
  - `both` - Combined results (default)
- **Incremental Sync** - Only re-embeds changed videos
  - Uses `indexed_at` timestamps to detect re-indexing
  - Auto-triggered after `nolan index` completes
  - Use `--force` to re-embed everything
- **CLI Commands**
  - `nolan sync-vectors` - Sync SQLite index to ChromaDB
  - `nolan semantic-search <query>` - Natural language search

### Integrations
- **ComfyUI Client** - Image generation via local ComfyUI API
- **Viewer Server** - FastAPI-based local viewer for reviewing outputs
- **Library Viewer** - Web UI for browsing indexed video library (`nolan browse`)
  - Keyword and semantic search modes with toggle
  - Project filtering support
- **Scene Plan Viewer** - A/B column viewer for scene plan review (`/scenes` route)
  - Left column: Scene details (ID, timing, narration, type, query/prompt)
  - Right column: Asset preview (image/video with lightbox)
  - Section and status filters
  - Audio sync with range playback (play single scene, loop option)
  - Click timestamp to play that scene's audio range

### CLI Commands
| Command | Description |
|---------|-------------|
| `nolan script <essay.md>` | Step 1: Convert essay to narration script |
| `nolan design <script.json>` | Step 2: Design visual scenes from script |
| `nolan process <essay.md>` | Full pipeline: essay → script → scenes |
| `nolan index <video_folder>` | Index video library for snippet matching |
| `nolan export <video>` | Export indexed segments to JSON |
| `nolan cluster <video>` | Cluster segments into story moments |
| `nolan browse` | Browse indexed video library in web UI |
| `nolan serve` | Launch local viewer to review outputs |
| `nolan generate` | Generate images via ComfyUI |
| `nolan generate-test` | Quick single-image generation for testing |
| `nolan image-search` | Search for images from web/stock photo APIs |
| `nolan match-broll` | Batch search and download images for b-roll scenes |
| `nolan match-clips` | Match scenes to video library clips using semantic search |
| `nolan transcribe` | Transcribe audio/video to SRT/JSON/TXT |
| `nolan align` | Align scene plan to audio with word-level timestamps |
| `nolan render-clips` | Pre-render animated scenes to MP4 clips |
| `nolan assemble` | Assemble final video from scenes + audio |
| `nolan infographic` | Generate infographics via render-service |
| `nolan yt-download` | Download YouTube videos using yt-dlp |
| `nolan yt-search` | Search YouTube for videos |
| `nolan yt-info` | Get information about a YouTube video |
| `nolan projects create` | Create a new project with slug |
| `nolan projects list` | List all registered projects |
| `nolan projects info` | Show project details and videos |
| `nolan projects delete` | Remove a project from registry |
| `nolan sync-vectors` | Sync video index to ChromaDB for semantic search |
| `nolan semantic-search` | Semantic search across video library |
| `nolan showcase` | Launch Motion Effects Showcase UI |
| `nolan library` | Launch Video Library Viewer UI |
| `nolan hub` | Launch unified NOLAN Hub (Library + Showcase + Scenes) |

### ComfyUI Integration
- **Custom Workflows** - Load any ComfyUI workflow (API format)
- **Auto-detection** - Finds prompt nodes automatically
- **Explicit Node Selection** - `-n "node_id"` for reliable prompt injection
- **Parameter Overrides** - `-s "node_id:param=value"` for any workflow parameter
- **Config File** - `nolan.yaml` for port and other settings

### Image Search
- **Multi-Provider Support** - Extensible provider system
  - DuckDuckGo (no API key required)
  - Pexels (requires API key)
  - Pixabay (requires API key)
  - Wikimedia Commons (no API key, public domain/CC)
  - Smithsonian Open Access (requires API key, CC0)
  - Library of Congress (no API key, public domain)
- **JSON Output** - Results saved with URLs, thumbnails, dimensions, license
- **Search All** - Query multiple sources at once with `--source all`
- **Vision Model Scoring** - Score images by relevance using AI
  - OpenRouter (default: `qwen/qwen3.7-plus`, reasoning off) — used by both
    `image-search --score` and `match-broll --score`
  - Gemini vision model (cloud, fast)
  - Ollama vision model (local, requires running Ollama)
  - Scores from 0-10 with explanations
  - Results sorted by relevance

### Video Assembly Pipeline
- **Unique Scene IDs** - Section-prefixed IDs (`Hook_scene_001`, `Context_scene_002`)
  - Prevents asset file collisions across sections
  - Automatically applied during scene design
- **Timeline-Aware Assembly** - Matches video duration to audio
  - Sorts scenes by start time from audio alignment
  - Fills gaps between scenes with black frames
  - Total video duration matches voiceover exactly
- **Format Handling** - Robust image format support
  - SVG to PNG conversion (via cairosvg)
  - AVIF/HEIC detection and conversion (via Pillow)
  - Handles mismatched file extensions
- **Asset Priority** - Smart asset resolution per scene
  1. `rendered_clip` - Pre-rendered MP4 (highest priority)
  2. `generated_asset` - AI-generated image
  3. `matched_asset` - Downloaded b-roll
  4. `infographic_asset` - Rendered SVG
  5. Black frame (fallback for missing assets)

### Motion Effects Library
- **Effects Registry** - Centralized catalog of motion effects for video essays
  - Organized by category: image, quote, statistic, chart, title, map, etc.
  - Each effect maps to underlying engine (Remotion, Motion Canvas, Infographic)
  - LLM-friendly descriptions for automated scene generation
- **Effect Presets** - Ready-to-use motion patterns with sensible defaults
  - `image-ken-burns` - Classic documentary pan/zoom
  - `image-zoom-focus` - Zoom to detail reveal
  - `image-parallax` - 2.5D depth parallax layers
  - `quote-fade-center` - Elegant centered text
  - `quote-kinetic` - Kinetic typography sequences
  - `chart-bar-race` - Animated bar charts
  - `stat-counter-roll` - Number counter animation
  - `title-card` - Full-screen title cards
  - `map-flyover` - Geographic pan/zoom
  - `light-leak` - Organic light leak and film burn overlay
  - `camera-shake` - Handheld camera shake for tension/urgency
  - `compare-before-after` - Before/after slider wipe transition
  - `text-pop` - Word-by-word text reveal animation
  - `source-citation` - Citation cards for sources
  - `screen-frame` - Browser/phone/laptop mockup frames
  - `audio-waveform` - Animated audio visualization
  - `zoom-blur` - Speed zoom with radial motion blur
  - `glitch-transition` - Digital glitch with RGB split
  - `data-ticker` - CNN-style scrolling news ticker
  - `social-media-post` - Twitter/social media post mockup
  - `video-frame-stack` - Grid/stack of video thumbnails
- **Showcase UI** - Web interface for browsing and generating effects
  - Gallery view with category filtering
  - Live parameter form for each effect
  - Image upload support
  - Preview generation with render service
  - Accessible at `nolan showcase` or via unified hub
- **Unified Hub** - Single entry point at `nolan hub` combining:
  - Video Library browser (`/library`)
  - Motion Effects Showcase (`/showcase`)
  - Scene Plan Viewer (`/scenes`) with dynamic project selection
  - Landing page shows all projects as clickable cards
  - Projects auto-discovered from `--projects` directory (default: `projects/`)
  - Project dropdown in scenes viewer for quick switching
- **API Endpoints**
  - `GET /effects` - List all effects with parameters
  - `GET /effects/:id` - Get specific effect details
  - `POST /render` - Render with `{effect, params}` format
- **Full-loop webUI (v1)** — hub now operates the pipeline from the browser, not just browse:
  - **Project Studio** (`/studio`) — per-project stage view: source → script/scenes → match assets → render/assemble, each with status + action buttons
  - **Add to Library** (`/library/add`) — index a file or YouTube URL with vision provider/model/reasoning picker
  - **New from Essay** (`/process`) — essay → script → scene plan
  - **Settings** (`/settings`) — vision provider/model/reasoning, persisted to nolan.yaml
  - In-process **job manager** (`webui/jobs.py`) + `/api/jobs/{id}` polling; shared `static/` theme + nav + job widget
  - Endpoints: `/api/ingest`, `/api/process`, `/api/match`, `/api/render-clips`, `/api/assemble`, `/api/sync-vectors`, `/api/project/{name}/status`
  - See `docs/WEBUI_ROADMAP_v1.md`
- **ComfyUI / Generation page** (`/comfyui`) — manage multiple generation models, each with its own
  workflow. Backed by a **WorkflowRegistry** (`workflow_registry.py`, `workflows/registry.json`):
  named entries `{file/builtin, checkpoint, prompt_node, w/h/steps, styles}`. Page shows ComfyUI
  connection + installed checkpoints + queue, lists/adds/deletes workflows (paste/upload a
  "Save (API Format)" JSON → prompt node auto-detected), and a **sample runner** (prompt → image →
  scratch preview in `samples/`). Generation (`/api/generate`, Studio) selects a registered workflow.
  Endpoints: `/api/comfyui/status`, `/api/comfyui/workflows` (GET/POST/DELETE), `/api/comfyui/sample`.
- **One-click launcher** - `start_webui.bat` (project root) builds + starts the
  render service (`:3010`) and launches the Hub on `:8011` in its own window,
  then opens the browser. Note: Hub uses `:8011` (not the default `:8001`,
  which is reserved by SPARTA). The Showcase tab requires the render service.

### Manual Clips (2026-06-24)

Cut a snippet from any indexed video by hand, save it as a reusable **clip
asset**, and materialize it on demand for a downstream consumer.

- **Data model** — schema **v7** adds a `saved_clips` table (`indexer.py`). A
  clip is a `matched_clip`-shaped **pointer** (`source_video_path` + `clip_start`
  /`clip_end` + `label`/`tags`/`project_id`), not a file. `project_id` NULL = global
  library. Methods: `add_saved_clip` / `list_saved_clips(project_ids=…)` /
  `get_saved_clip` / `delete_saved_clip`. v6→v7 migrates in place (segments preserved).
- **Cut UI** — the Library player (`/library`) gains Set In / Set Out / Preview /
  Clear / Save controls, reusing the existing loop-preview. Saving POSTs
  `/library/api/clips`. Cut from an auto-segment **or** the whole video via the
  **✂ Cut from full video** button (free scrubbing, no segment needed). A pending
  In/Out selection is kept **per video** — it survives closing the panel and
  switching videos, and the clip is saved against the video actually in the
  player (correct even for cross-project search results).
- **Clips page** (`/clips`, `clips.html`) — cross-project search across **saved
  clips + auto-snippets (segments/clusters)** with a **project-scope multi-select**
  ("all" or pick a list). `search`/`search_clusters` gained a `project_ids` arg for
  `IN (…)` scoping. Each result can be previewed, saved, or materialized.
- **Materialize on demand** (`operations.materialize_clip`, `/library/api/clips/{id}/materialize`)
  produces the form the consumer needs and caches it under `projects/_clips/<id>/`:
  `none` (pointer → video essay), `file` (.mp4 → ComfyUI), `frames` (JPGs → Claude).
  Cached results are reused unless `force`.
- **Analyze effect via Claude agent** — the Clips page "🎬 Analyze effect" button
  (`POST /library/api/clips/{id}/analyze-effect`, `operations.analyze_effect`)
  materializes the clip's frames + file, writes a task brief to
  `projects/_clips/<id>/effect_task.md`, and dispatches it to a **selectable tmux
  Claude Code agent** (the Clips page has an agent dropdown populated from
  `GET /library/api/tmux-sessions`, defaulting to `nolan2`; dispatch via
  `tmux send-keys`, `wsl.exe tmux` from the Windows hub).
  The agent identifies the effect, **dedups against the motion library**
  (`renderer/scenes/`, `renderer/effects.py`, `render-service/src/effects/`),
  assesses replicability, and writes findings to `effect_analysis.md`
  (readable via `GET /library/api/clips/{id}/analysis`, shown by the page's
  "View findings" button).
- Clips-page result handlers are **index-based** (read paths from stored result
  objects) so Windows file paths with backslashes aren't corrupted by inline
  HTML/JS string parsing — this fixed broken Preview/Save buttons.
- Endpoints: `GET/POST /library/api/clips`, `DELETE /library/api/clips/{id}`,
  `GET /library/api/clips/search`, `POST /library/api/clips/{id}/materialize`,
  `POST /library/api/clips/{id}/analyze-effect`, `GET /library/api/clips/{id}/analysis`,
  `GET /library/api/tmux-sessions`.

  *Usage:* open `/library`, play a video, Set In/Out, Save → switch to `/clips`,
  pick a project scope, search, then "Materialize file/frames" for downstream use.

### Script Styles — transcript corpora → style guides (M1, 2026-06-25)

Learn script-writing *craft* from reference transcripts and distill a reusable
**style guide**, then later write new scripts in that voice. The writing-side
mirror of the Clips/effects (visual-craft) feature.

- **Store** (`src/nolan/script_style.py`, `ScriptStyleStore`) — file-backed under
  `script_styles/<id>/`: `manifest.json`, `corpus/<slug>.txt`, `per_transcript/<slug>.json`,
  `style_guide.md`. CRUD + `add_source` with **video_id dedup** so repeat fetches
  skip known videos.
- **Acquisition** — paste text, upload `.txt/.srt/.vtt` (parsed via `TranscriptLoader`),
  or a list of **YouTube links**: `YouTubeClient.fetch_transcript` pulls the
  **original-language transcript only** (yt-dlp `skip_download`, single best track —
  no video, no auto-translations), reusing the 429-safe language picker.
- **Analysis (hybrid, Stage B)** — `operations.analyze_style`: inline LLM
  (`create_text_llm`) extracts per-transcript features (JSON), then dispatches a
  **synthesis task to a selectable tmux Claude agent** which authors
  `style_guide.md` (Voice, Hook patterns, Narrative structure, Pacing, Rhetorical
  devices, Do/Don't, Exemplars, and a copy-pasteable "How to Apply" block).
  Each transcript is capped at `extract_max_chars` (default **200k**) via
  `_sample_for_extraction`, which keeps a **head+tail sample (~60/40)** rather than
  a head-only slice — long-form videos (e.g. 30-min explainers) otherwise lost
  their endings, corrupting the `closing`/`narrative_structure` extracts. The
  `_meta.truncated` flag still records when a transcript overflowed the cap.
  Test: `scripts/test_script_style_extraction.py`.
- **UI** — `/script-styles` page: style library (left) + per-style detail (add
  transcripts → analyze → view guide), with an agent-session dropdown.
- Endpoints: `GET/POST /api/script-styles`, `GET/DELETE /api/script-styles/{id}`,
  `POST .../{id}/add-text|upload-file|add-youtube|analyze`, `POST .../{id}/remove-source/{slug}`,
  `GET .../{id}/guide`.
- **M2 (done, 2026-06-25) — apply a guide to script generation:**
  `ScriptConverter` (`script.py`) takes an optional `style_guide`; its
  `extract_style_instruction` pulls the guide's "How to Apply" block (fallback:
  whole guide) and injects it as the **system prompt**, plus a per-section
  instruction to write in that voice. `process_essay` accepts `style_id` (loads
  the guide from the library); the **New-from-Essay wizard (`/process`)** has a
  "Script style (optional)" dropdown listing styles that have a guide.
- **M3 (done, 2026-06-25) — channel acquisition:** `YouTubeClient.list_channel_videos`
  (flat enumeration of a channel's /videos tab; accepts @handle, UC… id, full URL,
  or bare handle via `channel_videos_url`) + `operations.fetch_channel`. Two modes:
  **last-N** (newest videos) and **date window** (`date_after`/`date_before`;
  newest-first with early-stop, probing per-video dates via `get_info` when flat
  entries lack them). Reuses `fetch_transcripts` for the actual fetch (dedup +
  pacing + 429 backoff). Endpoint `POST /api/script-styles/{id}/add-channel`; UI
  has a channel input with a last-N / date-range toggle on `/script-styles`.

### Script Projects — subject + style + sources → grounded script.md (2026-06-25)

The missing **front stage** of the pipeline: write a new, *source-grounded* script
from scratch (not the essay→narration adaptation in `script.py`). Output is a
normal **Director-ready project** (`projects/<slug>/` with `project.yaml` +
`script.md`), so it flows straight into `script_to_scenes → … → render` with no glue.

- **Store** (`src/nolan/scriptwriter/store.py`, `ScriptProjectStore`) — scaffolds a
  Director-ready project (same `project.yaml`/dir tree as `nolan projects init`) plus
  a `scriptgen/` workspace the Director ignores: `meta.json`, `brief.md`,
  `sources/{sources.md, raw/}`, `facts.md`, `factcheck.md`, `citations.md`. Sources
  are pasted text/files (saved to `raw/`, `status=fetched`) or bare URLs
  (`status=pending`, fetched by the agent).
- **Task brief** (`scriptwriter/tasks.py`, `write_script_task`) — the agent brief
  (mirrors `_style_synthesis_task`): fetch pending URLs via WebFetch → ground
  `facts.md` (every claim tagged `[S#]` or `[model: needs-check]`) → draft `script.md`
  using the chosen style's **How to Apply** block → fact-check. **Grounded-but-graceful**
  policy: prefer source-backed claims, allow flagged model-knowledge, never present
  unverified as certain. Output obeys the Director contract (`## ` beat headings +
  `**Total Duration:** M:SS`).
- **Dispatch** — `operations.write_script` writes the task file and dispatches to a
  tmux Claude agent (same mechanism as `analyze_style`); **standalone** — drops a
  Director-ready project, handoff to render stays a separate step.
- **Reuse, not rebuild:** voice from `ScriptStyleStore.read_guide(style_id)`; project
  shape + dir tree from `projects init`; agent dispatch from `analyze_style`. The new
  parts are only the sourcing/grounding layer + the fact-check gate.
- **UI** — `/script-projects` page: create (subject + style dropdown + angle/pivot/
  minutes) → add sources (**URL / paste / file upload** of .txt/.md/.srt/.vtt) →
  **Write script** with **live job progress** (polls `/api/jobs/{id}`) → view `script.md`
  and the **grounding artifacts** (Brief / Facts / Fact-check / Citations, plus each
  source's fetched text) in an in-page viewer.
- Endpoints: `GET/POST /api/script-projects`, `GET/DELETE /api/script-projects/{slug}`,
  `POST .../{slug}/add-source|upload-file|remove-source/{sid}|write`,
  `GET .../{slug}/script|artifact/{name}|source/{sid}`.
- Tested by `scripts/test_scriptwriter.py` (store scaffolding, source handling, artifact/
  source reads, task brief content — no LLM needed); UI verified live via headless render.
- **Note:** two distinct `style_guide.md` exist — `script_styles/<id>/style_guide.md`
  (narrative voice) vs `projects/<slug>/style_guide.md` (visual/scene, written by the
  Director). Disambiguating the project one (→ `visual_style.md`) is a recommended
  follow-up cleanup, not yet done.

### Video Styles — reference videos → visual style guide (2026-06-26)

The **visual twin of Script Styles**: distill the *production / visual* style of
reference library videos into a reusable `video_style_guide.md` so a similar look
(and visual-verbal feel) can be cloned. Mirrors the Script Styles flow — corpus →
per-video extract → agent synthesis → guide. **Descriptive-only v1** (not yet wired
into the render pipeline).

- **Module** `src/nolan/video_style/`:
  - `store.py` (`VideoStyleStore`) — file-backed `video_styles/<id>/`: `manifest.json`
    (reference videos + optional `script_style_id` pairing), `per_video/<slug>.json`,
    `frames/<slug>/`, `video_style_guide.md`. Dedups by video_path.
  - `visual_stats.py` — **deterministic** (OpenCV/NumPy, no LLM): format (aspect/fps/
    duration/orientation), color (k-means palette hex, saturation/contrast, warm↔cool),
    motion (frame-diff), graphics (edge/overlay density), pacing-from-segments
    (cuts/min, shot-length stats, tempo).
  - `pairing.py` — **script↔visual relationship** (the differentiator): per segment,
    BGE-cosine **directness** between `transcript` (said) and `combined_summary`/
    `frame_description`+`inferred_context` (shown), reusing `vector_search`'s embedder.
    Bands literal/associative/tonal, with distribution, arc variation (open/mid/close),
    and paired said↔shown samples for the agent. Needs an indexed video.
  - `tempo.py` — **video-measured** editing tempo (not the index proxy): true shot-cut
    detection (HSV-histogram diff, motion-robust), a windowed cuts/min **curve** + trend
    (accelerates/steady/decelerates/varied), and **motion-weighted energy** (intra-shot
    motion of non-cut transitions blended with cut-rate). On Liu Xiu it found 66 real
    cuts vs the index's 25 segments (~2.6× undercount). Primary pacing signal;
    `pacing_from_segments` is the cheap fallback.
  - `vision_pass.py` — style-focused vision prompt (cinematography/color/lighting/
    graphics) over sampled frames; provider injectable (defaults to **OpenRouter**, not
    Gemini, when run via `analyze_video_style`).
  - `extract.py` — samples the video once and assembles stats + pacing + pairing +
    cinematography into `per_video/<slug>.json` (+ caches frames). Graceful-degrades
    when un-indexed (no pairing) or no vision provider.
  - `tasks.py` — synthesis brief (sections incl. the **Script ↔ Visual Pairing** one).
- **Dispatch** — `operations.analyze_video_style`: per-video extract (loads segments
  from the index, runs stats+pairing+vision), then dispatches synthesis to the `nolan2`
  tmux agent (same mechanism as `analyze_style`).
- **UI** — `/video-styles` page: create → pick reference videos from the **library**
  (indexed videos flagged) → pair with a Script Style → **Analyze** (live job poll) →
  view per-video extract JSON + the guide.
- Endpoints: `GET/POST /api/video-styles`, `GET/DELETE /api/video-styles/{id}`,
  `POST .../{id}/add-video|remove-source/{slug}|pair-script|analyze`,
  `GET .../{id}/guide|extract/{slug}`.
- Reuses: `sampler`/cv2 (frames), `vector_search` BGE embedder (pairing), `vision.py`
  provider, `VideoIndex.get_segments`, the Script Styles store/UI/agent-dispatch pattern.
- Tested (no model/db needed): `scripts/test_video_style.py` (stats+store),
  `test_pairing.py`, `test_vision_pass.py`, `test_extract.py`,
  `test_video_style_synthesis.py`, `test_tempo.py`; UI verified headless.
  **End-to-end validated** on the indexed 「劉秀」 video (real BGE + OpenRouter vision +
  tempo) → `video_styles/liu-xiu-historical-narrative/`.
- Real-run fixes: non-ASCII paths broke `cv2.imwrite` (→ `imencode`+`tofile` + ASCII
  slugs); pairing bands recalibrated to **0.72/0.58** (BGE related-pairs cluster
  0.55–0.80); on-screen-text inflates said↔shown similarity (documented; future: strip
  rendered narration before embedding).
- **Open:** pairing bands still single-video-calibrated; on-screen-text confound; the
  tempo `energy` blend + cut threshold are heuristics; executable mapping (guide →
  render pipeline) is a deferred phase.

### YouTube Integration
- **Video Download** - Download YouTube videos using yt-dlp
  - Single video, batch from file, or entire playlists
  - Configurable quality formats (default: 720p)
  - Automatic subtitle download — fetches only the **video's original
    language** (detected from yt-dlp metadata) instead of all configured
    languages, avoiding YouTube's HTTP 429 subtitle rate-limit. If a subtitle
    download still fails, the video is **retried once without subtitles** so the
    download succeeds and the Whisper fallback transcribes it.
  - Progress tracking with callbacks
- **YouTube Search** - Search for videos without downloading
  - Returns video metadata (title, duration, views, channel)
  - Export results to JSON
  - Optional: download first result directly
- **Video Info** - Get detailed metadata for a single video
  - Title, description, tags, categories
  - Duration, views, upload date
  - Channel information

## Usage

```bash
# Install in development mode
pip install -e ".[dev]"

# === Video Production Workflow ===

# Step 1: Convert essay to script
nolan script path/to/essay.md -o ./output
# Outputs: script.md (human-readable), script.json (for design)

# Step 2: Design scenes from script
nolan design ./output/script.json
# Outputs: scene_plan.json

# Or run full pipeline in one command
nolan process path/to/essay.md -o ./output

# Index video library (Ollama vision - local)
nolan index path/to/videos --recursive

# Index with Gemini vision (cloud - faster, async)
nolan index path/to/videos --vision gemini

# Control concurrency for rate limits
nolan index path/to/videos --vision gemini --concurrency 3   # free tier
nolan index path/to/videos --vision gemini --concurrency 10  # pay-as-you-go (default)
nolan index path/to/videos --vision gemini --concurrency 30  # higher tiers

# Choose frame sampling strategy (ffmpeg_scene is default, 10-50x faster)
nolan index path/to/videos --sampler ffmpeg_scene  # Fast FFmpeg-based (default)
nolan index path/to/videos --sampler hybrid        # Python-based, more sensitive to gradual changes
nolan index path/to/videos --sampler fixed         # Fixed 5-second intervals

# Index with Whisper auto-transcription (GPU accelerated)
nolan index path/to/videos --vision gemini --whisper --whisper-model base

# Export indexed segments to JSON
nolan export video.mp4 -o segments.json
nolan export --all -o library.json

# Cluster segments into story moments
nolan cluster video.mp4 -o clusters.json
nolan cluster video.mp4 --refine  # Use LLM for better boundaries
nolan cluster --all -o all_clusters.json

# Browse indexed library in web UI
nolan browse

# === Semantic Search ===

# Sync index to vector database (first time or after new indexing)
nolan sync-vectors
nolan sync-vectors --project venezuela  # Only sync specific project
nolan sync-vectors --clear              # Clear and rebuild

# Semantic search with natural language
nolan semantic-search "person looking worried"
nolan semantic-search "dramatic landscape" --level clusters
nolan semantic-search "Hugo Chavez speaking" --project venezuela --level segments
nolan semantic-search "emotional moment" -n 20 -o results.json

# Launch viewer for project outputs
nolan serve -p ./output

# Generate images with custom ComfyUI workflow
nolan generate-test "a dragon" -w workflow_api.json
nolan generate-test "a dragon" -w workflow.json -n "26:24"  # explicit prompt node
nolan generate-test "a dragon" -w workflow.json -s "13:width=1536" -s "3:steps=40"

# Search for images from web/stock photos
nolan image-search "sunset mountains"
nolan image-search "sunset mountains" -s pexels -n 20  # Pexels (needs API key)
nolan image-search "sunset mountains" -s all -o results.json  # all sources

# Search public domain sources
nolan image-search "Hugo Chavez" -s wikimedia  # Wikimedia Commons
nolan image-search "Abraham Lincoln" -s loc     # Library of Congress
nolan image-search "dinosaur" -s smithsonian    # Smithsonian (needs API key)

# Score images by relevance using vision model
nolan image-search "sunset mountains" --score --vision gemini
nolan image-search "sunset mountains" --score --vision ollama -c "for a travel documentary"

# Generate infographics (requires render-service running)
nolan infographic --title "My Process" -i "Step 1:First" -i "Step 2:Second"
nolan infographic --template list --theme dark --title "Features" -i "Fast:Blazing speed"
nolan infographic --template comparison --theme warm --title "A vs B" -i "Option A:Pro A" -i "Option B:Pro B"
nolan infographic spec.json -o my_infographic.svg  # From JSON spec file

# === YouTube Operations ===

# Search YouTube for videos
nolan yt-search "python tutorial" -n 5          # Search and show top 5 results
nolan yt-search "documentary" -o results.json   # Export results to JSON
nolan yt-search "cooking tips" --download       # Search and download first result

# Download YouTube videos
nolan yt-download "https://youtube.com/watch?v=xxxxx"                      # Single video
nolan yt-download urls.txt -o ./videos                                     # From file (one URL per line)
nolan yt-download "https://youtube.com/playlist?list=xxxxx" --playlist     # Entire playlist
nolan yt-download "https://youtube.com/playlist?list=xxxxx" --limit 10     # First 10 from playlist
nolan yt-download "https://youtube.com/watch?v=xxxxx" -f "bestvideo[height<=1080]+bestaudio"  # Custom quality

# Get video info without downloading
nolan yt-info "https://youtube.com/watch?v=xxxxx"                          # Show video metadata
nolan yt-info "https://youtube.com/watch?v=xxxxx" -o video_info.json       # Save to JSON

# === Project Management ===

# Create a new project
nolan projects create "Venezuela Documentary" -d "Documentary about Hugo Chavez"
nolan projects create "My Project" -s custom-slug -p projects/my-project   # Custom slug and path

# List all projects
nolan projects list                                                         # Shows slug, name, video count

# View project details
nolan projects info venezuela                                               # Show project info and videos

# Index videos scoped to a project
nolan index path/to/videos --project venezuela                              # Associate videos with project

# Delete a project
nolan projects delete venezuela                                             # Remove from registry only
nolan projects delete venezuela --delete-videos                             # Also delete indexed videos
```

## Test Coverage

174 tests covering all modules:
- Configuration: 3 tests
- LLM Client: 2 tests
- Parser: 3 tests
- Script Converter: 5 tests
- Scene Designer: 3 tests
- Video Indexer: 5 tests
- Asset Matcher: 3 tests
- ComfyUI Client: 3 tests
- Viewer Server: 3 tests
- CLI: 4 tests
- Integration: 2 tests
- Vision Provider: 9 tests
- Sampler: 11 tests
- Transcript: 15 tests
- Analyzer: 10 tests
- Whisper: 17 tests
- Clustering: 34 tests
- Lottie: 42 tests (NEW)

## Project Structure

```
NOLAN/
├── src/nolan/
│   ├── __init__.py      # Package version
│   ├── __main__.py      # Module entry point
│   ├── cli.py           # CLI commands
│   ├── config.py        # Configuration loading
│   ├── llm.py           # Gemini client
│   ├── parser.py        # Essay parsing
│   ├── script.py        # Script conversion
│   ├── scenes.py        # Scene design
│   ├── indexer.py       # Video indexing + HybridVideoIndexer
│   ├── matcher.py       # Asset matching
│   ├── comfyui.py       # ComfyUI integration
│   ├── viewer.py        # Viewer server
│   ├── vision.py        # Vision providers (Ollama, Gemini)
│   ├── sampler.py       # Smart frame sampling
│   ├── transcript.py    # Transcript loading/alignment
│   ├── analyzer.py      # Segment analysis + inference
│   ├── whisper.py       # Whisper auto-transcription
│   ├── clustering.py    # Scene clustering
│   ├── aligner.py       # Scene-to-audio alignment
│   ├── library_viewer.py # Library browser server
│   ├── image_search.py  # Image search providers
│   ├── assets.py        # Asset management for motion effects
│   └── templates/
│       ├── index.html   # Viewer UI
│       ├── scenes.html  # Scene plan A/B viewer
│       └── library.html # Library browser UI
├── tests/               # Test suite (174 tests)
├── render-service/      # Node.js microservice for infographics/animations
│   ├── src/
│   │   ├── server.ts    # Express API server
│   │   ├── routes/      # API endpoints (health, render)
│   │   ├── jobs/        # Job queue and types
│   │   └── engines/     # Render engines (infographic, etc.)
│   └── package.json
├── assets/              # Visual assets for motion effects
│   ├── common/icons/    # Shared SVG icons (check, star, etc.)
│   └── styles/          # Style-specific assets (per EssayStyle)
├── pyproject.toml       # Package configuration
└── .env                 # API keys (not committed)
```

## Requirements

- Python 3.10+
- Gemini API key (set `GEMINI_API_KEY` in .env)
- Ollama (optional, for local vision model)
- ffmpeg (optional, for Whisper auto-transcription)
- ComfyUI (optional, for image generation)
- Node.js 18+ (optional, for Infographic & Animation Render Service)

## Documentation

| Document | Description |
|----------|-------------|
| [Fair Use Transforms](docs/FAIR_USE_TRANSFORMS.md) | Strategies for transforming third-party clips to reduce copyright detection |
| [Motion Effects](docs/MOTION_EFFECTS.md) | Motion effects library for video essays |
| [TTS Integration](docs/TTS_INTEGRATION.md) | Voiceover generation with MiniMax and Chatterbox |
| [LLM Content Authoring](render-service/docs/LLM_CONTENT_AUTHORING.md) | Guide for LLMs writing content with style markup |

## Next Steps (Backlog)

### Autonomous Quality System (Priority)

See [docs/plans/2026-01-30-autonomous-quality-system.md](docs/plans/2026-01-30-autonomous-quality-system.md) for full design.

**Goal:** Enable NOLAN to produce high-quality video clips autonomously with minimal human intervention.

**Four-Layer Approach:**
1. **Scope to Strengths** - Route visual types to appropriate pipelines (templates vs. generation)
2. **Template Library** - Expand Lottie/Motion Canvas templates for automatable content
3. **Video Generation** - Integrate LTX-Video/Runway for b-roll and cinematic content
4. **Quality Evaluation** - Vision-based scoring with retry loops and human fallback

**Phase 1 (Template System): COMPLETE**
- [x] Unified template catalog (`TemplateCatalog` class)
- [x] Semantic tagging (240+ auto-generated tags)
- [x] CLI commands (`nolan templates list/search/info/semantic-search/match-scene`)
- [x] Semantic template discovery (ChromaDB + BGE embeddings)
- [x] Scene-to-template matching (`find_templates_for_scene()`)
- [x] Visual type router (`VisualRouter` class in `visual_router.py`)
- [x] CLI: `nolan route-scenes` - show routing decisions
- [x] CLI: `nolan render-templates` - render templates to video clips
- [ ] Template library expansion (200+ templates - currently 52)
- [ ] Template schema completion for all templates (13/52 have schemas)

**Phase 2 (Quality Evaluation):**
- [ ] Quality scoring prompts (semantic fit, visual quality, style consistency)
- [ ] Quality gate integration after asset generation
- [ ] Per-video style guide system

**Phase 3 (Video Generation):**
- [ ] LTX-Video integration (self-hostable)
- [ ] Runway API integration (commercial)
- [ ] Video generation router with cost management

**Phase 4 (Human Review):**
- [ ] Review queue with priority scoring
- [ ] Review web UI for flagged scenes
- [ ] Notification system for pending reviews

---

- **Database-Backed Asset Management** - SQLite storage for large asset libraries (100+ assets)
  - Search by name, tags, category
  - Asset versioning and thumbnails
  - CLI for asset management (`nolan assets list/add/tag`)
  - Trigger: Implement when asset count justifies complexity
- **TTS Voiceover Generation** - `nolan voiceover` command with MiniMax API and Chatterbox local fallback
- **End-to-End Orchestrator** - `nolan make-video` single command for full pipeline automation
- **Fair Use Transform Presets** - Implement `--fair-use-transform` flag for automated clip transformation
- **AI Clip Regeneration** - `nolan regenerate-clips` using LTX-2 / Wan I2V to create new AI videos from key frames
- **yt-fts transcript search integration** - Use YouTube transcript search for full-text search
- **LLM infographic placement** - Detect data points in scripts and suggest infographic placement
- **HunyuanOCR integration** - Text extraction from video frames (subtitles, on-screen text, titles)
- **Image search browser display** - View image search results in web UI
- **Vision model image selection** - Auto-select best matching images using vision model
- **dotLottie Integration** ✅ COMPLETED
  - ✅ Spike completed: frame-accurate rendering with `setFrame()` works
  - ✅ No flickering observed (unlike @remotion/lottie)
  - ✅ `LottieAnimation` component added to Remotion engine
  - ✅ Python utility module: `src/nolan/lottie.py` (customize_lottie, validate, transform colors)
  - ✅ Scene plan support: `visual_type: "lottie"` with `lottie_template` and `lottie_config`
  - ✅ Asset library structure: `assets/common/lottie/` (lower-thirds, transitions, icons, etc.)
  - ✅ ThorVG engine supports: expressions, drop shadows, blur, masks, gradients, text
  - Test files: `render-service/test/dotlottie-spike/`
  - Docs: [docs/LOTTIE_INTEGRATION.md](docs/LOTTIE_INTEGRATION.md)
  - See: [ThorVG Lottie Support](https://github.com/thorvg/thorvg/wiki/Lottie-Support)
- **Lottie Template Catalog** ✅ COMPLETED (was: Motion Pattern Library)
  - ✅ LottieFiles Downloader: `src/nolan/lottie_downloader.py`
    - Rate-limited downloads (15-20 req/min), metadata extraction, duplicate detection
    - Color palette extraction, search functionality
  - ✅ Jitter.video Downloader: `src/nolan/jitter_downloader.py`
    - Playwright browser automation for Jitter's SPA
    - Category discovery, multi-artboard handling, blob content extraction
    - CLI: `python -m nolan.jitter_downloader --essential`
  - ✅ Lottieflow Downloader: `src/nolan/lottieflow_downloader.py`
    - Bulk download via network interception (no login required)
    - 21 categories of UI micro-interactions
    - CLI: `python -m nolan.lottieflow_downloader --essential`
  - ✅ 50+ production-ready animations across multiple sources:
    - LottieFiles: lower-thirds (2), title-cards (1), transitions (2), data-callouts (2), progress-bars (2), loaders (1), icons (2)
    - Jitter: text effects (glide, morph, sliding reveal), icons (rotate-scale)
    - Lottieflow: menu-nav (5), arrows (5), checkboxes (3), loaders (5), play (3), scroll-down (3), success (3), attention (3)
  - ✅ Catalogs: `catalog.json`, `jitter-catalog.json`, `lottieflow-catalog.json`
  - ✅ Template Schema System: `src/nolan/lottie.py`
    - `analyze_lottie()` - Discover customizable fields (text, colors, timing)
    - `generate_schema()` / `save_schema()` - Create `.schema.json` files
    - `render_template()` - Magicbox API with semantic field names
    - `list_templates()` - List templates with schema status
  - ✅ Curated schemas for 3 templates: magic-box, modern lower-third, simple lower-third
  - ✅ 42 tests: `tests/test_lottie.py`
  - ✅ Docs: [docs/LOTTIE_INTEGRATION.md](docs/LOTTIE_INTEGRATION.md#lottie-template-catalog)
- **Template Analysis Tool** - CLI to help document animation timing from reference
  - `nolan analyze-template <video>` to measure keyframes and timing
  - Export structured motion specs from reference videos
- **SVG Animation Import** - Parse animated SVGs (SMIL) to Motion Canvas code
  - Convert SMIL animations to Motion Canvas generator functions
  - Preserve timing, easing, and transform sequences
- **Canva Static Export** - Download Canva designs as static assets via API
  - OAuth flow for [Canva Connect API](https://www.canva.dev/docs/connect/)
  - Export PNG/SVG elements from Canva templates
  - Animate exported assets in NOLAN with custom timing
  - Note: No animation keyframe access, static export only

## Recently Completed

- ✅ **Animated Scene Renderer** - Codified animation system for generating animated video scenes
  - **nolan.renderer package** - Complete animation rendering framework:
    - `BaseRenderer` - Base class for all scene renderers with frame-by-frame rendering
    - `Element` - Scene element (text, rectangle, image) with property animation
    - `Timeline` - Global timing management for fade in/out sequences
    - `Easing` - 27 easing functions (linear, quad/cubic/quart/expo, back, elastic, bounce, spring, bezier)
  - **Composable Effects System** (46+ effects):
    - **Basic**: `FadeIn`, `FadeOut`, `SlideUp`, `SlideDown`, `SlideLeft`, `SlideRight`, `MoveTo`, `ScaleIn`, `ScaleOut`, `ExpandWidth`
    - **Text**: `TypeWriter`, `Reveal` (word/char), `CountUp` (number animation with prefix/suffix)
    - **Emphasis**: `Shake`, `Flash`, `Bounce`, `Glitch`, `Pulse`, `Hold`
    - **Rotation**: `RotateIn`, `RotateOut`, `Spin`, `Wobble`
    - **Blur/Focus**: `BlurIn`, `BlurOut`, `FocusPull`, `PulseBlur`
    - **Shadow**: `ShadowIn`, `ShadowOut`, `ShadowPulse`
    - **Glow**: `GlowIn`, `GlowOut`, `GlowPulse`, `Highlight`
    - **Color**: `ColorShift`, `ColorTint`
    - **Annotation**: `Underline` (incl. `style="highlight"` marker sweep with phrase-based `highlight_text` selection), `Strikethrough`, `CircleAnnotation`, `ArrowPoint`
    - **Cinematic**: `Letterbox`, `Scanlines`, `VHSEffect`
    - **Drawing**: `DrawLine`, `DrawBox`
    - **Sequencing**: `Loop`, `Sequence`, `Delay`, `StaggeredFadeIn`
    - Effects are stackable: multiple effects can be applied to a single element
  - **Easing Functions** (27 total):
    - Standard: `linear`, `ease_in/out/in_out_quad`, `ease_in/out/in_out_cubic`, `ease_in/out/in_out_quart`, `ease_in/out/in_out_expo`
    - Special: `ease_in/out/in_out_back` (overshoot), `ease_in/out/in_out_elastic` (spring), `ease_in/out/in_out_bounce`
    - Advanced: `spring` (physics-based), `bezier` (custom cubic bezier curves)
  - **Position/Layout System** (`layout.py`):
    - **Position System** (percentage-based): `Position` dataclass with x/y percentages (0-1)
      - 16 named presets: center, lower-third, upper-third, corners, split-screen
      - All renderers accept `position` parameter for placement control
    - **Slot/Layout System** (region-based): Cross-platform screen division
      - `Slot` - Rectangular region with x, y, width, height, padding
      - `Layout` - Divides screen into slots (columns, rows, grids)
      - `get_preset()` - Named layouts: "thirds", "golden", "split-1-2", "grid-2x2", etc.
      - JSON-serializable for Motion Canvas/Remotion integration
      - Templates can accept custom layouts as input
    - Aligns with render-service layout system for consistency
  - **Scene-Specific Renderers** (27 total):
    - **Core** (10): `QuoteRenderer`, `TitleRenderer`, `StatisticRenderer`, `ListRenderer`, `LowerThirdRenderer`, `CounterRenderer`, `ComparisonRenderer`, `TimelineRenderer`, `KenBurnsRenderer`, `FlashbackRenderer`
    - **Text Cards** (5): `DefinitionRenderer`, `SourceCitationRenderer`, `PullQuoteRenderer`, `QuestionRenderer`, `VerdictRenderer`
    - **Location/Time** (3): `LocationStampRenderer`, `ChapterCardRenderer`, `ProgressBarRenderer`
    - **Data Visualization** (4): `StatComparisonRenderer`, `PercentageBarRenderer`, `RankingRenderer`, `PieCalloutRenderer` (5-beat donut/pie: intro → scale-down → colour slice by % → eject slice → info-text reveal; controllable `pie_center`)
    - **Media Mockup** (3): `TweetCardRenderer`, `NewsHeadlineRenderer`, `DocumentHighlightRenderer` (its `highlight_text` param drives a phrase-targeted highlighter sweep)
    - **Transitions** (1): `SectionDividerRenderer`
    - **Portrait/Figure** (1): `portrait_reveal` - portrait slides aside to reveal bullet points (from video analysis)
    - **Smart Text Layout**: Automatic line wrapping with `max_width`, `max_lines`, dynamic font sizing
  - **Preset Functions** - One-line rendering for common scene types:
    - `documentary_quote()` - Dark background, red accent documentary style
    - `documentary_title()` - Near-black background, white title, red accent
    - `historical_year()` - Sepia tones, gold accents for historical content
    - `big_number()` - Statistics with modern/danger/success styles
    - `chapter_title()` - Chapter number and title combination
  - **Style Presets** - `StylePresets` class with documentary, historical, modern_clean, danger, success color schemes
  - **Frame-by-Frame Pipeline**:
    - Uses PIL for reliable text rendering (avoids MoviePy TextClip font issues)
    - Pre-renders all frames with eased properties
    - Composes into video using MoviePy VideoClip
    - Integrated with Quality Protocol for auto-validation
  - **Location**: `src/nolan/renderer/` (base.py, easing.py, effects.py, layout.py, text_layout.py, scenes/, presets.py)
  - **Test scripts**:
    - `scripts/test_all_renderers.py` - Tests core scene renderers
    - `scripts/test_venezuela_templates.py` - Tests all 15 new templates with Venezuela content
    - `scripts/test_new_effects.py` - Tests 10 advanced effects (CountUp, Shake, Rotation, Blur, Shadow, Glow, etc.)
    - `scripts/test_annotation_effects.py` - Tests 8 annotation/cinematic effects (Underline, Letterbox, Scanlines, etc.)
    - `scripts/test_highlight_sweep.py` - Tests the highlight-marker sweep (`Underline(style="highlight")`) and phrase-based selection
    - `scripts/test_pie_callout.py` - Tests the 5-beat donut callout (`PieCalloutRenderer`): slice tracks %, text reveal, controllable location

- ✅ **Quality Protocol Module** - Automated validation and fix system for rendered video content
  - **nolan.quality package** - Core quality assurance module:
    - `QualityProtocol` - Main validation class with configurable checks
    - `QAConfig` - Configuration for checks, tolerances, and auto-fix settings
    - `QAResult` / `QAIssue` - Result types with pass/fail status and issue details
  - **Validation checks**:
    - Properties: file exists, duration, resolution, file size
    - Visual: blank frame detection, brightness analysis
    - Text (optional): OCR-based text verification via pytesseract
    - Visual text comparison: reference-based text rendering quality check
  - **Auto-fix system**:
    - Font fallback chain for text rendering issues
    - Re-render with corrected parameters
    - Configurable max fix attempts
  - **Root cause discovery**: MoviePy TextClip has font rendering issues (character cutoff)
    - Solution: Use PIL direct text rendering + moviepy video encoding
    - `create_quote_frame()` function for reliable text rendering
  - **Integration**: `render_with_quality_check()` wrapper function
  - **Design document**: `docs/quality-protocol-design.md`
  - Location: `nolan/quality/` (protocol.py, types.py, checks/)

- ✅ **Video Generation Integration** - Dual-backend video generation for autonomous content creation
  - `VideoGenerator` abstract base class with unified interface
  - `ComfyUIVideoGenerator` for local video models (LTX-Video, Wan, HunyuanVideo, CogVideoX, AnimateDiff)
  - `RunwayGenerator` for commercial API (Gen-3 Alpha Turbo, Gen-3 Alpha)
  - Auto-detection of prompt nodes in ComfyUI workflows
  - Scene-to-video generation with optimized prompts: `generate_video_for_scene()`
  - CLI: `nolan video-gen check/generate/scene/batch`
  - Cost tracking for commercial API usage
  - Part of Autonomous Quality System Phase A-2
- ✅ **Visual Router** - Intelligent scene-to-pipeline routing for asset generation
  - `VisualRouter` class routes scenes to appropriate pipelines
  - Route types: template, library, generation, infographic, passthrough
  - Template types: lower-third, text-overlay, title, counter, icon, loading, lottie, ui
  - Library types: b-roll, a-roll, footage, cinematic
  - Generation types: generated, generated-image
  - Template matching with score threshold (default 0.5)
  - CLI: `nolan route-scenes`, `nolan render-templates`
  - Part of Autonomous Quality System Phase A-3
- ✅ **Template Catalog System** - Unified Lottie template management for autonomous video generation
  - `TemplateCatalog` class merges LottieFiles, Jitter, Lottieflow sources
  - 53 templates across 17 categories with auto-tagging (240+ tags)
  - `TemplateSearch` with ChromaDB vector embeddings for semantic search
  - Scene-to-template matching: `find_templates_for_scene()`, `match_scene_to_template()`
  - CLI: `nolan templates list/info/search/semantic-search/match-scene/index/auto-tag`
  - Visual type routing maps scene types to template categories
  - Part of Autonomous Quality System Phase A-1
- ✅ **Video Library Clip Matching** - `nolan match-clips` command for matching scenes to library clips
  - Semantic search using ChromaDB vector database finds relevant clips
  - LLM selection picks best candidate considering visual relevance, narrative fit, and duration
  - Smart clip tailoring algorithm: skips first 7% (avoid transitions), ratio-based centering
  - Combines `narration_excerpt + visual_description + search_query` for rich search queries
  - Configurable via `clip_matching` section in nolan.yaml:
    - `candidates_per_scene`: Top N candidates (default: 3)
    - `min_similarity`: Threshold 0-1 (default: 0.5)
    - `search_level`: segments, clusters, or both
  - Updates `matched_clip` field in scene_plan.json with video_path, clip_start, clip_end, reasoning
  - Supports --dry-run, --project filter, --skip-existing options
- ✅ **Semantic Search UI** - Toggle between keyword and semantic search in library viewer
  - Search mode toggle button (Keyword/Semantic) in web UI
  - Semantic scores displayed as percentage badges (e.g., "69.3%")
  - Fields dropdown hidden in semantic mode (not applicable)
  - `/api/search/semantic` API endpoint for programmatic access
- ✅ **Adaptive Scene Detection** - Automatic threshold tuning per video
  - Uses statistical analysis (mean + 5σ) to find significant scene changes
  - Adapts to different editing styles: fast cuts get higher threshold, slow pacing gets lower
  - Example: Fast-cut video (10.8 segments/min) vs slow video (5.1 segments/min)
  - Runs FFmpeg once to collect all scores, then filters - no repeated processing
  - Configurable sigma multiplier (default 5.0) in SamplerConfig
  - Falls back to fixed threshold if specified (for backwards compatibility)
  - **Score caching**: Saves frame scores to `video.scores.json` for instant reindexing
    - Skips FFmpeg on reindex if video unchanged (checks mtime + size)
    - ~100s savings on 40-min video reindex
  - **FFmpeg frame extraction**: Uses FFmpeg with input seeking instead of CV2
    - 3.7x faster frame extraction (190ms vs 700ms per frame)
    - Uses libdav1d for AV1 videos (faster decoder)
- ✅ **FFmpeg Scene Detection** - 10-50x faster frame sampling (new default)
  - Uses FFmpeg's hardware-accelerated scene detection filter
  - Only decodes frames at detected scene changes (vs every frame)
  - Respects min/max interval constraints for coverage
  - 30-min video: ~5 seconds (vs 3-8 minutes with Python-based hybrid)
  - Codec-aware decoder selection (libdav1d for AV1, native for others)
  - Use `--sampler hybrid` to fall back to Python-based detection
- ✅ **Combined Vision+Inference** - Single API call per frame (50% fewer calls)
  - Frame + transcript analyzed together in one vision call
  - Better inference: vision model can recognize faces, read text
  - Cost: ~$0.03-0.05 for 30-min video (vs ~$0.06-0.10 before)
- ✅ **Auto-Whisper Transcription** - Enabled by default when no subtitle exists
  - Generates transcripts automatically using faster-whisper
  - ~45 sec for 30-min video on GPU (base model)
  - Use `--no-whisper` to opt-out
- ✅ **Language-coded Subtitles** - Support for yt-dlp style .en.srt files
- ✅ **Async Batch Indexing** - ~10x faster video indexing with concurrent API calls
  - Process multiple frames in parallel using asyncio with semaphore
  - `--concurrency` CLI option to control parallelism (default 10)
  - Rate limit friendly: use 2-3 for free tier, 10-15 for pay-as-you-go
- ✅ **Project Registry** - Organize videos by project with human-friendly slugs
  - `nolan projects create/list/info/delete` commands for project management
  - Projects have internal UUIDs and CLI-facing slugs (e.g., `venezuela`)
  - `nolan index --project <slug>` scopes videos to a project
  - Auto-generated slugs from project names (URL-safe)
  - Database schema v4 with projects table
- ✅ **YouTube Video Download** - Download and organize YouTube videos with yt-dlp
  - Single video, batch, or playlist download
  - Automatic subtitle download (configurable languages)
  - Project-based folder organization
- ✅ **Video Assembly Pipeline** - Two-phase render pipeline for final video output
  - `nolan render-clips`: Pre-render animated scenes (infographics, sync_points) to MP4
  - `nolan assemble`: FFmpeg-based assembly of all assets + voiceover
  - Asset priority: rendered_clip > generated_asset > matched_asset > infographic_asset
  - Automatic scaling/padding to target resolution
  - Support for cut, fade, crossfade transitions
  - Full architecture documented in `docs/plans/2026-01-12-render-pipeline.md`
- ✅ **Scene-Audio Alignment** - `nolan align` command for word-level audio alignment
  - Transcribes audio with word-level timestamps via Whisper
  - Matches scene `narration_excerpt` to word stream using text matching
  - Updates scene_plan.json with `start_seconds` and `end_seconds`
  - Confidence scoring for alignment quality
  - Optional word timestamp export for debugging
- ✅ **Transcription Command** - `nolan transcribe` for audio/video to subtitles
  - Outputs SRT, JSON, or plain text formats
  - GPU (CUDA) with automatic CPU fallback
  - Multiple Whisper model sizes (tiny to large-v3)
- ✅ **B-Roll Image Matching** - `nolan match-broll` command for batch image search and download
  - Searches images for all b-roll scenes using search_query from scene_plan.json
  - Multiple providers: DuckDuckGo (default), Pexels, Pixabay, Wikimedia, Library of Congress
  - Optional vision model scoring (Gemini/Ollama) for relevance ranking
  - Downloads best match for each scene to assets/broll/
  - Updates scene_plan.json with matched_asset paths
  - Supports dry-run mode and skip-existing option
- ✅ **Two-Pass Scene Design** - Professional A/V script workflow based on video essay research
  - Pass 1 (`--beats-only`): Break narration into beats, assign visual categories
  - Pass 2 (default): Enrich beats with category-specific details
  - Visual categories: b-roll, graphics, a-roll, generated, host
  - Identifies "visual holes" (abstract concepts needing creative solutions)
  - Outputs A/V script format (av_script.txt) for human review
  - Based on "The Architecture of the Digital Argument" research
- ✅ **Standalone Script & Design Commands** - Split workflow into separate steps
  - `nolan script` converts essay to script.md + script.json
  - `nolan design` generates scene_plan.json from script.json
  - Script class now supports JSON export/import for workflow persistence
  - Enables review/editing between steps before committing to scene design
- ✅ **Scene Workflow Data Model** - Enhanced Scene dataclass for 5-step video pipeline
  - `SyncPoint` dataclass for word-to-action synchronization (trigger → action at precise time)
  - `Layer` dataclass for complex multi-element scenes (background, overlay, caption)
  - Scene fields for timing alignment: `start_seconds`, `end_seconds`, `subtitle_cues`
  - Animation fields: `animation_type`, `animation_params`, `transition`
  - Progressive enrichment pattern: Scene is a "holder" filled across workflow steps
  - Updated LLM prompt to request sync_points, layers, animation specs
  - Full plan documented in `docs/plans/2026-01-11-scene-workflow.md`
- ✅ **Motion Canvas Engine** - Render-service can export MP4s via Motion Canvas + FFmpeg
  - Generates a temporary Motion Canvas project (project, scene, render entry, spec)
  - Uses Vite + @motion-canvas/vite-plugin + @motion-canvas/ffmpeg for rendering
  - Launches headless Chromium to execute the render pipeline and writes MP4s to output
  - Supports basic spec fields (title, subtitle, items, width, height, duration, theme)
- ✅ **Remotion Engine** - Render-service can export MP4s via Remotion renderer
  - Bundles a temporary Remotion project for each job and renders via @remotion/renderer
  - Infographic composition supports title, subtitle, items, and theme colors
- ✅ **AntV Infographic Engine Enablement** - render-service now supports @antv/infographic via headless Chromium
  - Uses bundled `infographic.min.js` with Puppeteer for SVG extraction
  - Added template aliasing so `steps/list/comparison` map to real AntV templates
  - Added `INFOGRAPHIC_ENGINE` and `engine_mode` to force AntV vs SVG fallback
  - Added `PUPPETEER_EXECUTABLE_PATH`/`CHROME_PATH` support for local Chrome/Edge
  - Debug logging is gated behind `INFOGRAPHIC_DEBUG=1`
- ✅ **Render Service Engine Coverage** - Motion Canvas and Remotion engines now render MP4s
  - Processor wiring routes motion-canvas and remotion jobs to live engines
- ✅ **Render Service Code Quality Refactor** - Cleaned up engine and preset code
  - Extracted common utilities (`ensureDir`, `toNumber`, `toString`) to `engines/utils.ts`
  - Centralized theme definitions in `themes.ts` (used by all 3 engines)
  - Fixed inconsistent null handling: changed 70+ `||` to `??` for numeric params
  - Prevents bugs where falsy values like `0` incorrectly trigger fallbacks
- ✅ **Infographic Scene Integration** - Scene designer supports infographic suggestions
  - Prompt updated to allow infographic visual_type and spec payloads
  - Scene model stores infographic specs and rendered assets
- ✅ **Infographic Batch Rendering** - `nolan render-infographics` renders infographic scenes
  - Writes SVGs to assets/infographics and updates scene_plan.json
- ✅ **Viewer Infographic Review** - project viewer displays infographic specs and previews
  - Summary now includes infographic counts and render status

- ✅ **Infographic CLI Integration** - `nolan infographic` command for generating infographics
  - Connects Python CLI to Node.js render-service via HTTP
  - Three input modes: command-line options, JSON file, stdin pipe
  - Support for templates (steps, list, comparison) and themes (default, dark, warm, cool)
  - Configurable output size and location
- ✅ **Job Processor** - Connect infographic engine to job queue for render-service
  - Job processor polls for pending jobs and processes them through appropriate engines
  - Real-time status and progress updates during rendering
  - Error handling with detailed error messages stored in job
  - Singleton processor started with server
- ✅ **Infographic Engine** - SVG template-based rendering engine for render-service
  - RenderEngine interface abstraction for pluggable engines
  - InfographicEngine with native SVG template generation
  - Multiple templates: steps/sequence, list, comparison
  - Theme support: default, dark, warm, cool color schemes
  - SVG output with gradients, shadows, and proper styling
  - Note: Replaced @antv/infographic due to browser-only limitations
- ✅ **Public Domain Image Sources** - New providers for public domain images
  - Wikimedia Commons (100M+ images, no API key, CC licenses)
  - Library of Congress (historical photos, no API key, public domain)
  - Smithsonian Open Access (2.8M+ images, API key from api.data.gov, CC0)
- ✅ **Image Search Scoring** - Vision model scoring for image relevance
  - Score images from 0-10 with explanations
  - Support for Gemini (cloud) and Ollama (local) vision models
  - Quality scoring (0-10) based on resolution and aspect ratio
  - Combined sorting: relevance first, quality as tiebreaker
  - Fallback download: thumbnail → main URL if thumbnail fails
  - Optional context for better scoring (e.g., "for a documentary")
- ✅ **Image Search** - `nolan image-search` command for finding images from web/stock photos
  - DuckDuckGo search (no API key required)
  - Pexels and Pixabay stock photo APIs (optional, with API keys)
  - JSON output with URLs, thumbnails, dimensions
  - Extensible provider system for adding more sources
- ✅ **ComfyUI Custom Workflows** - Full workflow customization support
  - Load any ComfyUI workflow exported in API format
  - Explicit prompt node selection (`--prompt-node`)
  - Generic parameter overrides (`--set "node:param=value"`)
  - Auto-detection fallback for common workflow patterns
- ✅ **Video Index Viewer** - `nolan browse` command for browsing indexed video library
  - Browse videos and their segments in web UI
  - View frame descriptions, transcripts, inferred context
  - View clusters with summaries
  - Video preview playback at timestamps
  - Full-text search across segments
- ✅ **Scene Clustering** - `nolan cluster` command for grouping segments into story moments
  - Groups by shared characters, location, and story context
  - Optional LLM-based story boundary detection (`--refine`)
  - Cluster-level summaries for deeper narrative understanding
- ✅ **Export command** - `nolan export` for full JSON output with all fields
- ✅ **Gemini vision CLI** - `--vision gemini` option for cloud-based frame analysis (3-4x faster)
- ✅ **GPU Whisper** - CUDA acceleration with automatic CPU fallback
- ✅ **Hybrid inference** - LLM fusion of vision + transcript with inferred context (people, location, story)
- ✅ **Whisper integration** - Auto-generate transcripts using faster-whisper
- ✅ **Local VLM support** - Ollama integration with qwen3-vl:8b (switchable to other models)
- ✅ **Smart sampling** - 5 strategies (ffmpeg_scene, hybrid, fixed, scene_change, perceptual_hash)
- ✅ **Transcript support** - SRT, VTT, Whisper JSON loading and alignment
- ✅ **Essay Style System** - Consistent visual branding across video essay motion effects
  - **EssayStyle type** - Complete style definition with colors, typography, layout, motion, texture
  - **11 flagship styles** - noir-essay, cold-data, modern-creator, academic-paper, documentary, podcast-visual, retro-synthwave, breaking-news, minimalist-white, true-crime, nature-documentary
  - **Accent markup** - `**word**` syntax for emphasizing key terms in quotes and titles
  - **Auto-accent detection** - Numbers, dates, percentages, money auto-detected per style rules
  - **Style-driven presets** - All effect presets now support style parameter:
    - Title, quote, text (highlight, typewriter, glitch, bounce, scramble, gradient, pop, citation)
    - Chart (bar, line, pie, donut), statistic (counter, comparison, percentage)
    - Image (ken-burns, zoom-focus, parallax, photo-frame, document-reveal)
    - Overlay (picture-in-picture, vhs-retro, film-grain, light-leak, camera-shake, screen-frame, audio-waveform, data-ticker, social-media-post, video-frame-stack)
    - Transition (slide, wipe, dissolve, zoom, blur, glitch)
    - Progress, annotation, comparison, timeline, countdown, map
  - **Backward compatible** - Style parameter is optional; legacy color params still work
  - **Styles API** - Full REST API for styles:
    - `GET /styles` - List all available styles
    - `GET /styles/:id` - Get full style definition
    - `POST /styles/:id/resolve-accent` - Test accent resolution
    - `POST /styles/:id/preview` - Generate style preview with sample content
  - **Validation helper** - `validateSceneContent()` checks content against style accent rules
  - **LLM Authoring Guide** - Documentation for LLMs on how to write styled content (`render-service/docs/LLM_CONTENT_AUTHORING.md`)
  - **Texture rendering** - Grain, vignette, and gradient overlays rendered in Motion-Canvas engine
  - **Remotion style integration** - All 11 EssayStyles mapped to Remotion themes with texture support
  - **Font loading** - Inter, Georgia, Playfair Display loaded in Motion-Canvas for style fonts
  - **Style parameter convention** - Use `style` param when possible; use `essayStyle` when another `style` param exists (e.g., animation style, frame style)
  - **Known limitations**:
    - Motion timing (enterFrames, exitFrames, easing) not yet derived from style; uses per-effect defaults
    - Helper functions (getTextureSettings, getFontProps, getSafeArea) available but not fully utilized
- ✅ **Layout System** - Region-based positioning for effect placement
  - **Region type** - Position defined by `{ x, y, w, h, align, valign, padding }` (all percentage-based 0-1)
  - **11 layout templates** - Predefined region configurations for video essays:
    - `center` - Single centered region (default)
    - `full` - Full bleed with safe margins
    - `lower-third` - Bottom bar for names, citations
    - `upper-third` - Top bar for chapter titles
    - `split` - Left/right 50-50 comparison
    - `split-60-40` / `split-40-60` - Asymmetric left/right emphasis
    - `thirds` - Three equal columns
    - `split-with-lower` - Two columns + bottom bar
    - `presenter` - Main content + lower third
    - `grid-2x2` - Four equal quadrants
  - **Render API integration** - `POST /render` accepts `layout` parameter:
    - Template name: `{ layout: "lower-third" }`
    - Custom regions: `{ layout: { regions: { main: { x: 0.1, y: 0.8, w: 0.5, h: 0.15 } } } }`
  - **Engine integration** - Layouts resolved before bundling, passed as CSS styles to components
  - **Layouts endpoint** - `GET /render/layouts` returns all templates with region definitions
  - **Remotion CSS conversion** - `regionToRemotionStyle()` converts regions to CSS flexbox properties
  - **Motion Canvas support** - `regionToMotionCanvas()` converts to center-based coordinates
  - **Style layout merge** - `applyStyleToRegion()` merges EssayStyle.layout with region defaults
  - **Extensible architecture** - Phase 1 (templates) complete; designed for Phase 2 (composition) and Phase 3 (full CSS)
- ✅ **Asset Management System** - File-based visual assets for motion effects
  - **Folder structure** - Organized by style with common fallback:
    - `assets/styles/{style-id}/` - Style-specific assets
    - `assets/common/` - Shared assets (fallback for all styles)
  - **AssetManager API** - Python module for asset access:
    - `get_asset(style, name)` - Get path with style→common fallback
    - `get_asset_content(style, name)` - Read file content directly
    - `get_icon(style, name)` - Convenience for `.svg` icons
    - `list_assets(style, category)` - List available assets
  - **Common icons** - 9 SVG icons (24x24 viewBox, `currentColor` stroke):
    - check, star, arrow-up, trending-up, code, database, users, zap, award
  - **Design decision** - Chose file-based over database for simplicity
    - Database-backed system in backlog for future scaling (100+ assets)
  - **Documentation** - `assets/README.md` with guidelines and usage

## Local TTS + Voice Cloning (OmniVoice) — M1 (2026-06-26)

Local text-to-speech with zero-shot voice cloning via
[OmniVoice](https://github.com/k2-fsa/OmniVoice) (Apache-2.0). Fills the gap where
the orchestrator wrote *silent* audio ("TTS not yet integrated").

- **Isolated runtime:** OmniVoice runs in a dedicated CUDA conda env
  (`D:\env\omnivoice`), invoked as a **batch subprocess** so the heavy torch stack
  stays out of the lean `nolan` env and VRAM is freed when the job ends. Setup:
  `scripts/setup_omnivoice.ps1`, POC: `scripts/omnivoice_poc.py`, docs:
  `docs/OMNIVOICE_SETUP.md`.
- **Shared GPU lock:** `get_gpu_lock()` (singleton in `webui/jobs.py`) serializes
  GPU work across the hub event loop. `ComfyUIClient.generate()` and the TTS
  worker acquire the *same* lock so OmniVoice and ComfyUI never contend for the
  4090's VRAM; the TTS job can also POST ComfyUI `/free` first
  (`tts.omnivoice.free_comfyui_vram`).
- **Provider abstraction:** `src/nolan/tts.py` — `TtsProvider` ABC +
  `OmniVoiceTTS` (batch via `omnivoice-infer-batch`) + `create_tts_provider`
  (mirrors `create_text_llm`). Config: `TtsConfig`/`OmniVoiceConfig` + a `tts:`
  block in `nolan.yaml` (enabled default off).
- **Voice library:** `src/nolan/voice_library.py` — file-backed `voices/<id>/`
  (sample.wav + meta). Clone from an **uploaded clip** or from a **saved Clip's
  audio** (reuses the Clips feature). Optional reference transcript (OmniVoice
  auto-transcribes via Whisper otherwise).
- **Voiceover generation:** `operations.generate_voiceover` reads a project's
  `script.json`, batch-synthesizes per section under the GPU lock, concatenates →
  `projects/<name>/assets/voiceover/voiceover.mp3`. Run `nolan align` after for
  audio-accurate scene timings (replaces the 150-wpm estimate).
- **UI:** `/voices` page (add/clone/preview voices, generate a project's voiceover)
  + Voices nav link. Endpoints: `GET/DELETE /api/voices`, `/api/voices/upload`,
  `/api/voices/from-clip`, `GET /api/voices/{id}/sample`, `POST /api/generate-voiceover`.
- **Roadmap:** auto-wire TTS into the orchestrator (`SegmentBuilder.tts_fn` /
  `director` silent-audio replacement) + a `nolan voiceover` CLI — deferred.

### TTS Studio (`/tts`) — 2026-06-26

Interactive single-utterance TTS playground built on the OmniVoice integration.
- **Voice source** (4 modes): saved voice · upload a sample · **crop from a library
  video** (player + Set-In/Out, or click a segment/cluster to prefill the range)
  · **voice design** (`instruct` text, no cloning). Cropped/uploaded samples are
  **ephemeral** (`voices/_tmp/<token>.wav`) with an optional "Save as voice".
- **Text source**: write/paste, or load a project's script (`GET /api/project/{p}/script`).
- **Params**: num_step (16/24/32), speed, language_id, instruct.
- **Output**: inline player + wav download; runs under the shared GPU lock.
- Backend: `operations.tts_synthesize`; endpoints `POST /api/tts/sample`,
  `/api/tts/sample-from-library`, `/api/tts/synthesize`, `GET /api/tts/sample/{t}`,
  `/api/tts/output/{t}`, `POST /api/voices/save-sample`. `OmniVoiceTTS` now passes
  num_step/speed/instruct/language through.

### TTS Studio — Script Projects source + Project Voiceover modes (2026-06-26)

- TTS Studio text source now lists **Script Projects** (`/api/script-projects`),
  loading `script.md` with markdown headings/metadata stripped.
- New **Project Voiceover** panel + extended `operations.generate_voiceover`
  (source = render project's `script.json` OR a Script Project's `script.md`):
  - `script.py.parse_script_sections` splits `script.md` on `##` headings into
    `{title, timecode, body}`; `clean_tts_text` strips markdown so only bodies are
    spoken (headings/`**Total Duration**`/`---` never read aloud) — both modes.
  - **mode=full** → concatenated `assets/voiceover/voiceover.mp3`.
  - **mode=segments** → per-section `assets/voiceover/segments/<NN>_<slug>.wav` +
    `segments.json` (title, timecode, duration) for the segment pipeline.
- Endpoints: `POST /api/generate-voiceover` (now takes `script_project` + `mode`),
  `GET /api/voiceover/{project}/{path}` serves outputs. Segment-pipeline auto-wiring deferred.

### Voiceover captions (SRT/VTT + word JSON) — 2026-06-26

Hybrid word-timing for generated voiceovers: Whisper word timestamps snapped to
the KNOWN script words (correct spelling of proper nouns/numbers), no new deps.
- `src/nolan/captions.py`: `align_words` (difflib sequence-align known↔Whisper +
  gap interpolation), `group_lines`, `words_to_srt` / `words_to_vtt`.
- `operations.generate_captions(project)`: CPU Whisper `transcribe_words` per
  segment (or the full mp3), aligns to section bodies, stitches a global timeline
  via segment offsets. Writes `assets/voiceover/voiceover.{srt,vtt,words.json}`
  (full) + per-segment `<seg>.{srt,vtt,words.json}`.
- Endpoint `POST /api/generate-captions`; outputs served via `/api/voiceover/...`
  (now sends srt/vtt/json types); `/api/voiceover-info` reports a `captions` flag.
- UI: "Captions (SRT)" button in the TTS Studio Project Voiceover panel; SRT/VTT/
  word-JSON download links appear once generated.
- Word JSON ({word,start,end}) is ready for kinetic/karaoke caption effects.

## Agents dashboard: Run-all + authored-plan viewer (2026-07)

Two gaps closed on the `/agents` (Orchestrator Dashboard) page:

- **Run all (`--auto`)**: `trigger_orchestrate()` gains an `auto` flag (dashboard.py);
  `POST /api/agents/{slug}/run` reads `body.auto` and forwards it (hub.py). New
  "▶▶ Run all" button runs every remaining Director step in one go, vs. the existing
  single-step "▶ Run next step". Works both locally and dispatched-to-agent.
- **Authored-plan viewer**: new `read_authored_plan()` (dashboard.py) + `GET
  /api/agents/{slug}/plan` return the live `style_guide.md` and a compact per-scene
  summary of `scene_plan.json` (id / visual_type / energy / motion_speed / transition /
  narration). Rendered inline on the expanded project card as a collapsible "Authored
  Plan" panel — inspect steps 1–3 output without leaving /agents.

Usage: open a project on /agents → "Authored Plan ▸" to read the plan; "▶▶ Run all"
to run the whole pipeline. Verified via TestClient (/plan 200, /run forwards auto) and
node JS syntax check.

### Agents dashboard fixes: state preservation + run-log surfacing (2026-07)

- **#1/#7 ephemeral-state preservation**: `refresh()` rebuilt the whole project list
  via `innerHTML` every poll (2.5s while running), wiping in-progress feedback text,
  open artifact/plan/tool panels, and agent-select values. Added
  `captureEphemeralState()`/`restoreEphemeralState()` around the re-render to preserve
  textarea content + caret/focus, selected agent, and expanded panels.
- **#2 run failures now visible**: `read_run_logs()` (dashboard.py) tails
  `.orchestrator/last_run.{stderr,stdout}.log`; `GET /api/agents/{slug}/runlog` serves
  it; the page fetches it for expanded `error`-status projects and shows a red "Run Log"
  block — previously a failed local run showed only `status: error` with no detail.

Verified: Python syntax + `read_run_logs` tail behavior; `/runlog` and `/agents` 200 via
TestClient; node JS syntax check; presence of new UI strings.

### Agents dashboard: output link (#5) + feedback management (#6) (2026-07)

- **#5 View output**: `project_summary` reports `has_output` (output/final.mp4 exists);
  `GET /api/agents/{slug}/output` serves it; expanded card shows an "Output → ▶ final.mp4"
  link when present.
- **#6 Feedback management**: the page now renders `feedback_files` as a "Saved Feedback"
  list with consumed/pending badges + a delete (✕) button. `delete_feedback()`
  (name-validated to review_<n>.md) + `DELETE /api/agents/{slug}/feedback/{name}`.
  Previously feedback was write-only.

Verified via TestClient: /output 200 present / 404 absent; DELETE 200/400(bad name)/404;
has_output toggles; node JS syntax; new UI strings present.
