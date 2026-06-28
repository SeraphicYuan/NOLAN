# Figures — reuse before you hand-write Raw

**The single biggest cost in a build is re-inventing the same diagrams as bespoke `Raw`
in every section.** Most "Raw" is one of a handful of recurring shapes — a flow, a
hub-and-spoke, a comparison, a contrast, a card grid, a proportion bar. Those are now
**reusable figure components** that take data and style themselves from theme tokens
(so they restyle per theme automatically, exactly like reacticle's own components).

## The tiering (apply in order)

1. **Figure first.** If a visual matches one of the archetypes below, use the figure —
   supply *data only*, no layout code. Cheaper, consistent, pre-tested (responsive /
   token-correct / theme-portable).
2. **Compose primitives** (`Card / Chip / Sticker / NumberBadge / Arrow / FStack / FRow /
   FGrid / FLabel / Highlight`) for a semi-novel visual. Still token-correct by construction.
3. **Raw, last.** Only for the *signature*, genuinely can't-be-templated visual of the
   article (one or two at most). This keeps the raw-policy goal — Raw stays special — while
   killing the per-section re-invention tax.

Figures live in `article/figures/` (shipped by the scaffold). Import from the barrel:
`import { StepFlow, HubSpoke, CompareCards, VersusPair, CardGrid, ProportionBar } from "../figures";`

> **Token rule (enforced):** figures + primitives use ONLY generic `--ra-*` tokens
> (`--ra-color-accent-soft` etc.) — never theme-locked tokens like `--mc-yellow`. That is
> what makes them portable across all themes. When you compose primitives, do the same.

## Catalog (search by intent)

| Figure | Communicates (intent) | Data shape (props) | Replaces bespoke Raw like |
|---|---|---|---|
| `StepFlow` | a **sequential process / pipeline** (horizontal or vertical), optional final "result" | `steps: {badge?, title, body?, tag?}[]`, `direction?`, `terminal?: {title, body?}` | progressive disclosure, an activation/workflow flow |
| `HubSpoke` | **one-to-many connection** — one center reaching many sources | `center:{label,sub?}`, `nodes:{label,sub?}[]`, `busLabel?`, `centerTone?`, `nodesTitle?` | a client/server or protocol bus, an integration hub |
| `CompareCards` | a **comparison across N items** that would clip as a wide table | `items:{name, tag?, fields:{label,value}[]}[]` | a multi-column comparison table |
| `VersusPair` | an **A-vs-B contrast** | `left/right:{sticker?, title, body?, items?}`, `connector?` | ephemeral-vs-persistent, this-vs-that |
| `CardGrid` | a **grid of annotated cards** (checklists, permission chips) | `cards:{sticker?, title, subtitle?, items?, chips?:{label,on?}[], footnote?}[]`, `min?`, `lead?` | feature/track cards, agents-with-tools, option cards |
| `ProportionBar` | **relative size / capacity** | `segments:{label, sub?, weight, dashed?, hatch?, tag?}[]`, `caption?` | a capacity/quota/before-after bar |
| `Timeline` | **sequence of events over time** | `events:{date?, title, body?, badge?}[]` | a roadmap / history / step list with dates |
| `Stat` | **big-number callouts (KPIs)** | `items:{value, label, sub?, delta?:{dir:"up"\|"down", text}}[]` | headline metrics, a stats row |
| `PullQuote` | **decorative typographic quote** | `children`, `cite?` | a large pull-quote (NOT an attributed `Quote`) |

**Inline (used inside prose `<p>`):**
| Component | Communicates | Props |
|---|---|---|
| `Term` | **inline glossary** — define jargon on hover/focus | `def`, `children` (the word) |
| `Footnote` | **inline footnote / citation** — note on hover/focus | `marker?` (number or ●), `children` (the note) |

(Accordion / collapsible Q&A is already a first-class reacticle component: `Detail`. `Term`/`Footnote`
use a pure-CSS hover/focus popover — offline + SSR-safe, no JS.)

## Tier 1 & 2 — on-demand add-ons (see `references/registry.md`)

The six above are Tier 0 (ship with the scaffold, ~0 added weight). For shapes they can't
express, two **on-demand** figures exist as registry items — add them only when a plan resolves
to them (installs the npm dep + drops the file): `node <skill>/scripts/add-figure.mjs <item>`.

| Add-on | Intent | Covers | Cost when used |
|---|---|---|---|
| `figure-mermaid` → `Mermaid` | structured diagram (long tail) | flowchart, sequence, state, ER, gantt, timeline, mindmap, sankey, quadrant, class, kanban, xychart | **~+3.7 MB** (mermaid bundled for offline) — reserve for what the core figures can't do |
| `figure-chart` → `Chart` | real data visualization | line / bar / area charts of actual numbers | ~+0.5 MB (Recharts) — not for a 3-bar comparison ProportionBar already covers |

Both are themed from `--ra-*` tokens and render offline. Import them **directly** (not via the
barrel): `import { Mermaid } from "../figures/Mermaid"` / `import { Chart } from "../figures/Chart"`.

## How to select (do this at PLAN time)

In `plan/plan.md` Outline, for every visual a section needs, **name the figure** instead of
"needs Raw: yes". Resolve by intent: *sequential* → StepFlow · *one-to-many* → HubSpoke ·
*comparison* → CompareCards · *contrast* → VersusPair · *grid of cards* → CardGrid ·
*proportion* → ProportionBar · *collapsible Q&A* → Detail. Only write "Raw (bespoke)" when
nothing fits and the visual is the article's signature.

## Growing the library (promotion loop)

When you *do* hand-build a strong bespoke Raw that's clearly a general shape, promote it:
generalize to a data-prop component in `article/figures/`, add a row here, and it becomes
reusable for every future article. (Same spirit as promoting a discovered technique to a
NOLAN template.) The library should ratchet up; per-article visual code should trend toward zero.
