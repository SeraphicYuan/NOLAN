---
id: common.motion-craft
name: Motion craft
kind: craft
purpose: The motion umbrella — every registered effect with when-to-use guidance; how specs are authored, validated and promoted.
status: active
version: 1
handoffs: []
uses: []
evals: []
---

# Motion craft — the camera & effects umbrella

The registry of record is `src/nolan/motion/registry.py` (`REGISTRY`) — this
document is honesty-tested against it (built-in ids; promoted effects are
data in `registry_custom.json` and appear in `nolan capabilities --json`
/ `/api/map`, not here). Authoring path: natural-language scene design ->
LLM-compiled spec -> validated against the registry -> executed on the
right backend. To ADD an effect, use the Clips promotion pipeline
(proposal -> gate -> accept) — never edit the registry or Root.tsx by hand.

Picking rules of thumb: match the effect to what the narration is DOING
(comparing -> bar-compare; landing one number -> counter/annotate-stat/
stat-over by weight; walking geography -> route-map). One data moment per
beat; stills held >3s get still-motion by default; cards are punctuation.

## kinetic-text

**What:** Reveal a short headline word-by-word, accenting key words.

**When:** Hook lines and thesis statements — a spoken headline the viewer should read as they hear it. Not for body prose (>8 words reads as a wall of text).

## bar-compare

**What:** Animated bar comparison with count-up labels.

**When:** 2-4 quantities the narration explicitly compares ('X vs Y'). If the story is one series over time, use line-chart instead.

## k-shape

**What:** Two diverging lines (rising vs falling) from a shared origin — the K split.

**When:** Divergence narratives — winners/losers, rich/poor splitting from a shared origin. The shape IS the argument; don't use for mere difference.

## annotate-video

**What:** Draw-on circle + arrow + label pointing at a spot on b-roll.

**When:** Direct the eye to ONE spot in busy b-roll the narration points at ('this building here'). Needs a stable shot behind it.

## annotate-stat

**What:** Emphasize one number/stat with a drawn circle + caption.

**When:** One number the narration lands on hard and needs EMPHASIS. For scale-over-imagery (number + tangible referent) use stat-over.

## route-map

**What:** Animated pins + routes over a basemap (money/flow/geo).

**When:** Movement across geography — journeys, trade, money flows. Use when the narration names places in order; pins without narrative order confuse.

## premium-card

**What:** Glass/gradient hero or chapter title card.

**When:** Chapter openers and the cold-open title. At most one per section — cards are punctuation, not content.

## counter

**What:** Animated count-up number with a caption (a stat reveal).

**When:** A single inline stat reveal — the cheapest data moment. Escalate to bar-compare (context) or stat-over (scale) when the number needs more.

## title

**What:** Animated title card (title + subtitle + accent line).

**When:** A section title inside the flow when a full premium-card is too heavy.

## lower-third

**What:** Lower-third name/title caption.

**When:** Introducing a person/source on screen (name + role) without leaving the shot.

## comparison

**What:** Two-sided VS comparison.

**When:** A binary either/or the narration frames as a duel. For an IMAGERY collision use split-screen; for numbers use bar-compare.

## line-chart

**What:** Animated single-series line chart (rise/crash/rally).

**When:** One series over time — rise, crash, rally. Best when the narration traces the shape as it draws.

## loop-diagram

**What:** Animated feedback-loop: labelled nodes in a cycle with arrows.

**When:** Feedback loops and cycles (A feeds B feeds C feeds A) that the narration walks around once.

## photo-montage-pro

**What:** 'Photos on a table' montage with a per-card motion system (Remotion): each card declares where it rests and how it arrives (from-edge + timing + easing) independently. Polaroid/plain/cutout frames, handwritten captions, Ken Burns camera. Use for flexible b-roll/asset presentation.

**When:** 3-6 related stills that belong on one 'table' — an evidence cluster. Use when order/position of cards carries meaning; for a lone still use still-motion.

## photo-grid

**What:** Procedural photo grid with a 3-step choreography (Remotion): images fly in to fill a cols×rows grid (sequenced one-by-one / by row / by col), then one image zooms to center while the grid peters out, then it returns to the grid. Computed from grid shape + timings — scales to dozens of images.

**When:** MANY images (8+) as a wall — abundance of examples, then one zooms out as the specimen. Under 8 images the grid reads sparse.

## still-motion

**What:** Turn ONE still into a moving shot: motivated Ken Burns (push/pull/pan, origin on the salient subject), 2.5D parallax (rembg cutout over a blurred bg), rack-focus, blur-in, or an atmospheric overlay. The parallax/rack-focus cutout is derived automatically.

**When:** The default life-giver for any single still held >3s. Treatment by mood: ken-burns for narrative pushes, parallax for depth drama, rack-focus for a revelation, atmospheric for tone holds.

## split-screen

**What:** The relational/dialectical collision: two stills side by side (left|right) with opposing slow pushes, a divider, and optional labels — shot A + shot B make a third meaning.

**When:** The dialectical operator: two images whose collision makes a third meaning (then/now, cause/effect). Both halves must read at half width.

## stat-over

**What:** SCALE payoff: a big count-up NUMBER over a tangible-referent shot (stadium crowd / city aerial / grains of sand) + a caption. Number and caption are styled from the video THEME.

**When:** The SCALE payoff: a number counted up over a tangible referent (crowd, aerial, grains). Use when the audience should FEEL the magnitude, not just read it.

## clip-montage

**What:** Assemble b-roll clips/stills into one video with shot-to-shot transitions (dissolve/slide/wipe/clockWipe/cut) via @remotion/transitions.

**When:** Sequencing 3+ short clips/stills into one continuous b-roll bed — time compression, 'meanwhile' energy. Uniform transitions only; for authored per-shot cuts use scene.shots.
