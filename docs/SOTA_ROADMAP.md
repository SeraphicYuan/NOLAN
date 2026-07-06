# SOTA Roadmap — closing the craft gap

**Goal:** high-quality YouTube video essays across topics and styles, from the
one pipeline (script → plan → asset/motion/effect/words/charts/tempo/voiceover
matching → render), human-in-the-loop by choice.

**Diagnosis (2026-07-05):** NOLAN is strong on *correctness* (sync contract,
lossless plan, honest failures) and *acquisition* (assets, voices, styles,
deconstruction-as-taste-import). The remaining distance to SOTA is almost
entirely in the **invisible layers of craft** — sound, cutting rhythm, grade,
retention — plus trust (rights, identity) and iteration speed. Worked one by
one, in this order.

## Tier 1 — perceived quality

1. **Music bed + ducking + SFX** *(DONE 2026-07-05 — `nolan.audio_mix`,
   `soundtrack` Director step: author `soundtrack.json` → render executes
   `mix_from_spec`)* — the invisible half of every
   good essay. Music library with mood/energy manifest; selection follows the
   per-beat energy arc the tempo system already computes; ducked under VO;
   risers/whooshes on section transitions and motion hits; silence as
   punctuation. ONE integration point: a post-assembly mix pass serving both
   standard and premium modes.
2. **Shot-lists within scenes + J/L-cuts** *(DONE 2026-07-05 — premium mode,
   `nolan/premium_render.py`)* — editors cut in shots, not sentences.
   `scene.shots` `[{src, place?, weight?, caption?}]` expands a scene into
   weighted sub-steps sharing its narration window, each a camera-toured
   still (place = nine-dot camera target); audio slices are sample-exact so
   mid-speech seams can't click. J-cuts: internal cut boundaries into
   still-led scenes shift ~12 frames earlier (`j_cut_frames` in project.yaml,
   0 disables) — image arrives while the last sentence finishes; text cards
   keep straight cuts (their reveal waits for the word cue); section edges
   stay anchored, so |video − narration| is untouched by construction.
3. **Unified color grade** *(DONE 2026-07-06 — brief.json `grade` block
   (gated) -> Chapter PostFX per beat; ONE theme system: stage.mjs resolves
   active tokens into _active-theme.json so hosted comps match the blocks;
   accent override reaches everything)* — museum/stock/ComfyUI/screenshot assets are four
   color universes; one grade makes it *directed* instead of *assembled*.
   Premium: the Chapter composition's existing PostFX (grade/bloom/grain/
   vignette) wired from the theme (FLOW already uses it). Standard: an ffmpeg
   LUT/normalization pass over matched footage.
4. **Retention linter** *(DONE 2026-07-06 — nolan/retention.py: treatment
   monotony, visual-mode runs, energy plateaus, pacing-vs-brief (its first
   consumer), slow-hook, static-hold; report at render + `nolan lint`;
   never blocks)* — a static analyzer over the plan+render: hook length,
   visual-mode runs ("6 consecutive art stills at 2:35–3:10"), pattern-
   interrupt cadence (20–40s), energy plateaus. Rules seeded/learned from the
   deconstruction corpus, reported like the render report (no silent judging).

## Tier 2 — trust & packaging

5. **Asset identity verification + attribution manifest** *(DONE 2026-07-06 —
   nolan/attribution.py: attribution.json + CREDITS.md with a loud VERIFY
   BEFORE PUBLISH section; image-tier license sidecar fixed;
   `nolan credits --verify-identity` vision-checks named artworks)* — vision cross-check
   that a downloaded artwork IS its claimed work (the Nydia≠Bernini class);
   end-to-end per-video credits + license report from every matched asset
   (copyright strikes are the new-creator unknown-unknown).
6. **YouTube packaging** *(DONE 2026-07-06 — nolan/packaging.py + `nolan
   package`: chapters from section anchors, subtitles shipped from the
   captions pass, LLM titles/description with deterministic fallback,
   best-frame + brief-themed typographic thumbnails, credits)* — 3–5 thumbnail candidates (best frames + ComfyUI +
   block typography), title variants from the hook, chapter markers from
   beats, description with credits. CTR decides more than anything inside
   the video.
7. **Draft mode + beat render caching** *(DONE 2026-07-06)* — `draft: true`
   renders half-res / no whisper / no gate, loudly marked everywhere; the
   beat cache stamps each section job (content + referenced media + the
   section wav; regenerated _work slices excluded) and reuses unchanged
   beats — reuse REPORTED in the checkpoint, `beat_cache: false` opts out.
   Iteration speed IS craft.

## Tier 3 — compounding bets

8. **Image-to-video b-roll** — i2v models (Wan/Kling-class, in the existing
   ComfyUI) as one more asset-ladder rung: krea2 stills → real cinematic
   motion clips; generated scenes stop reading as animated slideshow.
9. **Taste feedback loop** *(DONE 2026-07-06 — nolan/taste.py: override
   ledger (test projects excluded) → `nolan retro` distiller with a
   deterministic evidence gate (>=3 events, >=2 projects) → rules as
   TIERED PRIORS (prefer-with-deviation + experiment clause; only
   human-locked rules constrain) scoped channel/video-type → injected
   into scenes/slides/motion prompts; /taste UI to review evidence,
   amend, lock, retire)* — every scene accept/reject/edit is preference
   data; per-channel tuning of slide_designer + tempo prompts so the system
   compounds instead of resetting each project.

Status is tracked in the session task list; completed items get their design
recorded in ARCHITECTURE.md.
