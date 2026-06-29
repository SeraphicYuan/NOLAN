# GSAP — leverage assessment (web-video workflow + NOLAN)

Researched gsap.com (Tools, Docs, Showcase) + mapped NOLAN's renderer. Verdict first.

## Can GSAP be deterministic under Remotion? YES (4/5, production-proven)
GSAP's timeline is a **pure function of its playhead**. The bridge: build a `paused`
timeline once, then `tl.seek(frame/fps)` every render; set `gsap.ticker.lagSmoothing(0)`,
`immediateRender:false` on stacked `from/fromTo`, and **ban** the non-deterministic bits
(InertiaPlugin, Physics2D, `RoughEase` default, `CustomWiggle({type:"random"})`,
`gsap.utils.random`). HyperFrames/HeyGen and public remotion-gsap demos do exactly this.
So "GSAP as a pure function of frame" is real — determinism is NOT the blocker.

## The value is concentrated (~80% redundant / ~20% new)
GSAP's famous ceiling (Awwwards sites) is mostly **scroll/pointer/interaction** —
ScrollTrigger, ScrollSmoother, Observer, Draggable, Inertia — which is **dead weight in a
pre-rendered mp4** (no scroll, no cursor). The part that transfers is SVG/type/easing craft,
and most of THAT we already built or trivially can:
- DrawSVG (line-draw) → already native via `@remotion/paths`.
- SplitText kinetic type, staggered reveals, ScrambleText, TextPlugin → trivial natively
  (we have KineticHeadline + the word-timestamp model; GSAP's edge is responsive line
  re-detection, which is moot at fixed resolution).
- Flip (layout-delta) → skip the plugin, keep the idea: in deterministic video we KNOW both
  layouts, so we interpolate directly; Flip's live DOM measurement buys little.
- Core eases / CustomEase → we have bezier + spring; CustomEase/Bounce/Wiggle is real but
  replicable polish.
- **MorphSVG (shape→shape morph, auto point-matching/rotation)** → the ONE genuine
  step-change. "X becomes Y" (icon→icon, shape→chart) is real explainer grammar with no
  native equivalent — and better than `flubber` (which we already installed, lower quality
  on mismatched point counts).

So the honest split: **GSAP is ~80% a nicer authoring layer over capabilities we already
have, and ~20% genuine new — and the new part is essentially MorphSVG.**

## 1) The improved web-video workflow → cherry-pick, don't adopt
Don't make GSAP a foundation. Reasons: (a) we already implemented the deterministic
frame-driven equivalents (visx charts, @remotion/paths draw, KineticHeadline, transitions,
our eases); (b) GSAP introduces a SECOND, *imperative* animation paradigm (build-once-seek
timelines) alongside our declarative "everything is a pure function of `useCurrentFrame()`"
blocks — a conceptual split that fights the simplicity that makes the library composable and
agent-authorable; (c) the determinism discipline adds footguns (random-baking eases,
immediateRender, rebuild-vs-seek). The only justified pull is **MorphSVG**, and even that is
partly covered by flubber. **Recommendation: keep flubber; pull GSAP MorphSVG only if/when a
signature shape-morph beat proves flubber insufficient** — a surgical, single-plugin add
(it's free now), not a platform bet.

## 2) NOLAN → mostly N/A; the lever is the Remotion backend, not GSAP
NOLAN is **dual-renderer**:
- **Primary = pure-Python (Pillow + MoviePy/ffmpeg).** No browser → **GSAP literally can't
  run there.** And it already has `effects.py` (~50 composable effects) + `easing.py` (full
  easing incl. spring + cubic-bezier). GSAP is irrelevant to NOLAN's main motion system; if
  that system needs more, the work is Python, in `effects.py`.
- **Secondary = the Remotion render-service** (`render-service/remotion-lib/*.tsx`, the
  sibling of our lab). Same situation as the web-video workflow: GSAP *could* live here
  frame-driven, but is ~80% redundant; the MorphSVG cherry-pick applies equally.
- **The strategic insight for NOLAN isn't "add GSAP" — it's "lean more on the Remotion
  backend and our boosted 22-block library."** That's where the determinism + theming +
  word-sync + chart tier already live. GSAP would be a detour.

## The one scenario where GSAP wins decisively
If we ever ship the **interactive, in-browser** presentation (the original
web-video-presentation skill's clickable-slides use case, NOT a rendered mp4), GSAP's
scroll/Flip/Draggable/Inertia ceiling becomes hugely relevant and largely irreplaceable.
GSAP is the right tool for *interactive web*, the wrong tool for *deterministic mp4*.

## Spike result — flubber vs MorphSVG (the one open question, now settled)
Ran a controlled side-by-side: the same **star → heart** morph (mismatched point counts +
concavity = the canonical morph stress test), same size/fill/ease, the morph algorithm the
only variable. GSAP MorphSVG driven deterministically (rebuild-per-frame + `seek`, no RNG).
Frames at prog 0.34 / 0.49 / 0.67 (`web-video-lab/gsap-spike/`):
**Visually equivalent.** flubber showed NO artifacts (no rotation flip, self-intersection,
or point teleporting) — its classic failure modes didn't appear on a dense-sampled
(`maxSegmentLength:3`) single-path morph. MorphSVG was *marginally* more refined near the end
(a hair more heart-like at the bottom point), but it's a tiny difference, not a quality gap.
**Conclusion: flubber (already installed, MIT, pure-function, zero determinism caveats) is
sufficient for our morph needs. MorphSVG's marginal edge does not justify adopting GSAP** (the
imperative build-once-seek paradigm, ticker management, plugin registration, random-baking-ease
footguns). GSAP + the MorphSpike composition were removed after the spike; flubber stays.
(MorphSVG would only pull ahead on harder cases — rotation control, `shapeIndex`, multi-shape
topology changes — which our explainer morphs don't need.)

## Bottom line
We independently arrived at GSAP's own architecture (seek = "compute, don't capture"). That's
validation, not a reason to adopt — we already have the thing GSAP would give us, minus one
plugin. **Verdict: do not adopt GSAP as a platform for either the web-video workflow or
NOLAN. Optionally pull the single free MorphSVG plugin if a shape-morph beat demands quality
beyond flubber. Revisit GSAP wholesale only if we build interactive browser presentations.**
