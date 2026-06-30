# Video-type flows — the meta-design

We make different *types* of explainer video (paper/article, artwork, …). They share an
engine but need different authoring logic. The danger is over-correcting into duplicated
pipelines OR under-correcting into one mega-flow whose planner makes mediocre choices for
every type. The right factoring is **four layers**:

## 1. Shared engine (one codebase — never duplicated)
The deterministic Remotion render + everything reusable across all types:
- render (`render.mjs`), themes (23 token sets), Surface, **captions**, word-timestamp sync,
  `gen_spec` (anchors→frames), `gen_registry`, the **pacing linter**, transitions (Montage),
  **PostFX**, and the primitives — `useKenBurns`, `Spotlight`, `annotate`, `RollingNumber`,
  `chart`, `fit`. ~90% of what's built lives here and is type-agnostic.

## 2. Flow (the per-type skill — the thing you fork)
Each video type = a flow descriptor: **{ ingest, grammar, palette, pacing-profile, defaults }**.
- **grammar** — the scene taxonomy + type-specific rules (e.g. paper's *redraw-vs-lift*; art's
  *always-lift + camera-tour*).
- **palette** — which blocks are in scope (a subset of the library + type-specific blocks).
- **pacing-profile** — the linter thresholds for this type (paper is punchy; art is slow).
- **defaults** — theme/transition/fx suggestions.
The flow is what keeps each planner sharp: a paper planner reasons "BarChart vs DataTable";
an art planner reasons "zoom to this detail as it's named." Don't merge them.

## 3. Ingest adapters (orthogonal axis — how assets arrive)
*Independent of type.* How we get `(segments, words, assets)`:
- **generate-from-source** — paper/article → script (script-skill) → TTS → align.
- **byo-script** — user brings the script → TTS → align.
- **byo-everything** — user brings script **and** voiceover **and** images (e.g. Dance of
  Death, already in NOLAN) → we only **whisper-align the existing voiceover** for word
  timing and pull the images. Same align step, different front door.
Any flow can use any ingest; they compose.

## 4. Router
User **picks the type** (explicit first; auto-suggest from input later — a PDF→explainer, an
image+script→art). The router loads that flow + the chosen ingest, then runs the shared engine.

## The registry
`registry.json` is the machine-readable list of types (each with the fields above). The
pacing linter reads a flow's `pacing` profile via `--profile <id>`. Adding a type = a new
registry entry + a flow doc + (maybe) a few type-specific blocks — not a new pipeline.
