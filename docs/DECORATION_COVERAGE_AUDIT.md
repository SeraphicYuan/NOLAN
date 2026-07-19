# Decoration coverage audit — theme ⇄ mapped-template full decorative lists (2026-07-19)

**The question that prompted this:** when the new-device backlog was built, did we go through the FULL
decorative-element list of each reference template every theme maps to? **Answer: no** — the backlog was
built from the *aggregate* gap analysis and assigned signature devices under a ≤3-device clutter cap. This
is the honest per-theme, per-template coverage check, run against the cloned reference repo
(`zarazhangrui/beautiful-html-templates`, at `/mnt/d/tmp/bht-templates`). Each of the 26 non-port themes'
mapped templates' `### Decorative Element Types` sections were unioned and every element classified against
the finished schema-v2 stack (Layer-1 type / Layer-2 color / Layer-3 shape / Layer-4 card+bar+bullet-marker
/ the 24 decoration devices / the 9 archetypes / the content blocks) or marked a GAP.

(blue-professional + vellum are ports OF reference templates → ~100% by construction; not re-audited.)

## Per-theme coverage

| Theme | Coverage | Theme | Coverage |
|---|---|---|---|
| monochrome-print | 92% | forest-ink | 75% |
| newsroom | 83% | neubrutalism | 75% |
| bold-signal | 82% | paper-press | 74% |
| split-canvas | 82% | indigo-porcelain | 73% |
| swiss-ikb | 81% | aurora-mesh | 70% |
| dune | 80% | warm-keynote | 69% |
| electric-studio | 79% | chalk-garden | 65% |
| midnight-press | 79% | blueprint | 63% |
| kraft-paper | 78% | neon-cyber | 63% |
| sunset-zine | 79% | pastel-dream | 62% |
| bauhaus-bold | 71% | creative-voltage | 59% |
| dark-botanical | 71% | terminal-green | 52% |
| highlighter-editorial | 71% | vintage-editorial | 71% |

**Mean ≈ 73%.** So even with all four schema-v2 layers + 24 decoration devices, a theme carries ~¾ of its
mapped templates' decorative vocabulary. The missing quarter is NOT more decoration devices — it clusters
into a small number of *systemic* gaps.

## ✅ SHIPPED 2026-07-19 — the systemic gaps built as UNIVERSAL primitives

Per the "universal capability vs theme signature" call: Tier 1–3 are content/composition primitives (not
theme signatures), so each was built ONCE at the engine level and is auto-painted 28 ways by the token
layers — closing its gap for ALL affected themes at once, not per-theme.

- **accent-stub rule** (22 themes) — `.kick::after`, a universal detail; the kicker→headline beat bar in
  every theme's `--accent`. (commit 0a3b50d)
- **pull-quote block** + **numbered-list** (17 / ~10 themes) — a new `pull_quote` block (quote-mark + display
  quote + cite) and a `bullet_list numbered:true` variant (01/02 ordinals). (9c7af1b)
- **comparison-table** + **ledger/index-list** archetypes (~14 themes) — the two macro-layouts; the
  comparison_table also lands the **pill/status-CHIP** primitive (correcting the earlier `pill = n/a`). (6c6be50)
- **highlight-mark** — found already covered by the existing `.hl` operative highlight (the audit agents
  didn't know it existed); highlighter-editorial's yellow accent makes `.hl` its namesake highlighter.
- **connector-arrow** (4 themes) — deferred as niche.

Each is a specimen now, so the theme books + samples matrix show it, and any theme can author it. Mean
coverage lifts from ~73% toward the high-80s across the board. Remaining are Tier-4 theme-scoped niches.

### ✅ Tier-4 signatures shipped via the 6 new Tier-1 themes (2026-07-19)

The theme-scoped niches don't build "once" — they ship as a new theme's signature device. Building the 6
Tier-1 gap-filling themes delivered these Tier-4 items along the way (each is a `_DECOR_RENDERERS` entry +
decorations.json + a theme's `decoration:[...]`):

- **hand-script font role** (4) — delivered by **scatterbrain**'s Caveat, routed through the `--font-mono`
  slot (loader scans only display/body/mono) as the kicker/caption voice.
- **pastel sticker ornaments** (kawaii) — `stickers` (daisy/star/cloud, daisy-days) + `pushpins` (tacked
  sticky notes + tape, scatterbrain).
- **pixel-face + pixel-landscape** (8-bit family) — `pixel-face`, `pixel-landscape` (8-bit-orbit).
- **window-bevel raised/sunken** (retro-windows) — `window-bevel`.
- **petal-cluster** + **rosette-seal** (vintage-JP) — sakura-chroma.
- **safety-pin** (field-notebook) — hand-drawn off-axis pins (pin-and-paper), over the shared `grain`.

- **metric-change delta chip** — shipped as a UNIVERSAL stat sub-field (not theme-scoped): `delta={dir,value}`
  on a stat item → ▲/▼/→ chip in --positive/--negative. The one Tier-4 niche with a universal consumer.

Still open Tier-4 (not tied to a shipped theme, build when their theme is the priority): rotation/tilt knob,
color-swatch row, drafting guide line, block-stamp 2×2, diagonal-clip, zigzag, QR-tile, marquee, tree-view,
RSVP form-field, toggle, card notch, orbit/radial.

## Ranked cross-theme gap backlog (by # of themes it blocks × build cost)

### Tier 1 — cheap + near-universal (build first)
1. **accent-stub rule** — **22 / 26 themes.** The short accent bar in the kicker↔headline beat (28–60px,
   sometimes with a hard-offset shadow). We have the `--rule` token and `double-rule` (a 2-line device) but
   NO short single free-standing accent stub. A ~10-line decoration device. **Highest ROI in the whole audit.**
2. **numbered-list (01 / 02 ordinals)** — **~10 themes.** `bullet_list` only does glyph markers; the decks
   want CSS-counter leading-zero ordinals. A cheap `bullet_list` variant (`marker: "ordinal"`).
3. **connector / flow arrow** — **~4 themes.** A clean typographic arrow between steps (distinct from the
   hand-drawn `scribbles` arrow). Cheap glyph/marker.

### Tier 2 — medium build, high value
4. **pull-quote block + quote-mark glyph** — **17 / 26 themes.** An oversized decorative quote glyph + quoted
   body + attribution. `statement` covers a manifesto, not an *attributed pull-quote*. A new block (and the
   glyph doubles as a scene decoration).
5. **highlight-mark (inline marker swipe)** — **6 themes, incl. highlighter-editorial's NAMESAKE.** The neon
   `<mark>` swatch behind headline/body words. We have no inline-emphasis primitive — the theme literally
   named for it can't render its identity element. A type/scene primitive.
6. **pill / status-chip component (states: yes / partial / no, + tags)** — **~6 themes.** ⚠️ This **corrects
   a wrong call**: Layer 4 marked `pill` **n/a** ("definitionally round, no axis"). The decks use pills
   pervasively as *state chips* and *tags* — the gap is the chip's fill/border/state semantics, not its
   radius. `pill` should be reclassified from n/a → a real Layer-4 component to build.

### Tier 3 — the archetype family (bigger build, broad value; already flagged by REFERENCE_TEMPLATE_ANALYSIS)
7. **comparison / matrix TABLE + ledger / index-list archetypes** — **~14 themes.** Two macro-layouts the
   analysis already recommended (§2): a real header-row × row-label × cell *matrix* (with state pills), and a
   dense hairline-separated *ledger/index* row-list (numeral · title · desc · meta). `split-screen` ≠ a table;
   `swiss-grid` ≠ a ledger. This is the single biggest *structural* gap.

### Tier 4 — theme-scoped niche (build when that theme is the priority)
- hand-script font role (4) · rotation/tilt knob on badges/cards (3) · color-swatch row (3) · metric-change
  delta chip (3) · drafting guide line (3) · block-stamp 2×2 mark (2) · pixel-face + pixel-landscape (3,
  8-bit family) · window-bevel raised/sunken (2, retro-windows) · diagonal-clip cover panel (2) · zigzag
  pattern (2) · pastel sticker ornaments — daisy/star/sun/cloud/rainbow (2, kawaii) · QR-tile (5, niche) ·
  marquee ticker · tree-view · RSVP form-field (3) · toggle switch (2) · card notch/tab · orbit/radial layout.

## What this means

The decoration new-device backlog was the right move but **not** a coverage-complete pass — it filled the
*canvas-furniture* gaps (compass-rings, tape, starfield, os-chrome, …), which is why coverage is ~73% and
not ~50%. The remaining gaps are mostly **NOT decoration devices** — they're a handful of missing
**primitives** (accent-stub, quote, highlight-mark, numbered-list, pill-chip, arrow) and two missing
**archetypes** (table, ledger). Building the Tier-1 + Tier-2 items (all small except the table archetypes)
would lift mean coverage from ~73% into the high-80s and, more importantly, close the identity gaps
(highlighter's highlight-mark, the universal accent-stub, editorial themes' pull-quote).

Source data: the 5-agent classification pass (2026-07-19) over `/mnt/d/tmp/bht-templates`. Method: union each
theme's mapped-template `Decorative Element Types`, classify vs the stack, GAP = distinctive quality not
reproducible by any layer.
