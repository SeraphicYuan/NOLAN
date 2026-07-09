---
format: 1920x1080
message: "The AI build-out is real and unstoppable — but its benefits are spread across everyone while its costs land on very specific people."
arc: The boom is real (spend · demand · power · the upside) → So where does the bill land? (power · water · noise · land · no jobs)
audience: News-explainer viewers who want the AI-datacenter numbers straight
---

## Frame 1 — The boom is real

- scene: Highlighter-editorial first act, all asset types — video cold-open, paper stat/chart beats with prop-cutout evidence, and a gen build-out close.
- duration: 67.76s
- transition_in: cut
- poster: 12s
- status: animated
- src: compositions/frames/01-boom.html
- blueprint: compose
- focal: the yellow sweeps on operative words + the counting numerals + the evidence cutouts
- asset_candidates: assets/videos/server.mp4 [video] — server-rack b-roll (root ground, Scene 1); assets/bg_gen_construction.png — data center under construction (Scene 6); assets/props/cash_stack_00.jpg — stack of cash; assets/props/gpu_card_00.jpg — GPU card; assets/props/smart_meter_00.jpg — electric meter
- roles: Scene 1 = TRANSPARENT (root video shows through — scrim + type only, NO ground clip); Scenes 2-5 = PAPER (mist) with prop cutouts + charts; Scene 6 = STILL image ground (bg_gen_construction, dimmed). Supporting: Inter labels, Lora asides, fig tags.
- voiceover: "Now, let's start with the part people online really don't want to hear… We are not un-building this thing."

GROUND CONTRACT (read carefully): This frame is mounted over root-level media. Give NO full-duration base ground. Each scene provides its OWN ground clip gated to its window — EXCEPT Scene 1, which must be fully TRANSPARENT (only a scrim gradient div + type; NO opaque ground) so a root-level `<video>` behind it shows through. Never put a `<video>` in this file.

**Time-coded shot sequence** (seconds into frame; reveals land on cue):
- Scene 1 — COLD OPEN over VIDEO (0.0–8.6s, TRANSPARENT + scrim): a bottom scrim gradient clip; Inter kicker `THE BUILD-OUT`; Libre Franklin footage-white statement lower-left, two lines rising (kinetic-beat-slam, calm): **The boom is real —** / **and it is not stopping.**; yellow block sweeps **real** ~4.4s (asr-keyword-glow). NO ground clip.
- Scene 2 — SPEND, PAPER + evidence (8.6–25.7s, mist ground clip): kicker `THE MONEY`. Two stat lockups count up (counting-dynamic-scale): **$800B** `AI INFRASTRUCTURE — 2026` (~12.8s, yellow underline sweep on land) and **$1T+** `— 2027` (~17s). A `cash_stack` cutout img rises in bottom-right (~10s, gentle scale/settle) and a `gpu_card` cutout slides in (~19s) — evidence. Lora aside (~21.4s): *that's roughly the entire US defense budget — into server farms.*
- Scene 3 — USERS CHART, PAPER (25.7–34.6s, parchment ground clip): h3 **Chatbot users, in one year**. An SVG line DRAWS left→right (svg-path-draw, thick terracotta, round cap) from **400M** to **900M**; a dot marker lands on 900M (~30s); dotted axes; fig-tag *fig. 01*; yellow underline under **900M** on land. Lora aside: *doubled.*
- Scene 4 — POWER CHART, PAPER (34.6–51.4s, parchment ground clip): h3 **Data centers' share of US electricity**. Two bars grow (stat-bars-and-fills): amber **4.4%** `2023` (~37s), sky **7–12%** `2028` (~43s); dotted axis; fig-tag *fig. 02*; yellow underline under **7–12%**. A `smart_meter` cutout img sits right, revealed ~46s; stat lockup **10×** counts up ~47.5s `ONE AI PROMPT vs A GOOGLE SEARCH`.
- Scene 5 — TOWNS CASH IN, PAPER highlight statement (51.4–64.3s, mist ground clip): kicker `AND THE PART CRITICS SKIP`. Statement **Some towns cash in.** — yellow block sweeps **cash in** (~52.6s). Below: **38%** counts up (~54.3s) `LOUDOUN COUNTY, VA — OF THE COUNTY BUDGET`; Lora aside (~62s): *enough that they cut property taxes.*
- Scene 6 — CLOSE over STILL (64.3–67.76s, image ground bg_gen_construction + scrim): footage-white statement **We are not un-building this.**; yellow block sweeps **un-building** (~65.9s); slow Ken-Burns on the ground (multi-phase-camera). Hold to cut (not final frame — no exit).

## Frame 2 — So where does the bill land?

- scene: The costs act, all asset types — the turn on a gen still (+ a small US map), paper power lockup with the real bill cutout, water over stock video, the held quote on the bedroom gen (+ earplugs + the spaceship nightmare), land over pylon video (+ gavel), and the jobs kicker over the lone-worker gen.
- duration: 91.76s
- transition_in: crossfade
- poster: 40s
- status: animated
- src: compositions/frames/02-bill.html
- blueprint: compose
- focal: the bill's line items — swept highlights, counting numerals, one held quote, evidence cutouts
- asset_candidates: assets/bg_bill_turn.png — house vs data center (Scene 1); assets/videos/water.mp4 [video] — cooling-tower b-roll (root ground, Scene 3); assets/bg_noise_house.png — dark bedroom (Scene 4); assets/bg_gen_spaceship_dream.png — spaceship at the window (Scene 4 sub-beat); assets/videos/grid.mp4 [video] — pylon b-roll (root ground, Scene 5); assets/bg_gen_control_room.png — lone worker (Scene 6); assets/props/electric_bill_00.jpg; assets/props/gavel_01.jpg; assets/props/earplugs_00.jpg; assets/props/water_glass_00.jpg; assets/props/us_map_blank_00.png
- roles: Scenes 3 & 5 = TRANSPARENT (root video shows through — scrim + type only, NO ground clip); Scenes 1, 4, 6 = STILL image grounds (dimmed + Ken-Burns); Scene 2 = PAPER (mist) with the bill cutout. Supporting: labels, Lora asides, caption-bars, prop cutouts.
- voiceover: "But — and you knew there was a but coming… OpenAI's giant Stargate site in Texas? About a hundred full-time jobs."

GROUND CONTRACT: NO full-duration base ground. Scenes 3 and 5 must be fully TRANSPARENT (scrim + type only, NO ground clip) so root `<video>` behind shows through. Never put a `<video>` in this file. Other scenes carry their own image/mist ground clip gated to their window.

**Time-coded shot sequence** (seconds into frame):
- Scene 1 — TURN over STILL (0.0–12.3s, image ground bg_bill_turn + scrim + Ken-Burns): kicker `THE BILL`. Two-line footage-white statement: **The benefits are spread out.** (~2.5s) / **The costs land on specific people.** — yellow block sweeps **specific people** (~7s). A small `us_map_blank` cutout appears top-right (~9s) with Virginia's approximate position marked by a yellow dot/highlight; caption-bar (~10.5s): `SO — LET'S FOLLOW THE BILL`.
- Scene 2 — POWER, PAPER + the bill (12.3–28.6s, mist ground clip): kicker `YOUR POWER · VIRGINIA · DOMINION ENERGY`. Three lockups: **×2** `GENERATION TO DOUBLE BY 2039` (~14s); **$103B** counts up `COST, UP TO` (~21s); **+50%** counts up `RESIDENTIAL BILLS, UP TO` (~26s) — yellow underline sweep under +50%. An `electric_bill` cutout img rises in right (~16s, slight tilt/settle) as the physical evidence.
- Scene 3 — WATER over VIDEO (28.6–45.2s, TRANSPARENT + scrim): kicker `WATER` (white). White stat lockups over the video: **43%** `OF THE BIGGEST CENTERS IN HIGH WATER STRESS` (~30s); **1.83B** counts up `GALLONS A YEAR — ONE ARIZONA CAMPUS` (~38s); **≈ 61,000 people** `A CITY THE SIZE OF SANTA CRUZ, CA` (~42s) — yellow block sweep on **61,000 people**. A small `water_glass` cutout lower-right (~34s). NO ground clip.
- Scene 4 — QUOTE over STILL, HELD (45.2–65.9s, image ground bg_noise_house + scrim; depth-of-field-blur rack focus): quote-text lower-left footage-white with quote marks: **"A low drone you don't just hear — you feel it in the walls."** revealing in two gentle phases; yellow sweep on **feel it in the walls** (~51s); Lora attribution *— Virginia residents* (~53s). Caption-bar (~55.5s): **$20,000** `ON WINDOWS + INSULATION — STILL COULDN'T SLEEP` with a small `earplugs` cutout. ~60–64s the ground CROSS-DISSOLVES to bg_gen_spaceship_dream (the 7-year-old's nightmare) as a fine Lora line reads `…nightmares about a spaceship parked outside.` (a held, quiet, cinematic sub-beat).
- Scene 5 — LAND over VIDEO (65.9–78.8s, TRANSPARENT + scrim): kicker `THE LAND · GEORGIA & KENTUCKY`. Statement **Some are losing their land — outright.**; yellow block sweeps **outright** (~69s). A `gavel` cutout lower-right (~71s, settle). Caption-bar (~74s): `EMINENT DOMAIN — FOR THE POWER LINES`. NO ground clip.
- Scene 6 — JOBS KICKER over STILL (78.8–91.76s, image ground bg_gen_control_room + scrim): kicker `AND THE JOBS?`. Three lockups land (counting-dynamic-scale): **< 150** `PERMANENT WORKERS — EVEN THE LARGEST` (~81s); **25** `SOME AS FEW AS` (~84s); **~100** counts up `OPENAI STARGATE, TEXAS — FULL-TIME JOBS` (~88s) — yellow underline under ~100 (~89.3s). FINAL frame: after ~89.5s a quiet settle to the end (the only permitted end-settle).

## Video direction

- **Look:** Highlighter Editorial (Vox) per frame.md — PAPER register (mist/parchment, ink-deep Libre Franklin sentence case, Lora italic asides, Inter label chrome) for argument/data; FOOTAGE register (full-bleed grounds + scrim, footage-white statements lower-left) for the world. Grounds this cut span ALL asset types: stock VIDEO (Scenes F1S1, F2S3, F2S5 — mounted at the host root, archetype B, frame stays transparent), NOLAN-gen stills (F1S6, F2S1/S4/S6), stock/gen PROP CUTOUTS as evidence (cash, GPU, meter, the electricity bill, gavel, earplugs, water glass), and a US map. ONE highlighter-yellow mark per scene, on the spoken cue, ink-deep on yellow.
- **Motion doctrine (greater variation — cite widely):** the sweep IS the word-sync (asr-keyword-glow); statements rise per line (kinetic-beat-slam, calm); numerals count up (counting-dynamic-scale); the users chart DRAWS (svg-path-draw), the power chart GROWS bars (stat-bars-and-fills); prop cutouts reveal with a small scale+settle (center-outward feel); grounds get a slow Ken-Burns (multi-phase-camera); the quote uses rack focus (depth-of-field-blur) and a ground cross-dissolve to the spaceship. Transforms/opacity/onUpdate-proxy only; deterministic, seek-safe; no CSS transitions/repeat/yoyo.
- **Pacing:** reveal on the VO cue across each scene's window; the quote (F2S4) is held/quiet. No front-loading; no mid-frame exits (only F2S6 end-settles).
- **Type safety:** Libre Franklin + Lora + Inter via Google Fonts @import; sentence-case display; content above y≈896px for the caption band.
