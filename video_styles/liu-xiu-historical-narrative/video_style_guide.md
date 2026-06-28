# Video Style Guide — Liu Xiu / Historical Narrative

*Synthesized from 1 reference video («劉秀」中國歷史上最漫長的一次忍耐, 9:33, 25 indexed
segments). Numbers are the computed backbone; cinematography is the vision read.
Single-video corpus — treat as provisional until more references are added.*

## Overview
A **slow, cinematic historical-narrative explainer**: painterly animated
illustrations of ancient China, grave English voiceover storytelling, and a sombre
sepia palette. The mood is contemplative and literary — long held scenes, dramatic
lighting, on-screen calligraphy of key lines. Built to make a history lesson feel
like an epic.

## Format & Specs
- **640×360, 16:9 landscape, 30 fps**, ~9.5 min. Standard horizontal long-form.

## Color & Lighting
- **Warm sepia** (`warm_ratio 0.87`), **muted** (`saturation 0.35`) and **low-contrast/
  flat** (`contrast 0.14`) — an aged, parchment mood.
- Palette: near-black → deep browns → muted terracotta → warm tan
  (`#0b0b0d #251d1d #483534 #874e44 #ca946a`).
- Vision reads: **low-key chiaroscuro**, dramatic **directional side/upward key light**,
  deep atmospheric shadows. High drama from light, not color.

## Editing & Pacing
- **Slow but not glacial** — *video-measured* **66 real cuts, ~7 cuts/min**, median
  shot **~5.6 s** (mean 8.6 s). (The index's 25 segments implied 2.6/min, 23 s shots —
  a ~2.6× undercount; true cuts are the right read.)
- **Rhythm shape**: opens brisk (~11/min), calms through the middle (3–5/min), and
  **lifts again toward the close** (~11/min) — a gentle build, not a flat tempo.
- `intra_shot_motion 0.02`, `energy 0.23` — low-energy: gentle pushes/parallax over
  stills, never frenetic.

## Cinematography
- **Medium / medium-close / medium-wide** shots; frequent **over-the-shoulder** framing.
- **Rule-of-thirds** composition with deliberate **negative space**; subject offset.
- **Shallow depth of field** (blurred backgrounds) for an intimate, layered feel.
- Eye-level, moderate angles; painterly illustrated (not photographic) frames.

## Motion Graphics & Text
- `lower_third_activity 0.86` + vision reads → **on-screen typography is a signature**:
  **bold gold calligraphy** of key narration lines, set in **ornate geometric borders**.
- Edge density is low (`0.058`) — clean, uncluttered frames; text is the main graphic.

## Script ↔ Visual Pairing  *(the defining trait)*
- **Mostly-associative**, lightly literal: `literal 0.33 / associative 0.63 / tonal 0.04`,
  `mean directness 0.70`, roughly flat across the arc (open 0.72 → mid 0.68 → close 0.70).
- The picture **illustrates the theme/figures of the moment without being a literal
  prop-for-noun match** — e.g. narration about the two brothers' fates → a **split-screen
  contrasting their portraits**; "the beginning of his life" → **a figure studying a war
  map**; the opening line about pain → **a melancholic nobleman portrait**. Concept-level,
  not object-level.
- **Confound to note:** the visuals frequently **render the narration line itself as
  on-screen gold calligraphy**, which inflates the said↔shown similarity. So part of the
  "directness" is literally *the words shown as text*, not the imagery depicting them —
  the imagery underneath is more associative than the score implies. Treat on-screen-text
  as its own motif, separate from the image↔script relationship.
- **Clone rule:** derive visuals from the **emotional/thematic beat** (a portrait, a
  contrast, a symbolic object), not the literal nouns of the sentence; and **burn the key
  line into the frame** as ornate calligraphy.

## Composition & Layout
- Off-center subjects, generous negative space, shallow-DOF separation; calligraphy
  occupying a balanced third.

## Asset Sourcing
- **Original painterly animation/illustration** (ancient-Chinese art style) — not stock
  or archival.

## Signature Motifs
- Sepia chiaroscuro; gold calligraphy of narration in ornate borders; split-screen
  character contrasts; long held painterly scenes; war-map / portrait iconography.

## Do / Don't
- **Do**: hold scenes long; light for drama (low-key, directional); keep the palette
  warm-muted; pair images to *concept/mood*; show key lines as ornate calligraphy.
- **Don't**: fast-cut; use saturated/high-contrast color; literally prop-match every
  noun; clutter frames with busy graphics.

## How to Clone (notes)
Aim for: 16:9, sepia low-key palette (`#251d1d`→`#ca946a`), ~20–25 s held painterly
scenes, rule-of-thirds medium shots with shallow DOF, narration-as-gold-calligraphy
overlays, and concept-level B-roll (portraits, split-screens, symbolic objects) rather
than literal illustrations. Pair with the matching grave/literary script voice.
