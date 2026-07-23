---
id: common.effects-craft
name: Effects craft
kind: craft
purpose: The effects umbrella — visual TREATMENTS (grades, grain, film damage, physical-element overlays) with when-to-use guidance; authored as a stackable ground.treatments list, validated + executed from the ONE registry.
status: active
version: 1
documents:
  module: src/nolan/effects/registry.py
handoffs: []
uses: []
evals: []
---

# Effects craft — the visual-treatments umbrella

The registry of record is `src/nolan/effects/registry.py` (`REGISTRY`) — this document is
honesty-tested against it (`tests/test_umbrella_skills.py`): every effect id below is a `##`
heading, and nothing here is unregistered.

Effects are **visual treatments** applied to any media asset: color grades, grain, film damage,
and physical-element overlays (fire/rain/smoke…). They are AUTHORED as a **stackable
`treatments: [...]` list** on a scene `ground` (and later per-block media), VALIDATED by
`validate_treatments`, and EXECUTED at render time (HyperFrames CSS filter + blended overlay
layers — `nolan.effects.render`) or BAKED to a new file (ffmpeg). Backend-agnostic: the same
`fire`/`vintage` vocabulary drives the HF compose executor now and a Remotion executor later
(exactly like `[[common.motion-craft]]`'s registry spans backends). Supersedes the bare
`compose.GRADES` map (kept in parity by `tests/test_ground_effect.py`).

Two orthogonal axes on every effect: **family** (color · grain · stylize · damage · element) and
**method** (the render-time mechanism — css_filter, an SVG/CSS overlay, or a baked ffmpeg pass).
Some element/damage effects are **bake-only** (can't be a live CSS filter). Stack subtractively —
one grade + at most one texture + at most one element reads as intentional; more reads as a mess.

### color

## warm
Nostalgia, hearth, human warmth; a cold stock photo that should feel lived-in.
## cool
Detachment, technology, night, unease; warm footage that clashes with a somber beat.
## darken
Push an over-bright asset back so overlaid text reads; night/foreboding register.
## brighten
Rescue an underexposed asset; airy/optimistic register.
## contrast
A flat, hazy image that needs snap; bold/graphic register.
## desaturate
Archival/serious tone without full B&W; unify a clashing palette.
## mute
Take the edge off a garish stock image so it recedes behind text.
## noir
Historical, funereal, or stark-editorial register; strip colour entirely.
## sepia
Old-photo / archival-document look; pairs into the `old-film` preset.
## faded
Faded-memory / bleached-film register; softens a harsh modern photo.
## vivid
Energetic/upbeat register; make a dull product shot vibrant.
## film-lut
A specific film emulation / colour science (Kodak, teal-orange) beyond css_filter grades. Bake-only.

### grain

## film-grain
Kill the digital-clean 'AI look'; give a flat gen image analogue texture. Subtle by default.
## heavy-grain
Degraded / lo-fi / found-footage register; pairs into `old-film` and `super8`.

### stylize

## scanlines
Retro-tech, surveillance-monitor, or VHS register; pairs into the `vhs` preset.

### damage

## dust-scratches
Aged-celluloid / decaying-archive register; the core of the `old-film` preset.
## old-movie
Vintage / archival / nostalgic register — make modern footage read as projected film (MULTIPLY).
## old-film
Retro / analogue-decay register — grittier and more coloured than the clean `dust-scratches`.
## projector
Cinema / archival-projection register — warmer and sparser than `old-film`.
## film-roll-h
Frame the shot as a strip of running film (letterbox-ish); pairs with sepia/old-movie.
## film-roll-v
Frame the shot as a vertical filmstrip; portrait/scroll register.

### element

## particles
Atmosphere + depth — floating dust in a light beam; softer and cooler than `embers`.
## particles-center
A soft particle burst anchored centre-frame (vs `particles` drifting from a corner).
## fire
Destruction, war, passion, collapse; literal fire behind a subject shot on black.
## embers
Aftermath, smouldering tension; subtler than `fire`.
## rain
Melancholy, hardship, film-noir mood over a street or portrait.
## snow
Winter, isolation, quiet; a cold beat over a landscape.
## smoke
Mystery, war, industry; add atmosphere and depth to a flat plate.
## light-smoke
Subtle atmosphere — a gentle mood wash under a scene; lighter/wispier than `smoke`.
## fog
Dread, dreaminess, the unknown; soften and recede a background.
## light-leak
Warm organic imperfection between beats; a nostalgic film-camera register.
## film-burn
A punchier warm-orange burst than `light-leak` — great as a beat / scene transition.
## bokeh
Dreamy / romantic / premium register — warm out-of-focus lights; pairs under a title.
