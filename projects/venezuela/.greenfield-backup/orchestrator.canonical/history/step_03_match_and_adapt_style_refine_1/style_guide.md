# Style Guide: Venezuela Documentary

A polished essay-documentary on how a country sitting on the world's largest oil reserves became one of its most fractured societies. Accessible to viewers who know "Venezuela" from the news but not the longer arc — Bolívar, the caudillos, the oil discovery, Gómez, Betancourt, the Caracazo, Chávez, Maduro, Guaidó. Explanatory, not partisan; the script explicitly disavows political statement and frames itself as causal analysis.

## Voice

Conversational essayist addressing the viewer directly ("we're going to explore today," "you might think," "we've taken a look"). The narration moves a general audience through 200 years of Venezuelan history without academic distance — names like Páez and Betancourt are introduced briefly and immediately tied to their structural consequence (fragmented power, failed reform). Educational posture: the script repeatedly refuses to prescribe, most explicitly with "this isn't a political statement — it is an analysis of the causes behind the crisis."

Recurring rhetorical moves the script actually uses:
- **Open on contrast.** The Hook puts cascading waterfalls and rainforests against poverty and political unrest, then escalates to the oil-reserves paradox.
- **One named human voice early.** Maria Rodriguez of Caracas appears in the first 30 seconds for stakes ("We are tired…"). Use this once. Do not invent additional civilian quotes.
- **Orient on first mention.** When a named historical figure (Bolívar, Páez, Gómez, Betancourt, Chávez, Maduro, Guaidó) first appears, the narration should carry a one-sentence orientation — era and role — rather than assume the viewer knows them (e.g., "Páez, the early-19th-century caudillo who broke from Bolívar's Gran Colombia"). Don't rely on name recognition. This is the narrative counterpart to the lower-third rule in Editorial; narrator and screen should land the orientation together.
- **Number the thesis.** The script states three lenses outright: colonial/caudillo legacy, oil dependence, political fragmentation. Each of the three Evidence sections maps to one. Echo this structure visually.
- **Cadence phrase: "here's the key insight."** The script uses this exact phrasing four times — in Thesis, Evidence 1, Evidence 3, and Conclusion. This is one acceptable cadence marker, not a mandatory beat. If a section has its own natural rhetorical pivot, use that instead — two of the four instances read as forced, and those should be allowed to find their own emphasis rather than have the phrase enforced on them.
- **Close on reflection.** The Conclusion ends on "dialogue, reconciliation, and sustainable growth" and a call to stay informed — not on a verdict about Chávez or Maduro. Visuals must hold the same line.

## Look

Cinematic, color-graded, documentary-grade. Four modes, drawn from what this project actually has:

- **Real footage from the indexed library** — three source documentaries cover the territory: *Hugo Chavez — Venezuela's Savior or Destroyer*, *Venezuela's Dark Secret — The History They Don't Teach*, and *Why The US & Venezuela Are On The Brink of War*. Expect strong coverage for: Caracas street life, oil infrastructure, Chávez and Maduro speeches, opposition protests, the migration exodus, hyperinflation-era currency. Coverage will be thinner for the 19th-century caudillo era and pre-Columbian indigenous societies.
- **AI-generated conceptual imagery** to fill the historical gaps the library cannot cover — Arawak and Carib societies, Bolívar's independence campaign, Páez and Gómez-era portraits, the 1989 Caracazo, symbolic compositions for "house of cards" oil economy. Lean cinematic and photorealistic; avoid illustration or caricature. Never generate likenesses of named living political figures (Maduro, Guaidó) — use library footage for those.
- **Text overlays** for the Maria Rodriguez quote, for each "here's the key insight" beat, and for section markers (Hook / Context / Thesis / Evidence 1–3 / Conclusion). Typography-driven, clean, no decorative motion.
- **Information graphics** — a Venezuela map for the Arawak-west / Carib-east split; a 1830→2024 timeline that the three Evidence sections progressively populate; an oil-price chart for the 1970s boom, 1980s crash, and 2014 collapse; a hyperinflation visualization for the Bolívar's collapse.

Match visual register to the script's restraint. Symbolic compositions yes (cracked flag, tilting oil derrick over a city, empty supermarket shelf). Political caricature no.

## Pacing

Total runtime 9:50 (590s). Average scene length ~10s, varied by section:

- **Hook (0:00–0:52, 52s)** — faster, 6–8s scenes; ~7–8 cuts. The waterfall→poverty→oil-paradox progression needs momentum.
- **Context (0:52–2:18, 86s)** — standard ~10s. Indigenous → Spanish colonization → Bolívar → 1821 independence → oil discovery is dense; let each beat breathe but do not stall.
- **Thesis (2:18–3:10, 52s)** — slightly slower around the three-lens enumeration; the section-preview graphic should hold long enough to read (~4–5s).
- **Evidence 1–3 (3:10–8:19, 309s total)** — standard ~10s, with a slight lift around archival or graphic-heavy beats (oil-price chart, Caracazo, hyperinflation). Each section opens with its own labeled card.
- **Conclusion (8:19–9:50, 91s)** — slowest, 12–15s. The three-lens recap and the final reflection both need landing room.

Enforce visual-type variety: no more than 2 consecutive scenes of the same `visual_type`. Every section boundary gets a distinct `text-overlay` or `graphic` marker so the viewer always knows where they are in the three-lens structure.

## Editorial

- **Maria Rodriguez quote:** once only, in the Hook, as a `text-overlay` over Caracas b-roll. Do not reuse her later. Do not invent any other civilian voices.
- **Named historical figures** (Bolívar, Páez, Gómez, Betancourt, Chávez, Maduro, Guaidó) get a brief identifying lower-third the first time they appear.
- **Caudillo era and 1976 oil nationalization** are the script's hardest beats to cover with library footage — plan for `generated-image` and `graphic` to carry these.
- **The three lenses must be visually echoed.** Each Evidence section opens with a small labeled card: "1 — Colonial Legacy & the Caudillos," "2 — The Oil Trap," "3 — Political Fragmentation." The Conclusion's recap calls these back in the same order.
- **The four "here's the key insight" beats** — at 2:18 (Thesis), 3:10–4:58 (Evidence 1, on Gómez), 6:48–8:19 (Evidence 3, on corruption), and 9:30 (Conclusion) — each get a dedicated `text-overlay` scene, not just narration. They are the structural spine.
- **No sustained talking-heads.** The source library has Chávez and Maduro speech footage; intercut, do not park.
- **Maintain analytical neutrality in visuals.** Footage of Chávez rallies and opposition protests should be balanced across the Chávez/Maduro arc. Avoid framing that reads as endorsement of either side.

## Visual Type Vocabulary

- `b-roll` — real footage from the three source documentaries (Caracas, oil infrastructure, Chávez/Maduro speeches, protests, migration, currency)
- `generated-image` — conceptual or historical imagery the library cannot supply (pre-Columbian, 19th-century caudillos, Bolívar campaign, symbolic compositions)
- `text-overlay` — Maria Rodriguez quote, the four "here's the key insight" beats, section markers, the three-lens labels
- `graphic` — Venezuela map, 1830→2024 timeline, oil-price chart, hyperinflation visualization

Target distribution given source-library coverage: ~45% b-roll, ~25% generated-image, ~18% text-overlay, ~12% graphic. Generated-image leans heavier than the template default because the 19th- and early-20th-century material has no archival equivalent in the library.

## Provenance

- **Descended from:** `essay-doc-explainer-v1` (version 1, match score 0.870 — genre exact, duration in range, strong text overlap).

This guide retains the template's full structural skeleton — three-lens thesis, conversational essayist voice, four-mode visual approach, section-marker discipline, and the "here's the key insight" cadence phrase, which the script already uses verbatim four times. The Look section was rewritten around the three actual source documentaries indexed in `source/`, which give strong coverage for contemporary Caracas, oil infrastructure, and the Chávez/Maduro era but require `generated-image` to carry the caudillo and pre-Columbian beats. Pacing windows were tuned to the script's actual 590-second runtime and its specific section boundaries rather than the template's generic ~10-minute defaults. The visual vocabulary is unchanged from the template since the project has no need for tech-explainer extensions; the distribution was shifted toward `generated-image` to reflect the historical depth of the script.
