# The Brief Layer — authoring broll/motion from intent

> Status: v1 implemented (`src/nolan/brief/`). First family: `photo-story`
> (photo-montage + photo-grid). Designed to generalize to every motion effect.

## Why this exists

The motion engines (`PhotoMontage`, `PhotoGrid`, the Python renderers, the Remotion
compositions) became *powerful* — per-card keyframe tracks, 3D pan/tilt, perspective,
grid choreography. A powerful low-level API is the **wrong** surface for an LLM agent or
a human comment: authoring 40 cards × keyframes is verbose, token-heavy, and error-prone.

The brief layer is the authoring surface that sits between the **broll/scene-design stage**
and the **render engines**. It is the single place that connects "what I mean" to "what
renders", whether the author is an LLM or a human comment in `/scenes`.

## The one principle

> **The model does the *semantic* part. Deterministic code does the *mechanical* part.
> They meet at a small, validatable contract — the _brief_.**

The LLM is good at *"these 6 pictures, 2×3 grid, zoom picture 4 when the VO says
'keyword'."* It is bad at — and must not do — grid math, keyframe generation, or timestamp
lookup. So those live in a deterministic resolver, and the model only authors the brief.

## Layers

```
NL comment / LLM intent
   │  LLM:  intent → brief            (semantic; the only thing the model writes)
   ▼
BRIEF            compact, declarative, per-family, explicit asset paths
   │  resolve_brief(brief, SceneContext)   deterministic · pure · testable
   ▼
SPEC            the existing validated nolan.motion spec (cols/rows, keys, rotX/rotY, …)
   │  nolan.motion.render → executor
   ▼
RENDER          python | remotion
```

Two pieces make this **general**, not photo-specific:

### 1. `TimeRef` — symbolic time (the reusable core)
The hard, reusable part of the example is *"when the VO says 'keyword'."* A `TimeRef`
resolves against the scene transcript:

| TimeRef | meaning |
|---|---|
| `3.2` | absolute seconds (scene-local) |
| `"start"` / `"end"` / `"mid"` | scene anchors |
| `"keyword"` or `{"cue":"keyword"}` | when the VO says it (cue start) |
| `{"cue":"keyword","at":"end"}` | when the VO finishes saying it |
| `{"frac":0.5}` | fraction of scene duration |
| `{"after":<TimeRef>,"delay":0.5}` | relative to another anchor |

`TimeRef` is **not** photo-montage-specific — any timed effect (annotation drawing on a
word, a counter starting on a phrase, kinetic text) can anchor to it. It is the bridge
between the VO-aware design stage and the number-based specs.

### 2. Motion verbs — not keyframes
Everything we built (enter-from-edge, fade, **tilt** (rotateZ), **pan** (rotateY 3D),
**3D tilt** (rotateX), **complex path**, **grid/tile**) is exposed as a tiny verb
vocabulary. The resolver compiles verbs → the low-level `keys` tracks.

```jsonc
{"enter":"left","at":"start"}            // entrance
{"fade":"in"|"out","at":<TimeRef>}       // opacity track
{"tilt":-6,"at":{"cue":"first"}}         // in-plane rotateZ
{"pan":-35,"at":{"cue":"second"}}        // 3D rotateY swing
{"tilt3d":20,"at":2.0}                   // 3D rotateX
{"move":[0.5,0.7],"at":1.5}              // single move
{"path":[{"to":[0.4,0.3],"at":1.6},{"to":[0.6,0.7],"at":3.0}]}  // multi-step path
{"zoom":0.8,"at":{"cue":"focus"}}        // scale to a height-fraction
```

The agent never writes a keyframe, a pixel, or a perspective value.

## The brief schema (photo-story)

```jsonc
{
  "kind": "photo-story",
  "layout": "grid" | "free",        // omittable; inferred (grid by default, free if any image has place/motion)
  "images": ["a.jpg", …] | [{ "src", "caption?", "place?":[x,y], "scale?", "frame?", "motion?":[…verbs] }],
  "background": "#241016" | "<image path>",
  "duration": 6.0,                  // optional; defaults to the scene's duration

  // grid layout
  "grid": "2x3",                    // rows x cols (omittable → near-square)
  "fly_in": "one-by-one" | "row" | "col",
  "focus": { "image": 4, "at": <TimeRef>, "hold": 1.4, "scale": 0.8 }

  // free layout: per-image place + motion verbs (see above)
}
```

`layout:"grid"` → the `photo-grid` composition; `layout:"free"` → `photo-montage-pro`.
The resolver hides which composition/backend is used — the author picks intent, not engine.

## Integration points

- **LLM authoring** — `resolve_brief(brief, ctx)`; the registry advertises the brief
  vocab so `nolan.motion`'s compiler can target it.
- **Human comments / `/scenes`** *(wired)* — `iterate/revise.py`'s LLM gate returns a
  `photo_brief` object for montage/grid notes; `revise_scene` resolves it against the
  scene's narration timing and sets `motion_spec`. Verified with a real LLM + comment:
  `scripts/test_router_brief.py` ("6 pics, 2×3 grid, zoom the 4th when VO says 'keyword'"
  → `photo-grid`, focusIndex 3, focusAt = 3.2s, rendered). Reachable from the **hub**
  (`POST /scenes/api/scene/revise`) and **CLI** (`nolan revise-scene --note`); both feed VO
  word-timing via `iterate.scene_words` (cached `voiceover.words.json`, transcribed once
  from `segment_meta.vo_path`) so `{cue:"..."}` resolves on live projects.
- **Design boundary (important):** cue→time resolution happens at **design time**, where
  the transcript lives. The resolved spec is persisted on the scene (`motion_spec`); the
  renderer stays context-free. This is why briefs slot into the existing edit/render loop
  without touching the executor.

## Asset binding (the input half)

Comments shouldn't require pasting paths. Each scene carries an **asset tray** —
`scene.assets: [{id, kind, src, label?, thumb?, place?, clip_start?, clip_end?}]` — curated
in the `/scenes` **Assets** tab via a slide-in **picker drawer**: tabs **Pictures**
(browse `/api/images/list` + CLIP search) and **Videos/Clips** — the videos tab has a
**scope toggle** (This project / All) and a **source toggle**: *Saved clips*
(`/library/api/clips?projects=`) or *Segments* (drill-down: `/library/api/videos` → pick a
video → `/videos/{path}/segments`). Thumbnails via `GET /scenes/api/frame-thumb`.
Multi-select → "Add N to scene". Tray
cards show a kind badge (IMG/VID), a remove button, and a 3×3 dot picker for `place`.
Library images resolve to a real path server-side; clips store `source_video_path` + span.
The resolver **kind-validates** (photo-story consumes images; a referenced clip warns —
video cards are TODO C). A later
comment references the tray by id/label ("grid of these, zoom the Knight"); the revise
gate sees the tray (ids/labels/kinds) and emits `images:[{ref:'<id>'}]`, which the
resolver dereferences to the bound `src` (and the asset's `place`/`scale`/`label` flow
through). Tray edits go through `POST /scenes/api/scene/assets` and do **not** invalidate
the rendered clip — only a comment/re-render does. Division of labor: the human curates
*which* assets, the agent decides *how* they move.

### Spatial control — the elegant boundary
Direct manipulation is offered **only** for what maps to a declarative field: the per-asset
3×3 `place` picker (and, later, a drag marker over a proportional "stage" for `place`/
`scale`). It never edits keyframes or timing — those stay comment-driven (a freeform canvas
would re-introduce the manual authoring the brief layer exists to remove, and scales badly
to 40-image grids). Anything the picker sets, a comment could also set, and vice versa —
the render preview is the source of truth.

## Failure modes (graceful by construction)

`resolve_brief` returns `(spec, messages)` and always produces a best-effort spec:
- missing cue → warns, falls back to a sensible anchor (does **not** crash);
- missing image file → warns, keeps the entry (render shows nothing rather than dying);
- grid overflow / unknown verb → warned and skipped.
Messages are meant to be surfaced to the author (LLM or human), not swallowed.

## Extending it

Add a brief family by writing `resolve(brief, ctx) -> spec` and registering it in
`BRIEF_REGISTRY` (e.g. `photo_story.RESOLVERS`). Reuse `resolve_time` for any timed field
and `SceneContext` for transcript/duration. New motion verbs are a few lines in
`_compile_verbs`. The brief stays small; the power stays in the engines.

## Files
- `src/nolan/brief/timeref.py` — `resolve_time`
- `src/nolan/brief/context.py` — `SceneContext` (+ `from_scene`)
- `src/nolan/brief/photo_story.py` — grid + free resolvers, verb compiler
- `src/nolan/brief/resolve.py` — `resolve_brief`, `resolve_for_scene`, `BRIEF_REGISTRY`
- `scripts/test_brief.py` — cue-timing, graceful degradation, verb compilation, render

## TODO
- **(C) Video-in-montage rendering** — `PhotoMontage`/`PhotoGrid` use `<Img>`; support
  `kind:"clip"`/`"video"` assets as moving cards by swapping to `<OffthreadVideo>` when a
  card's src is a video (honor the clip's in/out span). Also: upload-to-tray, and library
  videos (`/library/api/videos`) as a picker source alongside saved clips.
