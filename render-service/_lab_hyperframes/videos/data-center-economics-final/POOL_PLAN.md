# Final Vox cut — asset pool plan (for sign-off before authoring)

Full script, both beats (159.5s). Style: `highlighter-editorial` (Vox). Goal: all asset
types + greater motion variation. Below: the per-beat shot list (what I'd USE), what the
pool now HAS, and the gaps (assets I wish I had).

## Pool as collected (in this project)
- **Gen (ComfyUI/krea2, 1344×768, dark-cinematic):** 10 — `assets/bg_*.png`
  (bg_boom_hero, bg_boom_close, bg_bill_turn, bg_water_desert, bg_noise_house,
  bg_land_lines + NEW: bg_gen_hook_money, bg_gen_construction, bg_gen_control_room,
  bg_gen_server_hero).
- **Stock photo (Pexels/ddgs):** 15 — `capture/assets/*.jpg` (server_hall ×3,
  aerial_sprawl ×3, cooling_towers ×3, desert_campus ×3, transmission ×3).
- **Stock video (Pexels, 1280×720, 9–14s):** 6 — `capture/assets/videos/*.mp4`
  (server_broll ×2, grid_broll ×2, water_broll ×2). For archetype-B motion grounds.
- **Archival:** 0 (see gaps).
- Inventory + qwen captions + license/credit: `capture/extracted/asset-descriptions.md`.

## Proposed shot list (beat → register → asset → source)
FRAME 1 — "The boom is real"
1. Cold open "The boom is real" → FOOTAGE **video** `server_broll_01` (motion open) · alt gen_server_hero
2. Spend $800B / $1T / = defense budget → PAPER stat-lockup · faint ground `bg_gen_hook_money` (dim 70%)
3. Demand 400M→900M users → PAPER **chart** (svg-path-draw line) · no asset
4. Power 4.4%→7-12% electricity → PAPER **chart** (bars) · no asset
5. "Some towns cash in" 38% Loudoun → PAPER highlight-statement · no asset (or faint aerial_sprawl)
6. Close "not un-building this" → FOOTAGE **gen** `bg_gen_construction` (the build-out) · alt aerial_sprawl_00

FRAME 2 — "Where does the bill land"
1. Turn "costs land on specific people" → FOOTAGE **gen** `bg_bill_turn` (house vs data center)
2. Power ×2 / $103B / +50% → PAPER stat-lockup · faint ground `transmission_02` (dim)
3. Water 43% / 1.83B gal / 61k people → FOOTAGE **video** `water_broll_00` (steaming cooling towers) · alt gen_water_desert
4. Quote "low drone… in the walls" → FOOTAGE **gen** `bg_noise_house` (bedroom, the emotional peak; rack-focus)
5. Land "losing land outright" → FOOTAGE **video** `grid_broll_01` (pylons + moving sky) · alt bg_land_lines
6. Jobs <150 / 25 / ~100 → FOOTAGE **gen** `bg_gen_control_room` (lone worker dwarfed) under the stats

Asset-type spread: 3 stock video (archetype B) · 5 gen · stock-photo grounds/alts · 3 pure-paper charts/lockups.
Motion variation to cite (from motion-palette.md): svg-path-draw, stat-bars-and-fills,
counting-dynamic-scale, kinetic-beat-slam, asr-keyword-glow (the yellow sweep),
multi-phase-camera (footage Ken-Burns), depth-of-field-blur (quote), viewport pan.

## Assets I WISH I had (gaps / your call)
1. **Archival / historical** — the electrification/vintage-grid query returned nothing
   (wikimedia/LoC/openverse). A Vox-style historical aside ("we've built grids before")
   would let us use the `artwork-stage` block. → want me to try harder (extractors / a
   named collection) or drop it?
2. **An animated US map** — the script names Virginia, Arizona, Georgia, Kentucky, Texas.
   A route-map / spatial-pan "where the cost lands" map is a signature Vox move but needs
   a map asset/SVG (not in the pool). Strong addition if you want it.
3. **A real documentary photo** of a house at a data-center fence line / a specific
   Loudoun-County or Arizona establishing shot — gen covers the mood; a real photo would
   hit harder on the human-cost beats. Stock didn't surface a clean one.
4. **Cleaner licensed stock** — a few ddgs results are watermarked (`transmission_01`) or
   off (`desert_campus_02` = rock texture). I'd cull those and can re-pull licensed-only
   (pexels/unsplash/wikimedia) if you want every candidate clean.
5. **OpenAI / Stargate wordmark** for the jobs kicker — deliberately NOT sourced
   (brand-mark risk); the gen control-room covers it better anyway.

## Decision needed
Approve this shot list as-is, or adjust: (a) add archival + a map (I'll source them),
(b) swap any gen↔stock↔video per beat, (c) re-pull licensed-only stock. Then I author the
storyboard + build.
