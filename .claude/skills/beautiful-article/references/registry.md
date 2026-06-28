# Figures as a registry — reuse by name

The figure library is exposed as a **shadcn-style registry** (`registry.json` at the skill
root). This makes figures a searchable, install-by-name catalog — and lets the heavy Tier-1/2
figures be added **only when an article needs them** (so the default scaffold stays lean and
every article's `tsc` passes without mermaid/recharts installed).

## Two human/machine indexes
- **`references/figures.md`** — the human catalog (intent → figure). Read this at plan time.
- **`registry.json`** — the machine index. Each item lists its files + npm `dependencies`.

## Tiers
- **Tier 0 · core figures** (`figures-core`): ship with the scaffold (`article/figures/`),
  no extra deps, theme-portable. Import from the barrel: `import { StepFlow } from "../figures"`.
- **Tier 1 · Mermaid** (`figure-mermaid`): structured-diagram long tail. **On demand only.**
- **Tier 2 · Chart** (`figure-chart`): real data charts (Recharts). **On demand only.**

## Add a Tier-1/2 figure when the plan calls for it
When `plan/plan.md` resolves a visual to `figure:mermaid` or `figure:chart`, add it (installs
the npm dep + copies the file into `article/figures/`):

```bash
node <skill>/scripts/add-figure.mjs figure-mermaid   # installs mermaid + drops Mermaid.tsx + _theme.ts
node <skill>/scripts/add-figure.mjs figure-chart      # installs recharts + drops Chart.tsx + _theme.ts
```
(The skill's helper is the local equivalent of `npx shadcn add @beautiful-article-figures/<item>`
if the registry is hosted.) Then import the figure **directly, not from the barrel**:
`import { Mermaid } from "../figures/Mermaid"` / `import { Chart } from "../figures/Chart"`.

## Cost note (so you choose deliberately)
- Tier 0: ~0 added weight.
- **Tier 1 (Mermaid): ~+3.7 MB** to the single-file output when used — mermaid is bundled for
  offline. Reserve it for diagrams the core figures genuinely can't express.
- Tier 2 (Chart): ~+0.5 MB. Fine for a real chart; don't use it for a 3-bar comparison a
  `ProportionBar` or `CompareCards` already covers.

## Growing the registry
Promote a strong bespoke Raw into a new `registry:component` item (files + intent in `meta`),
add a row to `figures.md`, and it's reusable + addable-by-name everywhere after.
