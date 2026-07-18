# Composition architecture — layout as a first-class, shared, LLM-friendly module

**Date:** 2026-07-18 · **Status:** design / foundation (approved to build B1/B2 against this) ·
**Purpose:** define how NOLAN encodes scene *composition/layout* so it is not hardcoded per theme or
per scene, but a **shared module every theme, every block, and every AI-authored (bespoke) scene
references** — grounded in professional layout theory and proven LLM behaviour.

**Companions:** `docs/THEME_MODULE_REVIEW.md` (why themes are weak on composition — the trigger);
the bespoke/theme roadmap (Phase 2); `docs/WIRING_CHECKLIST.md` (the module contract this satisfies);
KB notes under `parsed/insights/…theme-composition…` (the atomic craft form). Gold-standard registries
to mirror: `src/nolan/motion/registry.py`, `src/nolan/editing.py`.

---

## 1. The problem, and the finding that reframes it

Themes encode colour + type + a decorative signature, but **no composition/layout character** — so an
LLM authoring a bespoke scene re-infers layout from the theme *name*, and defaults to a left-crowded
column. We ran the experiment (A/B/C/D):

| Run | What varied | Result |
|---|---|---|
| A | baseline, no direction | left-crowded |
| B | swap theme (colour/font) | still left — theme name does **not** steer layout |
| C | explicit "centre / full-canvas" instruction | **centred, full-canvas** |
| D | explicit instruction + non-list content | **centred, full-canvas** |

**Conclusion: composition is controlled by the presence of an explicit, named instruction — nothing
else.** Absent one, the agent takes the *web platform default* (CSS `text-align: start` = left;
absolute-position origin = top-left) plus the conventional editorial choice. This is not a model quirk
and not set anywhere in NOLAN — and it is trivially overridden by an explicit archetype. The lever is
therefore to **make composition its own declared thing** and pass it to the author.

## 2. The reframe — composition is its own axis

A theme should be a **bundle of defaults across orthogonal axes**:

```
theme = { palette ⟂ type ⟂ composition ⟂ motion ⟂ decoration }
```

The mistake today is entangling composition inside the theme's aesthetic identity as prose ("editorial
house style"), where it becomes the weakest, most-ignored signal. **Decouple composition into a
first-class, named, declarative axis.** A theme then *picks* a default composition + an allowed set; it
never reinvents layout. Palette and composition become independently overridable — any palette can pair
with any allowed composition.

## 3. The architecture

### 3a. A shared composition module (registry)

One source of truth — a registry of **named layout archetypes**, exactly like the motion/editing
registries (satisfying the module contract: registry → authored field → consumer → honesty test).
Proposed home: `themes/composition/archetypes.json` (data, readable by the bridge `compose.py` *and*
`src/nolan`), with a thin accessor `src/nolan/composition.py`. Each archetype:

```jsonc
{
  "id": "centered-hero",
  "intent": "One dominant idea, dead-centre, full canvas. Big-number / big-question / thesis beats.",
  "when_to_use": "a single statement, a number, a question — the beat has ONE thing to say",
  "not_for": "multi-item lists, comparisons, dense data",
  "anchor": "optical-centre; support text on the lower third",   // rule-of-thirds / 12-col, not pixels
  "balance": "symmetric",
  "density": "generous",
  "safe_areas": ["caption-keep-out-83pct", "title-safe"],
  "exemplar": "compositions/_exemplars/centered-hero.html"        // ONE worked example (few-shot)
}
```

`anchor`/regions are **guidance on a rule-of-thirds or 12-column grid, not pixels** — robust across
content length, font width, and aspect (the same principle as `data-fit` for text). The **exemplar is
load-bearing**: one worked example per archetype is the single biggest lever on LLM output quality and
the cure for the "three agents invent three unrelated styles" variance.

### 3b. Themes reference it (don't reinvent)

`theme.json` gains one block (validated against the registry, enriched, honesty-tested):

```jsonc
"composition": { "default": "editorial-column", "allowed": ["editorial-column","centered-hero","swiss-grid"], "density": "normal" }
```

The theme *constrains + skins*; it does not hardcode layout. Improve an archetype once → every theme
inherits it.

### 3c. One layout language for BOTH paths (the unifying win)

The block library and the bespoke path currently risk two dialects. In fact **your blocks already ARE
beat→composition pairings** — `stat` is a big-number lockup, `comparison` is a split, `newshead` is a
focal-card. If both the block composer (`compose.py`) and the bespoke agent reference the *same*
archetype registry + grid, the "two render paths diverge" problem and the "themes hardcode composition"
problem collapse into one architecture.

### 3d. The selection model — content-first, brand-second

Composition is not "theme → one layout." It is:

```
composition = f(beat/content type, theme.allowed, human direction)
```

The **beat suggests** the archetype (a number → centered-hero, a comparison → split, a quote → centred,
a list → column/grid); the **theme constrains + skins** it (its allowed set + house bias); the **human
overrides**. This is how professional editorial and motion design actually decide layout.

## 4. The archetype vocabulary (grounded in your 26 themes + 18 blocks)

A small orthogonal set using **standard design terms an LLM already knows** — so the instruction is
legible with zero training:

| Archetype | Beat types it serves | Grounded in existing themes / blocks |
|---|---|---|
| `centered-hero` | big-number, big-question, thesis | warm-keynote, bauhaus-bold · block: `stat` |
| `editorial-column` | running claim, narration-led | highlighter-editorial, newsroom, kraft-paper · block: `statement` |
| `swiss-grid` | multi-item, structured data | swiss-ikb, bauhaus-bold, neubrutalism, blueprint · blocks: `gallery`,`collage`,`carousel` |
| `split-screen` | comparison, dialogue, before/after | split-canvas · block: `comparison` |
| `full-bleed-overlay` | media/atmosphere is the hero, text overlaid | aurora-mesh, neon-cyber, terminal-green, chalk-garden · blocks: `geo`, `media_ground` |
| `focal-card` | one object/subject anchors the stage | bold-signal · blocks: `newshead`, `spotlight`, `document` |
| `rule-of-thirds` | asymmetric hero + support (portrait/subject) | dune, dark-botanical · block: `lower_third` |
| `framed` | contained artefact (chart, quote, code) | monochrome-print, vintage-editorial · blocks: `chart`,`diagram`,`code` |

(The exact set is a v1 proposal — settle it with the team; the mapping shows it fits what you already
have rather than importing an abstraction.)

## 5. Why this is LLM-friendly (the C/D lesson, generalised)

- **Named semantic archetypes over pixel math** — LLMs reason well about "rule of thirds" and "centered
  hero", poorly about coordinates.
- **Intent + constraints, let the model fill** — a one-line brief moved an entire layout (C/D). Give
  the archetype + regions + safe areas, not a rigid spec.
- **Exemplars (few-shot) are the biggest quality lever** — one worked example per archetype; the cure
  for style variance.
- **A grid as a shared coordinate language** — "headline spans the middle third, anchored to the
  upper-third line" is both LLM-legible AND machine-checkable (the position/overlap linter can verify
  the anchor was respected).
- **Composable primitives robust by construction** (Every Layout) — survive content, font, aspect.

## 6. SOTA grounding (read these)

- **Josef Müller-Brockmann, *Grid Systems in Graphic Design*** — the canonical grid theory.
- **Timothy Samara, *Making and Breaking the Grid*** — the clean taxonomy: manuscript / column /
  modular / hierarchical grids (a ready-made archetype spine).
- **Heydon Pickering & Andy Bell, *Every Layout*** — composable, intrinsically-robust layout primitives
  (Center, Stack, Cluster, Cover, Frame, Grid, Sidebar, Imposter).
- **Broadcast / motion** — title-safe / action-safe areas, rule of thirds, the animator's 12-field grid.
- **W3C Design Tokens Community Group** — colour/type tokens exist here already; spacing/layout tokens
  (a modular spacing scale, a grid definition) are the standard extension NOLAN is missing.
- **Nancy Duarte, *slide:ology*** — the slide archetypes (title, section, big-number, quote, comparison,
  full-bleed) that map ~1:1 to video-essay beat types.

## 7. Module-contract wiring (per WIRING_CHECKLIST)

- **Registry**: `themes/composition/archetypes.json` — id + intent + when_to_use + constraints + anchor
  + exemplar.
- **Authored field**: `theme.json.composition{default,allowed,density}`, validated against the registry
  in `validate_themes.py`; enriched fields (if any) in `enrich_themes.py`.
- **Consumer(s)**: the bespoke brief (`bespoke_task_brief` passes the resolved archetype + regions +
  exemplar); later, `compose.py` blocks declare their archetype. Both READ the registry (one dialect).
- **Honesty test**: every theme's declared archetypes exist in the registry; every archetype the brief
  passes is consumed; (stretch) the position/overlap linter verifies the rendered scene respects the
  archetype's anchor. Docs claim, tests enforce.

## 8. Pragmatic sequencing — don't over-engineer

1. **Semantic layer first (proven cheap, C/D-validated):** the named-archetype registry + one exemplar
   each + pass the resolved archetype into the bespoke brief (B2). This alone fixes the left-crowding on
   the next dispatch.
2. **Theme field (B1):** declare `composition{default,allowed}` on `theme.json` + `selector.json` +
   validator, so the archetype is chosen automatically per theme instead of a per-dispatch human note.
3. **Grid geometry + block integration (v2):** structured rule-of-thirds/12-col anchors + the
   position/overlap linter that checks them + `compose.py` blocks declaring archetypes (unifies the
   two paths, from roadmap B4b).

## 9. Decisions (settled 2026-07-18)

1. **Archetype set → refine.** Demote `rule-of-thirds` to the underlying **grid substrate** (all
   archetypes place against it), add **`sidebar`** (narrow+wide, distinct from `split-screen`'s 50/50).
   ~7-8, **extensible** — add an archetype only when a real beat can't be expressed.
2. **Registry home → shared JSON** at `themes/composition/archetypes.json` + `themes/composition/
   exemplars/`, read by the bridge composer + `validate_themes.py` + a thin `src/nolan/composition.py`
   accessor. Mirrors how `catalog.json` serves both paths. NOT a per-theme key (drift).
3. **Beat→archetype selection → the composition registry owns the archetype↔beat knowledge; the
   bespoke agent selects from the theme's `allowed` set given the beat** (C/D-proven, content-first).
   Blocks remain the templated pairing. The flow registry stays video-type pacing — NOT overloaded.
4. **Exemplars → hybrid.** Promote the best real renders (already have `centered-hero` from the C/D
   experiment + `focal-card` from spotlight) + hand-author the archetypes we lack. Add a "promote this
   scene as the `<archetype>` exemplar" action so the library self-improves (same spirit as
   propose→accept promotion).

**On the intellectual sources:** *Every Layout* supplies the module **philosophy** (a small set of
composable, robust-by-construction primitives — good for robustness AND LLM-friendliness). The archetype
**vocabulary** is domain-grounded in editorial / presentation / broadcast design (Swiss grid theory,
slide archetypes, broadcast safe-areas), because we author MOTION GRAPHICS (fixed frames, timed reveals,
safe areas), not web-page document flow — and the LLM reasons best about layouts named for the content
("big-number", "comparison", "centred thesis"), not "Cover"/"Imposter".

## 10. Wiring mandate — do NOT under-wire (owner requirement)

The composition module must wire into the **normal video-essay authoring pipeline**, not just the
bespoke path. Before building, run a wiring audit (per `docs/WIRING_CHECKLIST.md`) and wire EVERY
relevant consumer — an authored `composition` field with no consumer is a bug; a capable executor with
no authoring surface is the mirror bug. Consumers to check + wire:

- **Theme selection** — `themes/scripts/select_theme.py` / `selector.json`: composition fit can factor
  into theme ranking; `validate_themes.py` gains an archetype-parity check.
- **Scene planning / director spine** — `src/nolan/scenes.py` + `orchestrator/director.py`: a scene's
  archetype is authored (beat-derived or explicit), carried in the plan (a `PLAN_FIELD_CONSUMERS` entry).
- **The flows** — `src/nolan/flows/` (explainer/art) + `web-video-lab/flows/registry.json`: the beat→
  archetype default lives with beat metadata; theme supplies `allowed`.
- **The block composer** — `compose.py` (B4b — SHIPPED): every catalog block is *classified* by an
  archetype (coverage honesty-tested; `raw` is the one archetype-agnostic exempt; `linedraw`→focal-card).
  compose.py stamps `data-archetype` on each scene's content root (a first-class DOM fact — its real
  consumer is the layout linter, which now reads it for anchor-drift on composed frames) and HONOURS the
  theme's `--r-card` knob on the generic cards (the THEME_MODULE_REVIEW knob-drop, fixed for radius — so a
  flat theme finally gets flat cards). Still deferred: the `--stage-pad-x/y` edge-margin knob (cqw-vs-px
  unit mismatch + a position-shift across every block — needs its own careful pass).
- **The bespoke agent** — `bespoke.py` `bespoke_task_brief`: passes the resolved archetype + regions +
  exemplar (Phase-2 B2, the proven lever).
- **Gates / verify** — the deterministic layout linter (`src/nolan/hyperframes/layout_lint.py`, gate
  v2 — SHIPPED) checks a composed frame's DECLARED geometry (both inline styles AND the composer's
  CSS-class positioning — it resolves single-class rules from the frame's `<style>`) against the
  registry's machine-readable safe-areas (`caption_keep_out_y`=0.85, calibrated to where the caption bar
  actually sits) + per-archetype `zone`: overlap / caption-band collision / genuine off-canvas as HARD
  errors, anchor-drift as advisory. It reads each scene's archetype straight from the composed DOM
  (`data-archetype`). Cheap structural pass wired into BOTH the compose-first finish DAG (pre-render soft
  gate) and the bespoke/agent-edit proposal (advisory findings surfaced at review). render_gate stays the
  VLM perceptual pass; the human still LOOKs. Consolidated roadmap v2-gate-(a) with bespoke-P1 (one
  linter, two gates). Precision: 0 hard errors on the main shipped compose-first comps.
- **`/map` + the umbrella skills** — the composition registry is auto-surfaced + honesty-tested so the
  catalog can't rot.

## 11. Theme showcase page — expose the themes visually (owner requirement)

The owner is currently "blind" to what the 26 themes actually look like. Build a **theme gallery UI**
(a hub page) that renders, per theme, every axis: the **palette** (surface/text/accent ladders), the
**type** pairing (display/body/mono specimens), the **signature decoration**, and — once the
composition module lands — the theme's **composition archetype(s) with their exemplar renders**, plus
the **components/blocks** in that theme. End goal: a single page where the whole team can SEE each
theme + its exemplar at a glance (and, later, pick/preview one). This both fixes the blindness and gives
the composition work its visual QA surface. Scope it as its own deliverable alongside Phase 2.
