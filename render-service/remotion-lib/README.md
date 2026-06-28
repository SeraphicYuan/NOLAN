# remotion-lib — curated Remotion source

A **proper** static Remotion project (real `.tsx`, not the render-service code-generator)
for the scene types where Remotion is categorically better than the Python renderers.
Python stays the default; route to Remotion only within this curated scope
(see `docs/REMOTION_EVALUATION.md`).

## Style system
Two layers (shared + per-effect):

- **Shared style** = `theme` prop on every composition — a preset name (`"dark-editorial"`
  default, `"light"`, `"high-contrast"`) **or** a partial override object (`{"accent":"#0af"}`).
  Tokens: `bg, fg, muted, accent, up, down, neutral, fontFamily, speed` (`src/theme.ts`).
- **Per-effect style** = each composition's own switch + knobs:
  | Composition | style var | values | other knobs |
  |---|---|---|---|
  | `Kinetic` | — | — | `highlights[]`, `accent`, `scrim`, `videoSrc` |
  | `BarCompare` | `barStyle` | flat · gradient · glass | `bars[]`, `prefix/suffix` |
  | `KShape` | `lineStyle` | straight · zigzag | `jitter`, `segments` |
  | `AnnotateOverVideo` | `shapeStyle` | clean · scribble | `focusX/Y`, `rx/ry`, `label`, `videoSrc` |
  | `AnnotateStat` | `shapeStyle` | clean · scribble | `value`, `label` |
  | `RouteMap` | `routeStyle` | arc · straight | `pins[]`, `mapSrc` (basemap image) |
  | `PremiumCard` | `cardStyle` | glass · gradient · spotlight | `kicker`, `title`, `subtitle` |

Shared geometry helpers live in `src/shapes.ts` (`jaggedPath`, `scribbleEllipse`) — seeded
with Remotion's `random()` so paths are stable per-frame.

## Categories covered (curated scope)
1. kinetic-text (`Kinetic`) · 2. rich-chart (`BarCompare`, `KShape`) ·
3. svg-annotation (`AnnotateOverVideo`, `AnnotateStat`) · 4. map (`RouteMap`) ·
5. premium card (`PremiumCard`). (6 transitions = assembly-level; 7 3D = on-demand.)

## Layout & render
- `src/index.tsx` → `registerRoot(Root)`; `src/Root.tsx` → one `<Composition>` per type.
- `render.mjs` — bundle + `selectComposition` + `renderMedia` from a job JSON.
- Job JSON: `{ comp, out, durationInFrames, codec?, video?, image?, props:{…} }`.
  `video` → `<OffthreadVideo>` background; `image` → `mapSrc` basemap.
```
cd render-service
"/mnt/c/Program Files/nodejs/node.exe" remotion-lib/render.mjs remotion-lib/jobs/exampleA_thesis.json
```
Runs on Windows node (deps are Windows-built); no running service needed. Output → `output/`.
Render time ~5–9s/scene (cold bundle + Chromium each run).

## Wired & polished
- **Source:** `remotion` route in `visual_router.py` (`REMOTION_VISUAL_TYPES`), discoverable
  `registry.json`, render bridge `src/nolan/remotion_source.py`.
- **Font:** Inter via `@remotion/google-fonts` (`src/fonts.ts` → `theme.fontFamily`).
- **Transitions:** `@remotion/transitions` (`TransitionSeries`+`fade`) in `Showcase`.
- **Showcase reel:** `output/showcase.mp4` (~27s, intro + all effects, crossfaded).

## Possible next
- For overlay onto the Python pipeline, render `codec:"prores"` (transparent) and composite
  via `renderer/composite.py`.
- Wire the orchestrator render step to call `remotion_source.render_scene` for `route=="remotion"`.
