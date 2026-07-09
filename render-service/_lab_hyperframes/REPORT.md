# Hyperframes lab test — REPORT

**Run:** 2026-07-08, fleet agent `nolan4` (Claude Code).
**Inputs:** `inputs/script.md` (2 beats) + finished VO `inputs/sec_0000.wav` (67.76s) + `inputs/sec_0001.wav` (91.76s). Optional NOLAN stills `scene_018/020/022.png`.
**Deliverables:** `out/final.mp4`, `out/final_repeat.mp4` (1920×1080, 30fps), this report.
**Project:** `videos/data-center-economics/` (created by their `hyperframes init`).

---

## 1. Route taken (their router, faithfully)

Started at the installed `/hyperframes` router skill. Input = arbitrary explainer text + finished narration, no product, no URL, no site to capture → the router's `/faceless-explainer` workflow (exactly as TASK.md predicted). Spec defaults it states-not-asks: **16:9**, language = English. Autonomous mode (fleet), so the workflow's user-gated steps (0/3/6) were taken with documented defaults instead of a live prompt.

Workflow executed end-to-end, their steps:
- **Step 0 Setup** — `npx hyperframes init videos/data-center-economics --non-interactive --example=blank`. Ran with `HYPERFRAMES_SKIP_SKILLS=1` (their sanctioned CI opt-out) so init would NOT mutate the repo's global skill set mid-eval — keeps the run pinned and honours "work only in the lab folder". `auth status` → **not signed in to HeyGen** → local-engine fallback (Kokoro/MusicGen). Noted, continued offline.
- **Step 1 Brief** — synthetic capture package by hand: `capture/extracted/visible-text.txt` (script verbatim), `capture/extracted/tokens.json` (title/description; empty colors/fonts — no brand override). `user_script.txt` saved; `VO_MODE=verbatim` (the wavs ARE the locked narration).
- **Step 2 Design system** — the one judgment call their process asks of you: pick a preset. Chose **`broadside`** (see §2). `node scripts/build-frame.mjs --preset broadside` → `frame.md` + `.hyperframes/caption-skin.html`, self-check passed.
- **Step 3 Storyboard/Script** — wrote `SCRIPT.md` (2 lines = 2 beats, verbatim) and `STORYBOARD.md` (2 frames, see §3 for the architecture reason). Autonomous: no live approval prompt.
- **Step 3.1 Audio** — ADAPTED for finished VO (see §4). No TTS.
- **Step 4 Visual design** — enriched `STORYBOARD.md` with a time-coded shot sequence per frame (12 Broadside treatment-scenes total), paced to the ASR word timings, + a `## Video direction` block. Motion verbs drawn from `rules-index.md` (no invented names).
- **Step 5 Build frames** — dispatched one frame-worker sub-agent per frame (their model), each authoring one self-contained sub-composition HTML. Then `captions.mjs` + `assemble-index.mjs`.
- **Step 6 Finalize** — `transitions.mjs inject/verify`, `lint`/`validate`/`inspect`, `snapshot` contact sheet (looked — correct), then rendered twice.

---

## 2. Design decisions THEIR process made

- **Preset = `broadside`** (dark ink-black plane, single fire-orange accent, massive **lowercase** Barlow-900 as graphic primitive, IBM Plex Mono uppercase chrome, flat plane / 1px hairlines, "numbers come from the script"). Picked by their Step-2 method (best fit for topic/tone/audience): serious data-journalism for an investigative money/power/cost story, big-number display for the dense stats, and fire-orange-on-ink reads as power/heat/energy. No NOLAN taste imported; no brand tokens, so the preset's own palette/fonts shipped unchanged.
- **Register discipline (their frame.md law):** one register per scene; DARK throughout except Frame-1 Scene-5 ("some towns cash in") which flips to the ORANGE register as the single upside beat. Fire-orange is the only color.
- **Motion (their rules):** `counting-dynamic-scale` (number count-ups earn their size), `stat-bars-and-fills` (percent bars, transforms only), `kinetic-beat-slam` (per-word statement slams), `asr-keyword-glow` (one inked clause lights on its spoken word), and a slow bounded camera drift (`multi-phase-camera`) under everything. Flat-plane compatible (no 3D/tilt rules).
- **Captions:** their default karaoke pill (bottom ~17%), skinned by the preset's caption-skin; all frame content kept in the top ~83%.
- **Two frame-worker editorial calls (documented by the workers):** (a) Frame-1 Scene-2 card B renders "$1T+" as a real count-up that rockets through billions and tips over the trillion line (0→"$1000B"→"$1T+"), since counting to "1" doesn't read as a count; (b) the "≈" glyph was swapped to "~"/kept minimal to avoid a missing-glyph fallback in clean Chrome.

---

## 3. Architecture: why exactly 2 frames (narration owns duration, wavs unmodified)

Read their `assemble-index.mjs`: a per-frame voice `<audio>` is emitted with `data-duration = the frame's duration` (track 10) — i.e. **a voice clip is clipped to its frame's window; it cannot span multiple visual frames.** Therefore the only way to play each beat wav **fully and unmodified** with the stock tooling is **one frame per beat**:
- Frame 1 = beat 1, duration **67.76s**, voice = `assets/voice/01.wav`.
- Frame 2 = beat 2, duration **91.76s**, voice = `assets/voice/02.wav`.

Each frame is internally a **6-scene time-coded shot sequence** (HyperFrames' intra-frame development), so visual density is unchanged — 12 scenes total, just grouped under 2 frame files. `audio sync-durations` bound each frame's duration to its wav's real duration. Assembled total = **159.52s** = 67.76 + 91.76, verified at assembly. Slicing the wavs (to get more frames) was rejected — it risks the "wavs play unmodified" requirement.

---

## 4. Assets used and where they came from

- **Narration:** the two supplied wavs, **byte-copied unmodified** into `assets/voice/01.wav` / `02.wav` (SHA256 of copy == source, verified). This is the timing authority; no TTS was run.
- **Word timings (for captions + reveal pacing):** their `hyperframes transcribe` returned `whisper_unavailable` (see BLOCKED). Fell back to **NOLAN's local whisper** (`nolan.whisper`, faster-whisper base/int8) — this is transcription *metadata*, not a media asset. Word **text** was then re-aligned to the ground-truth script (difflib) so captions read the real words on ASR timings; word **timings** stay ASR-derived.
- **Fonts:** Barlow + IBM Plex Mono via Google Fonts `@import` (their frame.md's stated mechanism). The render host has network (GSAP loads from CDN), and `lint` confirmed "the producer resolves Google Fonts during compile/render". I added the same `@import` to `compositions/captions.html` (it shipped without one) so the caption pill renders in Barlow too.
- **Visuals:** 100% invented — typography + CSS (bars, cards, hairlines, quote-mark). **No images sourced or generated.** The `broadside` preset's process never calls for real imagery, so the NOLAN fallbacks were not needed: **no** hub `/api/images/search`, **no** ComfyUI/krea2 generation, **no** NOLAN assets. The supplied NOLAN stills (`scene_018/020/022.png`) were **not used** — the design didn't call for them.
- **BGM / SFX:** none (see BLOCKED).

Net asset provenance: **finished VO (given) + Google-Fonts type + CSS-invented visuals.** Nothing new from any asset pipeline.

---

## 5. Failures, retries, surprises

- **D: drive WSL mount went to "Input/output error"** at the very start (couldn't read the lab folder or exec the Windows python from `/mnt/d`). Windows interop (`cmd.exe`) still reached D:, and I read `TASK.md` through it. The user remounted D: and everything recovered. (Environment, not the pipeline.)
- **`hyperframes transcribe` → `whisper_unavailable`** (whisper-cpp not installed in the CLI env). Fell back to NOLAN whisper. See BLOCKED.
- **Caption font fallback warning** — `captions.mjs` warned Barlow has no local `.woff2`; captions would fall back. Fixed by adding a Google-Fonts `@import` to `captions.html` (network is available at render). Surprise: the frames `@import` fonts but the generated caption composition did not.
- **Structural false-alarm (mine, not the pipeline's):** a grep for `class="clip"` returned 0 on frame 1 — because that worker put `clip` as the *last* class (`class="scene s2 clip"`); the frame is correct (bg + 6 scene clips). No re-dispatch needed.
- **Checks:** `lint` 0 errors / 21 warnings (Studio-editable-id, file-size, google-fonts advisories — all non-blocking); `validate` 0 errors, 13 WCAG-AA contrast advisories (Broadside's intentionally-dim mono chrome + a few caption words caught mid-highlight); `inspect` 0 errors, 9 `container_overflow` warnings — all the camera-drift wrapper edging a few px past its container as it scales (expected for that effect) + 1 info (the oversized quote-mark pokes 4px above canvas by design). No frame-element `text_box_overflow`. No fixes needed.
- **Surprise (good):** the 2-beat / finished-VO constraint collapses the storyboard to 2 long frames, which is unusual for this workflow (built for many short per-frame-TTS frames) but maps cleanly onto their per-frame-voice model.

---

## 6. Determinism (render twice; SHA256)

Both passes: 1920×1080, **30fps**, 4786 frames, **159.55s**, H.264 + AAC 48kHz stereo. Rendered with `--skill=faceless-explainer --quality high` (their Step-6 command), 6 workers.

| file | bytes | SHA256 |
|---|---|---|
| `out/final.mp4` | 36,404,463 | `aa452399e28ad7caeb531ce5854b7a0e37ac0d1223c350ef368d72ae94024b61` |
| `out/final_repeat.mp4` | 36,400,247 | `40fb0a40f3f8e17cba8345d7aeac572f4337cae63d2e4bf2d25fa526538ece9e` |

**The two MP4s are NOT byte-identical (SHA256 differ).** Breaking it down:
- **Audio: bit-identical** — decoded-audio MD5 = `662b893e21eaa6cfd1a06ff49355a1c9` for BOTH. The narration is reproduced exactly.
- **Video: not bit-identical but visually identical** — decoded-video MD5 differs (`6af111a7…` vs `6d6f985e…`), yet **SSIM = 0.999917** and **PSNR = 64.68 dB average (max = inf → many frames identical)**. So the composition is deterministic (seek-safe; no `Date.now`/`Math.random`/network state), and the run-to-run delta is **non-deterministic multi-worker H.264 encoding / headless-Chrome sub-pixel rasterization**, not a content difference.
- HyperFrames ships a **`--docker`** flag ("Use Docker for deterministic render") for bit-reproducible output; I did not use it (see BLOCKED). With it, byte-level SHA256 reproducibility is the expected path.

---

## 7. Timings (wall-clock)

- **Env orientation + recovery:** the D: outage/recovery preceded authoring (not separately timed).
- **Authoring (init → render start):** 12:18:24 → 12:54:18 = **~35m54s**. Breakdown: setup/brief/design/storyboard/script/transcription/audio_meta ≈ 14m; two frame-worker sub-agents (parallel) ≈ 15m (14.5 / 15.2 min each); assembly + captions + transitions + lint/validate/inspect + snapshot ≈ 7m.
- **Render:** both passes ≈ **2m37s each** (~4.7min wall for the two).
- **Total:** ≈ 41 min wall from init to both renders complete.

---

## BLOCKED (things I lacked)

- **HyperFrames whisper (`transcribe`) unavailable** — CLI returned `{"ok":false,"skipped":true,"reason":"whisper_unavailable"}` (whisper-cpp not installed for `npx hyperframes`). Impact: their in-house word-timing path couldn't run. Worked around with NOLAN's local whisper (faster-whisper). To unblock their path: install whisper-cpp / Parakeet for the hyperframes CLI (`uv pip install parakeet-mlx`, or a whisper-cpp build).
- **Not signed in to HeyGen (offline)** — no `HEYGEN_API_KEY`. Impact: (a) their HeyGen TTS unused (moot — VO was supplied); (b) **their BGM catalog retrieval unavailable** → the video ships with **no background music**. I did not substitute NOLAN MusicGen (kept assets inside their process). To unblock: set `HEYGEN_API_KEY`, or wire a local MusicGen for `--only bgm`.
- **Deterministic (byte-reproducible) render** — requires their `--docker` path (Docker not verified available in this Windows/WSL env). Without it, renders are visually identical (SSIM 0.9999) but not SHA256-identical. To unblock: run `hyperframes render --docker`.
- **Studio-editability warnings** — Frame-2 clips lack stable `id`s (`studio_missing_editable_id`); harmless for rendering, but Studio can't target them for edits. Non-blocking; not fixed (out of scope for a render-only eval).
- **NOLAN stills unused** — `inputs/scene_018/020/022.png` were available but the `broadside` (typographic) design didn't call for real imagery; recorded here so it's explicit, not an omission.

---

## Files

- `videos/data-center-economics/` — the HyperFrames project (index.html, compositions/frames/{01-boom,02-bill}.html, compositions/captions.html, frame.md, STORYBOARD.md, SCRIPT.md, audio_meta.json, assets/voice/{01,02}.wav, snapshots/contact-sheet-*.jpg).
- `out/final.mp4`, `out/final_repeat.mp4` — the two renders.
- `.timings.log`, `.render.log` — raw timing / render logs.

---

# ADDENDUM (2026-07-08 PM) — NOLAN→HyperFrames asset bridge + blended re-cut

Follow-up run after the pure-type eval: test HyperFrames' "true potential" by blending
externally-sourced imagery into the same video, via a **video-agnostic** bridge.

## The seam (verified across all 9 workflows first)
Two independent skill-tree audits (byte-level) found HyperFrames has NO single shared
asset spine — staging scripts and plan fields (`asset_candidates`/`focal`/`roles` vs
`asset:{treatment,clips}` vs `asset_needs[]`) are per-workflow dialects. The genuinely
agnostic seams are the ENDS: the project `assets/<basename>` landing dir + the
hyperframes-core clip mount contract (and optionally media-use's `.media/` ledger).
The bridge targets those; a thin per-workflow "plan-writer" adapter speaks the dialect.
(Also found upstream doc drift: frame-workers say `public/<basename>`, the staging lib
and assemblers resolve `assets/<basename>` — standardized on `assets/`.)

## What was built (bridge/, this lab folder)
- `bridge/resolve_inject.py` — RESOLVE (NOLAN krea2/ComfyUI via workflow registry,
  "Dark Moody Atmosphere", sequential + GPU-locked) → INJECT (project `assets/` +
  `bridge_assets.json` provenance ledger). Workflow-agnostic core.
- `bridge/intents.json` — 6 per-beat asset intents (the common schema an adapter
  translates from).
- Faceless adapter step: `asset_candidates` + `roles` + a Video-direction blend note
  written into STORYBOARD.md; frame HTMLs realize it as dimmed (45–65% + left scrim)
  full-bleed `class="clip"` grounds under the type with slow linear Ken-Burns
  (scale 1.03→1.10, fromTo, seek-safe). Type/timing otherwise byte-identical to the
  pure-type cut — a clean A/B.
- Blend philosophy: per-scene mix, NOT image-everything — 6 concrete beats got grounds
  (boom hero, sprawl close, the turn, desert water, bedroom drone, power lines);
  stat grids / compare / bars / orange payoff / jobs kicker stayed pure type.

## Results
- `out/final_blend.mp4` — 1920×1080, 30fps, 4786 frames, 159.55s (timing identical;
  narration untouched). sha256 `690e488a6813b7710b02eb49955294ad6fba4c59a7295e8f4b5992e3b5083831`.
  64.4MB (vs 34.7MB pure-type — photographic grounds cost bitrate).
- checks: lint/validate/inspect 0 errors (contrast advisories 13→17, dim chrome over
  grounds; container_overflow warnings unchanged, camera-drift class).
- Verified visually: snapshot contact sheet + frames extracted from the encoded MP4.

## Failures during this phase
- ComfyUI crashed mid-first-generation at 1920×1080 (VRAM) and needed a human restart;
  retried at 1344×768 (grounds are dimmed + cover-cropped, so native 1080p buys nothing).
  Constraint honored thereafter: ONE ComfyUI job at a time (NOLAN GPU lock).
- Two more WSL /mnt/d I/O stalls interrupted the phase (recovered by remount).
- Stock search unavailable (no UNSPLASH/PEXELS/PIXABAY keys in env) → generation-only
  source mix this run; recorded as BLOCKED.

## A/B verdict pointer
Compare `out/final.mp4` (pure kinetic type — their faceless default) vs
`out/final_blend.mp4` (same cut + NOLAN-sourced photographic grounds on the 6 concrete
beats). The blend keeps Broadside's system (ink/fire-orange, lowercase Barlow-900)
while giving concrete beats a cinematic ground — the "assets + motion + type overlay"
mix, produced by THEIR pipeline + NOLAN's asset engine through the agnostic seam.

---

# ADDENDUM 2 (2026-07-08 PM) — Style encoding: `highlighter-editorial` preset + Vox-style re-cut

Phase 2 of the bridge program: prove a custom STYLE can be fed to HyperFrames formally.

## What was built
- `presets/highlighter-editorial/` — a first-class custom frame preset (Vox-lineage),
  authored to the full preset contract: FRAME.md (frontmatter tokens + ~6-treatment
  design constitution: Cold Open / Highlight Statement / Chart / Stat Lockup / Quote /
  Evidence Collage; two registers PAPER+FOOTAGE; ONE highlighter-yellow mark per scene
  landing on the spoken cue) + caption-skin.html (mist plate, ink text, yellow karaoke
  block). Tokens grounded in github.com/mjsxi/vox-style-guide (authentic palette
  #FFF200/#6D98A8/#F1F3F2/#4C4E4D; Balto/Harriet/Alright Sans → Libre Franklin/Lora/
  Inter stand-ins; chart look from its fig. reference images). Deconstruction-driven
  style extraction DEFERRED (expensive) — later validation path.
- `videos/data-center-economics-vox/` — same VO, same word timings, same 6 NOLAN
  grounds; new storyboard in the Vox grammar; 2 frame-workers rebuilt both frames.
- **`--preset-dir` confirmed as the custom-style seam** — build-frame adopted the
  preset and passed its self-check (keys + ink/canvas contrast) with zero vendored-
  skill edits. The storyboard's `asset_candidates` also drove their own staging
  ("assets staged: 6/6") — the plan-level asset path exercised end-to-end.

## Results
- `out/final_vox.mp4` — 1920×1080, 30fps, 4786 frames, 159.55s. sha256
  `8c7ec376e26ad516404fccf57591b9ffdd8f86e7e30d5787e4b59a94b002067a`.
- Checks: lint 0 errors; validate CLEAN (40/40 text elements pass WCAG AA — the light
  paper register outperforms Broadside's dim chrome); inspect 0 errors after two fixes
  (chart year-labels below the axis marked `data-layout-allow-overflow` — intentional
  chart design; assembler auto-repaired missing root dims on both frames).
- Caption skin gap repeated from run 1: generated captions.html shipped without a font
  @import → added Google-Fonts import (systemic upstream nit: captions.mjs doesn't
  carry the skin's font dependency).
- Visual verification: contact sheets + encoded-MP4 frames — the signature reads
  unmistakably (yellow sweeps on "cash in"/"un-building"/"outright", parchment charts
  w/ fig. tags + dotted axes + terracotta drawing line, mist stat lockups, white
  statements over footage w/ scrim, evidence caption-bars, yellow-karaoke captions).

## The three-way A/B (same VO, same timing, same narration)
1. `videos/data-center-economics/out/final.mp4` — Broadside pure kinetic type.
2. `videos/data-center-economics/out/final_blend.mp4` — Broadside + NOLAN photographic grounds.
3. `videos/data-center-economics-vox/out/final_vox.mp4` — highlighter-editorial (Vox-school),
   full re-design: registers, charts, highlight grammar, new caption skin.
Together: HyperFrames separates STYLE (preset) from STORY (storyboard) from ASSETS
(the agnostic assets/ seam) — all three were swapped independently across these cuts.

---

# ADDENDUM 3 (2026-07-08 PM) — Bridge program complete: Phases 1.5 / 2.5 / 3

## Phase 1.5 — "NOLAN is the camera": collect → caption → select (`bridge/pool.py`)
Fans out NOLAN's WHOLE acquisition stack into a HyperFrames-native selectable inventory.
Corrected an earlier error: stock keys DO load (via repo-root `.env` / dotenv) — Pexels,
Pixabay, Unsplash all live. Run against 6 shot-needs produced a real POOL in
`pool_demo/capture/`: **11 valid stock images** (ddgs/pexels + AVIF/WebP) + **4 stock
VIDEO clips** (pexels_video, 1280×720, 9–14s, licensed w/ photographer credit), each
image vision-captioned by **OpenRouter qwen-VL** (`nolan.vision` + `_vision_config`) into
`capture/extracted/asset-descriptions.md` — the exact inventory shape product-launch /
website workflows SELECT `asset_candidates` from. So HyperFrames keeps selection; NOLAN
fills the pool. Captions are selection-grade (subject/setting/mood/palette/photoreal).
- Findings/hardening: (1) `image_search.download_image` throws `NameError: logger` in its
  gate-refuse branch — a real NOLAN bug (fails candidates, didn't block). (2) `ddgs` can
  return watermarked previews — prefer the licensed providers (pexels/unsplash/wikimedia).
  (3) Added a Pillow decode-validation to `pool.py` that culls HTML-error-pages-saved-as-
  .jpg (one occurred) — pool hygiene the first run surfaced.

## Phase 2.5 — variation push + a NOLAN-flavored registry block
- `bridge/motion-palette.md` — a Step-4 authoring reference mapping video-essay beat
  archetypes onto HyperFrames' FULL vocabulary (36 rules · 15 blueprints · 24 text
  effects · transitions catalog · 7 adapters), with an adapter-escalation ladder
  (GSAP→animate-text→Lottie→Three→TypeGPU). Our cuts used ~5 rules; this widens the
  cited set so future cuts use the framework's real range. Variety = authoring depth,
  not a framework limit.
- `blocks/artwork-stage.html` — a NOLAN-flavored registry BLOCK porting ArtworkStage:
  a motivated, focal-targeted Ken-Burns push on an archival still + an on-frame MUSEUM
  LABEL (italic-serif title + mono collection + gold hairline) — the citation habit the
  typographic presets lack. Variable-driven (`data-composition-variables`: src/title/
  collection/focal/push), renderable standalone. Demoed over a real archival artwork
  (Vergilius Vaticanus) → `videos/block-demo/out/artwork_stage_demo.mp4` (6s, lint/
  validate clean). This is how NOLAN craft gets INTO HyperFrames' vocabulary, not around
  it — installable per-project with zero vendored-skill edits.

## Phase 3 — video b-roll via archetype B (`videos/broll-demo/`)
The pattern guard ② blocks inside sub-comps, done the legal way: real stock CLIPS from
the pool mounted full-bleed as GROUNDS at the `index.html` HOST ROOT (`<video muted
class="clip">`, direct root child), with the Vox statement + highlighter sweep on the
MAIN timeline at global time. Two back-to-back video beats on one video track.
`out/broll_demo.mp4` (18s, 1920×1080/30fps, lint 0 errors). Verified from encoded frames:
the footage ADVANCES (server rack framing differs 1.5s→6.5s — the clip plays, not a still),
the yellow sweeps land on "sleep"/"vertical", and the second clip (pylons) plays in beat 2.
So HyperFrames CAN do motion-footage b-roll; it just isn't wired into the per-frame
faceless model — it needs the host-root archetype-B path (a small assembler extension to
productionize).

## Program status
Phase 1 (asset bridge + blend) · 1.5 (pool/inventory) · 2 (style preset + Vox cut) ·
2.5 (variation ref + registry block) · 3 (video b-roll) — ALL DONE and verified.
DEFERRED: deconstruction-driven style extraction (expensive; a later validation path);
productionizing archetype-B video into the faceless assembler; per-workflow plan-writer
adapters beyond faceless (product-launch/music/motion-graphics).

## Bridge artifacts (all under render-service/_lab_hyperframes/)
- `bridge/resolve_inject.py` · `bridge/pool.py` · `bridge/needs.json` · `bridge/intents.json`
- `bridge/motion-palette.md` (Step-4 variation reference)
- `blocks/artwork-stage.html` (registry block)
- `pool_demo/` (demonstrated pool + qwen inventory)
- `videos/block-demo/out/artwork_stage_demo.mp4` · `videos/broll-demo/out/broll_demo.mp4`
- three A/B cuts: `videos/data-center-economics/out/{final,final_blend}.mp4` ·
  `videos/data-center-economics-vox/out/final_vox.mp4`

---

# ADDENDUM 4 (2026-07-08) — THE FINAL CUT (everything baked in)

`videos/data-center-economics-final/out/final.mp4` — the culmination: full script (both
beats, 159.55s, narration owns duration), Vox `highlighter-editorial` style, ALL asset
types, greater motion variation — sourced via the NOLAN→HyperFrames bridge and curated in
the NOLAN pool.

## Specs
1920×1080 · 30fps · 4786 frames · 159.55s · h264 + aac 48k. 72.5 MB.
sha256 `3389a24bea8ca8a4d3b5fc8570c4184dc4f0f4997f1701cbf008ceae5fe16d65`.
Checks: lint 0 err (after the track-layer fix below), validate 0 err (6 contrast
advisories on yellow-on-video text), inspect 0 err.

## All asset types, in one cut
- **Stock VIDEO grounds (archetype B)** — 3, mounted at the index HOST ROOT (track 0),
  behind transparent Vox scenes: server-rack b-roll (opener), aerial cooling towers
  ("43% water stress"), pylons-in-cloud ("losing their land"). Verified in the ENCODED
  mp4 (not just preview). grid clip looped to cover its 12.9s window.
- **NOLAN-gen stills** — house-vs-datacenter (the turn), dark bedroom w/ rack-focus (the
  quote) cross-dissolving to the spaceship-at-the-window (the 7-yo nightmare), lone-worker
  control room (the jobs kicker), construction build-out (the close).
- **Paper / charts** — the $800B/$1T lockups, the terracotta 400M→900M svg-draw chart
  (fig.01), the electricity bars (fig.02), the 38% / power lockups.
- **Prop cutouts (Vox evidence)** — cash stack, GPU, the real electricity bill, gavel,
  earplugs, water glass, US map w/ a Virginia marker.

## Greater variation (vs the earlier ~5-rule cuts)
svg-path-draw (chart line) · stat-bars-and-fills (bars + underline sweeps) ·
counting-dynamic-scale (every numeral) · kinetic-beat-slam (per-line statements) ·
asr-keyword-glow (the yellow highlighter sweep, one per scene) · multi-phase-camera
(ground Ken-Burns) · depth-of-field-blur (the quote rack-focus) · a two-lane ground
cross-dissolve (bedroom→spaceship) · prop cutout reveals.

## The one integration fix worth noting
Root videos + the crossfade collided on track 0 (the transition injector demotes frame 1
to track 0). Resolved by layering: videos track 0 (backmost) < frame1 track 1 < frame2
track 2 < captions track 3. This is the archetype-B "productionization" the plan flagged
as deferred — done here by hand (`bridge/inject_root_video.py` + a track re-layer). A
clean upstream version would teach the faceless assembler to reserve track 0 for root
media and shift the frame/caption tracks up automatically.

## The full deliverable set (render-service/_lab_hyperframes/)
Cuts: `videos/data-center-economics/out/{final,final_blend}.mp4` (Broadside pure-type /
+grounds) · `videos/data-center-economics-vox/out/final_vox.mp4` (Vox, gen grounds) ·
**`videos/data-center-economics-final/out/final.mp4` (Vox, ALL asset types + variation)**.
Bridge: `bridge/{resolve_inject,pool,inject_root_video}.py` + `motion-palette.md`.
Preset: `presets/highlighter-editorial/`. Block: `blocks/artwork-stage.html`.
NOLAN pool project: `projects/data-center-final/` (75-asset curatable pool).
Code change: `InternetArchiveImageProvider` in `src/nolan/image_search.py` (archival stills).

---
# ADDENDUM 5 — Registry-block / kit speed test

Q: can recurring scene types become reusable blocks to avoid ~16 min/frame LLM authoring?

## Finding: true multi-instance block mounting FAILS for animated blocks
Built `stat-lockup` as a real HyperFrames registry block (variable-driven, `<template>`,
`data-variable-values`) and mounted it TWICE. Smoke test: instance 1 rendered its data
($800B); **instance 2 rendered blank**. Cause: every clone shares the same element ids
(`getElementById` returns instance 1's nodes) and the same `window.__timelines["stat-lockup"]`
key (second registration is orphaned). So registry blocks are great as ONE instance per
composition (or distinct blocks — e.g. `artwork-stage`), but you cannot mount the same
ANIMATED scene-block N times. (A block that scoped all lookups to its root + keyed its
timeline off the host's unique id could work — an upstream fix.)

## So the kit is realized at BUILD time — a deterministic composer
`bridge/compose.py` holds 3 reusable block-templates — **media_ground · stat_lockup ·
highlight_statement** — and stamps a compact `scenes_spec.json` into the two frame HTMLs
with per-scene id prefixes + one merged timeline. Same output the frame-workers hand-wrote.

## Speed result
| step | LLM frame-authoring | kit composer |
|---|---|---|
| generate 2 frame HTMLs | ~19 min wall (17m54s + 19m08s, parallel; ~37 min compute) | **0.097 s** |
| authoring input | 2 sub-agents writing ~600 lines each | one ~60-line `scenes_spec.json` (structured data) |
| assemble + checks + render | ~3m assy + 3m24s render | ~3m assy + 3m22s render |
| determinism | LLM variance per run | identical every run |

`videos/data-center-economics-kit/out/final_kit.mp4` — 1920×1080/30fps/159.55s, lint 0 err,
verified: all 3 block types render, video passthrough + image Ken-Burns + yellow sweeps +
count-ups all correct. It's simpler than the hand-authored `final.mp4` (charts→stat-lockups,
no props/rack-focus/cross-dissolve — template-coverage choices, not limits).

## Takeaway
The **generation step drops from ~16 min/frame to ~0.05 s** once a template kit exists.
A new same-length cut in this style: write the spec (~minutes) → compose (instant) →
render (~3.5 min). The kit is one-time; add `chart`/`prop-cutout` templates to close the
fidelity gap with the bespoke cut. Reuse in HyperFrames for animated scenes = a build-time
composer, not runtime block-mounts.

## Addendum 6 — prop-cutout template (fidelity gap, part 1 closed)

Added a 4th reusable module to `bridge/compose.py`: **`prop_cutout`** — the Vox
"object-as-evidence" photo card. A scene declares `data.props:[{src,corner,cue,tilt,
width,caption?}]`; the composer stamps each as an `<img class="clip">` on its **own**
track (`4+i`) with a scale+settle(+tilt) reveal, layered ON TOP of the scene's
`media_ground`. Wired 7 props into `scenes_spec.json` (cash+GPU on $800B, meter on the
power stat, the actual bill on Dominion, water glass, earplugs, gavel).

Layering verified (`snapshots/props/contact-sheet.jpg`): props composite over paper
stats, over the yellow-sweep statements, and — critically — **over the root b-roll
video** (water glass on the cooling-towers clip, gavel on the sky/pylon clip). Two props
on one scene (cash+GPU) render simultaneously once each is on its own track — the
`overlapping_clips_same_track` error first appeared when both shared track 4, then
cleared with the `4+i` offset. Kit re-composes in <0.1 s; lint 0 errors.

### Chart template — NOT d3
Checked whether HyperFrames exposes d3 before adding a chart template. It does the
opposite: `hyperframes-creative/references/data-in-motion.md:19` — *"No chart library
output — build with GSAP + SVG/CSS, not D3 or Chart.js."* Reasons: seek-safety (d3/Chart.js
animate with their own timers/transitions, which break frame-by-frame seek) and aesthetics
(the same ref bans gridlines/ticks/legends/pie/multi-axis). The bespoke charts already used
the prescribed path (`svg-path-draw` line + `stat-bars-and-fills` bars). So a future `chart`
template stays GSAP+SVG/CSS — d3 is a banned pattern, not an uncalled capability.

## Addendum 7 — geo-map composer template (fidelity gap, part 2)

Ported the d3 map into `bridge/compose.py` as a 5th reusable module: **`geo_map`** (a
tier-2 build-time composer template, not a runtime registry block — so it merges into the
frame's single timeline alongside stat/statement/prop, no multi-instance id collision).

A geo beat is now a spec entry: `{type:"geo", data:{kind:"us"|"world", highlight:[ids],
primary?, kicker, title, sub}}`. `kind:"us"` → FIPS ids + `geoAlbersUsa`; `kind:"world"` →
ISO-numeric ids + `geoNaturalEarth1`. d3 computes projection + geometry + centroid at frame
load; GSAP reveals (seek-safe); CSS themes (`.gstate`/`.ghl` = mist/highlighter). `highlight`
is an array (multi-state), and the label auto-flips to the side opposite the primary region.

Wiring detail: geo scenes need d3 + topojson + the geometry loaded before the timeline
script that holds their setup IIFE, so `compose_frame` injects `vendor/{d3,topojson-client,
us-states|world}.*` next to GSAP (script order guaranteed on mount, same as the existing
GSAP usage). **Dependency:** any project using geo scenes must have `vendor/` at its root
(d3.min.js ~280KB, topojson-client ~7KB, us-states.js ~127KB, world.js ~127KB).

Verified: `videos/geo-block-demo/` composes a 14s frame with TWO geo scenes (US Virginia +
world Ireland) → lint 0 errors, both render correctly with the right projection, highlight,
pin, leader, adaptive label, and house style (`snapshots/geo/contact-sheet.jpg`). The
composer now stamps a full data-viz map beat in <0.1 s.

The chart template (part 3) stays open, and stays GSAP+SVG/CSS per data-in-motion.md.

## Addendum 8 — compose-first authoring: catalog + gate + the thin NOLAN author step

Turned the composer from a hand-driven kit into an **agent-routable authoring path** (the
"prefer a template, go bespoke only when nothing fits" loop the user asked for).

### Option 3 — catalog + raw passthrough + coverage render (all done)
- **`bridge/catalog.json`** — the module-contract registry entry for the composer: each
  scene template (`stat`/`statement`/`geo`) + component (`media_ground`/`prop_cutout`) with
  `purpose` / `when_to_use` / `not_for` / `data_schema` / `constraints`. This is what an
  agent reads to route.
- **`bridge/check_catalog.py`** — honesty test: catalog scene types ≡ `compose.BLOCKS`,
  each entry names the real function, components exist. Passes; can't rot.
- **`raw` block type** in compose.py — bespoke passthrough (agent-authored `html` + `tl`
  merged into the frame's one timeline). So templated + hand-authored scenes coexist in a
  frame.
- **Coverage render:** swapped the Virginia stat beat for a `geo` map and re-rendered the
  full 2 beats → `out/final_kit.mp4` (159.55s, 72.3MB, h264+aac, 0 console errors). All FIVE
  modules verified in one cut: media_ground, stat_lockup, highlight_statement, prop_cutout,
  geo_map (Virginia confirmed in the encoded MP4 at 85s).

### Option 1 — the thin NOLAN author step (built + demonstrated)
- **`bridge/author.py`** — the deterministic gate: validates an agent's proposed spec
  against the catalog (type in catalog, required non-empty fields, geo kind, statement
  operative-in-line), reports the templated-vs-bespoke split, then builds via compose. NOLAN
  module contract: *draft → validate → accept.*
- **`bridge/AUTHOR_PROMPT.md`** — the agent contract: read catalog, classify each beat,
  prefer a template, author `raw` only when nothing fits.
- **Demonstration:** a FRESH general-purpose agent (no shared context, no outside HyperFrames
  knowledge — only `catalog.json` + `AUTHOR_PROMPT.md`) authored a 4-beat frame. It routed
  beat1→stat (a rate), beat2→geo (a place, VA), beat3→statement (operative "water"),
  beat4→raw (a custom POWER/WATER/LAND triptych with no template). `author.py` validated
  (3 templated, 1 bespoke), composed, lint 0 errors; all four render in consistent Vox style
  (`videos/author-demo/snapshots/beats-grid.png`). The bespoke triptych sits seamlessly
  beside the templated scenes in one timeline.

**Net:** the composer is now catalog-described, honesty-tested, and agent-routable, with a
validating gate — the compose-first / bespoke-fallback tier NOLAN's contract calls for, and
that HyperFrames' prose-blueprint system doesn't provide as a code generator.

## Addendum 9 — plumbed into the faceless Step-5 orchestrator

The compose-first author step is now a **drop-in Step-5 path** in the faceless-explainer
pipeline — no fork of the surrounding orchestration.

### What changed
- **`faceless-explainer/sub-agents/compose-first-frame-worker.md`** — a new Step-5 sub-agent
  with the SAME input/output contract as the stock `frame-worker.md` (reads its `## Frame N`
  block + `frame.md`; writes `compositions/frames/<id>.html`; never touches `STORYBOARD.md`),
  but it expresses each Scene with a composer template (`catalog.json`) and builds the frame
  via `author.py`, hand-authoring `raw` only where no template fits. Extra input: `BRIDGE_DIR`.
- **`faceless-explainer/SKILL.md` Step 5** — one added paragraph: dispatch the compose-first
  worker per frame (passing `BRIDGE_DIR`); stock `frame-worker.md` stays the fallback for a
  fully bespoke frame. Everything else in Step 5 (duration-sync, SFX, captions,
  `assemble-index.mjs`) is untouched — the artifact is identical, so nothing downstream cares.
- **`bridge/vendor/`** — canonical geo libs (d3/topojson/us-states/world); the worker copies
  them into a project when a scene is `geo`.

### Demonstrated
Built a faithful mini-project (`videos/faceless-demo/`: real-format `STORYBOARD.md` + Vox
`frame.md`) and dispatched the compose-first worker as the orchestrator would. It read the
storyboard block + catalog with no outside HyperFrames knowledge, routed Scene1→stat,
Scene2→geo(VA), Scene3→statement (0 bespoke), copied vendor, and self-ran the gate:
`OK — spec validates: 3 scenes (3 templated, 0 bespoke)` → `built 01-power.html`. Lint 0
errors; all three scenes render in consistent Vox style (`snapshots/f1-grid.png`).

### The contract caught real drift
Mid-task an external edit added a 6th template (`timeline` — a Vox horizontal timeline:
spine draw + camera pan + circular cutouts). `check_catalog.py` FAILED with
`compose.BLOCKS has types the catalog does not document: ['timeline']` — exactly the honesty
test doing its job. Reconciled by documenting `timeline` in `catalog.json` (+ its required
`events` field in `author.py`); test green, and the template is now agent-routable. Six
templates total: stat · statement · geo · timeline · (media_ground · prop_cutout components)
· raw escape hatch.

### Honest edge
Verified the frame via a host mount + snapshot (the artifact is byte-compatible with the
stock worker, which the assembler already consumes). The full Steps 0-4 → compose-first
Step 5 → assemble → render on real VO is the natural next end-to-end; the per-frame contract
is proven.

## Addendum 10 — a REAL end-to-end run (Steps 0-6, compose-first Step 5, VO-synced)

Ran the full faceless-explainer pipeline on a fresh topic (`videos/dc-real/`, ~27s, 3 frames)
with the compose-first Step 5 as the frame builder, and verified VO↔animation sync.

### The run
- **Step 0/2** — init + `build-frame.mjs --preset highlighter-editorial --preset-dir …` → Vox
  `frame.md` + caption skin.
- **Step 1/3** — brief + `STORYBOARD.md` (3 frames) + `SCRIPT.md` (numbers spelled for TTS).
- **Step 3.1 (audio)** — HeyGen not signed in → local Kokoro. Kokoro's TTS shells out to
  `npx` and failed (`npm_execpath` unset when run via bare `node`). **Pivoted to NOLAN
  OmniVoice** (`create_tts_provider(cfg.tts)`) for the 3 VO wavs, and NOLAN faster-whisper
  (forced `device=cpu` — `auto`→CUDA hit a missing `cublas64_12.dll` in the nolan env) for
  word timings. Built `audio_meta.json` in the faceless schema by hand and synced STORYBOARD
  durations (12.01 / 9.36 / 5.48s = 26.85s). Narration owns duration.
- **Step 4** — enriched STORYBOARD with time-coded shot sequences paced to the measured word
  cues (map on "Virginia" 8.28s, water-sweep on "water" 1.34s, triptych on power/water/land
  1.66/2.32/2.72s).
- **Step 5** — dispatched **3 compose-first workers in parallel** (the real Step-5 shape).
  Routing, entirely from `catalog.json`: F1 stat→geo, F2 statement→stat, F3 raw triptych →
  **4 templated + 1 bespoke**. Then `captions.mjs` (38 groups / 80 words) + `assemble-index.mjs`
  (3 frames track 1, 3 VO `<audio>` track 10, captions track 2).
- **Step 6** — render → `out/dc-real.mp4` (26.88s, 1920×1080, h264 + **aac**, 3.1MB).

### Two real bugs found + fixed
1. **Digit-first id selectors.** Faceless frame ids are `NN-title` (`01-power`), scenes
   inherited them, and the composer emitted `#01-power-s1-k` — invalid CSS, so
   `querySelectorAll` threw and those scene timelines silently didn't run (caught in the
   first render's `Browser:ERROR`). Fixed in `compose.py` with `_safe_sid` (prepend a letter
   when digit-first) applied in `compose_frame`; ids are now `#s01-power-s1-k`. General
   robustness win for any faceless project.
2. **Caption font.** `captions.html` used "Libre Franklin" with no `@font-face` (lint error);
   added the Google-Fonts `@import` (the frames already had one).

### Sync verified (the point of the run)
Extracted frames at the exact word-cue timestamps: 12% on "12 %" (3.5s), Virginia map on
"Virginia" (8.7s), the "water" sweep on "water" (13.5s), the triptych columns on
power/water/land (24.3s), the closing question on "who pays" (25.9s) — each reveal lands on
its VO word, and the karaoke caption shows the same word. `out/sync-grid.png`. Full pipeline,
real voice, compose-first frames, in sync.
