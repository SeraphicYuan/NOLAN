# slide_designer report — venezuela

## Summary
- **Info-scenes processed:** 26 (10 `text-overlay` + 16 `graphic`)
- **All targeted scenes received a `layout_spec`.** Final JSON re-parses cleanly.
- No scenes outside the `text-overlay` / `graphic` set were modified.

## Template counts

| Template | Count | Scene IDs |
|---|---|---|
| `title` | 7 | scene_001, scene_009, scene_023, scene_026, scene_032, scene_059, scene_069 |
| `timeline` | 5 | scene_010, scene_014, scene_017, scene_030, scene_036 |
| `custom` | 5 | scene_011, scene_042, scene_051, scene_053, scene_066 |
| `chapter_card` | 3 | scene_027, scene_038, scene_050 |
| `list` | 2 | scene_025, scene_064 |
| `pull_quote` | 1 | scene_005 |
| `lower_third` | 1 | scene_057 |
| `section_divider` | 1 | scene_062 |
| `ranking` | 1 | scene_007 |

## `template: "custom"` scenes (no built-in template fits)
- **scene_011** — animated map of Venezuela showing the Arawak/Carib east-west split. The catalog has no map renderer.
- **scene_042** — animated oil-price line chart 1970–1990 with 1973 boom + 1980s crash callouts.
- **scene_051** — animated oil-price line chart 2010–2016 with 2014 collapse callout.
- **scene_053** — hyperinflation visualization (counter + log-scale collapse curve + price side-panels).
- **scene_066** — full-span oil-price line chart 1970–2024 (lens-2 callback).

All five are flagged with `note: "no built-in template — needs custom render or replan as image"` so the renderer can either implement a custom path or downstream specialists can replan as `generated-image`.

## Patterns worth flagging
- **The script leans on line charts.** Four of the five `custom` scenes are oil-price line charts (or hyperinflation, also a temporal line). If we keep this style of script in production, a `line_chart` template would pay back fast.
- **A Venezuela / regional map template would also be useful** — scene_011 was the only map but maps recur in this genre.
- **The four "KEY INSIGHT" cadence beats** (scene_023, 032, 059, 069) all map cleanly to `title` with `"KEY INSIGHT"` as title and the body as subtitle, per the rule preferring the simpler template over `verdict`.
- **The three lens markers** (scene_027, 038, 050) used `chapter_card` with `chapter_number: "1" / "2" / "3"`. The recap card scene_064 used `list` rather than `chapter_card` since all three lenses appear together.
- **scene_007 (ranking of world's oil reserves)** uses `ranking` with placeholder rank labels (`#1`–`#5`) rather than barrel-volume figures, since the script does not state the reserve volumes — sticking to the "don't invent script content" rule.
