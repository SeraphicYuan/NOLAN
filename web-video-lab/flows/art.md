# Flow: Artwork Explainer (`art`) — scope

The inverse of the explainer flow: **image-first**. The artwork IS the subject; the narration
interprets what's on screen; the "visual generation" is **camera navigation** of a persistent
hero image (the museum-docent move), in a gallery/series. Status: **built + proven end-to-end** —
the full 8-beat Holbein *Dance of Death* (6:23) renders all-Remotion from real NOLAN voiceover
word-timestamps, gated by the pre-render QA tiers below. `ArtworkStage`, `DetailLoupe`,
`ImageCompare` all built. Delivery: `web-video-lab/art/final/dance-of-death.mp4`.

## When to use
A single artwork or a series (paintings, prints, photographs, diagrams-as-objects). Never
redraw — you always *lift* the real image.

## Ingest — `byo-everything` (the Dance of Death case)
The user already has script + voiceover + images in NOLAN, so this is **assemble, not
generate** — and the heavy step is free, because the voiceover is already word-timestamped:
- **Audio + words**: `projects/<slug>/assets/voiceover/segments/segments.json` (the partition
  manifest: segment → wav → duration) + per-segment `NN_title.words.json` (word-level timing).
  No TTS, no Whisper — read the existing timings straight into the spec's `words`.
- **Script/beats**: `projects/<slug>/script.md` (## headings = beats), aligned 1:1 to segments.
- **Images**: `_library/images/files/<hash>/<hash>.jpg` (content-addressed; the project's set
  is found via `catalog.db`). Map each artwork to its beat(s).
- An `art_ingest.py` adapter (to build) emits the spec: one `ArtworkStage` (or gallery of them)
  per image, `audioSrc`+`words` from the segments, focuses authored per beat.

## Grammar
- Per piece: **establish → tour → step back**. Show the whole (a contemplative hold), then —
  as the narration names a detail — push in + spotlight + label it, then pull back.
- **Rules**: always-lift-never-redraw · the image is *persistent* across a beat's tour · holds
  are long (let the eye look) · the wall-label grounds every piece.
- Series structure: optional `ChapterCard` between pieces; a `Timeline` for historical context;
  `PullQuote` for a contemporary voice; `EndCard` to close.

## Palette
- ✅ **ArtworkStage** (built) — full-bleed image + word-synced Ken Burns tour + spotlight +
  callouts + museum wall-label. Props: `{ src, label?, focuses:[{word,x,y,w,h,caption?}],
  introHold?, maxZoom? }`. (`maxZoom` caps the push-in so low-res scans stay legible.)
- ✅ **DetailLoupe** (built) — crop-and-enlarge a detail *beside* the whole (context retained).
  Props: `{ src, region:{x,y,w,h}, label?, caption?, revealFrames:[whole,loupe] }`.
- ✅ **ImageCompare** (built) — two artworks / two details side-by-side (ComparisonVS for images).
  Props: `{ kicker?, left, right, verdict?, revealFrames:[left,right,verdict] }`. Panels carry a
  slow deterministic Ken Burns drift so a held woodcut never sits dead-static.
- ◻ **WallLabel** (scope) — currently inline in ArtworkStage; promote to standalone for
  label-only beats.
- Reuse: ChapterCard, PullQuote, Timeline, EndCard.

## Pacing profile (linter `--profile art`)
WPM 95–140 (contemplative) · dead-gap checks OFF (long holds are correct here) · **min-hold
2.5s** (a beat that flashes by reads as rushed — the inverse of the explainer's dead-stretch
rule) · density ≤0.8 reveals/s.

## Defaults
Theme: a neutral "gallery wall" — a dark surface makes B&W prints pop (used `midnight-press`
for the test; a dedicated `museum-neutral` theme is a nice-to-have) · cross-fade transitions
between pieces · subtle grade + vignette (PostFX) for a lit-gallery feel.

## QA gate — check per beat, *before* the full render (cheapest-first, fail-fast)
Checking only the finished mp4 inverts the cost gradient: a defect costs ~7 min to surface
(or ships, if you don't sample that beat). Almost nothing needs the concatenated video — gate
each beat first, and only a green beat earns a place in the full render. One entry point:

```
python web-video-lab/art_check.py art/<name>.job.json --profile art   # runs all tiers, fail-fast
```

| Tier | Tool | Cost | Catches |
|------|------|------|---------|
| 0 · structural | `art_validate.py --flow art` | ~1s, no render | bad image/audio path, focus rect out of frame, reveal-slot count < block arity, unknown block, **block outside the flow palette** (soft warn — RAW allowed-but-flagged, shared set exempt; `--show-palette art` lists the blocks to reach for) |
| 0 · temporal | `pacing_lint.py` | ~1s, no render | WPM band, late first-reveal (black-screen class), reveal gap, density |
| 1 · spatial | `art_contact.py` | ~25s (1–2 stills/beat) | clipped/off-frame content, single-panel compare, empty/near-black beat — emits a **labeled contact sheet** (`output/<name>.contact.png`) + auto-flags black beats |
| 3 · full render | `render.mjs` | ~minutes | only after Tiers 0–1 are green |

Tier 1 renders stills via `renderStill` (no encode/audio) through the **same** `stage.mjs` the
real render uses, so the sheet can't lie. This is also what makes safe **parallel (subagent)
rendering** possible: each beat is independently gated, so beats can be farmed out and only
clean ones stitched. Both defects found in the Dance of Death build (DetailLoupe clipped
off-frame; ImageCompare single-panel) are exactly Tier-1 catches — one contact sheet shows them.

## Known limitations & room to improve (found building the Dance of Death)
- **Pacing profile vs real VO fight** — every beat warned "fast" (148–188 wpm vs the 95–140
  art band) because the real narrator is brisker than the contemplative ideal. The flow has no
  lever to *re-pace* (insert breath/silence). Fix: per-voice profiles, or a silence-pad control.
- **Authoring is hand-tuned JSON** — focus rects are guessed fractions, images are 64-char
  hashes, anchors are hand-picked words. Doesn't scale. Wants an image picker + click-to-place
  regions + vision-suggested salient regions.
- **Quality ceiling = camera-over-flat-image** — "always-lift" is faked with Ken Burns +
  spotlight + drift; can't isolate/animate a figure within the woodcut. Inherent to image-first.
- **No cross-beat transition grammar** — beats hard-cut (`premountFor` only prevents pop-in).
- **Dual Python env** — `art_ingest.py` needs WSL `python3` (POSIX paths) while `_montage.py`
  needs the nolan env python (Pillow). Normalize onto one interpreter.
- **Tier-1 spatial auto-check is black-only** — clip/overflow detection is still human-glance
  on the contact sheet (border-touch heuristic false-positives on full-bleed ArtworkStage).

## ⚠️ Resolution caveat (real, found in the Dance of Death assets)
The library scans are **750px wide** — well below the ≥2000px ideal for deep zoom. ArtworkStage
caps zoom (`maxZoom` ~1.6) so they stay legible, leaning on **spotlight + callout** more than
deep push-in. For production quality, **source high-res public-domain scans** (these Holbein
woodcuts exist at 3000px+ from museum/IA collections) — then zoom can go deeper.
