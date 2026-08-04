---
status: active
---

# infographic — what survives the port to the HyperFrames spine?

Started 2026-08-04. Protocol follows `explore/2026-08-02-script-loop-graph/`.

## The question

NOLAN does **not** lack an infographic pipeline. It has one, wired to the path that was
superseded:

- **The engine** (2026-01-10, `docs/plans/2026-01-10-infographic-render-service.md`):
  `@antv/infographic` behind an Express service with a job queue —
  `render-service/src/engines/infographic.ts` (977 lines), `src/nolan/infographic_client.py`,
  `src/nolan/infographic_icons.py`, live CLI commands `nolan infographic` /
  `nolan render-infographics`, theme packs (`brand-*`, `docu-*`), SVG + PNG export.
- **The accumulation model** (2026-07-06, IMPLEMENTATION_STATUS "infographics that ACCUMULATE"):
  the motif layer, `nolan/motion/motifs.py` — `scene.motif = {id, delta}`, base + settled deltas
  + `isNew`, contract "render accumulated items statically, animate only isNew".

Both sit on the legacy Director/`scene_plan.json`/render-service path. **Nothing in
`src/nolan/hyperframes/` or the HF bridge references either.**

So the question is not "should we build infographics" but:

> **Of the infographic capability NOLAN already has, what survives the move to the HF spine —
> and which AntV structures can wear a NOLAN theme?**

## Why this is explore and not a feature branch

The plumbing needs no exploration — there is no new renderer, no new interpreter, no subprocess.
(Contrast `math-animation`, which forced a second conda env and earned its heavy phase 1.)

What needs exploring is **taste**, because it does not have one right answer. Freezing a registry
before the vocabulary stabilises freezes the wrong vocabulary — the `WIRING_CHECKLIST`
"characterise before wiring" rule.

## Three findings that shaped the design

1. **No service is needed.** The Jan-2026 architecture is Express + job queue + polling because
   *Remotion* needs a server. AntV ships a UMD browser bundle (`dist/infographic.min.js`, 605 KB)
   exporting `AntVInfographic.renderSVG`. HyperFrames already renders in a headless browser, so
   the integration is a `<script src="vendor/...">` tag — **exactly how `geo` and `diagram`
   already load d3** — and GSAP animates the resulting SVG DOM. No subprocess, no marshalling,
   no port 3010. This deletes rather than ports `infographic_client.py`.

2. **It is seek-safe by construction.** `@antv/infographic` renders SVG via `createElementNS`
   (canvas only for text measurement and PNG export) and contains **zero `requestAnimationFrame`**
   — 3 `Math.random` hits in the whole source, in `uuid` and `padding`, neither pixel-affecting.
   That satisfies the house rule at `compose.py:2343`: static geometry from the library, motion
   from GSAP.

3. **The icon path is dead at both ends** (probed 2026-08-03):
   - `infographic.antv.vision/icon` — the URL hardcoded in `IconResolver` — returns **HTML**, not
     JSON. `_parse_icon_response` throws into a bare `except`, so every icon silently resolves to
     `None` and infographics render iconless at **exit code 0**.
   - `weavefox.cn/api/open/v1/icon` — what the library itself calls — returns `code:429` plus
     `"此接口将于 2026-06-30 下线"`, i.e. past its own shutdown date.

   Icons must be **vendored locally**. This is independent of the version upgrade.

## Phases

**Phase 0 (this) — does it wear our clothes?** Upgrade, render in-page, theme from NOLAN tokens,
and test **adversarially**. No pipeline wiring, no registry, no block.

The test design matters more than the count. Picking easy structures gives a false green light:
`list-row` / `list-column` / `chart-bar` will pass trivially **and** are exactly what NOLAN
already has as `bullet_list` / `ledger` / `chart`. So:

| case | structure | proves |
|---|---|---|
| trivial | `list-row` | the pipe works at all |
| **wanted** | `list-pyramid` / `sequence-roadmap-vertical` | real value — NOLAN has no block for it |
| **loud** | `sequence-ascending-stairs-3d` | the theming **floor** |

The theme surface is `ThemeSeed {colorPrimary, colorBg, isDarkMode}` + palette + text attributes.
That retheme **colour and type**; it cannot retheme **geometry**. `sequence-ascending-stairs-3d`,
`sequence-cylinders-3d`, `sequence-zigzag-pucks-3d`, `sequence-color-snake-steps` are
style-as-shape — a NOLAN theme can recolour a 3D isometric staircase but cannot make it not one.

**So the verdict of phase 0 is a per-structure PARTITION, not a boolean.** That partition is the
adoption list.

**Phase 1 — the temporal model.** Port the motif contract (accumulate statically, animate only
`isNew`) onto whichever structures survive phase 0.

**Phase 2 — promotion.** Registry entry + block + gate + skill, per `docs/WIRING_CHECKLIST.md`,
only for the surviving set.

## Files

| file | what |
|---|---|
| `render_svg.mjs` | AntV spec → SVG string, headless. The whole "engine". |
| `theme_bridge.py` | NOLAN theme tokens → AntV `ThemeConfig` |
| `cases.py` | the adversarial three, as specs |
| `RESULTS.md` | **the verdict** — the per-structure partition |

## Run it

```bash
node explore/2026-08-04-infographic/render_svg.mjs <spec.json> <out.svg>
```

## Deliberately not decided here

Whether AntV ends up a **runtime dependency** or a **geometry oracle** (take its layout, own the
rendering — the relationship `diagram` has with d3). Its velocity argues for the latter: 33
versions in 9 months, still pre-1.0, and the repo was 12 releases behind before this. Phase 0's
stills decide it on evidence.
