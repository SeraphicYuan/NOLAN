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

1. **Music bed + ducking + SFX** *(in progress)* — the invisible half of every
   good essay. Music library with mood/energy manifest; selection follows the
   per-beat energy arc the tempo system already computes; ducked under VO;
   risers/whooshes on section transitions and motion hits; silence as
   punctuation. ONE integration point: a post-assembly mix pass serving both
   standard and premium modes.
2. **Shot-lists within scenes + J/L-cuts** — editors cut in shots, not
   sentences. Scenes gain an optional shot sequence sharing their narration
   window (the deconstruction shots table proves the target cadence: 2–4s
   shots under longer spans). Visuals may overlap beat boundaries ~0.5s while
   audio stays anchored — kills the cut-on-sentence-boundary AI tell without
   breaking the sync contract.
3. **Unified color grade** — museum/stock/ComfyUI/screenshot assets are four
   color universes; one grade makes it *directed* instead of *assembled*.
   Premium: the Chapter composition's existing PostFX (grade/bloom/grain/
   vignette) wired from the theme (FLOW already uses it). Standard: an ffmpeg
   LUT/normalization pass over matched footage.
4. **Retention linter** — a static analyzer over the plan+render: hook length,
   visual-mode runs ("6 consecutive art stills at 2:35–3:10"), pattern-
   interrupt cadence (20–40s), energy plateaus. Rules seeded/learned from the
   deconstruction corpus, reported like the render report (no silent judging).

## Tier 2 — trust & packaging

5. **Asset identity verification + attribution manifest** — vision cross-check
   that a downloaded artwork IS its claimed work (the Nydia≠Bernini class);
   end-to-end per-video credits + license report from every matched asset
   (copyright strikes are the new-creator unknown-unknown).
6. **YouTube packaging** — 3–5 thumbnail candidates (best frames + ComfyUI +
   block typography), title variants from the hook, chapter markers from
   beats, description with credits. CTR decides more than anything inside
   the video.
7. **Draft mode + beat render caching** — `--draft` (quarter-res, low fps, no
   grade) and content-hash caching per section job so only changed beats
   re-render. Cuts the judge-a-cut loop from ~20 min to ~2; iteration speed
   IS craft.

## Tier 3 — compounding bets

8. **Image-to-video b-roll** — i2v models (Wan/Kling-class, in the existing
   ComfyUI) as one more asset-ladder rung: krea2 stills → real cinematic
   motion clips; generated scenes stop reading as animated slideshow.
9. **Taste feedback loop** — every scene accept/reject/edit is preference
   data; per-channel tuning of slide_designer + tempo prompts so the system
   compounds instead of resetting each project.

Status is tracked in the session task list; completed items get their design
recorded in ARCHITECTURE.md.
