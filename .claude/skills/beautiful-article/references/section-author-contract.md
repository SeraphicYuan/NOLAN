# Section author contract (read this once; don't re-paste it into prompts)

Every section is `article/sections/NN-*.tsx`, exports one `Section` component, owns only its
own file. This file is the single source of truth a section author (or subagent) needs.

## Components (import from "reacticle")
- Structure: `Section index title`, `Subsection index title` (subsection index prefix = NN),
  `Conclusion`. Prose = `<p>`; lists = `<ul><li>`.
- Emphasis: `<strong>` ONLY. **Never `<em>`/italics** (banned by warm/serif themes).
- Accents (use only when the content *is* that thing): `Aside tone="note|principle|capability|warning" label="…"`
  (ALWAYS an explicit English label), `Quote who? source?`, `CodeBlock language title code`,
  `Table caption columns rows` (column field is `label`, not `header`), `Detail summary` (collapsible).

## Visuals — figures first (see references/figures.md)
1. **Figure** for any recurring shape: `StepFlow / HubSpoke / CompareCards / VersusPair /
   CardGrid / ProportionBar`. Import `from "../figures"`, supply *data only*. Wrap in
   `<Raw title="caption"><Figure …/></Raw>` for a caption.
2. **Compose primitives** (`Card / Chip / Sticker / NumberBadge / Arrow / FStack / FRow /
   FGrid / FLabel / Highlight`, also from `../figures`) for semi-novel visuals.
3. **Raw (bespoke)** only for the article's one signature visual.

## Token rule (hard)
Style only via generic `--ra-*` tokens (color/space/radius/text/font families), always with a
`var(--x, fallback)`. **Never theme-locked tokens** (e.g. `--mc-yellow`) — they break other
themes. Figures/primitives already obey this; if you write any inline style, do the same.

## Hard rules
- Prose-first: the section is mostly `<p>`. Components/figures are accents.
- One file = one Section. `index="NN"` exactly (main agent assigns it). Don't touch Article.tsx.
- TS strict: no unused imports/vars, no `any`, type local arrays.
- SSR-safe figures/primitives (no state). Faithful to source; code verbatim; don't invent facts.

## Self-check before done
Outline task done? retention met? connects to neighbors? not over-componentized? enough prose?
every figure/Raw serves a specific paragraph? numbering self-consistent? no `<em>`, no
theme-locked tokens, all Asides labelled in English?
