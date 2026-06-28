# Slide Designer Report — Venezuela Documentary

## Summary
- Info-scenes processed: **24** (9 text-overlay + 15 graphic)
- All 24 received a `layout_spec`. No non-info scenes were modified.

## Per-template counts
| Template | Count | Scenes |
|---|---|---|
| `list` | 7 | 022, 023, 025, 028, 041, 053, 065 |
| `title` | 6 | 014, 017, 034, 036, 061, 070 |
| `chapter_card` | 4 | 024, 026, 066, 068 |
| `custom` | 4 | 011, 045, 054, 056 |
| `timeline` | 2 | 009, 031 |
| `quote` | 1 | 005 |

## Custom-template scenes (no built-in renderer fits)
- **scene_011** — Stylized Venezuela map shading Arawak (west) ochre and Carib (east) teal. No map template in the catalog; flagged for custom render or replan-as-image.
- **scene_045** — Dual-line chart of crude oil price + Venezuelan GDP, 1970–1989 with "1980s collapse" marker. No line-chart template.
- **scene_054** — Brent crude line chart 2010–2016 with "2014 oil crash" marker. Same gap as scene_045 — should reuse the same custom chart system for visual continuity.
- **scene_056** — Hyperinflation log-scale chart of Bolivar inflation % 2015–2019 with stacked-banknotes inset. No log-chart template.

## Design notes
- **Recurring "three lenses" device.** The script reuses a 3-card lenses graphic at the thesis introduction (023), three Evidence openers (028/041/053), the in-thesis lens-2 callout (025), and the conclusion synthesis (065). All six render with `list` (title indicates the active lens, items are the three lens labels). The catalog has no native "highlight one item" affordance — the renderer can use the active lens in the title to drive emphasis, or treat these consistently and let the active lens be conveyed via accompanying narration.
- **"Key insight" cadence.** The script's spine phrase appears five times: 022 (thesis, three drivers), 036 (Evidence 1, wealth wasn't shared), 061 (Evidence 3, corruption accelerant), 070 (conclusion). 022 has three discrete drivers so it uses `list`; the other three use `title` with "HERE IS THE KEY INSIGHT" as the title and the body as subtitle, per the catalog's ambiguity rule.
- **Section markers.** "FIRST", "SECOND" (visualized as the 3-lenses card with lens 2 lit), and "FINALLY" use `chapter_card` for text-overlay variants and `list` for graphic-card variants.
- **Date markers** (014, 017, 034) all collapse to `title` with the date range as title and a one-line gloss as subtitle.
- **Timelines.** scene_009 covers the full Venezuelan arc (Pre-1500 → Today, 5 events). scene_031 covers the caudillo era 1830–1935 with Páez and Gómez as anchor events.

## Patterns worth flagging
- The script's **information-graphics share leans heavily on charts and maps** that the current template catalog doesn't cover (4 of 15 graphic scenes had to be marked `custom`). If the project ships often, the renderer would benefit from a `line_chart` and a `region_map` template.
- The "three lenses" recurring card is a project-specific motif. A purpose-built `lenses_card` template (with an `active_index` parameter) would let the design intent — dimming non-active lenses — be captured natively rather than being implied through the `list` title.
