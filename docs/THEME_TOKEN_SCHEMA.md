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

## Layer 2 — Semantic color-alias layer + auto-derived ladders — ✅ DONE 2026-07-19

**Half already satisfied:** our block CSS already references SEMANTIC token names (`--accent`, `--surface`,
`--text`, `--rule`, …) — the reference decks needed an alias layer only because their palettes were
BRAND-named (`cobalt`, `cream`); ours are the aliases. So Layer 2 for us = the **auto-derived ladder** half.

**Shipped** as native CSS `color-mix()` in tokens.css, NOT a runtime executor. A single-accent / single-hue
theme expresses its whole depth language as one base colour + a function:
`--surface-3: color-mix(in srgb, var(--accent) 4%, transparent)` (then 8 / 15 / 20% for soft/glow/rule) —
so changing `--accent` updates the entire ladder. Chosen over a compose-time executor because color-mix is
read by BOTH render paths (the HyperFrames composer AND the Remotion pipeline, which loads tokens.css
directly — an executor would have derived only for the composer and left the pipeline's `--accent-soft` etc.
undefined). Exemplars: **blue-professional** (cobalt accent ladder 4/8/15/20%), **vellum** (fg-alpha ladder,
chartreuse text at 62/55/35%). Render A/B: pixel-equivalent to the hand-set rgba (worst Δ=2/255). Enforced by
`tests/test_color_ladders.py` (ladder is a monotonic function of one base var, base is a hex literal).
**Rollout DONE 2026-07-19:** all 27 single-accent themes converted — 58 accent/text-derived rgba tokens
(`--accent-soft`/`--accent-glow` universally, plus per-theme `--surface-3`/`--rule`/fg tokens) rewritten to
`color-mix(var(--accent|--text) N%, transparent)` at each theme's OWN opacity, so every theme's accent is a
true single knob. Pixel-verified equivalent (worst Δ=2/255 across 84 cells). The multi-hue *candy* palettes
stay bespoke (no single-accent ladder).

---

### Original design (for reference)


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

## Layer 3 — Shape + spacing scale — ✅ DONE (shape axis) 2026-07-19

**Shipped** the shape half — corner radius + border weight as a real theme axis. `themes/composition/
shape_scale.json` documents the canonical ladders (radius `none/xs/sm/md/lg/pill/round`; border-weight
`hair 1 / thin 1.5 / base 2 / bold 3 / heavy 4`). Mechanism: the card-family block CSS reads
`var(--r-card, <default>)` (corner) + `var(--bw, 2px)` (border weight), so a theme sets `--r-card` / `--bw`
and every framed panel, carousel + listicle card follows — backward-compatible (a theme setting neither
keeps the block defaults). `--bw` set across 10 themes by shape character: brutalist (bauhaus/bold-signal/
neubrutalism) 3px, editorial/gallery (vellum/dark-botanical/newsroom/…) 1px, consulting (blue-professional)
1.5px, rest 2px. Render-verified: the framed card border ranges heavy→hairline across themes. Honesty-tested
(`tests/test_shape_scale.py`: tokens consumed, values are ladder steps, axis separates brutalist>gallery).
**Spacing half — resolved (covered, not a gap):** each render path already tokenises spacing. The HyperFrames
composer scales every inset/gap via `--density` on container-relative `cqw` units (so a theme is more/less
generous — vellum density 1.2), and the Remotion pipeline consumes the absolute `--stage-pad-x/y` steps
(Surface.tsx). Named `pad.card`/`gap.grid` sub-steps are deliberately NOT added — they'd duplicate `--density`
for negligible gain. Layer 3 is complete.

---

### Original design (for reference)


**Radius ladder (a real theme axis, 0 → pill):** `0` (brutalist: raw-grid/studio/monochrome) · `xs 4` ·
`sm 10` · `md 14` (soft cards) · `lg 24` (vellum/daisy) · `pill 999` (capsule/emerald) · `round 50%`
(dots/avatars, universal) · optional `blob` (playful organic radius). **Border-width scale:** `hair 1 /
thin 1.5 / base 2 / bold 3 / heavy 4` (themes span the whole range). **Spacing:** `pad.slide` (x/y),
`pad.card` (lg/md/sm/xs ladder), `gap.grid` (lg/md/sm), `max-content-width` (~1000–1200). Our `--density`
stays the multiplier ON TOP of these named steps. THEME-SPECIFIC: `pixel-unit 4px` (8-bit), magazine
frame insets (pink-script), pill-pad set (capsule), OS-chrome pads (retro-windows).

---

## Layer 4 — Component tokens — ✅ DONE (card flagship + registry) 2026-07-19

**Shipped** the component-token mechanism + the flagship. `themes/composition/components.json` is the typed
registry (each component = a param bundle mapping to `var(--token, <default>)` the block CSS consumes);
`tests/test_components.py` enforces that every `wired` component's tokens are actually consumed — the guard
that caught the flagship bug: **`--card-shadow` was authored by 24 themes and read by NOTHING** (a dead
Layer-4 token). Wiring it (framed card + `.lt-bar`/`.lt-card`) activated a huge amount of designed, dormant
character: neubrutalism/bauhaus HARD-OFFSET shadow (7/8px, no blur — the brutalist signature), swiss-ikb
INSET hairline, terminal-green inset + phosphor GLOW, aurora-mesh layered drop+glow, blue-professional/vellum
FLAT (none) — verified across the framed archetype. Scoped to PANEL cards; image cards (galcard/carousel)
keep their block-tuned lift (the schema's card vs img-placeholder split). Registry status (each resolved
on inspection, not left vaguely pending): `card` + `image-card` + `bar` **wired** (bar-cap radius follows the
shape scale — sharp vs rounded bars, verified); `pill` **n/a** (a pill is definitionally fully-round — no
theme radius axis); `timeline-dot` **n/a** (the production timeline is an intentionally cinematic dark
variant; the themed timeline is the archetype seed); `counter` **n/a** (ordinal type comes from Layer-1 +
the `background-ordinal` decoration); `bullet-marker` **pending** — genuinely blocked on a bullet/list block
that doesn't exist (a new BLOCK feature, orthogonal to the token schema). The honesty test enforces that a
non-`wired` component documents its reason. Layer 4's mechanism + flagship are complete.

---

### Original design (for reference)


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
2. ✅ **Color-alias layer + ladders** (Layer 2) — DONE. Alias half already satisfied (our tokens ARE
   semantic); ladder half shipped as native `color-mix()` in tokens.css (dual-path-safe), proven on
   blue-professional + vellum. Remaining: roll to the other single-accent themes (per-theme ratios).
3. ✅ **Shape + spacing scale** (Layer 3) — shape axis DONE (radius ladder + `--bw` border weight,
   shape_scale.json, wired into card-family blocks + 10 themes). Remaining: named pad/gap spacing steps.
4. ✅ **Component tokens** (Layer 4) — mechanism + flagship DONE. components.json registry + honesty test;
   `card` wired (activated the dead `--card-shadow` → hard-offset/inset/glow/flat character). Remaining:
   wire the pending components (bullet-marker/timeline-dot/pill/bar/counter) as their blocks appear.
5. **A/B validation** — map a reference `design.md` (blue-professional) into the v2 token system, render
   through our engine (archetypes + decoration + levers), and compare side-by-side with our nearest theme
   (electric-studio / swiss-ikb). Answers "does the richer token layer close the quality gap?" + seeds a
   new theme. Do NOT adopt their themes wholesale (slide-specific; abandons composability + video).

Each layer follows the module contract (registry of roles + per-theme authored values + block executors
consume + honesty test) — richer themes, same composability.
