# archival-canvas — the de-facto NOLAN house style

**Status: control specimen.** This documents what the pipeline ALREADY does by
default — archaeology, not aspiration. A second style pack will be authored
against it.

**Identity in three sentences.** Archival stills and museum art carried by a
Ken Burns-family camera (push/pull/pan, salience-targeted), interleaved with
ComfyUI-generated art in the krea2 look when no real asset clears the gates.
Text blocks (quotes, chapter cards, stats) act as punctuation between image
scenes, styled by one compiled theme; transitions are soft (fade/dissolve at
low energy, hard cut only when the arc drives up). The result reads as a
British-museum documentary: composed, flat-lit, digitally clean.

---

## Per spine step (PIPELINE_STEPS, `src/nolan/orchestrator/director.py:44-56`)

### 1. match_and_adapt_style
Agent writes `style_guide.md` (prose); the Brief Compiler turns it into
`brief.json`: theme picked deterministically by the explainable selector over
LLM-extracted descriptors, plus music_mood, voice_id, pacing, optional accent
hex. Fallback theme when no selector signal fires: **bold-signal**
(`src/nolan/project_brief.py:64`, `:304`). Themes live in `themes/` (25 packs,
compiled to `render-service/remotion-lib/src/styles/_active-theme.json` — one
theme per render).

### 2. script_to_scenes
Produces `scene_plan.json` (lossless schema v2). Scene `visual_type` mix is
the style's backbone — observed evidence below.

### 3. tempo_enrich
Editorial Arc pass (`src/nolan/tempo_plan.py`): whole-script energy CURVE →
per-beat `transition` (cut|dissolve|fade), `motion_speed`, `shots` density.
Energy→lever map (`tempo_plan.py:86-96`): fade <0.35, dissolve <0.55, cut
above. Profiles: punchy / contemplative / balanced.

### 4. select_clips
Library clip matching for footage scenes (clip_matcher); most house-style
projects have few true footage beats, so this mostly passes through to stills.

### 5. slide_designer
Text/data scenes get `layout_spec` blocks from the TEMPLATES palette
(`src/nolan/layout_blocks.py:420-483`): 31 templates — quote, pull_quote,
chapter_card, title, statistic, counter, timeline, bar/line charts,
kinetic_headline, detail_loupe, etc. Content budgets enforced at one choke
point (`BLOCK_BUDGETS`, `layout_blocks.py:495`). INFO_SCENE_TYPES =
text-overlay | graphic | infographic (`director.py:61`).

### 6. motion_design
Authored `motion_spec`s validated against the motion registry
(`src/nolan/motion/registry.py:70-377`): ~30 effects across remotion / block /
python backends — kinetic-text, bar-compare, still-motion, split-screen,
stat-over, photo-montage-pro, photo-grid, route-map, timeline (motif layer:
accumulating infographics via `motion/motifs.py`), plus gap effects
(screen-frame, camera-shake, before-after, whip-transition, typewriter, PiP).
In practice the house style uses motion sparingly — see evidence.

### 7. generate_assets
The asset engine ladder (`src/nolan/asset_engine.py:1-25`): human shortlist
(tier 0) → exact-title museum pass for archival-art → library video (footage,
threshold-gated) → picture-library stills (hybrid threshold 0.24) → external
stock/archival providers (Pexels/Pixabay/Unsplash + museum providers, all
through asset_gate) → **ComfyUI generation** → none. Generation uses the
krea2 workflow (`src/nolan/config.py:38` `workflow: "krea2-style-select"`);
policy: never diversify by switching models — vary via Fooocus styles/prompts.
Every resolution stamped on `scene.resolved_source`; no-reuse across scenes.

### 8. voiceover
Per-section VO wavs (`assets/voiceover/_work/sec_*.wav`) are THE beat anchors
— narration owns duration. Voice from brief.json voice_id (project.yaml
outranks; default from voice library, `project_brief.py:226-240`).

### 9. align_narration
Word-level alignment stamps `start_seconds`/`end_seconds` on scenes; the
camera-tour and kinetic word cues hang off these.

### 10. soundtrack
`src/nolan/audio_mix.py`: energy-arc-matched music bed from
`projects/_library/music/` (closest mean-energy track, 2s fade-in/4s
fade-out), sidechain-ducked under VO (music_gain_db default -14), whoosh on
section transitions, **risers** when the next section jumps up the energy arc
(`audio_mix.py:392-399`), **hits** on data punches, ambient SFX cues authored
from narration keywords (fire crackle, ocean waves — `_SFX_AMBIENCE`,
max 2/section). Audibility is measured (band RMS), not assumed.

### 11. render
Premium lane (`src/nolan/premium_render.py`). Stills get the camera pre-pass
`assign_still_treatments` (`src/nolan/still_motion.py:135-170`): narrative
cues pick kenburns-pan (narration MOVES) / kenburns-out (WIDENS) /
kenburns-in (NAMES/examines, also the fallback), hard no-two-consecutive
rule, and the last <0.3-energy scene of a section gets **drift** (the quiet
close). Vocabulary: `STILL_TREATMENTS = kenburns-in|out|pan, drift, tour`
(`still_motion.py:112`). Camera origin aims at the rembg-salient subject
(`subject_center`, `still_motion.py:173`). Long spans may split into 2-4s
camera-toured shots (`shot-list`, `src/nolan/editing.py:53-73`). Scene entry
is theme-background opacity ramp: dissolve ≈0.27s, fade ≈0.47s, else hard cut
(`editing.py:74-92`); overlap dissolves are banned (duration-preserving).

---

## Defaults observed

| Lever | Default behavior | Where |
|---|---|---|
| Camera on stills | kenburns-in fallback; pan/out/in by narrative cues; no two consecutive identical; drift on low-energy section close; `tour` only word-anchored | `still_motion.py:81-170` |
| Transition | energy-mapped: fade <0.35, dissolve <0.55, cut ≥0.55; vocabulary `cut|dissolve|fade` only | `tempo_plan.py:86-96`, `editing.py:34` |
| Theme | selector over brief descriptors; fallback **bold-signal** | `project_brief.py:64,304` |
| Asset tiers | shortlist → museum exact-title → library video → picture library (0.24) → stock/archival → ComfyUI krea2 → none | `asset_engine.py:1-25` |
| Generation | krea2-style-select workflow, one model, Fooocus-style variation | `config.py:38` |
| Music | closest mean-energy library track, -14 dB under VO, sidechain duck | `audio_mix.py` |
| SFX | whoosh on section cuts, riser on energy jump-up, hit on data punch, ≤2 ambient cues/section | `audio_mix.py:245-340` |
| Text blocks | 31-template palette, budget-gated, blocks as punctuation not content | `layout_blocks.py:420-483` |

## Evidence: projects/aeneid-2beat-v2/scene_plan.json

18 scenes: archival-art 7, generated-image 6, text-overlay 4, graphic 1 —
i.e. ~72% image scenes, ~28% text/graphic punctuation. Transitions: fade 9,
dissolve 9, cut 0 (a contemplative-profile piece living entirely below the
0.55 energy line). motion_spec 0, shots 0, layout_spec 5 — motion effects
unused; the camera pre-pass carries all still life. Authored camera locks on
4 scenes (kenburns-out ×2, kenburns-pan, drift).

## Known gaps (what the style does NOT have)

- **No analog grammar**: no film grain, gate weave, jitter, paper texture,
  vignette-as-style, or cutout/collage compositing — stills render flat and
  digitally clean over the theme background.
- **No color grade signature** beyond the theme tokens; the krea2 look is the
  only "grade" generated art gets.
- **Camera vocabulary is small**: five treatments, one easing family; no
  handheld drift-noise on stills (camera-shake exists in the registry but is
  an explicit punctuation effect, not a texture).
- Transition vocabulary is deliberately minimal (cut/dissolve/fade); whips,
  wipes and clockWipes exist only inside clip-montage / whip-transition
  motion specs, not as scene boundaries.
