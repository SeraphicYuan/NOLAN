# Theme decoration map — evidence-based signature decoration (lever #3 enrichment)

Instead of assigning decoration devices generically, each theme is **mapped to its related reference
templates** (from the 34-template study, `docs/REFERENCE_TEMPLATE_ANALYSIS.md`), and its `decoration`
is **aggregated from those templates' declared decorative elements**, expressed with the devices in
`themes/composition/decorations.json`. Rule: ≤1 texture + 1–2 marks (avoid double-texture / clutter);
themes whose mapped templates are deliberately clean stay bare.

## Theme → mapped reference templates → devices

| Theme | Mapped reference template(s) | Their decoration → our device(s) |
|---|---|---|
| aurora-mesh | biennale-yellow, pink-script | radial bloom → `glow` |
| bauhaus-bold | bold-poster, neo-grid-bold, studio | corner marks + oversized numeral → `corner-brackets`, `background-ordinal` |
| blueprint | cobalt-grid, cartesian | graph-paper grid + corner → `graph-paper`, `corner-brackets` |
| bold-signal | bold-poster, peoples-platform | pillar panel + numeral → `interior-frame`, `background-ordinal` |
| chalk-garden | playful, daisy-days, pin-and-paper | scribble/blob + chalk dust → `grain`, `blob` |
| creative-voltage | creative-mode, 8-bit-orbit | electric frame + scanline → `interior-frame`, `scanlines` |
| dark-botanical | pink-script, vellum, mat | hairline magazine frame + rail → `grain`, `interior-frame`, `rail-label` |
| dune | vellum, monochrome | sand/paper texture → `grain` |
| electric-studio | blue-professional, studio | cover dots → `dot-grid` |
| forest-ink | editorial-forest, grove | chapter number → `grain`, `background-ordinal` |
| highlighter-editorial | neo-grid-bold, studio | **bare** — the yellow highlight IS the identity (block-level) |
| indigo-porcelain | cartesian, monochrome | scholarly rail → `grain`, `rail-label` |
| kraft-paper | long-table, retro-zine, sakura-chroma | paper + rail + stamp → `grain`, `rail-label`, `seal` |
| midnight-press | broadside, signal, pink-script | catalogue number + terminal → `scanlines`, `background-ordinal` |
| monochrome-print | monochrome, studio | sophisticated minimal → `grain` |
| neon-cyber | 8-bit-orbit, retro-windows | pixel brackets + CRT → `scanlines`, `corner-brackets` |
| neubrutalism | block-frame, raw-grid, creative-mode | frame + oversized numeral → `interior-frame`, `background-ordinal` |
| newsroom | broadside, studio | edition number + newsprint → `grain`, `background-ordinal` |
| paper-press | cartesian, soft-editorial | magazine → `grain`, `rail-label` |
| pastel-dream | soft-editorial, daisy-days, capsule | soft shapes → `blob` |
| split-canvas | coral, playful | oversized numeral + playful → `blob`, `background-ordinal` |
| sunset-zine | retro-zine, coral, playful | ribbon bands + giant numeral → `ribbon`, `background-ordinal` |
| swiss-ikb | blue-professional, studio | **bare** — Swiss International Style, no ornament |
| terminal-green | retro-windows, 8-bit-orbit | scanline + pixel bracket → `scanlines`, `corner-brackets` |
| vintage-editorial | emerald-editorial, retro-zine, cartesian | stamp + numeral → `grain`, `seal`, `background-ordinal` |
| warm-keynote | blue-professional, soft-editorial | keynote dots → `dot-grid` |

## New-device backlog (mapped templates that want devices we DON'T have yet)

The mapping surfaced decorative elements our 12-device set can't yet express — the priority list for a
future lever-#3 device expansion (each ties to specific themes):
- **compass-rings** (cartesian → blueprint, indigo-porcelain) — concentric + dashed drafting arcs
- **letterpress-shadow** / **pillar-panels** (bold-poster → bold-signal, bauhaus) — stacked 3D text shadow
- **scribbles / doodles** (playful, pin-and-paper → chalk-garden) — hand-drawn SVG squiggles/stars
- **tape / thumbtack** (retro-zine, scatterbrain → sunset-zine, kraft-paper) — collage furniture
- **starfield** / **pixel-brackets** (8-bit-orbit → neon-cyber) — pixel-native marks
- **OS-chrome** (retro-windows → terminal-green) — title bar / bevel panels
- **rosette-seal** / **petal-cluster** (sakura-chroma → kraft-paper) — ornate stamp / floral mass
- **double-rule ornament** (emerald-editorial → vintage-editorial) — a word bracketed by two rules
- **drop-cap** (retro-zine, soft-editorial → sunset-zine, paper-press) — an oversized initial
- **diagonal hatch** (coral → split-canvas) — 45° line texture on color panels

These are the theme-scoped identity devices (per the schema); most map to 1–3 specific themes.

## ⚠️ REVISIT — this mapping covers only ONE layer

A reference `design.md`'s flat "Decorative Element Types" list actually spans **4–5 of our layers**; this
mapping (lever #3) enriched only the **canvas-wide signature** layer. Worked example (vellum, ~11
elements): `pin-annotation`/`chrome-bar`/`foot-bar` = canvas decoration (this layer — and even here I used
APPROXIMATE fits: `rail-label` ≈ pin-note, `interior-frame` ≈ hairline frame; the exact devices are in the
new-device backlog above); `kicker`/`display`/`stat-value`/`caption`/`label` = **Layer-1 type roles**
(only eyebrow wired so far); `pin-stat`/`bullet-list-numbered`/`bar-fill`/`chart-baseline`/`img-placeholder`
= **Layer-4 component tokens** (NOT built — hardcoded in block CSS today, unvaryable per theme);
`rule`(accent-stub)/`quote-mark` = **scene-scoped decoration** (NOT built); `compare-panel-pair` = the
split-screen archetype (built).

**So for EVERY theme's decoration here, revisit once the other layers exist:** (a) swap approximate
canvas devices for exact ones as the new-device backlog is built; (b) fold in the Layer-1 type-role
character; (c) add Layer-4 component treatments; (d) add scene-scoped devices (accent-rule, quote-mark).
The decoration mapping alone can't match a reference template's richness — it's ~1 of ~5 layers. See
`docs/THEME_TOKEN_SCHEMA.md` for the full layer plan.
