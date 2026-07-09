---
version: alpha
name: Highlighter Editorial — Frame (video / frame layer)
description: >
  Explanatory-journalism frame system (Vox-lineage; tokens grounded in the voxdotcom
  brand guide). Two registers — a warm PAPER field (mist/parchment, graphene ink) for
  argument and data, and full-bleed FOOTAGE (photo/film ground, white statement type,
  bottom scrim) for the concrete world. ONE accent: highlighter yellow, applied as a
  physical block/underline that SWEEPS onto the operative words as they are spoken.
  Bold gothic sans display (sentence case), italic serif as the annotating editorial
  voice, thick rounded chart strokes on parchment with dotted axes and fig. tags.
unit: the frame — 1920×1080 primary; 9:16 and 1:1 documented
principle: atoms are sacred · composition is free · numbers come from the script

colors:
  mist: "#F1F3F2"
  parchment: "#EFE9DC"
  graphene: "#4C4E4D"
  ink-deep: "#2B2D2C"
  highlighter: "#FFF200"
  slate: "#6D98A8"
  terracotta: "#C0603F"
  leaf: "#8BBD7A"
  amber: "#F2B13D"
  sky: "#4FB3E5"
  hairline: "#D8D5CC"
  footage-scrim: "rgba(20,21,20,0.55)"
  footage-text: "#F6F7F6"

typography:
  # — reading ramp (Inter = Alright Sans stand-in) —
  body:       { fontFamily: "Inter", cqw: 1.1,  weight: 400, lineHeight: 1.55 }
  label:      { fontFamily: "Inter", cqw: 0.8,  weight: 600, tracking: "0.12em", upper: true }
  caption-sm: { fontFamily: "Inter", cqw: 0.85, weight: 500, lineHeight: 1.45 }
  # — the annotating editorial voice (Lora italic = Harriet Display stand-in) —
  annotation: { fontFamily: "Lora", cqw: 1.35, weight: 500, italic: true, lineHeight: 1.4 }
  fig:        { fontFamily: "Lora", cqw: 1.0,  weight: 500, italic: true }
  # — display ramp (Libre Franklin = Balto stand-in; SENTENCE CASE, never lowercase-all) —
  h3:         { fontFamily: "Libre Franklin", cqw: 2.4, weight: 700, lineHeight: 1.18 }
  quote-text: { fontFamily: "Libre Franklin", cqw: 3.4, weight: 800, lineHeight: 1.22 }
  h2:         { fontFamily: "Libre Franklin", cqw: 4.2, weight: 800, lineHeight: 1.12 }
  h1:         { fontFamily: "Libre Franklin", cqw: 5.4, weight: 900, lineHeight: 1.06, tracking: "-0.015em" }
  stat-value: { fontFamily: "Libre Franklin", cqw: 6.2, weight: 900, lineHeight: 1.0,  tracking: "-0.02em" }
  display:    { fontFamily: "Libre Franklin", cqw: 7.2, weight: 900, lineHeight: 1.04, tracking: "-0.02em" }

spacing:
  pad-x: "6cqw"
  pad-y: "6cqw"
  gap-lg: "3cqw"
  gap-md: "1.8cqw"
  gap-sm: "0.9cqw"

components:
  registers:
    paper: "ground {colors.mist} (or {colors.parchment} for charts), text {colors.ink-deep}/{colors.graphene}, accent {colors.highlighter}"
    footage: "ground = full-bleed photo/film + {colors.footage-scrim} bottom gradient, text {colors.footage-text}, accent {colors.highlighter}"
    description: "Two registers only. PAPER argues and measures; FOOTAGE shows the world. One register per frame-scene."
  highlight:
    geometry: "a solid {colors.highlighter} block behind the operative word(s): padding 0.06em 0.18em, 0 radius, no shadow"
    motion: "scaleX 0→1 from the left (transform-origin left), landing ON the spoken word; ink on yellow is ALWAYS {colors.ink-deep} (both registers)"
    description: "THE signature. At most one clause per statement; never a whole sentence."
  underline:
    geometry: "a {colors.highlighter} bar 0.14em tall under a numeral/word, full word width, 0 radius"
    motion: "scaleX 0→1 left→right on cue"
    description: "The quieter sibling of highlight — for stat numerals."
  caption-bar:
    surface: "a {colors.mist} strip, ink {colors.ink-deep}, {typography.label} + {typography.caption-sm}; sharp corners"
    placement: "lower-left over FOOTAGE, above the karaoke band"
    description: "The source/attribution voice over footage (the white evidence bar)."
  fig-tag:
    typography: "{typography.fig} in {colors.graphene}, e.g. “fig. 01”"
    placement: "top-right of a chart panel"
  chart:
    surface: "{colors.parchment} panel edge-to-edge or inset; DOTTED 1px axes in {colors.graphene} at 45% opacity; no box, no gridlines beyond dots"
    strokes: "series lines/bars 0.4–0.5cqw thick, ROUND caps, colors from {colors.terracotta}/{colors.leaf}/{colors.amber}/{colors.sky}/{colors.slate}; one series may carry a filled dot marker at its 'now' point"
    labels: "{typography.label} axis, {typography.annotation} for the editorial aside on the chart"
  photo-card:
    surface: "white-bordered photo (0.5cqw border #FFFFFF-equivalent {colors.mist}), subtle 1px {colors.hairline} edge, caption in {typography.annotation} beneath"
    description: "The desk-evidence unit for collage frames."
  scrim:
    geometry: "linear-gradient(transparent 38%, {colors.footage-scrim} 78%, rgba(20,21,20,0.72)) over FOOTAGE"
    description: "Guarantees statement + caption legibility on footage; never a full-frame dim below 35% image visibility."
---

# Highlighter Editorial — Frame (video / frame layer)

## Overview

Explanatory journalism at frame scale: **the argument is typeset on paper, the world is
shown as footage, and one yellow highlighter ties them together.** The system speaks in
sentence-case gothic bold (never shouting caps, never lowercase-poster), annotates itself
in an italic serif voice, and measures things with thick, friendly chart strokes on warm
parchment. The single most recognizable move: a **highlighter-yellow block sweeping onto
the operative words at the moment they are spoken**.

**Key characteristics at frame scale:**

- **Two registers** — PAPER (mist/parchment ground, graphene/ink-deep text) and FOOTAGE
  (full-bleed image, white text over a bottom scrim). One per frame-scene.
- **Highlighter yellow is the only accent** — as a swept block or underline; it never
  colors text directly and never appears as a large field.
- **Sentence case display** (Libre Franklin 800–900). The italic serif (Lora) is the
  editorial aside: annotations, fig. tags, attributions, captions.
- **Charts are warm and physical** — parchment, dotted axes, thick round-capped strokes,
  a dot marker, an italic fig. tag. Never a cold grid.
- **Evidence is cited on screen** — footage carries a caption-bar; charts carry fig. tags.
- **Soft depth allowed but scarce** — a photo-card may cast a 0–2px hairline edge; no
  drop shadows on type, no gradients except the footage scrim.

## The Frame

### Frame Craft Bar

- **Squint** — one statement OR one number OR one chart dominates; the yellow highlight
  is the brightest thing on screen and appears exactly once.
- **Silence** — PAPER frames read 40–55% empty; FOOTAGE frames keep the upper 40% mostly
  image (the world gets room to breathe).
- **Restraint** — one register per scene; yellow touches at most one clause or one
  numeral per scene; at most 3 stat lockups; chart series ≤ 4.
- **Reference** — aim at explanatory-journalism video (a Vox-school explainer: paper,
  highlighter, annotated charts, footage with a white evidence bar). Failure looks like
  a corporate slide deck or a meme caption.

- **Primary:** 1920×1080 (16:9). Type in **`cqw`** (px ÷ 1920 × 100).
- **Safe area:** `pad-x`/`pad-y` 6cqw; statements sit lower-left on FOOTAGE, upper-left
  on PAPER.

**The container law (load-bearing).** Every frame ground sets `container-type: size`;
ALL frame-relative units are `cqw`/`cqh` — never `vw`. Hairlines stay 1px.

## Colors

PAPER: `{colors.mist}` ground (charts may sit on `{colors.parchment}`), `{colors.ink-deep}`
display, `{colors.graphene}` secondary text, `{colors.hairline}` rules. FOOTAGE: the image
is the ground; `{colors.footage-text}` type over `{colors.footage-scrim}`. In BOTH
registers the accent is `{colors.highlighter}` and ink-on-yellow is always
`{colors.ink-deep}`. Chart series draw from terracotta/leaf/amber/sky/slate only.
**No second accent. Yellow is never a text color, never a full-field.**

## Typography

Three voices. **Libre Franklin** (display, 700–900, sentence case, tight but not
crushed) carries statements and numerals. **Lora italic** (the editorial voice) carries
annotations, fig. tags, attributions, photo captions — it is never a headline.
**Inter** carries labels (uppercase, tracked 0.12em) and small captions.

- **Legibility floor:** any load-bearing line ≥ 1.4cqw; labels are chrome only.
- **Fit-to-measure:** cap a statement block at ≤ 74cqw and 3 lines; 1–3 words → `display`;
  a full clause → `h1`/`h2`. One display moment per scene.
- Sentence case for display — never ALL CAPS (labels only), never all-lowercase.

## Depth & Surface

Flat paper with two sanctioned exceptions: the footage scrim (a gradient, FOOTAGE only)
and the photo-card's 1px hairline edge. **No drop shadow on type, no rounded corners
(0 radius everywhere), no gradient grounds on PAPER.** Hierarchy = size, weight, the
yellow accent, and dotted hairlines.

## Shapes

0 radius. Highlight blocks, underlines, caption-bars, photo-cards, chart panels — all
sharp rectangles. Chart strokes are the only rounded thing (round line caps).

## Components

- **registers** — PAPER argues/measures; FOOTAGE shows. **highlight / underline** — the
  yellow signature (block for words, bar for numerals). **caption-bar** — the evidence
  voice over footage. **fig-tag** — italic chart numbering. **chart** — parchment +
  dotted axes + thick round strokes + dot marker. **photo-card** — bordered evidence
  stills. **scrim** — footage legibility gradient.

## Frame Treatments

> Recipe: ground · register · composes · focal · accent · silence · Fixed/Free · density.
> One statement per scene; the yellow appears exactly once per scene.

### 1 · Cold Open (identity · move: statement over the world · FOOTAGE · lower-left)

**Ground** full-bleed photo/film + scrim. **Composes** scrim, statement (h1/display,
2–3 lines, footage-text), highlight, optional caption-bar. **Focal** the statement; its
operative clause takes the yellow highlight block ON its spoken cue (ink-deep on yellow).
**Silence** upper 40% is image. **Fixed** white sentence-case bold lower-left, one yellow
clause. **Free** the image, the statement. **Density** low.

### 2 · Highlight Statement (declarative · move: the sweep · PAPER · upper-left)

**Ground** mist. **Composes** label kicker, statement (h1/h2, ink-deep), highlight,
annotation. **Focal** the statement; yellow block sweeps onto the operative words on cue.
A Lora-italic aside may answer it below. **Silence** ~50%. **Fixed** sentence case,
ink-on-yellow, one sweep. **Free** the words, which clause is yellow. **Density** low.

### 3 · Chart (data · move: the drawing line · PAPER/parchment)

**Ground** parchment. **Composes** h3 headline, chart (dotted axes, 1–4 thick round
strokes drawing left→right, dot marker landing on the 'now' value), fig-tag, label axis,
annotation aside. **Focal** the accented series (terracotta first). **Accent** a yellow
underline under the chart's ONE takeaway numeral. **Silence** moderate. **Fixed** dotted
axes, round caps, fig. tag, series palette. **Free** the data (from script), the aside.
**Density** the dense exception.

### 4 · Stat Lockup (data · move: count-up + underline · PAPER)

**Ground** mist. **Composes** label kicker, 1–3 stat lockups (stat-value numeral
counting up + Inter label), underline. **Focal** the lead numeral; its yellow underline
sweeps when the count lands. Lockups reveal on their spoken cues, left→right or stacked.
**Silence** ~45%. **Fixed** Franklin-900 tabular numerals, ink-deep, one yellow underline.
**Free** figures (from script), labels. **Density** moderate.

### 5 · Quote / Human (quote · move: spoken words made physical · FOOTAGE)

**Ground** full-bleed photo + scrim. **Composes** quote-text (footage-text, sentence
case, quotation marks), highlight on the emotional core, Lora-italic attribution,
optional supporting stat in a caption-bar. **Focal** the quote. **Silence** the image
holds the mood; motion is quiet. **Fixed** white quote, one yellow clause, italic
attribution. **Free** quote, image. **Density** low.

### 6 · Evidence Collage (argument · move: desk evidence · PAPER)

**Ground** mist. **Composes** 1–3 photo-cards (bordered stills w/ italic captions),
h3 claim, a yellow underline or circled annotation on ONE card. **Focal** the annotated
card. **Silence** moderate. **Fixed** white borders, italic captions, one yellow mark.
**Free** the stills, the claim. **Density** moderate.

## Composition Rules

### Do

- Sweep the yellow **on the spoken cue** — the highlight IS the word-sync.
- Keep display **sentence case**; let the italic serif do the annotating.
- Give FOOTAGE frames a real scrim and put statements lower-left.
- Draw charts (strokes animate left→right); land a dot marker on the takeaway.
- Cite on screen: caption-bar on footage, fig. tag on charts.
- Count numerals up; underline the one that matters.

### Don't

- Never color text yellow; never fill a field yellow; never two yellow marks in a scene.
- No ALL-CAPS display, no lowercase-poster display, no mono chrome voice.
- No drop shadows on type, no rounded corners, no gradient paper.
- Don't put a statement over footage without the scrim; don't dim an image below ~35%.
- Don't exceed 4 chart series or 3 stat lockups; don't front-load a scene's reveals.

## Aspect-Ratio Behavior

| Treatment      | 16:9                      | 9:16                        | 1:1              |
| -------------- | ------------------------- | --------------------------- | ---------------- |
| Cold Open      | statement lower-left      | statement lower third       | lower-left       |
| Highlight Stmt | statement upper-left      | statement upper third       | centered-left    |
| Chart          | chart right, head left    | head top, chart below       | head top         |
| Stat Lockup    | 1–3 across                | stacked                     | 2+1              |
| Quote          | quote left over image     | quote lower third           | centered         |
| Collage        | cards fanned right        | cards stacked               | 2-up             |

`pad-x` holds; re-step display so the longest line stays ≤ 74cqw and above the 1.4cqw floor.

## Approved Entities

No logos or wordmarks are part of the system (the lineage brand's marks are explicitly
excluded). Named works/people appear as photo-cards or caption-bars with attribution text.

## Numerals & Claims (hard rule)

Never invent figures, dates, or counts. Render slots as `— figure —` / `NN%` until the
script supplies them. fig. numbers (fig. 01) are decorative chrome and may be sequential.

## Pre-Render Self-Audit

- **Squint** — one dominant statement/number/chart; the yellow reads as the brightest mark, once.
- **Register** — PAPER or FOOTAGE per scene, never mixed grounds; ink-on-yellow is ink-deep.
- **Type** — sentence-case Franklin display; Lora italic only annotates; labels only chrome.
- **Charts** — parchment, dotted axes, round caps, fig. tag; series from the five approved hues.
- **Footage** — scrim present; statement lower-left; image ≥ 35% visible.
- **Fabrication** — every numeral traces to the script.

## Known Gaps

- **Motion intentionally out of scope** here; the sweep/draw/count choreography lives in
  the storyboard's Video direction + cited motion rules.
- **Fonts are stand-ins** (Libre Franklin/Lora/Inter via Google Fonts) for the lineage
  faces (Balto/Harriet Display/Alright Sans), which are commercial.
- 9:16 / 1:1 are guidance; verify the fit-to-measure rules per ratio.
