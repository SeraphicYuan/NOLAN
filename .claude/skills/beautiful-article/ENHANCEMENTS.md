# beautiful-article — enhancements (case study from the "skills-explained" run)

These changes target the three inefficiencies found while running the skill end-to-end:
re-inventing visuals as bespoke Raw, a template that wasn't offline/English, and avoidable
per-run friction. All changes are additive.

## 1. Figure library (the big one) — `article/figures/` + `references/figures.md`

The skill used to make the LLM hand-write ~100 lines of styled JSX **per section** for every
diagram. In practice ~90% of those were one of six recurring shapes. Those are now reusable,
data-prop, **theme-portable** components:

| Figure | Replaces | Intent |
|---|---|---|
| `StepFlow` | progressive-disclosure, activation flow | sequential process |
| `HubSpoke` | MCP client/server bus | one-to-many connection |
| `CompareCards` | wide comparison table | comparison across items |
| `VersusPair` | ephemeral-vs-persistent, know-vs-do | A-vs-B contrast |
| `CardGrid` | subagent delegation, getting-started tracks | grid of annotated cards |
| `ProportionBar` | 200K + RAG capacity | relative size / capacity |

Plus `primitives.tsx` (`Card / Chip / Sticker / NumberBadge / Arrow / FStack / FRow / FGrid /
FLabel / Highlight`) for composing semi-novel visuals. Tiering is now **figure → primitives →
Raw** (Raw reserved for the one signature visual), documented in `references/figures.md`,
`references/section-author-contract.md`, and a pointer added to `raw-policy.md` /
`section-build.md`.

**Key property:** figures/primitives use only generic `--ra-*` tokens (`--ra-color-accent-soft`,
etc.) — never theme-locked tokens like `--mc-yellow`. So the same figure renders correctly in
all 11 themes. (The old bespoke Raw was freddie-locked.)

### Measured impact (refactoring the skills-explained article to use figures)
- Section code: **2,192 → 917 lines (−58%)**, and the remainder is mostly figure *data* +
  verbatim code blocks, not layout. The visual layout now lives once in the 749-line library.
- Theme-locked tokens in sections: **many → 0** (now portable across themes).
- Authoring cost: a section now supplies data (~10 lines) instead of writing a diagram (~100).
- The 6-section refactor was done by **one** agent (~71k tokens) vs the original 7 build agents
  (~190k); future builds drop further since layout isn't generated at all.
- Rendered output is visually equivalent (verified by screenshot) and still builds clean.

## 2. Offline + English by default — scaffold/template fixes

- `assets/scaffold-template/index.html`: removed the remote Google-Fonts `<link>` (it broke
  "opens offline") and the `lang="zh-CN"`. Default is now offline with system-font fallback.
- `scripts/embed-theme-fonts.py`: optional, theme-agnostic — embeds a theme's fonts as base64
  `@font-face` into `article/fonts.css` for exact typography offline (give it the theme's
  Google css2 URL).
- `scripts/patch-reacticle-i18n.mjs`: reacticle ships Chinese UI labels (TOC "目录", copy
  buttons, etc.); `scaffold.sh` now runs this automatically so the UI is English by default.
- `scaffold.sh`: now ships `article/figures/`, is robust on WSL/DrvFs (`--no-bin-links`
  fallback + `.bin` shims so `npm run dev/build` work), and typechecks via the direct `tsc`
  path. Eliminates the per-run rework cycle the original needed.

## 3. Investigated, deferred to upstream (with rationale)

- **Bundle size (~2 MB):** KaTeX is pulled into every article's bundle even with no `Formula`
  used, and a consumer-side `katex` alias does NOT strip it — so it's not removable downstream.
  Real fix = code-split Formula/katex in **reacticle** (upstream).
- **Static render / drop the React runtime:** would cut build time + file size dramatically,
  but is blocked by reacticle's CSS-in-JS-import architecture (component modules `import
  "./x.css"`), which node can't process outside a Vite SSR build. Recommend a `vite build
  --ssr` static mode upstream.

## 4. Figure tiers + registry (point 3 — tap external libraries by intent)

The house figures (Tier 0) cover the common shapes; two **on-demand** tiers cover the rest, and
the whole library is exposed as a **shadcn-style registry** so figures are reuse-by-name.

- **Tier 1 · `Mermaid`** (`registry/figures/Mermaid.tsx`): Mermaid text → themed SVG (flowchart,
  sequence, state, ER, gantt, timeline, mindmap, sankey, quadrant, …). Themed from `--ra-*`,
  renders offline (mermaid bundled). Validated: themed sequence diagram renders correctly.
- **Tier 2 · `Chart`** (`registry/figures/Chart.tsx`): Recharts line/bar/area, themed from
  tokens, `isAnimationActive=false` for static/print-safe render. Validated: themed bar chart.
- Both are **off the main barrel** and **install-on-demand** (so the default scaffold stays lean
  and a fresh `tsc` never breaks without the heavy deps). Add via
  `node scripts/add-figure.mjs figure-mermaid|figure-chart` (installs the npm dep + drops the
  file — the local equivalent of `npx shadcn add`).
- **`registry.json`** (shadcn schema) describes all items (files + npm deps + intent meta);
  `references/registry.md` documents consume-by-name + the **cost guidance**: Tier 0 ~0,
  **Tier 1 ~+3.7 MB when used** (mermaid is large — reserve it), Tier 2 ~+0.5 MB.
- Plan phase now resolves visuals to `figure:<id>` / `figure:mermaid` / `figure:chart` /
  `primitives` / `raw` at plan time (`plan-template.md` + `figures.md` in the Phase-2 reading list).

### Measured
- Lean article (Tier 0 only): **2,360 KB**. Adding the demo's Mermaid + Chart → 6,092 KB
  (mermaid ≈ +3.7 MB) — confirming the off-barrel / on-demand design is what keeps that cost
  opt-in. Both render themed + fully offline (0 external loads).

## Files changed
```
.claude/skills/beautiful-article/
  assets/scaffold-template/article/figures/   (new: primitives + 6 figures + index)
  assets/scaffold-template/index.html         (offline + lang=en)
  scripts/patch-reacticle-i18n.mjs            (new)
  scripts/embed-theme-fonts.py                (new, generalized)
  scripts/scaffold.sh                         (ship figures, i18n, WSL-robust install)
  references/figures.md                       (new: catalog + tiering)
  references/section-author-contract.md       (new: consolidated author rules)
  references/raw-policy.md, section-build.md  (pointers to figures-first)
  ENHANCEMENTS.md                             (this file)
```
Validation workspace: `beautiful-articles/skills-explained-build/` (article refactored to use
the figures; `article/article.html` is the rebuilt, offline, theme-portable deliverable).
