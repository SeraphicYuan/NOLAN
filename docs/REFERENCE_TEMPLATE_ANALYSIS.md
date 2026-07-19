# Reference-template analysis — `zarazhangrui/beautiful-html-templates` → NOLAN

34 hand-authored slide-deck templates studied (all 34 `index.json` entries + all 34 `design.md` specs +
a visual pass over cover + content screenshots) to answer three questions: **themes to add**,
**archetypes to add**, and the **decoration vocabulary** that feeds the composition-DNA lever #3
(signature decoration). Their architecture ≠ ours (each of their templates *integrates* layout + type +
decoration + palette into one hand-made identity; we *separate* archetype-layout from theme-paint), so
the value is stealing their **ideas** (decoration devices, layout grammars) into our deterministic
composer — not cloning their monolith templates.

---

## 1. Themes worth adding (distinct characters our 26 don't cover)

17 of their 34 map cleanly to one of our themes (skip). These are genuine gaps, tiered:

**Tier 1 — unmistakably new, high value**
1. **Windows-95 desktop-OS chrome** (`retro-windows`) — beveled windows, title bars, group-boxes. No analog.
2. **Pixel-art CRT arcade** (`8-bit-orbit`) — pixel-grid, scanlines, hard 4/8px stacked shadows. `neon-cyber` is dark-neon but not *pixelated*.
3. **Vintage-Japanese product catalogue** (`sakura-chroma`) — cream + 6 primaries, petal blobs, ribbon bands, starburst seals, spec checkboxes.
4. **Post-it corkboard brainstorm** (`scatterbrain`) — sticky notes on cork, thumbtacks, masking tape, doodles.
5. **Field-notebook / pinned-paper** (`pin-and-paper`) — legal-pad yellow, hand-drawn safety-pins, Caveat marginalia.
6. **Childlike storybook / kawaii** (`daisy-days`) — hand-drawn daisies/suns/rainbows cropping past edges, Fredoka.

**Tier 2 — distinct sub-genres, worth adding**
7. **Nocturnal couture luxe** (`pink-script`) — hot fuchsia on warm-black, DM Serif to 600px, film-grain + neon halo.
8. **WPA / protest poster** (`peoples-platform`) — cobalt+amber+red, letterpress 3D text-shadow, screen-print grain.
9. **Pill / Memphis candy** (`capsule`) — universal `radius:9999px` geometry + 2px ink outline, confetti pills.
10. **Fashion-masthead playbill** (`emerald-editorial`) — Bodoni to 460px + a signature *double-rule* bracketing device.
11. **Stencil / municipal-signage** (`stencil-tablet`) — Stardos Stencil, numerals to 540px, tablet color-blocks.
12. **Single-hue art-biennale** (`biennale-yellow`) — one solar yellow flooding parchment, radial sun-bloom, zero shadows.

**Tier 3 — nuanced, lower urgency:** mid-century warm-material (`mat`), graph-paper riso trend-report
(`cobalt-grid`), monochromatic colorfield (`vellum`), one-warm-ink riso program (`long-table`), green-riso
collage zine (`retro-zine`).

**Map-to-existing (skip):** block-frame/raw-grid/creative-mode→neubrutalism; neo-grid-bold→highlighter;
studio→electric-studio; monochrome→monochrome-print; editorial-forest/grove→forest-ink; cartesian→
vintage-editorial/paper-press; signal→midnight-press; blue-professional→swiss-ikb/warm-keynote;
soft-editorial→pastel-dream; coral→sunset-zine/split-canvas; bold-poster→bold-signal; broadside→newsroom;
playful→sunset-zine.

---

## 2. Archetypes worth adding (macro-layouts our 8 don't cover)

Our 8: centered-hero, editorial-column, swiss-grid, split-screen, full-bleed-overlay, focal-card,
sidebar, framed.

**Genuinely new macro-layouts — recommend adding as archetypes 9–11:**
- **A · Timeline / process-flow** — a *sequence* of nodes on a rail/arrows with directionality. In nearly
  every deck (`8-bit-orbit`, `blue-professional` 4-step, `capsule`, `stencil-tablet`, `monochrome` spine,
  `coral`). None of our 8 encodes sequence + connectors. **Highest-value gap for essays** (chronology, how-it-works).
- **B · Comparison-table / matrix** — header row + row-labels + heterogeneous cells + status pills
  (`neo-grid-bold`, `pink-script`, `stencil-tablet`). Not `swiss-grid`'s uniform item-cards.
- **C · Ledger / index-list** — dense hairline-separated rows (`numeral + title + description + meta`),
  subsumes TOC/agenda (`cobalt-grid`, `long-table`, `emerald-editorial`, `cartesian`, `monochrome`). Distinct
  from `swiss-grid` (2D cards) and `editorial-column` (prose).

**First-class VARIANTS (not new macro-layouts):**
- **Stat-wall** — 3–6 big numerals dominating (a `swiss-grid` param). **Resolves F2**: `stat` is a single
  *callout* (left/editorial), stat-wall is the grid version — so reclassify `stat`, add stat-wall as the
  grid variant rather than forcing `stat`→centered-hero.
- **Pull-quote** — dead-center + oversized quote-mark glyph + attribution (a `centered-hero` mode; universal).
- **Chapter-divider** — an oversized ordinal + short title (`focal-card`/`centered-hero` variant); worth a beat name.
- Team/people-grid → `swiss-grid` instance; two-column body → `split-screen`; cover-metadata-corners → a cover convention.

---

## 3. Decoration vocabulary → the lever-#3 architecture (key deliverable)

Every `design.md` declares a "Decorative Element Types" list. Consolidated across 34, ~60 devices in **10
motif groups**:

| Group | Devices |
|---|---|
| **G1 rules/stubs** | full hairline · short accent-stub (kicker↔headline beat, 28–80px) · heavy structural rule (3–6px) · top/bottom framing hairlines |
| **G2 corner marks** | L-corner brackets · interior margin frame (inset 36–48px) · 2×2 corner block-stamp |
| **G3 shapes** | concentric rings / dashed compass arcs · radial bloom/glow (depth in shadowless systems) · organic blobs |
| **G4 background ordinals** | giant numeral/char behind content at low opacity (chapter identity + region fill) |
| **G5 stripes/ribbons** | diagonal hatch · multi-color ribbon bands · scanlines · zigzag |
| **G6 grain/texture** | fractal grain · halftone dots · graph-paper grid · faint dot-grid — **near-universal, declared NON-optional** |
| **G7 numbered chips** | step circles/nodes · list markers (01/02) · catalogue/edition numbers · `NN/NN` page counter |
| **G8 figurative** | hand-drawn nature · safety-pins · thumbtacks+tape · doodles · rubber-stamp/seal marks · mascot/OS glyphs |
| **G9 depth** | hard offset shadow (zero-blur, ~12 templates) · stacked letterpress text-shadow · bevels · tilt/rotation |
| **G10 pills/labels** | eyebrow pill · status pills (yes/partial/no) · vertical rotated rail-label · corner pin-note |

**Architecture this implies for a per-theme signature-decoration system:**
1. **Decoration is identity, not garnish** — most systems declare their texture (G6) + signature mark
   (G8/single-device) as *non-optional*. ⇒ a theme should carry: (a) a required ground **texture**, (b) 1–2
   **signature devices**, (c) a **marker convention** (bullet/ordinal/page-counter style).
2. **Shared parameterized primitives** (one executor, palette/weight varies per theme): **G1 rules/stubs,
   G4 background-ordinal, G7 numbered-chips/page-counter, G9 offset-shadow+tilt, G10 pills/rail-labels.**
   These are the "editing/motion-registry"-style reusable executors.
3. **Theme-scoped identity primitives** (assigned per theme, not global): **G3 blooms/blobs, G5
   ribbons/hatch, G8 figurative ornaments, and the single-template signatures** (emerald's double-rule,
   cobalt's glitch-column, sakura's petal-cluster/rosette, universal oversized quote-mark).

⇒ Lever #3 = a **decoration registry** (like `nolan.motion` / `nolan.effects`): shared primitives (G1/G4/
G7/G9/G10) parameterized by theme tokens, + a per-theme `signature` declaration (texture + 1–2 devices +
marker convention) drawn from G3/G5/G6/G8. Wired into the composer as gated `ground.decoration` /
scene-level decoration, honesty-tested against the registry.
