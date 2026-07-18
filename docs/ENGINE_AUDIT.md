# Composition-engine audit — findings from the theme × archetype sample matrix

The sample-matrix build (compose one canonical scene per archetype under every theme, screenshot,
LOOK) doubles as an **engine audit**: every cell where the render doesn't read right is a registry
fix, a layout gap, or a theme-application bug — surfaced concretely instead of guessed. Cheap findings
are fixed inline; structural ones are logged here for a dedicated pass. Feeds the composition module
(`docs/COMPOSITION_ARCHITECTURE.md`) + the theme module review (`docs/THEME_MODULE_REVIEW.md`).

Status: `FIXED` (inline) · `LOGGED` (structural, pending) · `WONTFIX`.

---

## F1 · Statement block smears a dark scrim on type-only, light-theme beats — `FIXED`

**Evidence:** editorial-column sample (a `statement` with no ground) under highlighter/swiss-ikb showed
a muddy grey radial gradient instead of the theme's clean light ground.
**Cause:** `highlight_statement` defaulted the ground to `{kind:"transparent"}`, and `media_ground`
paints a hardcoded dark scrim (`rgba(20,21,20,…)`) for `transparent` (it's meant to darken a root
video). With no media, that scrim just muddies a light theme.
**Fix (compose.py):** default the ground to `paper` (clean, no scrim) when the statement is NOT grounded
(`reg=="paper"`), keeping `transparent` only for `footage`/root-video beats. Mirrors the existing
`_grounded` register logic; explicit `ground:{kind:transparent}` still scrims. Verified by re-render.

---

## F2 · `stat` is mis-classified as `centered-hero` — `LOGGED` (registry / design)

**Evidence:** the centered-hero sample (a `stat` "73%") renders **upper-left and small**, not dead-centre
and huge. The catalog itself calls `stat` "a data **callout**."
**Implication:** the archetype registry maps `stat → centered-hero` (`archetypes.json` centered-hero
`blocks:["stat"]`), but stat's real layout is a left/editorial **callout**, not a hero. So block→archetype
classifications don't all match the blocks' actual layouts, and `centered-hero` has no block that truly
delivers it (the promoted exemplar was a custom raw scene).
**Options (needs a design call):** (a) reclassify `stat` (→ editorial-column or a new `callout`
archetype — ties into task #2, "archetypes to add"); AND/OR (b) make `stat` honour centered-hero (a real
centre-anchored big-number layout — the B4b gap); (c) add a dedicated centered-hero block. Do NOT quietly
flip the mapping — decide the intent first. **This is exactly the block↔archetype audit the matrix is
meant to produce; expect more cells like it.**

---

## F3 · Composer loads only 4 font families; ~30 theme fonts silently fall back — `FIXED` (per-theme loader; tier-B vendoring pending)

**Fixed:** `compose.py` now has a per-theme font loader (`_theme_fonts` / `_theme_font_families`) that
replaces the fixed `FONTS` `@import`. It reads each theme's PRIMARY families from its `--font-*` stacks,
substitutes Source Han → Noto, and emits one Google-Fonts `@import` per family (isolated so a bad weight
fails just that font). Verified by render: newsroom→Playfair, bauhaus-bold→Archivo Black, kraft-paper→
Fraunces (were all Libre-Franklin fallback before). Honesty test: `tests/test_theme_fonts.py`.
**Still pending:** tier-B Fontshare faces (Satoshi, Clash Display — neon-cyber) aren't on Google Fonts,
so they still fall back until vendored as `@font-face` woff2. Tier-D (GT Sectra etc.) turned out to be
only *fallback* entries in stacks, never a primary, so no substitution was needed.

--- original finding, kept for the record ---


**Evidence:** `compose.py` `FONTS` is a fixed `@import` of **Inter, Libre Franklin, Lora,
UnifrakturMaguntia**. The 26 themes declare **~30 real families**. `_theme_vars` injects each theme's
`--font-*` vars but NOT any `@import`/`@font-face`, so any family outside those 4 renders in a **fallback**
(system serif/sans). ⇒ ~22/26 themes never show their declared display type — a correctness bug in ALL
renders, not just samples, and a big reason themes feel same-y.

**Font availability (what we actually have):**
| Tier | Families | Action |
|---|---|---|
| A · on Google Fonts (loadable — composer just doesn't) | Inter, Libre Franklin, Lora, Playfair Display, Manrope, Space Grotesk, Fraunces, EB Garamond, IBM Plex Sans/Mono, Source Serif 4/Pro, Work Sans, Outfit, Plus Jakarta Sans, Syne, Instrument Serif, Cormorant(+Garamond), Caveat, Patrick Hand, Archivo(+Black), JetBrains Mono, Space Mono, UnifrakturMaguntia | build the `@import` from the theme's declared fonts |
| B · free, not on GF (Fontshare) | Clash Display, Satoshi | vendor `@font-face` (woff2) |
| C · CJK (critical — Chinese narration) | Noto Sans SC, Noto Serif SC (GF); Source Han Sans/Serif SC = Noto | load Noto SC/Serif SC; alias Source Han → Noto |
| D · we DON'T have | GT Sectra (commercial), Recoleta (commercial), Bodoni 72 / SF Mono / SF Pro Display (Apple-only) | substitute a close GF family per theme (record the swap) |
| E · system (OS-dependent) | Arial, Georgia, Times New Roman (OK on Windows); Helvetica, Helvetica Neue (Mac) | leave for system; Helvetica→Arial/Inter fallback |

**Fix (structural pass):** replace the fixed `FONTS` with a per-theme font loader — derive families from
the theme's `--font-*` (+ CJK Noto), emit a Google-Fonts `@import` for tier A/C, `@font-face` for vendored
tier B, and a substitution table for tier D (theme keeps its declared name; the loader maps it to a real
face + records the swap). This is a **prerequisite for a trustworthy sample matrix** — samples in fallback
fonts misrepresent the theme.
