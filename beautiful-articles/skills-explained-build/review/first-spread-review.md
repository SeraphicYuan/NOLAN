# First Spread Review — skills-explained-build (freddie)

**Verdict: PASS-WITH-FIXES** — Strong, on-theme, content-faithful first spread. One real theme violation (`<em>` italic) and a couple of small polish items.

## Findings

1. **[FIX] sections/01-skills.tsx:28 — italic-for-emphasis via `<em>`.** freddie's profile bans italic emphasis at protocol level ("强调不用斜体（协议级禁用）"). `<em> progressive disclosure</em>` will render italic unless reacticle restyles `<em>` in freddie. Verify the rendered output; if it's italic, switch to `<strong>` or the theme's highlight treatment (it's already a key term, so a yellow highlight fits freddie better than italics).

2. **[NIT] Cover.tsx:96 — yellow as text color on central node.** `color: var(--ra-color-accent-contrast)` renders yellow text on the dark accent badge. This is the theme's *intended* contrast token (theme-faithful, and switches correctly on theme change), and it's a single display badge ("Claude"), so it's within bounds — but it does brush freddie's "黄绝不作文字色" rule. Acceptable as-is; just confirm the badge reads cleanly. All other yellow usage is highlight-only (correct).

3. **[NIT] Cover.tsx:181 vs Article.tsx:14 — title near-duplicate of Hero.** Cover h1 "Skills, explained." ≈ Hero title "Skills explained". This is NOT the anti-pattern (kicker, subtitle differ, no meta/date stacked), and a cover legitimately bears the title. Differentiation is otherwise good (cover sub "Five building blocks, one system…" vs Hero subtitle). Leave as-is; flag only if you want the cover to lean fully on a non-title hook.

4. **[PASS] Cover 5 self-checks.** (a) visual+text both present — node-and-edge diagram + text band; (b) tokens only, hex are inline fallbacks (allowed); (c) content-faithful — Claude hub + 5 labelled building blocks, Skills highlighted = exactly the article's subject; (d) ratio-adaptive — `%` node positions, `inset:0`, SVG `viewBox` + `preserveAspectRatio`, grid/flex, no absolute px; (e) text distinct from Hero (see #3). Strong cover.

5. **[PASS] Component policy — prose-first.** Section 01 is mostly paragraphs + one list + one Aside + one Raw. `Summary` ("At a glance", 6 pts) and `Aside tone="note" label="Example"` are both used for content that genuinely *is* that structure. No over-componentization; no card-stacking.

6. **[PASS] Raw policy — ProgressiveDisclosure block.** Serves the "how Skills work" paragraph directly, all `--ra-*`/`--mc-*` tokens, no app/widget feel. Three load stages (Metadata ~100 / Full instr <5k / Scripts as-needed) match the source exactly. The rotated yellow number stickers + accent-soft underline are idiomatic freddie. Good.

7. **[PASS] Content fidelity vs source "What are Skills?".** Definition, training-manual framing, progressive-disclosure mechanics (token budgets), the 3 when-to-use categories (Organizational / Domain / Personal with the same examples), and the brand-guidelines Example are all faithful, nothing invented or dropped. The closing "many Skills without overwhelming context" sentence is borrowed from the source FAQ but used accurately. NIT: intro phrase "the one everyone's asking about" is light editorial framing not in source — harmless.

8. **[PASS] Tone / rhythm.** Fraunces title with yellow underline sets the right friendly-explainer gravitas; density and the cover→Hero→Lead→Summary→section-with-diagram cadence give good visual rhythm for a guide. Headings Fraunces, body Hanken via tokens; no neon/purple/gradient.
