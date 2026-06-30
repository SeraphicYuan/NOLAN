# Scope: per-beat human-in-the-loop editor + authoring mode (flow video editing)

Make a flow video (art, explainer, …) **editable per beat** through NOLAN's existing Scene
page, with two human-in-the-loop stages over one shared, persistent spec — and two autonomy
modes. This is the productization of the authoring step (retires the "authoring is hand-tuned
JSON" limitation). Builds on `INTEGRATION.md` (the flow runner) and the QA gate.

## The big picture — most of it already exists
NOLAN already ships a **production-ready scene-iteration HITL system** (Scene page `/scenes`,
commit `e0541e3`): per-scene view, **comment → LLM patch → re-render-just-that-scene**, a
**per-scene asset tray** (add/remove/place images & clips from the library), selective
re-render + re-assemble, and agent/fleet dispatch — but only for the *segment/orchestrator*
pipelines. This feature is **making flow videos first-class citizens of that system**, not a
new tool.

## Two HITL stages, one shared object
The same persistent per-beat spec is edited at two stages — the two bookends of the pipeline:

```
script + VO ──► PLAN (authoring) ──► RESOLVE (gather assets) ──► RENDER ──► review
                     ▲ Gate A  (plan-time HITL)                     ▲ Gate B (render-time HITL)
                     authoring mode                                  Scene page
```
- **Gate A — authoring mode (plan-time):** the Scene page in a *plan* state. Per beat: planned
  **motion** (from the flow's palette — the blessed motions), planned **assets**, a **wishlist**
  of assets you ideally want *even if not in the pool*, and a **status** (have ✓ / find 🔍 /
  generate ✨). You tweak beats and link assets. The wishlist *is* your shopping list.
- **Gate B — scene editing (render-time):** the Scene page in a *rendered* state (today's
  behaviour). Comment → patch → re-render just that beat; swap motion; adjust assets.

Both edit the **same persistent spec**; the tray works at both gates.

## Autonomy = which gate blocks (not separate code)
One pipeline; the "mode" only decides whether **Gate A** blocks. **Gate B is always available.**
- **Auto:** Gate A off — serve script + VO, agent runs plan → resolve → render straight
  through; you review/tweak at Gate B. (≈ what exists today.)
- **Semi-auto:** Gate A on — agent drafts the plan, pauses in authoring mode; you tweak + link
  the assets it can't auto-source; agent resolves the rest + renders; you tweak at Gate B.
Pausing at *authoring* is high-leverage: cheapest stage, drives everything downstream, and it's
exactly where you supply the hard assets before a render is spent on placeholders. (Generalizes
to per-gate config later; two named modes is the right default — don't over-build.)

## Render dispatch — branch on MECHANISM, not video-type
A growing `if art / elif explainer / elif book` is the anti-pattern. What differs between
re-render branches isn't the video-type, it's the render **mechanism**, and there are few:

| mechanism | used by | re-render-one = |
|---|---|---|
| `clip-library` | segment | vector-search b-roll → clip |
| `orchestrator-scene` | orchestrator | `render_dispatch.render_one` per scene |
| **`chapter-block`** | **art, explainer, book, … every `_lab_chapter` flow** | single-step `_lab_chapter` job → beat clip |

art/explainer/book all render the *same way* (the `_lab_chapter` bundle); they differ only in
ingest + palette + profile (the Flow descriptor). So the engine dispatches on
`flow.render_mechanism`; **adding "book" = one registry row + maybe an ingest adapter + a skill,
zero engine branches.** A new branch is added only for a genuinely new mechanism (rare).

```
Flow = { id, ingest, authoring, palette, profile, defaults, render_mechanism }
```

## Render model — per-beat clips + concat (decided)
Art renders as **N single-step `_lab_chapter` jobs → beat clips → concat + audio** (cross-fades
via ffmpeg `xfade` at concat), not one Chapter-of-N. This is what makes per-beat re-render real
and plugs into the existing selective-re-render machinery. **The enabling property: each beat's
duration is pinned to its voiceover segment**, so a visual edit (swap motion, change asset, nudge
a focus) never reflows the timeline — the beat is independently re-renderable. (Trade-off:
cross-beat transitions move from in-composition to concat-time; the #29 whole-composition render
becomes an optional high-fidelity master if ever wanted.)

## Data-model additions (thin, additive)
NOLAN's `Scene`/`scene_plan.json` is persistent + resume-friendly but built for per-scene clips
and missing what flows need. Additions (all optional fields, no schema breakage):
- Persist the flow spec as a **project-owned** artifact (`projects/<slug>/`), beat-addressable.
- Per beat: `block`/`props`, `words[]` + `revealFrames[]` (frame-accurate word sync),
  `focuses[]` (art), `audioSrc` (the voiceover segment), and an **asset wishlist** + status.
- The project records its **flow id** → inherits palette/profile/theme via `get_flow`.
- Reuse the existing `scene.assets[]` tray for per-beat asset bindings.

## Phases
1. **Persistence** — project-owned, beat-addressable spec; the shared object for both gates.
2. **`chapter-block` mechanism** — one render mechanism, dispatched via `flow.render_mechanism`;
   art/explainer/book reuse it (per-beat clip + concat; plug into `iterate/engine.py`).
3. **Scene-page wiring (Gate B)** — beats as scene rows; comment → re-render-one; tray binds into
   block props; palette as the "swap the blessed motion" menu (governed by the #31 soft check).
4. **Sub-beat granularity** — per-focus override + click-to-place-region UI ("segment within a
   beat" — the finer grain NOLAN lacks today).
5. **Authoring mode (Gate A) + autonomy** — LLM drafts a per-beat plan from script+VO, flow-aware
   (palette), with the asset wishlist (have/find/generate); human-tweakable; auto vs semi-auto =
   Gate A off/on.

## Reuses (so it's mostly wiring, not building)
Scene page UI, comment→patch (`iterate/revise.py`), selective re-render (`iterate/engine.py`),
the asset tray + picker (`scene.assets[]`, `/scenes/api/scene/assets`), fleet dispatch, the Flow
descriptor + palette (`get_flow`, `art_validate --flow`), the QA gate, the 39-block library, and
the `_lab_chapter` render bundle. Net-new: the persistent flow spec, the `chapter-block`
mechanism, per-focus overrides + region-picker, and the authoring-mode plan/wishlist surface.
