# beautiful-article — a NOLAN-native skill

This started as a fork of an open-source skill (ConardLi/garden-skills) but has been
substantially rebuilt and extended for NOLAN; it's now **our skill**, not a vendored one.
Articles it produces carry a "Made with **NOLAN**" colophon.

## What NOLAN added on top of the original

1. **Figure library** (`article/figures/`) — theme-portable, token-only, SSR-safe components,
   replacing hand-written Raw with data-prop figures. Tiering: **figure → primitives → Raw**.
   - Core (Tier 0): `StepFlow, HubSpoke, CompareCards, VersusPair, CardGrid, ProportionBar,
     Timeline, Stat, PullQuote` + inline `Term`/`Footnote` + primitives.
   - On-demand (Tier 1/2): `Mermaid` (diagrams), `Chart` (Recharts) — registry add-ons.
   - See `references/figures.md`.
2. **Registry** (`registry.json` + `references/registry.md` + `scripts/add-figure.mjs`) —
   the library exposed shadcn-style, reuse-by-name; heavy figures install on demand.
3. **Brand recolor** (`scripts/brand-theme.mjs` + `references/brand-theme.md`) — oklch palette
   from one seed color, keeping a theme's type + decoration.
4. **Offline + English by default** — embedded fonts (`scripts/embed-theme-fonts.py`),
   English UI (`scripts/patch-reacticle-i18n.mjs`), no remote font links, WSL-robust scaffold.
5. **Workflow** — figure-first resolved at plan time; consolidated `section-author-contract.md`.

## Decisions on record
- **Themes stay reacticle** (not shadcn): the 11 themes carry distinct typography + ~20–30
  per-theme component decoration rules each — shadcn's color-token model can't reproduce that
  faithfully. We borrow shadcn's *oklch color generation* (the brand recolor), not its themes.
- **MCP deferred**: the local registry + `add-figure.mjs` already covers in-skill discovery/
  install; an MCP server is only worth it if figures become a shared cross-project library.

See `ENHANCEMENTS.md` for the full change log + measured impact.
