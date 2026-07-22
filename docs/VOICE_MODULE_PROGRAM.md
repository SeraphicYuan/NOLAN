# Voice Module Program — quality, wiring, and a redesigned /voices

Status: PLAN (2026-07-22). Derived from a 3-agent deep review of the voice
organ, the `/voices` page, and the script→voice handoff. This is the tracking
doc; update it as items ship (mark ✅ + IMPLEMENTATION_STATUS entry).

## What the module is (one paragraph)

`voice_pipeline.py` is the shared VO core; `tts.py` drives **OmniVoice** as a
subprocess into a separate CUDA env (24 kHz, diffusion `num_step`, voice cloning
via `ref_audio`+`ref_text`, **unseeded**). `voice_library.py` = on-disk clones.
Whisper/aligner/captions do *timing*, not correctness. One `##` beat-heading in
`script.md` = one section = one `sec_NNNN.wav` = one beat anchor. The Director's
`voiceover` step and the `/voices` page call the identical core. The handoff is
real but **convention-based**: `promote_draft` copies a winning draft to
`projects/<slug>/script.md` (root), and everything downstream reads that path.

## Governing principles (the blindspots, promoted to rules)

1. **Stochastic TTS is a workflow problem.** Some section will be bad every run.
   The module must support *per-section* iteration + reproducibility (seed), not
   only whole-project regeneration.
2. **VO bugs are video bugs.** Narration owns duration — a section 3 s too long
   shifts every later beat. Duration gates + silence-trim protect the *render*,
   not just the audio.
3. **"Wired" ≠ "safe."** The handoff is a shared filename with no schema
   coupling. Make the promoted/written state *visible and guarded*, never trusted.
4. **Verify like an editor** (NOLAN's own rule) — the voice organ currently does
   NO measurement of its own output. Every VO op must measure (RMS/LUFS/duration
   delta) and fail loudly.
5. **The engine is a swappable ceiling.** `TtsProvider` is a clean abstraction;
   a higher tier (e.g. ElevenLabs) can be added as an injectable tier later.

---

## Section A — VO quality & module correctness

Every item lands as the module contract: a rule/registry + an executor in the
path + an honesty test. "Failures are loud."

### A1. Text normalization before TTS  ← highest quality/effort ratio
- **What:** a normalization pass turning numbers, currency, dates, ranges,
  units, percentages, ordinals, and known acronyms into spoken forms
  ("$4.2B in 2019" → "four point two billion dollars in twenty nineteen").
- **Why:** today the only pre-TTS step is markdown strip (`script.py:clean_tts_text`,
  48-58). Raw digits/symbols are mangled by OmniVoice. This is *the* classic TTS
  lever and it's deterministic — NOLAN routing says deterministic-where-computable.
- **Where:** new `src/nolan/tts_normalize.py` (`normalize_for_speech(text) -> str`),
  called inside `clean_tts_text` (or right after it) so BOTH the script_project
  and legacy `script.json` paths get it. Libraries: `num2words` (+ small rule set
  for currency/date/unit/acronym). Keep a per-project acronym allowlist override.
- **Contract:** `tts_normalize.py` rule table + honesty test
  `tests/test_tts_normalize.py` (a fixture table of input→spoken; includes
  currency, %, years vs plain numbers, ranges, common acronyms, decimals,
  negative/temperature). Provenance: log a normalization diff per section.
- **Effort:** S–M. Risk: low (pure function, table-tested).

### A2. VO quality gate (protects the duration invariant)
- **What:** after the batch, every section must yield a wav that is present,
  non-silent (RMS ≥ floor), non-clipped (peak < 0 dBFS w/ margin), and of
  *plausible* duration (within ±X% of `words/WPM`). Fail loud OR auto-retake
  (A6/B2). Never ship a short/empty/missing section silently.
- **Why:** today missing ids are only *logged*; concat skips them
  (`voice_pipeline.py:201-203, 240`), which shortens the VO AND breaks the
  `len(sec_files) == len(plan.sections)` equality the beat-anchor step relies on
  (`cli/audio.py:268`) → silent downgrade to fuzzy tiling. Violates "failures loud."
- **Where:** new `src/nolan/voice_gate.py` (`gate_voiceover(vo_dir, sections) ->
  Report` with typed checks, mirroring `scriptwriter/gate.py`). Call it at the end
  of `synthesize_voiceover` / `produce_voiceover`; on fail, either raise or feed
  the failing section ids to the retake path.
- **Contract:** typed checks list + `tests/test_voice_gate.py` (synthesize-free:
  feed crafted wavs — empty, clipped, too-short, count-mismatch — assert the gate
  flags each). Honesty: the gate's check list is surfaced on `/voices`.
- **Effort:** M. Risk: low.

### A3. Silence-trim + loudness-normalize + measure the VO output
- **What:** (a) trim leading/trailing silence per section wav (OmniVoice adds it →
  inflates section durations → beats drift); (b) LUFS-normalize the VO
  (`loudnorm I=-16:TP=-2:LRA=11`) so the `/voices` preview matches the final mix;
  (c) record a `voiceover.measure.json` (per-section RMS, peak, LUFS, duration,
  duration-delta-vs-expected).
- **Why:** loudnorm/RMS exist only in the *final mix* (`audio_mix.py:432-548`),
  downstream of the organ; the organ measures nothing. "After audio work, measure it."
- **Where:** `voice_pipeline.py` post-synthesis (before concat): a
  `_trim_and_measure(wav)` step; write the measure sidecar next to `voiceover.mp3`.
  Trim BEFORE the sec-duration is read for anchoring so the beat clock is honest.
- **Contract:** `tests/test_voice_measure.py` (a wav with known head silence →
  trimmed duration correct; measure sidecar shape). Surface the measure summary in
  the UI (A2/UI).
- **Effort:** M. Risk: medium (trimming too aggressively clips speech — use a
  conservative threshold + min-keep; test with real VO).

### A4. Seeded, reproducible synthesis
- **What:** thread a `seed` per section through the batch JSONL so a good take is
  reproducible and retries/A-B are controllable. Store the seed in the measure
  sidecar per section.
- **Why:** synthesis is currently unseeded → a good take is unrecoverable; retries
  can't reproduce (blindspot #1).
- **Where:** `tts.py:synthesize_batch` (add `seed` to each JSONL line if OmniVoice
  supports it — verify the infer-batch CLI flag; if unsupported, document the
  limitation loudly and fall back to caching accepted wavs). `build_tts_items`
  carries a per-item seed (default derived from section index for stability).
- **Contract:** `tests/test_tts_items.py` seed propagation; a note in the module
  doc if the engine ignores it.
- **Effort:** S (if engine supports) / M (if we must cache-accepted-takes instead).

### A5. Sentence-aware sub-chunking within a section
- **What:** synthesize a long section as sentences, then concat — keeping the
  section=beat boundary intact (the concat = one `sec_NNNN.wav`).
- **Why:** one `##` section = one OmniVoice call regardless of length
  (`voice_pipeline.py:72-73`); diffusion TTS quality degrades with length, and a
  single long call gives no sub-timing. Sub-chunking improves quality AND yields
  finer caption timings.
- **Where:** `build_tts_items` / a new `_split_section_to_utterances(text)` (spaCy-
  free sentence splitter; respect abbreviations). Concat utterances → the section
  wav. Caption path already handles word timing; feed it the finer pieces.
- **Contract:** `tests/test_section_chunking.py` (section → N utterances → one wav;
  count invariant preserved; total duration ≈ sum). 
- **Effort:** M. Risk: medium (sentence splitter edge cases; join clicks — add a
  few-ms crossfade at joins).

### A6. Per-section prosody / delivery notes
- **What:** allow a per-section `instruct` / delivery note ("somber", "brisk,
  wry") instead of one global instruct; optionally have the script pipeline
  AUTHOR a per-beat delivery note (LLM judgment) that flows in as `instruct`.
- **Why:** prosody today is one global knob (`instruct` + global `atempo`).
  Per-beat delivery is a real quality lever and a natural synergy with the typed-
  script work.
- **Where:** section model gains an optional `delivery` field (authored field);
  `build_tts_items` maps it to the per-item `instruct`. Script pipeline: an
  optional `delivery:` note per `##` beat (a new authored field + AUTHOR_PROMPT
  line) — gated, Auto-fallback to none.
- **Contract:** authored-field consumer test (PLAN_FIELD_CONSUMERS style — a
  `delivery` note with no executor is a bug); WIRING_CHECKLIST pass.
- **Effort:** M–L (the authoring half is the larger part). Defer authoring to P4.

---

## Section B — Wiring & workflow

### B1. Written-state guard (stop voicing a scaffold)
- **What:** `/voices` shows each script-project's promoted/written state
  ("draft-03 promoted · 2,424 w" vs "not promoted — scaffold"), and refuses /
  hard-warns generating VO from an unpromoted scaffold.
- **Why:** the handoff is a path string; `is_written()`/`current_draft()`
  (`store.py:364, 488`) detect scaffold-vs-real but the UI ignores them.
- **Where:** `/api/script-projects` (or a small `/api/script-projects/{slug}/vo-readiness`)
  returns `{written, promoted_draft, words}`; `/voices` renders it + gates the
  Generate button.
- **Contract:** endpoint test; UI shows the state (no silent fall-through).
- **Effort:** S.

### B2. Per-section retake (backend + surfaced in UI)
- **What:** re-synthesize a SINGLE `sec_NNNN.wav` (new seed or edited text/
  delivery), splice it back, re-concat `voiceover.mp3`, re-caption — preserving the
  section count invariant.
- **Why:** the single biggest workflow gap; mirrors the per-finding granularity of
  script-review. Today only whole-project regen exists.
- **Where:** new `retake_section(vo_dir, index, *, seed?, text?, delivery?)` in
  `voice_pipeline.py`; CLI `nolan voiceover retake` (also fills the missing
  dedicated `nolan voiceover` command family); endpoint
  `POST /api/generate-voiceover/{slug}/retake/{index}` → job.
- **Contract:** `tests/test_retake.py` (retake index i replaces only sec_i;
  count + total-duration invariants hold; captions regenerated). Runs the A2 gate
  on the new wav.
- **Effort:** M.

### B3. Regenerate confirm + versioning (no silent overwrite)
- **What:** regenerating a project VO confirms first and archives the prior take
  (`assets/voiceover/_takes/<ts>/`) instead of `rmtree`. Keep last N takes;
  a "restore take" action.
- **Why:** `Generate` silently clobbers (segments `rmtree`, mp3 overwrite,
  `voice_pipeline.py:212`); with unseeded TTS a good take is unrecoverable.
- **Where:** `synthesize_voiceover` archive-then-write; small takes registry;
  UI confirm + take list.
- **Contract:** test that a second generate preserves the first under `_takes/`.
- **Effort:** S–M.

### B4. Close the loop between /script-projects and /voices
- **What:** on `/script-projects`: a VO status chip (generated? total dur? matches
  beats?) + a "→ Generate voiceover" CTA (deep-link into the redesigned Produce
  tab, project preselected). On `/voices`: a back-link + provenance ("VO built
  from draft-03, 2026-07-22").
- **Why:** data-connected but the *user journey* dead-ends; VO is the script's
  natural next step.
- **Where:** `/script-projects` route + template (status from
  `assets/voiceover/voiceover.measure.json` + readiness); `/voices` provenance from
  a `voiceover.prov.json` written at generate time (draft n, script hash).
- **Contract:** provenance sidecar test; the CTA deep-link works.
- **Effort:** S–M.

### B5. Voice as a create-time preset (surface the lazy default)
- **What:** voice becomes a presettable decision at script-project create (next to
  angle/spine/rubric) with an explicit Auto/default fallback; the resolved voice is
  shown on the script page and in the Produce tab.
- **Why:** the pipeline resolves voice from `project.yaml`/`nolan.yaml` upstream and
  the Director never prompts — the exact "lazy default falling through the crack"
  pattern already fixed for angle/spine. `resolve_voice_ref` ladder
  (`voiceover.py:51`) stays the executor; we just surface + preset the input.
- **Where:** script-project create form + store field (`voice_id`), written into
  `project.yaml`; field-parity honesty test (like the angle/spine ones).
- **Effort:** S–M.

### B6. UI hygiene (mechanical)
- Remove dead endpoint `/api/project/{project}/script` (`voices.py:365`, no caller).
- Collapse the 3 duplicated JS pollers (`pollJob`/`pollVO`/`pollRenderVO`) into one
  shared helper.
- Move page CSS onto `nolan.css` tokens; kill hardcoded hex (`#7fd3e0`, `#3a2f12`,
  `#7c3aed`, …); move `<link rel=stylesheet>` from `<body>` to `<head>`.
- **Effort:** S. (Folds naturally into the C redesign.)

---

## Section C — /voices redesign (senior-designer critique + IA)

### Critique of the current page
- **One flat scroll, four stacked panels** (Voice library, All voiceovers, TTS
  Studio, Project Voiceover). No hierarchy, everything competes for attention.
- **The actual job is scattered.** To make a project's VO you pick a voice in *TTS
  Studio*, but press Generate in a *different* panel (Project Voiceover), then find
  the result in a *third* (All voiceovers). Three panels, one task — incoherent.
- **No section-level view.** The thing you most need after generating — audition
  and fix individual beats — doesn't exist; you get one long mp3.
- **Bespoke, off-token styling** (inline CSS, hardcoded colors) inconsistent with
  the rest of NOLAN.

### The redesign — 3 tabs, one primary workflow

Tabs across the top: **Narrate · Voices · Library**. (Optional 4th: **Defaults**.)
Shared shell (nav.js + nolan.css tokens), responsive, one primary action per view.

**Tab 1 — Narrate (the consolidated VO workflow — the point of the page):**
A two-pane workspace. Left rail = setup; main pane = the section workspace.

```
┌─ Narrate ─────────────────────── Voices · Library ───────────────┐
│ ┌─ setup (sticky left rail) ─┐ ┌─ section workspace ───────────┐ │
│ │ Script project ▾           │ │ ● VO: 12 beats · 4:58 / 5:00  │ │
│ │  the-diamond-illusion      │ │   ▓▓▓▓▓▓▓▓▓▓▓░  (waveform)     │ │
│ │  ✓ draft-03 promoted 2,424w│ │ ─────────────────────────────  │ │
│ │                            │ │ 1 Cold open        0:22 ▶ ⟳ ✓ │ │
│ │ Voice ▾                    │ │   "For a century, a single…"  │ │
│ │  ◉ saved: Narrator-A       │ │ 2 The setup        0:31 ▶ ⟳ ⚠ │ │
│ │  ○ upload  ○ crop  ○ design│ │   flagged: 38% faster than…   │ │
│ │  [▷ audition]              │ │ 3 The turn         0:41 ▶ ⟳ ✓ │ │
│ │                            │ │ …                             │ │
│ │ ▸ Advanced (pace, steps,   │ │ ─────────────────────────────  │ │
│ │   language, seed)          │ │ [Captions ⤓] [Download mp3 ⤓] │ │
│ │                            │ │ [Open in Timeline →]          │ │
│ │ [ Generate voiceover ]     │ │                               │ │
│ │  mode ◉ full ○ segments    │ │                               │ │
│ └────────────────────────────┘ └───────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```
- **Setup rail** consolidates TTS Studio's voice column + Project-Voiceover's
  project/mode picker + params — the whole *input* in one place.
- **Section workspace** = the beats from `script.md`, each row: # · heading · text
  preview · duration · ▶ play · ⟳ retake (B2) · status (✓/⚠ from the A2 gate +
  A3 measure). Top strip: overall status, total vs target duration, waveform.
- One coherent flow: pick project → pick voice → Generate → audition & retake per
  beat → captions → hand off to Timeline. Regenerate confirms + versions (B3).
- Written-state badge (B1) gates Generate; provenance shown after (B4).

**Tab 2 — Voices (the library / voice management):**
Clone grid (cards: name, source, ▶ sample, delete). "Add voice": upload /
clone-from-clip / crop-from-library. A compact **Audition** box (type a line, hear
it in the selected voice) — the old single-utterance TTS Studio, repurposed as
*voice auditioning*, not the main flow.

**Tab 3 — Library (browse all voiceovers):**
The read-only index of existing project + HF voiceovers (today's "All
voiceovers"), with filters + players. Provenance + measure summary per item.

**Optional Tab 4 — Defaults:** global default voice, default pace/WPM, engine
(`num_step`) — surfacing `nolan.yaml` `tts.*` so it's not buried.

### Design principles applied
- **One task per tab; one primary action per view** (Generate on Narrate).
- **Progressive disclosure** (Advanced collapsed; audition tucked in Voices).
- **Section-as-workspace** mirrors the script-review round-strip you already like.
- **Status-forward** — the gate/measure results are visible per beat, not buried.
- **Token-based, shared-shell styling** (kills the bespoke CSS / hardcoded colors).

---

## Phasing

- **P1 — Correctness core (protects the invariant, immediate quality): ✅ SHIPPED 2026-07-22.**
  A1 normalization (`tts_normalize.py`, pure-python, wired at the `build_tts_items`
  synthesis chokepoint + studio) · A2 quality gate (`voice_gate.py`, loud fail on
  missing/silent/too-short/count-mismatch) · A3 trim+measure+LUFS (`voice_audio.py`
  trim/stats, `finalize_sections` writes `voiceover.measure.json`, `loudnorm` on
  concat) · B1 written-state guard (`store.vo_readiness`, `/…/vo-readiness` endpoint,
  409 in the generate route, /voices badge). Wired into BOTH `synthesize_voiceover`
  (async: /voices + Director) and `produce_voiceover` (sync: segment builder).
  Tests: test_tts_normalize (50), test_voice_quality (10), test_voice_pipeline_integration
  (3, fake provider e2e), test_vo_readiness (1) — all green; 225-test voice/script/hub
  regression green. Live golden test on the-diamond-illusion still TODO (needs GPU).
- **P2 — Workflow (iteration + reproducibility): ✅ SHIPPED 2026-07-22.**
  A4 seed — **NOT ACHIEVABLE with the current OmniVoice build**: `omnivoice.cli.infer_batch`
  exposes no `--seed`/per-item seed and never calls `fix_random_seed`, so synthesis is
  inherently non-deterministic (verified in the env). We do NOT fake seed plumbing; instead
  reproducibility = take-PRESERVATION (B3), and a retake is intentionally a fresh attempt you
  keep-or-discard. · B2 per-section retake · B3 versioning (archive full-VO takes + snapshot a
  section before a retake) · the `nolan voiceover` CLI family.
- **P3 — Redesign + wiring surfaced:** IN PROGRESS 2026-07-22.
  ✅ **C tabs + Narrate workspace** (Narrate·Voices·Library; `/api/voiceover-beats/{slug}`
  merges script sections + measure + provenance; per-beat play + ⟳ retake + gate pills;
  takes dropdown; shared job poller) — browser-verified live on the-diamond-illusion.
  ✅ **B4 (part)** provenance sidecar (`voiceover.prov.json`) + Narrate provenance line.
  ✅ **B6 (part)** dead `/api/project/{project}/script` removed; single poller; tokenized CSS.
  TODO: B4 the /script-projects status-chip + "Generate VO" CTA (reverse link);
  B5 voice as a create-time preset.
- **P4 — Advanced quality:**
  A5 sub-chunking · A6 per-section/authored delivery notes.

## Sequencing notes
- P1 is backend-only and de-risks everything (loud failures, honest durations)
  before we build UI on top.
- P2's retake needs A2 (a gate defines "bad section" → what to retake) and A4
  (seed makes a retake meaningful).
- P3 is mostly reorganization + surfacing P1/P2; the tab shell can start in
  parallel since it's low-risk.
- P4 is optional polish; A6's authoring half ties back into the script pipeline.

## Golden test (end-to-end acceptance)
Cold project → promote a draft → Narrate tab → Generate → one section auto-flags
(gate) → retake it (seed) → passes → captions → measure sidecar shows all beats
within tolerance → Timeline shows video ≡ narration. If that loop is smooth, the
program worked.
