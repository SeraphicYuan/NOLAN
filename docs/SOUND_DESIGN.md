# Sound / SFX — design & wiring (the `sound` umbrella)

Status: **Phase 0 landed** (registry seed + validators). This doc is the durable
reference for the curated SFX library and its wiring into both render paths.
Design ratified 2026-07-18.

## The reframe: curate + catalog + finish the wiring (not greenfield)

Sound is a **half-wired umbrella** — the machinery already runs, the *registry
skin* is what was missing.

Already exists and works:
- **Sourcing** — `src/nolan/sfx_search.py`: a working `FreesoundProvider` (API key
  via `config.py` `freesound_api_key` / `FREESOUND_API_KEY`) + `source_sfx()` that
  downloads and caches into `projects/_library/sfx/` with a `sfx.json` manifest.
- **Placement + mix (standard pipeline)** — `src/nolan/audio_mix.py`: the `scene.sfx`
  authored field (already in `PLAN_FIELD_CONSUMERS`), the `soundtrack` spine step,
  a real VO-sidechain **ducking** mixer (`mix_from_spec`), and
  `measure_sfx_audibility()` (the "shipped a whoosh nobody could hear" instrument).
- **HyperFrames rails** — `audio_meta.json` already defines an `sfx[]` shape
  `{frame, file, offset_s, duration_s, volume}`; `assemble-index.mjs` mounts SFX on
  their own timeline lanes (track 20+i) in *both* render surfaces; in the
  incremental renderer SFX rides *inside* each per-frame clip (survives concat,
  unlike BGM).

Missing (this program): a **curated, quality-rated catalog**, the **registry skin**
the module contract demands, and the compose-first **authoring path** that populates
the HF `sfx[]` rail.

## Ratified decisions

1. **Store SSOT** = the NOLAN-Python bank under `projects/_library/sfx/` (where
   `audio_mix`/Director live); *register into* the media-use ledger for the Node/HF
   side. One curated bank; media-use `resolve` hits it first. (Avoids pitfall #4
   "two dialects for one decision" — document the boundary.)
2. **License** = CC0-first for the initial ~100 (zero attribution burden); CC-BY
   allowed later only with the attribution gate enforced.
3. **Authoring** = human-authored cues first, but built on the framework below so
   it becomes systematic (a pairing operator), never permanent ad-hoc.
4. **Taxonomy** = the 19 cue-kinds below (`src/nolan/sound/registry.py`).

## The design: two layers bound by a `kind` foreign key

- **Layer 1 — the registry (19 cue *kinds*)** — `src/nolan/sound/registry.py`.
  The vocabulary + craft (`when_to_use` = the authoring trigger). This is what
  satisfies the module contract; ~dozens of entries, hand-written, stable.
- **Layer 2 — the curated bank (~100 *files*)** — flat `projects/_library/sfx/
  sfx.json` (house "Pattern A", like the voice/music libraries; **not** Chroma —
  there is no audio embedding in the codebase, so search is lexical over
  tags/title/description, optionally BGE-ranked over `description`). Each record:
  `{ id, file, kind, title, description, tags[], duration, rating, source,
  license, attribution, page_url, curated }`. Multiple files per `kind`.
- **Selection within a kind** is deterministic: highest `rating`, right duration,
  round-robin variance so the same whoosh doesn't repeat; stay within one coherent
  family per video (motif consistency).

**Three stores (mind the boundary — pitfall #4):**
- `src/nolan/sound/registry.py` — the 19 cue-*kinds* (code; the vocabulary).
- `projects/_library/sfx/sfx.json` — the curated *bank* manifest: the files we
  actually mix (`curated:true`, with `kind`/`rating`/license/attribution).
- `projects/_library/sfx/catalog.db` — the **candidate catalog** (SQLite + FTS5,
  `src/nolan/sound/catalog.py`): every crawled external sound (7.5k CC0 to start),
  its metadata + preview link, and an `in_library` flag pointing back at the bank.
  Queryable locally (`nolan sfx search`) so future sourcing never hits the website.
  The crawl upserts it (idempotent, refreshes download counts); `nolan sfx add`
  flips `in_library`.

**CLI** (`src/nolan/cli/sfx.py`): `nolan sfx crawl` (fill the catalog) · `search`
(query it locally) · `add <id> --kind <k> --rating N` (gate → normalize 48 kHz
stereo → curate → mark in_library) · `list` (the bank by kind).

## Authoring = a pairing operator (decision #3)

SFX authoring is the same shape as the existing narrative→asset **pairing engine**
(bridge → retrieve → gate → accept): a **scene-event** pairs to a **cue-kind**.
The registry's `when_to_use` *is* the rulebook, and because the HF spec exposes the
triggers concretely, the rulebook is mostly **computable** — the path off ad-hoc.

Rulebook (each row reads off the spec; `at` is scene-local seconds):

| HF spec signal | → cue-kind | at |
|---|---|---|
| scene enter / frame transition | `whoosh` | `start` − 0.4 |
| statement `data.cue` (operative word) | `impact-soft` | `start` + `cue` |
| register/mood flips to the "turn" | `riser` then `impact-hard` | into → on `cue` |
| `stat` count-up | `data-tick` + `data-punch` | count window → land |
| `newshead` headline cascade | `type` / `paper` | on reveal |
| `newshead` photo slide-in | `camera-shutter` | on image cue |
| `document` block | `paper` | on reveal |
| reveal style ∈ decode/scramble/glitch | `glitch` | on reveal |
| `social_card` | `notification` | on reveal |
| dollar figure in a stat | `cash` | on number land |
| dark-polarity dread beat | `sub-drop` (+ `room-tone`) | on beat |
| long-hold / `relieve` flag | `room-tone` / bed | scene span |

**Restraint budget** (baked into the operator, mirrors `audio_mix`'s
`max_per_section=2` / `min_gap_s=20`): ≤ ~1 cue per 8–10s of the same family; hard
cues land in VO gaps, never over a clause; beds duck under VO; **analogy/emotion
beats get *space*, not sound**; reuse one whoosh/impact family per video.

## The 19 cue-kinds

Motion & tension: `whoosh` · `riser`
Impact & punctuation: `impact-soft` · `impact-hard` · `sub-drop` · `stinger`
Digital / UI: `click` · `type` · `notification` · `error-buzz` · `glitch`
Foley / object: `camera-shutter` · `paper` · `stamp` · `cash`
Data sonification: `data-tick` · `data-punch`
Ambience beds: `room-tone` · `crowd-murmur`

Full craft (`purpose`, `when_to_use`, family, dur, gain, `authored_by`, executor)
lives in `src/nolan/sound/registry.py`. `data-punch` aliases the legacy
`audio_mix` `hit`; `whoosh`/`riser` match the existing synths.

## Wiring into the two pipelines

### Standard pipeline (≈90% there)
- **Field**: extend `scene.sfx` to accept `{cue:<kind>, at, gain}` alongside the
  legacy `{query, at, volume}` (both validated by `validate_scene_sound`).
- **Executor**: `audio_mix._source_scene_sfx` resolves `cue → best file of that
  kind` from the curated bank, then the existing `mix_from_spec` ducking mixer runs
  post-assembly. `measure_sfx_audibility` already reports audible/inaudible.

### HyperFrames (the genuinely missing authoring path)
- **Field**: add `scene.data.sfx: [{cue, at, gain}]` to the frame spec, `at` =
  scene-local seconds (mirrors `data.cue`), so a cue fires on the operative-word
  reveal.
- **Executor**: one new step in `src/nolan/hyperframes/finish.py`, placed
  **between word-sync and assemble-index**. It reads each scene's *post-word-sync*
  `start` (authored `start` is provisional!), resolves `cue → frozen file`,
  computes `offset_s = scene.start + at`, and **merges** `{frame, file, offset_s,
  duration_s, volume}` into `audio_meta.sfx[]`. No renderer change — track-20+i
  mounting is already generic.

### HF landmines (must respect)
1. **Merge, never regenerate** `audio_meta` — the "bgm-wipes-`voices[]`→silent" bug;
   re-assert the finish.py voices-count guard.
2. **Normalize every SFX file to 48 kHz stereo at ingest** — a stream-copy concat
   silently drops audio when params differ.
3. SFX must be a **root child** of the index, never inside a scene sub-comp (renders
   blank). The `audio_meta → assemble-index` path already does this.
4. One timeline **lane per cue** (track 20+i); same-track overlap is a lint failure.

## Gaps — status

1. **Anchor to repo-root** — ✅ done in the new code (`crawl.library_dir`,
   `resolve` use a repo-root anchor). The legacy `sfx_search.SFX_LIBRARY` (used only
   by the live-search fallback) is still CWD-relative; the curated `cue` path is safe.
2. **Freesound `_RateLimiter`** — ⬜ still open (the crawler throttles; the rare
   live `source_sfx` path is unbounded). Low priority.
3. **Audio acquisition gate** — ✅ `check_sound` gates both download doors
   (`cli/sfx.py`, `sfx_search.fetch_to_library`), in `ASSET_GATE_DOORS`.
4. **`measure_sfx_audibility` in the checkpoint** — ✅ already wired
   (`director.py` soundtrack mix step).

## Module-contract checklist (what makes `sound` a real umbrella)

| Part | Status | Where |
|---|---|---|
| Registry (`when_to_use` catalog) | ✅ Phase 0 | `src/nolan/sound/registry.py` |
| Validator (authoring gate) | ✅ Phase 0 | `validate_scene_sound` / `validate_plan_sound` |
| Spine step | ✅ exists | `director.py` `soundtrack` |
| Authored field `scene.sfx` | ✅ exists + in `PLAN_FIELD_CONSUMERS` | `scenes.py` |
| Executor (organ) | ✅ exists | `audio_mix._source_scene_sfx`, `mix_from_spec` |
| Shared resolver (kind → curated file) | ✅ Phase 2 | `src/nolan/sound/resolve.py` (`resolve_cue`, `sfx_event_for_cue`) |
| `_umbrellas()['sound']` | ✅ Phase 2 | `system_map.py` (22 cue-kinds) |
| `UMBRELLA_WIRING['sound']` | ✅ Phase 2 | `system_map.py` |
| `CATALOG_CONSUMERS['sound']` | ✅ Phase 2 | `system_map.py` (audio_mix `from nolan.sound` + skill) |
| Skill `common.sound-craft` | ✅ Phase 2 | `skills/common/sound-craft.md` + `skills/index.json` |
| Honesty tests (umbrella/skill/catalog) | ✅ Phase 2 | `tests/test_sound.py` (+ generic umbrella/consumer tests) |
| Audio acquisition gate | ✅ Phase 2 | `check_sound` on `cli/sfx.py` **and** `sfx_search.fetch_to_library` (both in `ASSET_GATE_DOORS`) |
| HF-usable merge primitive | ✅ Phase 2 | `src/nolan/hyperframes/sound.py` (`build_audio_meta_sfx` + `merge_sfx_into_audio_meta`, preserves `voices[]`) |
| Authored field `scene.data.sfx` (HF) | ✅ Phase 3 | validated by `validate_scene_sound`; consumed by `apply_scene_sfx` |
| HF merge executor + render mount | ✅ Phase 3 | `hyperframes/sound.apply_scene_sfx` (finish DAG step 4b: resolve → **stage into `assets/sfx/`** → merge `audio_meta.sfx`); `assemble-index.mjs` mounts it on track 20+i |

Note: adding `sound` to `_umbrellas()` forces `UMBRELLA_WIRING` + `CATALOG_CONSUMERS`
(both grep-verified) — done together in Phase 2, suite green.

## Phased roadmap

- **Phase 0 — DONE**: `src/nolan/sound/{__init__,registry}.py` (cue-kinds + validators).
- **Phase 1 — DONE**: `nolan sfx crawl/search/add/remove/list/doctor`; catalog
  (SQLite+FTS, 7.5k CC0); **118 curated CC0 sounds across 22 kinds** (48 kHz stereo,
  silence-trimmed, gated).
- **Phase 2 — DONE**: first-class umbrella (`_umbrellas`/`UMBRELLA_WIRING`/
  `CATALOG_CONSUMERS`) + `skills/common/sound-craft.md` + `tests/test_sound.py`; the
  shared `resolve_cue`/`sfx_event_for_cue` (Director prefers the curated bank via it);
  the HF-usable `hyperframes/sound.py` merge primitive (preserves `voices[]`); both
  download doors gated. Gap #2 (rate-limiter) remains.
- **Phase 3 — DONE**: `scene.data.sfx` frame-spec field (validated) + the finish DAG
  step `apply_scene_sfx` (after word-sync, before assemble-index): reads the field off
  the ALIGNED specs → resolves via `nolan.sound` → **stages files into
  `<comp>/assets/sfx/`** (project-relative, what the render mounts) → merges into
  `audio_meta.sfx[]` (preserves `voices[]`, idempotent, loud on bank gaps).
  `assemble-index.mjs` mounts them on track 20+i. Verified end-to-end on
  the-openai-debate; honesty-tested in `tests/test_sound.py`.
- **Phase 4 (next) — the pairing operator**: registry-aware auto-author pass that emits
  `scene.data.sfx` from the spec (deterministic triggers first, LLM for taste),
  human-reviewed. The executor + render path it targets are now in place.
- **Phase 4 — the pairing operator**: registry-aware auto-author pass over the spec
  (deterministic-first, LLM only for taste calls), human-reviewed.

Litmus (WIRING_CHECKLIST): *which registry did this land in? what field authors it?
who consumes that field? which gate classifies it? where does an agent learn when to
use it? which test fails if any answer stops being true?* — Phases 2–3 close the last
three for `sound`.
