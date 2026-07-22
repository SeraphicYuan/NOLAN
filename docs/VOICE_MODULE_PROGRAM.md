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
- **P3 — Redesign + wiring surfaced: ✅ SHIPPED 2026-07-22.**
  **C tabs + Narrate workspace** (Narrate·Voices·Library; `/api/voiceover-beats/{slug}`
  merges script sections + measure + provenance; per-beat play + ⟳ retake + gate pills;
  takes dropdown; shared job poller) — browser-verified live on the-diamond-illusion.
  **B4** provenance sidecar (`voiceover.prov.json`) + Narrate provenance line + the
  /script-projects VO status chip ("🎙 13:27") + "Generate →" CTA deep-linking to
  `/voices?project=` (reverse link). **B5** voice as a create-time preset (create form
  dropdown → `project.yaml voice_id` → `resolve_voice_ref`). **B6** dead
  `/api/project/{project}/script` removed; 3 pollers → one; tokenized CSS. Browser-verified.
- **P4 — Advanced quality: ✅ SHIPPED 2026-07-22.**
  **A5** sentence sub-chunking: `synthesize_sections` splits a beat longer than
  `tts.omnivoice.sub_chunk_words` (default 60) into greedily-packed sentence chunks,
  synthesizes each, and concatenates them (small silence gap) into the one `sec_NNNN.wav`
  — beat boundary preserved. Live-verified: De Beers sec 8 (222w → 5 chunks) retook clean,
  gate ok. Routed through synthesize_voiceover + produce_voiceover + retake_section.
  **A6** delivery notes: a `[delivery: <note>]` line per beat (parsed by parse_script_sections,
  stripped from speech, authorable via the draft prompt) → per-section `instruct`; surfaced on
  the beats endpoint + `retake --delivery`. ENGINE LIMIT (emotion-probe, 2026-07-22): this
  OmniVoice build yields **NO audio for ANY item carrying an `instruct`** — with OR without a
  clone (instruct-alone → nothing; clone+instruct → nothing; no-ref *neutral* alone → works).
  So the delivery field is parsed/surfaced/authorable but `instruct` is gated behind
  `tts.omnivoice.supports_instruct` (default OFF) — sending it would silently break synthesis.
  Delivery is captured metadata, ready for an instruct-capable engine; today it is inert.

## P5 — VO quality validation + the polish loop (NEW 2026-07-22)

The A2 gate is MECHANICAL (broken-audio detection); it can't hear a mispronounced name,
a garbled number, a dropped word, or the clone drifting. P5 adds the PERCEPTUAL sensor and
the loop the retake actuator (B2) + take-preservation (B3) were built for.

- **P5.1 — WER scorer (`voice_quality.py`): FIRST.** ASR round-trip: transcribe each
  `sec_NNNN.wav` with the Whisper we already run for captions (CPU/int8 — no GPU), token-
  normalize both the transcript and the *spoken* (normalized) script text, compute word-error-
  rate per beat. High WER ⇒ the TTS said the wrong thing. Pure, unit-tested `word_error_rate`;
  scorer scores wavs ALREADY on disk (verifiable against the De Beers VO today).
- **P5.2 — companion signals:** pace-outlier (a beat's WPM far from its neighbors) and
  voice-consistency (speaker-embedding similarity of each beat to the reference clip → drift).
- **P5.3 — gate + surfacing:** high-WER beats become a `warn` in the voice gate + a `wer` field
  on `/api/voiceover-beats` (shown in the beat pill tooltip on the Narrate tab).
- **P5.4 — the polish loop (`nolan voiceover polish <slug>`):** score → **best-of-N retake**
  only the flagged beats, keeping the take with the lowest WER → re-score → converge (bounded
  rounds). This is the practical "finetune toward quality": OmniVoice is a black-box subprocess
  (no weight training, no seed), but non-determinism means each retake is a fresh attempt, so
  best-of-N selection genuinely improves a weak beat. Mirrors the script-review loop; Narrate
  gets a "Polish weak beats" button.

## Engine option — CosyVoice 3.0 provider (SHIPPED 2026-07-22, unblocks P6)

The P6 blocker was OmniVoice, not the idea. **CosyVoice 3.0** (Apache-2.0) does what OmniVoice
can't: `inference_instruct2(text, "…tone.<|endofprompt|>", ref_wav)` = **clone + natural-language
emotion in one call** (probe-verified: grave/happy/angry all land while keeping the voice).
Quality A/B on the full De Beers script (same narrator clone): **comparable — CosyVoice mean WER
0.031 vs OmniVoice 0.043**, 2× realtime; user note: neutral runs a touch tense, fixable with a
baseline `neutral_instruct` ("calm, measured"). Wired as a `TtsProvider`:
- `CosyVoiceConfig` + `TtsConfig.instruct_capable()` (True for cosyvoice3); `config.tts.provider =
  "cosyvoice3"` switches, OmniVoice stays the fallback.
- `CosyVoiceTTS` (tts.py) subprocesses into `D:\env\cosyvoice` via the standalone
  `tts_cosyvoice_runner.py`, which handles the three CosyVoice3 rules (16 kHz ref, `<|endofprompt|>`,
  float32→PCM16) so the pipeline stays engine-agnostic. `synthesize_sections` now sends the delivery
  as `instruct` whenever the engine is instruct-capable (no longer dropped on clone).
- Env: separate CUDA conda env (nolan runs CPU torch) — `D:\env\cosyvoice` + the ~10 GB
  `Fun-CosyVoice3-0.5B` model. Standing this up cost several install cycles (setuptools/pkg_resources,
  openai-whisper build isolation, sys.path shadowing `packaging.py`, 16 kHz/`<|endofprompt|>` inputs)
  — all captured in [[reference-omnivoice-engine-limits]]-style notes.

With CosyVoice3 selected, `supports_instruct` is effectively True → **A6 delivery notes + the P6
emotion arc below are now buildable for real** (no longer engine-blocked).

## P6 (EXPERIMENTAL) — tone / emotion arc

Highly experimental; gated behind a hard engine constraint. Two halves:
- **Can OmniVoice act on emotion? NO (emotion probe, 2026-07-22).** Its only nominal per-utterance
  emotion lever is the voice-design `instruct` field — and the probe proved `instruct` yields NO
  audio in EVERY combination (with/without clone). Voice-design *neutral* (no ref, no instruct)
  works, but the moment you add `instruct` OmniVoice produces nothing. So emotion-via-instruct is
  dead on this build. The ONLY working knobs with a consistent narrator clone are **pace**
  (`speed`/atempo) and the **emotion baked into the reference clip**. The one clone-compatible
  emotion experiment worth trying: a small set of same-narrator reference clips in different
  registers (calm / intense / wry), switched per pivot beat — each is a valid clone, so it should
  synthesize, and it stays "the same voice-ish." Needs a listening test. The real unlock is a
  higher-tier `TtsProvider` with native emotion (the abstraction is already there).
- **How to ASSIGN the arc (the judgment):** an LLM/agent reads the script and labels the
  emotional register of each beat, but crucially identifies the FEW pivot beats that carry the
  arc (hook, reveal, turn, close) — over-emoting every beat sounds fake. This is the A6 authoring
  half, routed to an agent (taste). Output = `[delivery: …]` on the pivots only. Deferred/experimental
  because it depends on (a) the engine constraint above and (b) subjective validation we don't
  yet automate. First experiment before any build: confirm OmniVoice's `instruct` audibly changes
  emotion at all, and whether multi-reference-register clips preserve voice identity.

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
