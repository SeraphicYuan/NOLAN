---
id: common.composition-craft
name: Composition craft
kind: craft
purpose: The composition umbrella — the named layout archetypes (centered-hero, split-screen, swiss-grid…), when to use each, and how a theme + beat resolve one. The A/B/C/D-proven lever that moves an LLM off its left-column default.
status: active
version: 1
handoffs: []
uses: []
evals: []
---

# Composition craft — the layout archetype umbrella

A scene's **composition archetype** is its macro layout — where the content sits on the frame. It is an axis of its own (palette ⟂ type ⟂ **composition** ⟂ motion ⟂ decoration): declare it, don't let it be inferred from a theme's name. Selection is **content-first** — the beat/scene-type suggests the archetype, the theme's `allowed` set constrains it, an explicit human direction overrides it. Registry: `themes/composition/archetypes.json` (the ONE source both the block composer and the bespoke agent read). Design: `docs/COMPOSITION_ARCHITECTURE.md`.

All archetypes place against a shared grid: **12 columns**, rule-of-thirds bands ['upper-third', 'middle-third', 'lower-third'], primary weight near ~45% height (slightly above geometric centre). Safe areas: content stays in the TOP 83% (bottom ~17% reserved for captions); keep primary content inside a ~5% inset from every edge. Anchors are grid guidance, **not pixels**.

## centered-hero

One dominant idea, dead-centre, using the full canvas.

- **When**: the beat has ONE thing to say — a single statement, a big number, a big question, a thesis, a reveal.
- **Not for**: lists, comparisons, or dense multi-part data.
- **Serves beats**: thesis, big-number, big-question, statement, reveal
- **Layout**: primary element at optical centre; a short eyebrow on the upper third, optional support on the lower third. Symmetric about the vertical axis.
- **Balance / density**: symmetric · generous
- **Blocks**: stat

## editorial-column

Text set as a reading column against a margin axis, ragged right — the Vox/editorial voice.

- **When**: narration-led running claims, a quote with attribution, a labelled statement — text carries the beat.
- **Not for**: a single hero word (use centered-hero) or media-forward beats.
- **Serves beats**: claim, statement, quote, narration, definition
- **Layout**: column occupies the left ~55% (columns 1-7) with a rule/margin at its edge; content top-aligned to the upper third and flowing down.
- **Balance / density**: asymmetric · normal
- **Blocks**: statement, lower_third

## swiss-grid

A modular grid — several items placed on columns and rows with consistent gutters.

- **When**: an enumeration, a multi-item structure, a small matrix, several stats or images together.
- **Not for**: a single idea (use centered-hero) or a two-way comparison (use split-screen).
- **Serves beats**: list, enumeration, gallery, multi-stat, matrix, index
- **Layout**: items laid on the 12-column grid with even gutters and a shared baseline; a strong top rule or header row.
- **Balance / density**: symmetric · tight
- **Blocks**: gallery, collage, carousel, timeline, diagram

## split-screen

Two zones side by side, in dialogue.

- **When**: a comparison, before/after, this-vs-that, a two-sided argument.
- **Not for**: a single idea, or more than two items (use swiss-grid).
- **Serves beats**: comparison, versus, before-after, dialogue, tension
- **Layout**: left half (cols 1-6) + right half (cols 7-12) with a seam at centre; each half's content centred within its zone; an optional 'vs' hinge on the seam.
- **Balance / density**: symmetric · normal
- **Blocks**: comparison

## full-bleed-overlay

Media or atmosphere fills the frame edge-to-edge; text is overlaid on a legible zone.

- **When**: a photo/video/map/gradient IS the hero; an establishing or atmospheric beat.
- **Not for**: type-only beats (nothing to fill the bleed).
- **Serves beats**: media, establishing, atmosphere, map, b-roll, cold-open
- **Layout**: media on track 0 edge-to-edge; a scrim (track 1) for contrast; text confined to a safe zone (lower third, or a corner panel) — never floating over busy media.
- **Balance / density**: asymmetric · normal
- **Blocks**: geo, media_ground

## focal-card

One object or subject anchors the stage; supporting text orbits it.

- **When**: a background-removed subject, a hero object, a news card, a document, a portrait.
- **Not for**: beats with no single focal object.
- **Serves beats**: subject, object-as-evidence, news-card, portrait, document
- **Layout**: focal element centred (or offset to a thirds line); label/kicker flanking it or on the lower third; the focal object owns the middle band.
- **Balance / density**: symmetric or asymmetric (centred vs offset) · normal
- **Blocks**: newshead, spotlight, document, social_card, prop_cutout

## sidebar

A narrow fixed rail beside a wide flexible content zone.

- **When**: an index/number/label/step marker beside the main content; a running marker + body.
- **Not for**: 50/50 comparisons (use split-screen).
- **Serves beats**: indexed, labelled, step, annotated, chapter
- **Layout**: a narrow rail (~cols 1-3: a number, label, or index) + a wide content zone (cols 4-12) filling the rest; the rail is a persistent marker, the body carries the beat.
- **Balance / density**: asymmetric · normal
- **Blocks**: (bespoke-only for now)

## framed

A self-contained artefact presented cleanly within a margin frame.

- **When**: a chart, a code block, a pull-quote, a diagram — an object to present, not narrate.
- **Not for**: full-bleed media or running narration.
- **Serves beats**: chart, code, quote, diagram, artefact, spec
- **Layout**: artefact centred within a generous margin (frame inset ~10-14%); a caption or source on the lower third; the frame itself may carry the theme's rule/decoration.
- **Balance / density**: symmetric · generous
- **Blocks**: chart, code, diagram, document

## Growing this umbrella

Add an archetype ONLY when a real beat can't be expressed by the existing set (keep it small + orthogonal). A new archetype needs: a registry entry (intent/when_to_use/serves_beats/anchor/blocks), a `## <id>` heading here, and — ideally — a promoted exemplar. `validate_themes.py` enforces theme↔registry parity; `tests/test_composition.py` + `tests/test_umbrella_skills.py` enforce the rest.
