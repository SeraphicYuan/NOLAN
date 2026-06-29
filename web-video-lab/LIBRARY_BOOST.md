# Library boost — research roadmap (web sweep, 4 streams)

How to grow the web-video library (blocks, primitives, themes, transitions, charts,
figure-annotation) by leveraging existing libraries/frameworks/patterns. Synthesized
from a 4-stream web search: motion/animation, React data-viz, design systems, and
data-storytelling/explainer ecosystems.

## The one rule that governs every adoption
**Adopt libraries as geometry / math / asset *generators*, never as animation
*runtimes*.** Anything that animates on wall-clock time — react-spring, Framer Motion's
`<motion.*>` runtime, GSAP's ticker, CSS `transition`/`@keyframes`, canvas RAF,
expression-driven Lottie, `Date.now()`, unseeded `Math.random()` — is invisible to
Remotion's frame-seeking and breaks headless determinism. The right layer is anything
that, given a **frame or a 0→1 progress, returns a static SVG**. We already own the
cursor (`useCurrentFrame()` + word timestamps), so we keep owning every reveal. Every
"interactive" storytelling tool (Scrollama scroll, Gapminder play, OWID timeline) is
just a `cursor→state` machine — we adopt the animated version and drop the interactivity,
which is strictly simpler and deterministic.

## Guardrails — do NOT adopt as runtimes
Framer Motion runtime (helpers/math only), react-spring/Popmotion (use Remotion
`spring()`), FLIP via runtime DOM measurement, naive GSAP/anime.js without paused
`seek(frame/fps)`, expression/random Lottie, Chart.js (canvas, no crisp clip-reveal),
`@visx/xychart` (bundles react-spring — use the low-level visx primitives), dotLottie
runtime theming (unzip to inner `.json` + lottie-colorify instead), Leader-Line lib
(DOM/timer — hand-roll the SVG `<path>`).

---

## Wave 1 — adopt first (high value, low cost, deterministic)

### Theme tokens (the foundation — everything else compounds on it)
- **Named motion tokens** (from Material 3): duration tiers `--dur-short/medium/long`
  + easing sets `--ease-standard/-emphasized-decel/-accel`, with the **enter=decelerate
  / exit=accelerate** asymmetry. Gives each theme a motion personality; our timestamp
  engine clamps duration to the word-gap but keeps the easing fixed. *Pure token add.*
- **12-step color ramp + semantic step roles** (Radix/M3): a reference ramp (accent 1–12,
  neutral 1–12) with steps having fixed jobs (bg / subtle-fill / border / solid / text);
  `--accent`/`--surface` become aliases into it. Fixes "where do hover/border/subtle-fill
  colours come from" deterministically across all 23 themes. *Script ramps from one hue.*
- **Elevation / shadow scale** `--elev-0..5` (layered shadows — lift Open Props' values)
  + optional `--surface-tint`. We currently layer by colour only; real shadow tiers are a
  big, cheap polish lift on every card block (PaperFigure, DataTable, StatCount).
- **Composite type tokens**: each `--t-*` step carries size + line-height + letter-spacing,
  generated from one `--scale-ratio` (1.2 dense ↔ 1.333 editorial). Biggest "designed vs
  generated" lever for text blocks.

### Figure-annotation (upgrades PaperFigure — our signature)
- **Frame-driven `clip-path`/`mask` substrate** → **Spotlight / dim-the-rest** (mask cutout
  that glides between regions; soft edge via `feGaussianBlur`) + **Ken Burns zoom-to-region**
  (`scale + translate` to a region bbox). "Box locates, dim isolates, push-in reads." ~30
  lines each, fully deterministic. *Foundation for the sticky-graphic stepper.*
- **rough-notation / Rough.js (seeded)**: hand-drawn box/circle/underline/strike that draws
  on via frame-driven `stroke-dashoffset` — an "annotated exhibit" character. Pin the `seed`
  (else geometry jitters every frame); bypass the time-based `show()`.
- **Datawrapper emphasis grammar** (reusable across PaperFigure + every future chart):
  gray-out-the-rest (same hue, lower saturation — never a new hue), **direct labels** at
  line ends (kills legends in motion), staged arrow callouts pinned to data, value callouts
  on peaks. All frame-keyed, near-zero cost, highest narrative payoff.

### Motion / transitions (between beats)
- **@remotion/transitions** (`<TransitionSeries>`): designed wipes/flips/clock-reveals/
  fade-through between beats instead of hard cuts. Native, deterministic. Caveat: overlap
  subtracts from total duration — our word-frame math must account for it. Film-grammar
  rule: **cut within a topic, fade/dissolve between topics.**
- **@remotion/motion-blur** (`CameraMotionBlur`/`Trail`): single biggest *perceived-quality*
  lift on our snappy word-synced moves + Ken Burns pans. Cost = render time only.

### Charts (close the biggest gap — see Wave 2 for the full family)
- **visx + d3 generators** as a `useChartScales` primitive — start by refactoring BarChart's
  internals onto `d3-scale`/`d3-shape` (free log scales, ticks, stacks), proving the pattern.

---

## Wave 2 — the chart tier (the single highest-leverage bet)

**Architecture: "d3 generators + visx primitives + our own frame-driven reveal."** Treat
charts as *geometry computed per frame, never self-animating components.* One shared
`useChartScales` (d3-scale) + pure path/geometry helpers (d3-shape/d3-array), wrapped in
visx for React ergonomics, with our existing word-timestamp reveal as the ONLY animation
driver (clip-reveal, stroke-dashoffset, interpolated domain/value). Deterministic by
construction, SVG-native (crisp + clip-revealable), fully token-themeable, unbounded in
archetypes. The batteries-included libs (nivo/Recharts/Victory/ECharts) own their animation
clock → relegated to **static-snapshot escape hatches** for exotic archetypes only.

New blocks this unlocks (all "redraw synthetic" tier): **LineChart/Area** (PnL curves),
**Scatter**, **Distribution/Histogram**, **Heatmap**, **BoxPlot/Violin** (`@visx/stats`),
**Donut/Pie**, **Slope/Bump**, **Sparkline**, **Forest plot**, **Candlestick** (Victory's
`VictoryCandlestick` static, or compose), **small-multiples** (Observable Plot faceting).
Escape hatch: **ECharts SSR `renderToSVGString` + `animation:false`** for sankey/parallel-
coords/themeRiver/chord. Style skin: **rough.js (seeded)** for a "sketchy" theme variant
over the same paths. Annotation layer: **react-annotation** (callout/arrow/bracket fed by
our scales, revealed by us).

**BarChartRace** (from Bostock's d3 race): interpolate `k` keyframes between data points,
rank on interpolated values, object-constancy free via React `key={id}`. Yields the block
**and** a generic ranked-list-reorder transition.

---

## Wave 3 — new structural blocks + the transition layer + paths/morph

### New block archetypes (relations our 13 don't cover)
- **VS / comparison** (mirrored split, two accents) — contrast/opposition (before-after,
  ours-vs-baseline). Very common, currently inexpressible.
- **Pull-quote / definition card** — emphasis / vocabulary (define jargon for paper content).
- **Step / process flow** — sequence / causality / method (methods sections, algorithms);
  shared-axis reveal, can pin a visual and mutate per step.
- **Chapter / section-divider + end-card pair** — pacing + closure (acts + outro/citation).
- **Themed Lottie asset block** — `@remotion/lottie` (`goToAndStop` = deterministic for
  keyframed assets) + **lottie-colorify** (`getColors`→`replaceColors` to theme tokens,
  byte-stable). Icons, number-counters, lower-thirds, checkmarks. Gate out expression/random
  assets at intake; unzip `.lottie`→inner `.json`. (We already have a lottie catalog.)

### Primitives (shared mechanics)
- `useChartScales` (d3-scale), `usePathDraw`/`useMoveAlongPath` (@remotion/paths `evolvePath`
  / `getPointAtLength`), `useMorphPath` (**flubber** — unequal point counts; Remotion
  `interpolatePath` when counts match), `useKenBurns`, `useSpotlight`, `useStagger`,
  `useSpringToWord` (sibling of `useCountToWord`). @remotion/shapes for vector furniture
  (progress rings, pies, stars); @remotion/noise + `random(seed)` for organic motion/texture.
- **GSAP SplitText** (now free) for *wrapping only* → a **KineticHeadline** block whose
  per-unit reveals are driven by our per-word timeline (not GSAP's runtime).

### Transition layer (standardize a scene grammar)
Hard cut (default, within topic) · cross-fade/dissolve (topic boundary) · **mark-constancy
morph** (same keyed entities fly between encodings — highest-value new primitive) · ranked-
list reorder · time-cursor glide (shared `frame→t`, any chart subscribes — Gapminder/OWID)
· spotlight/Ken-Burns hand-off (sticky-graphic stepper) · staged annotation reveal.

### Authoring / eval (borrow the scene grammar, not code)
From **Paper2Video / PPTAgent / Data-Player** literature: an empirically-grounded **section
scene taxonomy** (Motivation→Method→Results→Ablation→Limitations) as the planner backbone;
**audio = master clock** (scene duration = narration length — we already do this);
**Entrance/Emphasis/Exit** animation grammar with gate rules (emphasis only after entrance);
**figure-role classification** (key_visual/method/results) to drive emphasis & pacing;
**enter-order = narration token order**. Eval: **PaperQuiz/PresentQuiz-style comprehension
metric** (does a viewer answer paper questions after watching?) — the most transferable
video-quality measure. Open gaps everyone leaves (we can own): **equations** under-served,
**citations** universally ignored. Offline authoring aid: capture figure region bboxes with
annotorious → export normalized coords into scene data (never ship the lib in the bundle).

---

## Recommended sequencing
1. **Wave 1 theme tokens** (motion + ramp + elevation + type) — compounds under everything,
   pure additive, re-render proves it. Then **PaperFigure annotation** (spotlight + Ken Burns
   + Datawrapper emphasis) — upgrades the signature for ~little code.
2. **Wave 2 chart tier** (visx+d3 `useChartScales`, refactor BarChart, add LineChart/
   Distribution/Heatmap) — biggest capability gap; finance/ML papers need these.
3. **Wave 3** transition layer + new structural blocks + KineticHeadline/Lottie as pulled by
   real videos.
