# Motion palette — a Step-4 variation reference (NOLAN→HyperFrames)

**Why this exists.** HyperFrames frame-workers realize ONLY the motion a storyboard's
Step-4 shot sequence *cites* (by rule/blueprint id) — they never invent moves. So output
variety is an **authoring-depth** decision, not a framework limit. Our first three cuts
cited ~5 rules; HyperFrames ships **36 atomic rules · 15 scene blueprints · 24 named
text effects · a transitions catalog · 7 runtime adapters**. This maps video-essay beat
archetypes onto the widest sensible spread, so Step-4 pulls from more of it. Pick 2–4 per
scene and compose; escalate the adapter only when the beat earns it.

## The adapter escalation ladder (default → reach)
1. **GSAP + CSS** (default) — every beat below. Flat, fast, deterministic, seek-safe.
2. **`animate-text`** (24 named text effects) — when the WORDS are the hero (decode,
   scramble, per-char cascade, glitch, typewriter variants). `adapters/animate-text.md`.
3. **Lottie** — when a beat wants illustrated/vector motion (an icon that performs, a
   drawn diagram that assembles) beyond CSS. `adapters/lottie.md`.
4. **Three.js** — genuine 3D/space (a globe, a rotating object, depth parallax that CSS
   3D can't hold). `adapters/three.md`. Reserve for one "wow" beat; costs render time.
5. **TypeGPU / shaders** — texture/energy fields, generative grounds. `adapters/typegpu.md`.
   Rarely for explainers; a title or transition accent at most.

## Beat archetype → vocabulary (rules `rules/<id>.md`, blueprints `blueprints/<id>.md`)

| Beat archetype | Primary blueprint | Rules to compose | Reach / text-effect |
|---|---|---|---|
| **Hook / cold open** | `titlecard-reveal` | `kinetic-beat-slam`, `ambient-glow-bloom`, `multi-phase-camera` | `animate-text` decode; footage ground (archetype B) |
| **Statement / thesis** | `kinetic-type-beats` | `kinetic-beat-slam`, `asr-keyword-glow` (the on-word accent) | per-word `animate-text` cascade |
| **Single stat / number** | `dataviz-countup` | `counting-dynamic-scale`, `stat-bars-and-fills` (underline/fill) | `vertical-spring-ticker` for a rolling odometer |
| **Chart / data-viz** | `dataviz-countup` | `stat-bars-and-fills`, `svg-path-draw` (line draws), `counting-dynamic-scale` | Lottie for a bespoke animated chart |
| **Comparison / before-after** | `comparison-split` | `split-tilt-cards` (skip if flat-plane style), `stat-bars-and-fills` | `video-text-pivot` |
| **List / enumeration** | `grid-card-assemble` | `center-outward-expansion`, `depth-scatter-assemble` | `ticker-takeover` for a fast run |
| **Process / how-it-works** | `spatial-pan-stations` | `viewport-change`, `coordinate-target-zoom`, `svg-icon-enrichment` | `cursor-ui-demo` for UI flows |
| **Concept / network / system** | `constellation-hub` | `avatar-cloud-network`, `orbit-3d-entry`, `center-outward-expansion` | Three.js for a real 3D graph |
| **Map / place** | `spatial-pan-stations` | `viewport-change` (pan/zoom-to-place), `svg-path-draw` (routes) | route-map block (registry) |
| **Quote / human** | (compose) | `depth-of-field-blur` (rack focus), `asr-keyword-glow`, `ambient-glow-bloom` | footage ground + scrim (archetype B) |
| **Archival still / artwork** | (compose) | `multi-phase-camera` (motivated push) | **`artwork-stage` block** (museum label — NOLAN-flavored) |
| **Overwhelm / scale** | `overwhelm-surround` | `depth-scatter-assemble`, `multi-phase-camera` | TypeGPU field for a texture wall |
| **Reveal / turn** | `video-text-pivot` | `depth-of-field-blur`, `viewport-change` | scene transition (below) |
| **Logo / brand close** | `logo-assemble-lockup` | `svg-path-draw`, `ambient-glow-bloom` | Lottie lockup |
| **Idle / ground bed** | — | `sine-wave-loop`, `ambient-glow-bloom` (bounded, ≤0.45 peak) | shader ground |

## Between-scene transition grammar (`transitions/catalog.md` + `TRANSITION-REGISTRY.md`)
Cited via the storyboard `transition_in` + injected by `transitions.mjs`. Families:
`css-dissolve` (argument breathes), `css-cover` / `css-grid` (hard editorial cut with
structure), `css-blur` (soft focus change), `css-3d` (space pivot), `css-light`
(flash/exposure), `css-distortion` / `css-destruction` (energetic, use sparingly).
Match the STYLE: editorial = hard cuts + occasional dissolve; kinetic/promo = cover/3d/
light. Per-style bias belongs in the storyboard `## Video direction` block.

## Composition rules (do not regress on determinism)
- 2–4 motions per scene, composed on ONE paused timeline; reveals paced to the VO cue,
  never front-loaded. Transforms/opacity/`onUpdate`-proxy only — no CSS transitions,
  no repeat/yoyo state, no `Date.now`/`Math.random`.
- Adapter escalation is per-scene and must justify itself: a Lottie/Three beat should be
  a deliberate highlight (≤1–2 per piece), not the default — they cost render time and
  can fight a flat-plane preset's identity.
- Style caps the palette: a preset's `motion_avoid` (e.g. broadside/editorial ban 3D
  tilt + shadow) overrides this menu. When in doubt, fewer moves, better timed.

## Where this plugs into the bridge
This is the reference the **plan-writer adapter** consults when authoring Step-4 shot
sequences from a NOLAN beat plan — it widens the cited vocabulary per beat archetype so
a HyperFrames cut uses the framework's real range instead of a 5-rule subset.
