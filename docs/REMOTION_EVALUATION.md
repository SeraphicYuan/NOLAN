# Remotion fit evaluation (2026-06-25)

**Question:** Remotion renders video programmatically with React — should it be a
rendering path in NOLAN (beyond the existing infographic/Lottie niche)?

**Short answer:** Remotion is genuinely capable and a strong fit for a *future*
high-ceiling rendering layer — but **only as a proper Remotion project that renders the
whole essay as one composition**, not as a per-scene bolt-on to today's pipeline. For now
the Python renderer suite is faster, Python-native, and good enough. Treat Remotion as a
deliberate "rendering v2" decision, not an incremental add.

## What was confirmed

Capabilities (real, current Remotion v4):
- **Transparency** — ProRes 4444 (`yuva444p10le`) or VP8/VP9 WebM (`yuva420p`). This is
  the exact thing whose absence killed Lottie compositing.
- **Video embedding** (`<OffthreadVideo>`), **web-font text** (`@remotion/google-fonts`),
  **native transitions** (`@remotion/transitions`: fade/slide/wipe/clockWipe),
  `interpolate`/`spring`, `<Audio>`, `<Series>`/`<TransitionSeries>`.
- So Remotion can render a *complete* scene — b-roll + animated caption + transition +
  audio — declaratively, solving three Python-path weaknesses at once (text layout/clipping,
  compositing hacks, the crossfade stub).

Empirical test (through our render-service):
- Rendered the FLUX breadline as a Remotion Ken-Burns: **9.7s** for a 5s 1080p clip,
  **equivalent quality** to our Python/MoviePy KenBurns (~2–4s).
- The 9.7s is dominated by ~7–8s of **cold re-bundle + Chromium launch the service pays on
  every render** (no warm-bundle cache). Per-scene rendering pays this N times.

## The real blocker: our integration is the wrong shape

`render-service/src/engines/remotion.ts` is a **code-generator**, not a Remotion project:
- It writes throwaway `.tsx` **as strings**, bundles, renders a single hard-coded
  composition (`"NolanInfographic"`) selected by data-shape, then deletes the temp dir.
- It uses none of the things we'd need: no `<OffthreadVideo>`, no transitions, no web fonts,
  no transparency (h264 only). Adding them means editing ~1100 lines of string-templated TSX
  (no type-checking/JSX tooling) + new deps.
- It re-bundles + launches Chromium every render.

This shape is fine for one-off infographics but unusable as a general scene renderer.

## Options

- **A — Don't adopt beyond infographics (recommended near-term).** Keep Python renderers +
  ffmpeg. We just built compositing, line chart, loop diagram, auto-fit, fades — fast,
  Python-native, fits the LLM scene-design pipeline, zero extra ops. Remotion's wins are real
  but largely worked around.
- **B — Adopt as the rendering layer (rendering v2).** Build a *proper* static Remotion
  project: scene components (.tsx files), one `<TransitionSeries>` timeline composition that
  takes the whole `scene_plan` as props (b-roll via `<OffthreadVideo>`, VO via `<Audio>`,
  transitions between scenes, web-font kinetic text), rendered in **one** pass → replaces
  both the Python renderers and ffmpeg `assemble`. Highest ceiling, single declarative
  system, idiomatic Remotion (pays bundle/Chromium overhead once). Cost: real project (days),
  Node/React, headless-Chromium ops, abandons some Python renderer work.
- **C — Hybrid (not recommended).** Remotion only for kinetic text/transparent overlays,
  Python for the rest. Two systems + per-overlay overhead; marginal over our Python overlays.

## Recommendation

Don't bolt Remotion onto the current pipeline per-scene — the code-generator is the wrong
architecture and per-scene overhead is real. Keep Python for now (Option A).

Revisit **Option B as a deliberate project** if/when the quality ceiling (kinetic typography,
seamless transitions, true layered compositing, one declarative timeline) matters more than
ops simplicity. The gating question is strategic: should NOLAN's rendering be **Python-native**
(current — fast, good-enough, integrated) or **React-native** (Remotion — higher ceiling, more
ops)? That's a user/product call, not a code detail.

## If Option B is chosen — concrete first steps
1. Scaffold a real Remotion project (`render-service/remotion/` with `src/*.tsx`, multiple
   `<Composition>`s), not string templates.
2. One `Essay` composition: props = `scene_plan` + audio path; body = `<TransitionSeries>` of
   scene components; b-roll `<OffthreadVideo>`, overlays as React, VO `<Audio>`.
3. Warm-bundle once; render whole video in one `renderMedia` call.
4. Bridge: emit `scene_plan.json` → Remotion props (the service already serializes
   `spec.data` → `spec.json`).
