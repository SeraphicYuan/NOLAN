# Brand recolor (oklch palette from one seed color)

Keep a reacticle theme's **typography + decoration** (its design language) but swap its
**color palette** to a brand color. `scripts/brand-theme.mjs` derives a perceptually-even
ramp from one seed via oklch and emits `article/brand.css` (plain hex, works in any browser,
offline).

```bash
node <skill>/scripts/brand-theme.mjs --theme press --color "#3257d6" [--mode light|dark]
# then add  import "./brand.css";  to article/main.tsx AFTER  import "reacticle/styles.css";
```

It overrides only the generic `--ra-color-*` tokens (bg / surface / border / text / heading /
muted / faint / accent + soft/strong/contrast, and `info` → brand). It does NOT touch fonts,
component decoration, or `risk/warn/success` (semantics stay readable).

## When to offer it (Checkpoint 1)
If the user has a brand color (or wants one), offer "theme + brand recolor" as the theme
choice. Resolve a base theme for the *design language*, then recolor the palette to brand.

- **Best on the typographic themes** — `press` (editorial), `tufte` (data), `bodoni`
  (high-contrast serif), `vignelli` (swiss), `knuth` (academic) — they ride the generic
  tokens, so they recolor cleanly into "that design language, in your brand color."
- **Signature-color themes keep their identity by design:** `freddie` (yellow highlighter
  via `--mc-yellow`), `sottsass`/`bayer`/`fuller` (named `--st-*`/`--by-*`/`--fl-*` palettes).
  Brand-recolor won't override those signature accents — and shouldn't (you don't rebrand
  Memphis). Use a typographic theme if full brand control matters.

## How it works (so you can tune)
Seed `#hex` → oklch(L,C,H). Hue `H` is shared across the palette; neutrals use very low chroma
(a whisper of brand), the accent uses the seed chroma (tamed to avoid neon), `accent-contrast`
flips to white/near-black for legibility. Light + dark ramps are L-value tables in the script.
