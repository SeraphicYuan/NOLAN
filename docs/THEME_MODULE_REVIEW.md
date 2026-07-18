# Theme module review — composition & layout gaps

**Date:** 2026-07-18 · **Status:** analysis complete, remediation NOT started (pick up later) ·
**Trigger:** the bespoke-scene pipeline (three test frames) exposed that themes don't tell downstream
consumers how to *lay out* a scene — every bespoke scene crowded to the left of the canvas.

**Companion:** the prioritized build plan lives in the bespoke/theme roadmap (Phase 2 = "Theme →
composition"). This doc is the durable, evidence-grounded record of *why* — read it before beefing up
the theme module. Related: `themes/THEMES.md` (the playbook), `themes/THEME-GAP-ANALYSIS.md`,
`docs/WIRING_CHECKLIST.md` (the "authored-but-unconsumed" pitfall this is an instance of).

---

## Bottom line

Themes are **strong on colour + type + a single decorative signature**, and they *do* define density/
radius/rule knobs — but:

1. There is **no declared composition/layout/rhythm/motion character at all**. Whether a scene is
   centred vs left-column vs split vs grid vs full-bleed is knowable per theme but lives **only in the
   theme's NAME + English `description` prose** — so every LLM consumer (the block composer and the
   bespoke agent) must *re-infer* composition from the name every time. This is why the bespoke scenes
   all defaulted to the editorial left-column: the theme name "highlighter-editorial" reads as Vox
   left-column, and the LLM's own default is also left.
2. The character knobs the themes **do** define (`--stage-pad`, `--r-card`, `--rule-*`, and the
   signature decoration layer) are **dropped by the primary block-kit composer** (`compose.py`
   references zero of them). So even the theme's defining "signature" doesn't reach the screen on the
   main render path.
3. **Registry drift** undercuts trust in the contract: the composer's own default theme is missing
   from the selector + playbook, and a flow defaults to a theme that doesn't exist on disk.

The single highest-value change is a **declared composition archetype** on `theme.json` (that the
consumers actually receive), plus honouring the existing character knobs + signature decoration on the
`compose.py` path.

---

## 1. Inventory — 26 themes

```
aurora-mesh, bauhaus-bold, blueprint, bold-signal, chalk-garden, creative-voltage,
dark-botanical, dune, electric-studio, forest-ink, highlighter-editorial, indigo-porcelain,
kraft-paper, midnight-press, monochrome-print, neon-cyber, neubrutalism, newsroom,
paper-press, pastel-dream, split-canvas, sunset-zine, swiss-ikb, terminal-green,
vintage-editorial, warm-keynote
```

Each theme = `theme.json` + `tokens.css`. The `theme.json` field set is **identical across all
themes**: `id`, `name`, `nameZh`, `description`, `descriptionZh`, `mood[]`, `bestFor[]`,
`preview{shell,surface,text,accent}`, `fonts{displayEn,body,cjk,mono}`, `avoidFor[]`.

## 2. The contract (enforced by code, no JSON Schema)

- **`themes/THEMES.md`** — authoritative playbook. Token contract at ~L120-213; theme.json field table
  ~L296-311; anti-patterns ~L340-354.
- **`themes/scripts/validate_themes.py`** — machine-enforced required set:
  `REQUIRED = {id, name, nameZh, description, mood, bestFor, preview}`, `PREVIEW_KEYS =
  {shell, surface, text, accent}` (hex-validated). Also checks both files exist, a `selector.json`
  entry exists, selector `tone` doesn't contradict `mood`, and enrichment is fresh.
- **`themes/scripts/enrich_themes.py`** — derives `fonts` (parsed from `tokens.css`) and `avoidFor`
  (promoted from `selector.json`). tokens.css is the source of truth for fonts.
- **`themes/selector.json`** — a *separate* reasoning table the raw theme.json lacks. Per theme adds
  `tone`(light/dark), `energy`(calm/medium/high), `formality`(casual/neutral/formal), `tags[]`,
  `avoid[]`. Consumed by `themes/scripts/select_theme.py` (`score_theme`).
- **`tokens.css` contract** (THEMES.md L130-213): REQUIRED = 4 surface + 4 text + 1 rule + 3 accent + 4
  font families. OPTIONAL "character knobs" = `--r-card`, `--r-stage`, `--rule-w`, `--rule-style`,
  `--hero-num-*`, `--stage-pad-x/y`, `--card-shadow`, `--stage-border`. OPTIONAL "signature
  decoration" = `--surface-pattern*`, `--surface-vignette`, `--text-shadow`. Defaults live in
  `render-service/_lab_listreveal/src/styles/base.css`.

## 3. The critical finding — themes carry NO declared composition/layout character

**By explicit design.** `themes/THEMES.md` (~L306-308) states themes no longer constrain
animation/timing/type-size — "rhythm and visual presentation are fully delegated to the per-scene
agent." Layout robustness is modelled purely as a **font-width** risk (`author.py` L130-132), not as
composition.

What a theme **DOES** tell a consumer: the full palette, the type pairing + OpenType features, a
**padding density** via `--stage-pad-x/y` (25/26 themes), a **radius character**, a **rule character**,
ONE **signature decoration** as a paint layer (swiss's hairline grid, aurora's radial mesh, etc.), and
a **motion mood** as free-text `mood[]` tags (no numbers).

What a theme **DOES NOT** tell a consumer about laying out a scene:
- **No composition archetype** — nothing declares centred vs left-column vs split vs grid vs full-bleed.
  (The swiss "grid" is a *decorative* 1px CSS grid, not a column system blocks snap to.)
- **No alignment default** (left / centred / justified).
- **No content density / word-rate / reveal-rate** (that lives in the *flow* registry — see §4).
- **No spacing/rhythm scale** — a single `--stage-pad` pair is the only spatial knob. `--scale-ratio`
  and `--motion-intensity` exist in only **2/26** themes (aurora-mesh, neubrutalism), so even the
  type-scale ratio is not part of the contract.
- **Motion character only as prose tags**, not a structured intensity/easing profile.

The composition character is therefore **implicit in the theme NAME + prose `description`** — e.g.
bold-signal's "oversized orange focal card as the stage's anchor," swiss's "1px hairline grid +
200-weight hero numbers" — English an LLM must read and infer, never a field a program can branch on.

## 4. Consumer → usage map

| Consumer | Where | Uses from the theme | Would benefit from but doesn't get |
|---|---|---|---|
| `_theme_vars` (block-kit composer) | `render-service/_lab_hyperframes/bridge/compose.py` ~L2496-2538 | Injects **every** `--name:value` from tokens.css onto `#root`. But block CSS references only **~18 vars, all colour/font** — **zero** character/layout knobs. | A composition archetype + spacing scale it could branch layout on. Each block **hardcodes its own composition** in `cqw/cqh` and paints its own backdrop; `#root` is `background:transparent`, so **the theme's signature decoration layer is dropped on this path.** |
| `_theme_polarity` | `compose.py` ~L2467-2493 | The **only** structural signal: `light`/`dark` from `--surface` luminance. | A colour signal, not composition. |
| `_theme_tokens` (bespoke brief) | `src/nolan/hyperframes/bespoke.py` L58-71 | First ~22 tokens (palette + fonts + a few knob lines) handed to the agent as "match the theme … prefer over hardcoded colours." | **Any layout direction.** The agent gets colours + fonts + "design to the meaning" — no composition archetype, alignment, density, or motion guidance. (`limit=22` also cuts off before the decoration tokens.) |
| `resolve_theme` | `render-service/_lab_hyperframes/bridge/author.py` L26-45 | The theme **slug string** by priority (`--theme` > `spec.theme` > `hyperframes.json.theme` > Vox default). | — |
| `theme_layout_audit` | `author.py` L129-147 | **STUB** — only checks tokens injected + text is `data-fit` tagged. Comment: "the one real theme risk is a wider theme font overflowing." | The codebase models theme risk as **font width only**; there's no composition-robustness concept. |
| `base.css` primitive path | `render-service/_lab_listreveal/src/styles/base.css` | Primitive classes DO consume the knobs: `.scene-pad`→`--stage-pad`, `.card`→`--r-card`, `.rule`→`--rule-*`, `.stage-frame::after`→`--surface-pattern`. | So the knobs + signature reach the screen **only if a scene uses these primitives**. The `compose.py` block-kit path bypasses this file → ignores every knob. **Two render paths, only one honours the theme's non-colour character.** |
| Flows | `src/nolan/flows/authoring.py`, `ingest.py` | Theme as a single **default string**. | Composition/pacing lives in `web-video-lab/flows/registry.json` keyed by *video type* (`pacing.wpm`, `density_high_rps`, block `palette`, `defaults.transitions/fx`) — orthogonal to the theme. NOTE: `art.defaults.theme:"museum-neutral"` is a dangling slug (no such theme dir). |

## 5. Prioritized gaps (highest conviction first)

1. **No composition archetype field — the single biggest gap.** Centred vs left-column vs split vs
   grid vs full-bleed is knowable per theme (bold-signal = focal-card, swiss = grid, split-canvas =
   split, dune = wide-margin) but encoded only in the name + prose. Both structured consumers (the
   block composer's per-block layout, the bespoke agent) get nothing. **Fix:** declare a
   `composition` archetype on `theme.json` (+ `selector.json`).
2. **The knobs themes DO define are ignored by the primary render path.** 25/26 ship `--stage-pad`,
   all ship `--r-card`/`--rule-*`, several ship `--surface-pattern`/`--vignette` — but `compose.py`
   references 0 of them. The theme's "signature" (the defining ~10% of its DNA) is not applied on the
   block-kit path. **Fix:** wire the knobs + decoration into `compose.py` (aligns it with the
   `base.css` primitive path that already honours them).
3. **No spacing/rhythm/density scale in the contract.** One `--stage-pad` pair is the only spatial
   token; `--scale-ratio`/`--motion-intensity` are ad-hoc (2/26). If per-theme rhythm is wanted, add
   it to the token contract + enrichment.
4. **Motion character is prose-only.** `mood[]` carries no numbers. A small
   `motion:{intensity, easing, reveal_rate}` block would make "snappy vs cinematic" machine-readable
   for both the composer and the bespoke agent.
5. **Registry hygiene** (lower severity, real): `highlighter-editorial` is a live theme (the composer
   default) **missing from `selector.json` and `THEMES.md`**, so `validate_themes.py` fails it and
   `select_theme.py` can't see it. And `registry.json` defaults the art flow to `museum-neutral`, a
   theme that doesn't exist on disk. Declared-vs-actual drift.

## 6. The grounded composition-archetype vocabulary

Derived from the 26 themes' OWN `description`s (not invented). Only ~6 themes actually *state* a
composition; the rest describe decoration + register and leave layout implicit (mostly "editorial →
left-column" — the bias that crowded the bespoke tests left). Recommended model:
`composition: { default: <archetype>, allowed: [<archetype>…] }` — the theme steers, the scene picks
within range (many themes suit more than one).

| Archetype | Grounded in (theme's words) | Themes |
|---|---|---|
| `focal-card` | "oversized focal card as the stage's anchor" | bold-signal |
| `split` | "dual-tone surface, left / right" | split-canvas |
| `grid` | "1px hairline grid", geometric, blocky | swiss-ikb, bauhaus-bold, neubrutalism, blueprint |
| `full-bleed` | mesh / neon / halftone / phosphor / chalkboard fills the canvas | aurora-mesh, neon-cyber, creative-voltage, terminal-green, chalk-garden |
| `centred` | "keynote", "manifesto", "gallery, wide-margin" | warm-keynote, bauhaus-bold, dune, electric-studio, pastel-dream |
| `left-column` | "editorial / newspaper / magazine" (default cluster) | highlighter-editorial, newsroom, monochrome-print, forest-ink, kraft-paper, indigo-porcelain, paper-press, vintage-editorial, sunset-zine, dark-botanical, midnight-press |

## 7. Remediation roadmap (Phase 2 of the bespoke/theme roadmap)

- **B1** — declare `composition:{default, allowed[]}` on `theme.json` + `selector.json`, using the §6
  vocabulary. Extend `validate_themes.py` + `enrich_themes.py` to cover it (docs claim, tests enforce).
- **B2** — pass the composition character (archetype + `description` + `mood`) to the bespoke brief in
  `_theme_tokens`/`bespoke_task_brief`, so the agent gets explicit layout direction (and stops
  defaulting to left-column). Also raise/repair the `limit=22` token truncation so the decoration
  tokens are visible.
- **B3** — registry hygiene: add `highlighter-editorial` to `selector.json` + `THEMES.md`; fix the
  `museum-neutral` art-flow default.
- **B4a** — `compose.py` honours the character knobs + signature decoration (aligns with `base.css`);
  then instruct the bespoke agent to paint the same signature so `raw` scenes match block-kit scenes.
- **B4b** (larger, later) — theme-*driven* block composition (archetype → block layout). A real
  refactor of blocks that currently hardcode a tuned composition; do it after B1/B2.
- **Motion / spacing** (gap 3 & 4) — optional structured `motion` + a spacing/rhythm scale on the
  token contract, if per-theme rhythm is wanted.

## 8. Empirical check to run before committing to B1/B2

Re-dispatch one bespoke scene with the SAME content + direction under a **non-left-column theme**
(e.g. `bold-signal` = focal-card/centred). If the layout un-crowds purely from the theme change, the
name-driven hypothesis is confirmed and B1/B2 are validated. (This is cheap — one agent + one render.)
