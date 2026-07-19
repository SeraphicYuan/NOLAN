# Theme schema v2 — token granularity (from the 34-template `design.md` study)

**The gap (measured):** a typical reference `design.md` defines **~60 named tokens** (~150–300 discrete
values): ~19 typography roles + ~9 colors (+9 semantic aliases in 62%) + ~15 spacing/radii + ~17
components. Our engine exposes **~31 CSS vars** (15 color, 6 font *family-only*, 5 radii, +type-scale/
density). The single biggest gap is **per-role type treatment** — their templates average 19
fully-specified type roles; we have **0** (eyebrow/stat/quote treatment is hardcoded in block CSS, so a
theme can't vary it — e.g. every theme's "By the numbers" eyebrow is identical). Design: adopt their
token STRUCTURE (split common vs theme-specific) into our composable engine — the same "registry +
per-theme values + executor consumes" contract we already use for archetypes/decoration. Keep our `cqw`
(container-relative) sizing, not their absolute `clamp(px,vw,px)`.

Source: `docs/REFERENCE_TEMPLATE_ANALYSIS.md` + a 34-template token extraction (9 read in full).

---

## Layer 1 — Type-role tokens (highest priority; fixes the eyebrow-sameness) — ✅ DONE 2026-07-19

**Shipped** via a personality REGISTRY + EXECUTOR rather than 26 hand-set CSS blocks. Roles wired into
BOTH seeds and the live production blocks: `eyebrow` (`.kick`), `hero-num`/`stat-number` (`.slnum`),
`display` (`.stmt`), `stat-label` (`.sllabel`), `caption` (`.capbar`) — each `var(--{role}-{prop},
default)`, backward-compatible. `themes/composition/type_roles.json` defines 6 **personalities**
(geometric-sans / editorial-serif / elegant-italic / mono-technical / brutalist-heavy / friendly-rounded),
each a recipe assigning every role a font SLOT (display|body|mono) + weight/size/tracking/style; every
`theme.json` names a `typePersonality`; `compose._theme_type_roles()` emits the recipe's vars on `#root`
BEFORE `_theme_vars` so a theme's own tokens.css (the two ported exemplars, blue-professional + vellum)
overrides. Slots resolve against each theme's own fonts → same-personality themes still differ by typeface.
Honesty-tested (`tests/test_type_roles.py`: phantom-field guard + parity; `validate_themes.py`: personality
∈ registry). Drove by A/B-porting two reference `design.md` systems (docs below). **Remaining in Layer 1:**
the THEME-SPECIFIC signature numerals/decorative display variants (agenda-num, drop-cap, script ladder) —
the open per-theme extras, not yet exposed.

---

### Original design (for reference)


Replace the 6 family-only font vars with a `type.<role>` map. **Family selectable per role** (most
templates use a 3-face model: display / body / mono, assigned per role — not one global triple).

**COMMON roles (shared engine tokens; every theme sets values):** `display`, `h2`, `h3`, `eyebrow`
(a.k.a. kicker/label — the one we most need), `body`, `body-sm`, `stat-number`, `stat-label`, `quote`,
`quote-mark`, `caption`, `mono-tag`. Each carries `{family, weight, size-step, lineHeight,
letterSpacing, textTransform, color-alias}`. Blocks/seeds CONSUME `var(--eyebrow-*)` etc. instead of
hardcoding.

Spread that proves the value (eyebrow): blue-professional `Space Grotesk 600 / 0.08em / uppercase /
primary`; 8-bit-orbit `Space Mono 400 / 0.3em / uppercase`; broadside `IBM Plex Mono 500 / 0.14em`.
Today all three render identically in NOLAN.

**THEME-SPECIFIC (open per-theme map, like our lossless `extra`):** signature numerals + decorative
display variants — `agenda-num`, `orbit-numeral`, `pillar-num`, a `script` size-ladder (pink-script has
9 steps), `hand-scribble`, `drop-cap`, `team-initial`. Rule: expose the 12 common roles; let a theme
declare extras.

---

## Layer 2 — Semantic color-alias layer + auto-derived ladders (62% of templates have this)

Templates map their arbitrary brand-named palette onto a **canonical semantic vocabulary** that block
CSS references. Adopt the alias slots as the stable contract:

`c-bg`, `c-bg-alt`, `c-fg`, `c-fg-mute`, `c-fg-hint`, `c-accent`, `c-border`, `c-card` (+ status
`positive`/`negative`). The theme's named palette *maps onto* these; blocks reference the aliases.

**Auto-derive the opacity ladder** (the depth mechanism in single-accent systems): `card-bg` = accent
@4%, `accent-light` @8%, `accent-medium` @15%, `border` @20% (blue-professional); + an fg alpha ladder
(mute/hint/hair). ⇒ a single-accent theme becomes **one color + a function**, replacing 4–6 hand-set
vars.

**THEME-SPECIFIC:** multi-hue *candy* palettes with no semantic meaning (daisy-days/capsule/scatterbrain
— a rotating `surface-set[]`, optional extra); retro *system* palettes (Win9x, neon trio); register-flip
pairs (broadside dark+orange, no light).

---

## Layer 3 — Shape + spacing scale (we tokenize radii only)

**Radius ladder (a real theme axis, 0 → pill):** `0` (brutalist: raw-grid/studio/monochrome) · `xs 4` ·
`sm 10` · `md 14` (soft cards) · `lg 24` (vellum/daisy) · `pill 999` (capsule/emerald) · `round 50%`
(dots/avatars, universal) · optional `blob` (playful organic radius). **Border-width scale:** `hair 1 /
thin 1.5 / base 2 / bold 3 / heavy 4` (themes span the whole range). **Spacing:** `pad.slide` (x/y),
`pad.card` (lg/md/sm/xs ladder), `gap.grid` (lg/md/sm), `max-content-width` (~1000–1200). Our `--density`
stays the multiplier ON TOP of these named steps. THEME-SPECIFIC: `pixel-unit 4px` (8-bit), magazine
frame insets (pink-script), pill-pad set (capsule), OS-chrome pads (retro-windows).

---

## Layer 4 — Component tokens (currently hardcoded in block CSS)

Define ~10 COMMON components as a typed registry, each a param bundle `{fill, border, radius, shadow,
padding}` a theme fills: `card`, `pill`/`tag`, `bar-track`+`bar-fill`, `stat-card`, `rule`/`accent-line`,
`nav-dot`, `pagenum`/`counter`, `bullet-marker` (em-dash / slash / chevron / dot — a real per-theme
choice), `img-placeholder`, `timeline-dot`. Blocks consume them → a "brutalist" card vs a "porcelain"
card differ without touching block code. THEME-SPECIFIC components go in an extension registry (cf.
`compose_extension.py`): retro-windows OS-chrome kit, 8-bit pixel-stack, post-it/pin/tape, sakura
rosette-seal, etc.

---

## Build plan (theme schema v2)

1. ✅ **Type-role tokens** (Layer 1) — DONE. Shipped as the personality registry + executor (see the
   Layer-1 section above): eyebrow/hero-num/display/stat-label/caption wired in blocks + seeds; all 28
   themes carry a `typePersonality`; the 2 ported exemplars keep hand-tuned overrides. Fixes the
   eyebrow-sameness. Remaining: the theme-specific signature-numeral extras.
2. **Color-alias layer + ladders** (Layer 2) — the semantic contract + auto-derived opacity/alpha.
3. **Shape + spacing scale** (Layer 3).
4. **Component tokens** (Layer 4).
5. **A/B validation** — map a reference `design.md` (blue-professional) into the v2 token system, render
   through our engine (archetypes + decoration + levers), and compare side-by-side with our nearest theme
   (electric-studio / swiss-ikb). Answers "does the richer token layer close the quality gap?" + seeds a
   new theme. Do NOT adopt their themes wholesale (slide-specific; abandons composability + video).

Each layer follows the module contract (registry of roles + per-theme authored values + block executors
consume + honesty test) — richer themes, same composability.
