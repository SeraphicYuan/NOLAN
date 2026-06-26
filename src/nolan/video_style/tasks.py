"""Synthesis brief handed to the video-style agent (the reduce step).

Mirrors ``webui.operations._style_synthesis_task`` but for *visual* style: the
agent reads the per-video extracts (computed stats + pairing profile + vision
reads) and the cached frames, and writes ``video_style_guide.md``.
"""

from __future__ import annotations

from typing import List


def video_style_synthesis_task(style_id: str, name: str, slugs: List[str]) -> str:
    base = f"video_styles/{style_id}"
    return f"""# NOLAN video style-guide synthesis: "{name}"

The per-video extraction is done. Your job is the **synthesis**: distill a single,
opinionated, reusable **video / production style guide** from this corpus, as a
professional director/editor would — so a similar look (and visual-verbal feel)
can be cloned.

## Inputs
- Per-video extracts (JSON): `{base}/per_video/*.json`  ({len(slugs)} files)
  Each has: `format` (aspect/fps/duration), `color` (palette hex, saturation,
  contrast, warm/cool `temperature`), `motion`, `graphics` (edge/overlay density),
  `pacing` (cuts/min, shot-length stats, `tempo`), `cinematography` (per-frame
  style reads from the vision model), and **`pairing`** (the script↔visual
  relationship — see below).
- Sampled frames to look at: `{base}/frames/<slug>/*.jpg`

## What to do
1. Read all extracts; open the frames to ground your reading. The computed numbers
   (palette, pacing, directness distribution) are the **objective backbone** — trust
   them; use the frames + vision reads for interpretation.
2. Find the **recurring** patterns across the corpus (not one-off shots). Cite which
   are consistent vs occasional.
3. Write the guide to `{base}/video_style_guide.md` with these sections:
   - **Overview** — what this visual style is, genre/platform, who it's for.
   - **Format & Specs** — aspect ratio, orientation, fps, typical length.
   - **Color & Lighting** — palette (real hex from `color.palette`), warm/cool,
     saturation/contrast, lighting mood.
   - **Editing & Pacing** — use **`tempo`** (video-measured: true `cut_count`,
     `cuts_per_min`, shot-length stats, `intra_shot_motion`, `energy`, `trend`, and
     the per-window `curve`) as the PRIMARY signal; `pacing` (index-segment-derived)
     is only a fallback. Describe fast vs contemplative, whether it accelerates/
     steadies/decelerates, and the transition vocabulary.
   - **Cinematography** — shot types, framing, camera/lens feel, composition
     (synthesize the per-frame vision `reads`).
   - **Motion Graphics & Text** — overlay/title/lower-third/caption/data-viz style
     (use `graphics` density + the vision reads).
   - **Script ↔ Visual Pairing** — THE KEY SECTION. Using each extract's `pairing`
     (`distribution` of literal/associative/tonal, `mean_directness`,
     `directness_by_position`, and the paired `samples` of said-vs-shown): describe
     **how this creator couples words and images** — is the picture a literal
     illustration of the narration, or conceptual/metaphorical, tonal/atmospheric,
     or counterpoint? Does the literalness change across the arc (hook vs body)?
     Quote 2–3 real said↔shown sample pairs as evidence. Make explicit the rule a
     cloner should follow (e.g. "derive ~40% of visuals from the section's mood/
     concept, not the literal nouns").
   - **Composition & Layout** — framing tendencies, negative space, split-screen.
   - **Asset Sourcing** — original / stock / archival / screen-rec / illustration.
   - **Signature Motifs** — recurring transitions, brand colors/fonts, repeated shots.
   - **Do / Don't** — concrete rules for reproducing the look.
   - **How to Clone (notes)** — practical guidance for recreating this style.

Keep it specific and example-driven — generic advice is useless. Where a dimension
is missing for a video (e.g. `pairing.available == false` for an un-indexed clip),
say so rather than inventing it.
"""
