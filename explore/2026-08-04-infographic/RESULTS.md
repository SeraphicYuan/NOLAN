---
status: phase-0 complete
---

# RESULTS — phase 0: does AntV wear NOLAN's clothes?

Run 2026-08-04, theme `highlighter-editorial`, `@antv/infographic@0.2.19`.
Evidence: `_out/highlighter-editorial/*.svg`, contact sheet `_out/sheet-highlighter.png`.

## Verdict

**Colour and type theming: PASS. Geometry: per-structure, as predicted.**

The pipeline works and is cheap. What it cannot do is retheme a shape — so the adoption list is a
partition, not a yes.

## What was proven

| claim | evidence |
|---|---|
| **No service needed.** | `renderToString(spec) -> string`, 40-line `render_svg.mjs`. Express + job queue + polling + puppeteer all deleted. |
| **No browser needed.** | 0.2.19's `./ssr` export renders through a `linkedom` shim. This **did not exist in 0.2.7** — the upgrade was load-bearing, not hygiene. |
| **NOLAN's theme lands.** | Every emitted colour is a NOLAN token: `#2b2d2c` ink, `#4c4e4d`, `#6b6d68` mute, `#e7e9e6` shell, `#fff200` accent. Every AntV brand hue (`#1783FF #00C9C9 #F0884D #D580FF …`) is **purged**. |
| **Zero remote references.** | `setDefaultFont(<NOLAN face>)` leaves the font registry empty, so the `<?xml-stylesheet href="https://assets.antv.antgroup.com/…">` preamble is never emitted. 8/8 artifacts, 0 refs. |
| **Text is addressable.** | Text renders as HTML inside `<foreignObject>`, so NOLAN CSS styles it and GSAP can animate per element — better than the opaque `<text>` nodes assumed. |

## The partition — this is the adoption list

| structure | verdict | why |
|---|---|---|
| `list-row` | **keep** | Neutral chevron strip. Geometry carries no style of its own. |
| `list-pyramid` | **keep, with a caveat** | The most neutral of the four — but it is plain cards in a hierarchy, which `layout` (arrange:`stack`/`triptych`) already expresses. Adopting it may buy nothing. |
| `sequence-roadmap-vertical` | **reject** | A literal ROAD with dashed lane markings. Skeuomorphic corporate infographic; no token changes this. |
| `sequence-ascending-stairs-3d` | **reject** | 3D isometric blocks with generated gradient shading (the greys are *not* from the palette — the structure injects its own). Style-as-shape, exactly the predicted floor. |

The two rejects are the two the theming *cannot* reach, and they are `wanted`/`loud` — so the
adversarial test design did its job. Had this run used `list-row` / `list-column` / `chart-bar`, it
would have returned a clean green light that transferred to nothing.

## Three defects found by LOOKING, not by a gate

1. **`themeConfig.colorPrimary` is not the colour lever.** The first bridge set it and produced
   byte-identical output. Reading the emitted colours showed `colorBg` and text fills DID land, but
   every item colour comes from **`themeConfig.palette`**, defaulting to AntV's 11 brand hues. The
   palette is what makes it look like AntV.

2. **A palette needs a separability floor.** The first ink palette used `surface` as its 4th
   colour; the stills showed step "04" as a near-invisible chevron and an unreadable roadmap node.

3. **WCAG contrast is the WRONG metric for that floor** — the second attempt at the fix. Against
   the `#E7E9E6` shell:

   | colour | contrast | OKLab distance |
   |---|---|---|
   | `surface` `#F1F3F2` | 1.10 | **0.031** — same colour |
   | `accent` `#FFF200` | 1.04 | **0.197** — clearly different |

   Contrast rejects both; distance separates them correctly. So the gate reuses
   `mathanim.style.MIN_ROLE_DISTANCE` (0.12, already calibrated) rather than inventing a threshold.
   Contrast still governs text legibility; distance governs "is that a distinct mark".

## The design finding that matters most for phase 1

**A cycling categorical palette conflicts with NOLAN's accent discipline.** In the `accent`
variant, items 1 and 4 both come out yellow because the 4-colour array wraps — which says nothing.
NOLAN uses the accent for **the one** thing being emphasised.

AntV's `Palette` type is `string[] | ((datum, index, count) => string)`, so the fix is expressible:
an **emphasis-aware palette function** — ink ramp for every item, accent for the authored
`emphasis` index only. That maps directly onto how NOLAN already authors a scene.

The `ink` variant is the better default for this theme's register regardless.

## Open, deliberately

- **Sizing.** Output is intrinsically sized (e.g. 460×245); `width`/`height` in the spec were
  ignored. NOLAN frames are 1920×1080, so fitting is on us — `_FIT_SCRIPT` already exists, untested
  here.
- **`#ffffff` survives** in every artifact (card fills). On a `#E7E9E6` shell that reads as a
  raised card, which may or may not be the theme's intent. One theme is not enough to tell.
- **One theme tested.** The partition is claimed for `highlighter-editorial` only. A dark theme is
  the obvious next probe, since the 3D structures' generated shading assumes a light ground.
- **Runtime dependency vs geometry oracle** — still open, and phase 0 nudges toward *oracle*:
  0.2.19 tightened `exports` enough to break a `require('@antv/infographic/package.json')` that
  worked in 0.2.7. 33 versions in 9 months, pre-1.0.

---

# RESULTS — #3: vector-figure extraction, PyMuPDF vs MinerU

Run 2026-08-04 against `render-service/_lab_hyperframes/videos/doc-pdf/assets/attention.pdf`
("Attention Is All You Need") — the paper whose Figure 1 is *literally* the example
`document/ingest.py` names as its known gap.

## Verdict: PyMuPDF closes it. MinerU is not needed.

`page.get_drawings()` + proximity clustering, ~60 lines, in the existing `nolan` env. No VLM, no
new conda env, no SAM3. This is the "deterministic code where correctness is computable" routing.

| page | figure | current ingest | with clustering |
|---|---|---|---|
| 3 | Fig 1 — Transformer architecture | **raster** ✓ already handled | — |
| 4 | Fig 2 — Scaled dot-product attention | **raster** ✓ already handled | — |
| 13 | Fig 3 — attention example | ✗ invisible | **recovered** 385×218pt, 17.3% of page |
| 14 | Fig 4 — two attention heads | ✗ invisible | **recovered** 382×518pt, 40.8% |
| 15 | Fig 5 — head behaviour | ✗ invisible | **recovered** 379×480pt, 37.5% |

Crop inspected (`_out/vecfigs/p13_v0.png`): Figure 3 extracted cleanly, token labels and
attention-weight lines intact, correctly bounded.

**A correction to my own earlier framing:** I said "most ML papers draw their architecture figures
as vectors, so the most important figure is the one NOLAN cannot extract." In *this* paper that is
false — Figures 1 and 2 are embedded raster, and already work. The real gap is the *analysis*
figures (3–5), which are vector. Still a genuine 3-figure gap on one paper, but the claim needs
restating: it is not "the architecture diagram is missing", it is "roughly half the figures are".

## Open

- **Caption↔cluster matching is 1/3.** Figures 4 and 5 report `UNMATCHED` because the matcher only
  looks for a cluster ABOVE the caption. Reported honestly rather than silently mis-assigned, but
  it needs the caption-above-figure case before this is promotable.
- **One paper is not a corpus.** Thresholds (`min_paths=4`, `min_area_frac=0.010`, `pad=12pt`) are
  fitted to a single document. Characterise across a set before wiring.
- Vector figures come out as **cropped PNG** here. Keeping them as vector (SVG) through to the
  composition would let GSAP animate their internals — strictly better, untested.
