# Style Guide: Homer

A polished, accessible-but-rigorous video essay on Homer, the Odyssey, and the two-hundred-year question of whether "Homer" was ever a single man. An explainer-documentary hybrid for a general audience that wants the literature, the archaeology, and the scholarship — without academic distance. Runtime is short (8:05), so every section must earn its seconds; this is a tight, single-metaphor essay, not a sprawling survey.

## Voice

Conversational essayist with a literary ear. Addresses the viewer as a fellow reader straining toward the same unreachable shore ("What Ithaca is to Odysseus, Homer is to us," "We will never dock at Homer"). The register is warmer and more lyrical than a news explainer — it borrows the cadence of the poem it describes — but it stays rigorous: it names dates, diggers, and scholars, and it refuses the easy conspiracy answer in favor of the honest, complicated one.

Educational posture, not advocacy. The live debate here is "did Homer exist / are the epics a forgery," and the script's job is to *analyze* that question, side with scholarly complexity over online flattening, and never sneer. Keep that even hand in every beat.

Recurring rhetorical moves as this script actually uses them:
- **Open on paradox** — seven cities claim a poet none can produce; a blind man writes the most visual verse ever. Lead the hook with the contradiction, not the summary.
- **The controlling metaphor, not a numbered thesis.** This essay does *not* split into "three lenses." It runs one image the whole way: Homer is the Ithaca we never reach. Do not manufacture a numbered structure the script doesn't have — let the metaphor recur instead (Book 8 mirror → the sung breath with "no single author" → the poet "just over the horizon").
- **Quote the poem, not modern people.** The human texture here comes from Homer's own epithets — "swift-footed Achilles," "gray-eyed Athena," Dawn's "rosy fingers," the "wine-dark" sea, the "sweet singing art" — and from Achilles' ghost preferring "a landless servant among the living" to "king over all the dead." The named real people (Schliemann, Calvert, Ventris, Wolf) are cited for what they *did*, not quoted. Preserve that distinction.
- **Cadence phrase: "Notice…" / "Now watch…"** The script's recurring takeaway signal is the invitation to observe the blind poet's choices ("Now watch what this vanished, sightless poet chose to make his hero," "Notice the pattern the blind poet keeps drawing," "And notice his one great failure"). Use this as the key-insight cue instead of the template's "here's the key insight" — mark those beats visually.
- **End on reflection, not conclusion.** Close on the withheld homecoming — the poet left "blind, nameless, singing, forever just over the horizon." No thesis restatement, no call to action.

## Look

Cinematic, color-graded, premium — but with one hard constraint: **the project's source library is empty. There is no indexed archival footage to draw on.** Do not promise drone, news, or contemporary documentary b-roll that does not exist. The look must be built primarily from generated imagery and typography, with real imagery sourced deliberately rather than assumed.

Combine these modes:

- **AI-generated conceptual imagery (dominant mode)** — the workhorse here. Wine-dark seas, a blind bard singing in a torchlit Bronze-Age hall, the wooden horse, the Cyclops' cave, Odysseus lashed to the mast, Penelope at her loom, the olive-tree bed. Lean cinematic and photorealistic-with-a-mythic-cast; symbolic compositions land harder than any literal reconstruction. A recurring visual motif — a solitary figure/voice receding over water — should thread the hook, the Book 8 mirror, and the close.
- **Sourced real imagery** — where authenticity matters, pull from the picture library / asset extractors (Met, Wikimedia): Greek black- and red-figure vase paintings of Odysseus and the Sirens, the ruins at Hisarlik/Troy, Linear B tablets, early manuscript pages of the Odyssey, portraits/busts of Schliemann and the idealized blind "Homer." Treat these as museum-grade stills, not stock b-roll.
- **Text overlays** — for the epithets (set them as recurring typographic refrains), for the "Notice…/Now watch…" key-insight beats, and for section markers. Clean, typography-driven, serif-forward to match the literary subject.
- **Information graphics** — a map of the seven cities claiming Homer and of Odysseus's voyage across the Mediterranean; a timeline (oral tradition → ~700 BC composition → the 24 books carved up ~400 years later → Wolf 1795 → Schliemann/Calvert 1873 → Ventris 1952); the ram-escape and Nobody/name beats as small diagrammatic cards.

Avoid the stock-footage look entirely — there is no real archival library to fall back on, so the burden is on generation quality and museum sourcing.

## Pacing

Total runtime 8:05 (~485s), eight sections. Average scene ~8–11s, varied by section. Tuned to *this* script's proportions, not the template's 10-minute default:

- **Hook (0:00–0:55, ~55s)** — faster, 5–7s scenes, ~8–9 shots, to carry the seven-cities paradox and land the Demodocus reveal.
- **Thesis (0:55–1:25, ~30s)** — slow down to ~10–12s; this is the controlling metaphor and it must register. 2–3 scenes.
- **Body — Book 8 mirror / Sung not written / The wanderer (1:25–5:45)** — standard ~9–11s explanatory pacing. This is the longest stretch; enforce visual-type variety hardest here.
- **The ground under the myth (5:45–7:00, ~75s)** — steady, graphic-and-timeline-heavy; the archaeology and the Wolf question want maps and dates on screen.
- **Recognition & Close (7:00–8:05, ~65s)** — slightly slower, ~12s, for the scar/olive-bed recognition and the receding-poet ending to land.

Visual-type variety enforced: no more than 2 consecutive scenes of the same `visual_type`. Each section opening gets a distinct marker — a text-overlay section card or a graphic beat.

## Editorial

- **Human stakes come from the poem's language**, not from quoting modern scholars. Set the epithets as recurring typographic refrains; give Achilles' underworld line ("rather be a landless servant among the living…") a dedicated text-overlay beat near the close.
- **The archaeology section leans on graphics** — timeline and map are near-mandatory for the 1795/1873/1952 dates and the Troy location. Name Frank Calvert on screen where the narration restores his credit.
- **Mark "Notice…/Now watch…" moments visually** with dedicated text-overlay scenes, not narration alone — these are the key-insight beats.
- **Echo the single controlling metaphor visually**, not a fake multi-part structure. Reprise the receding-figure-over-water motif at the thesis, the Book 8 mirror, and the close so the through-line reads.
- **No sustained talking-heads / no lecture stills** — always intercut generated imagery, vase art, or graphics.
- **Hold the even hand on the "forgery" debate.** Visuals should dramatize scholarly complexity (rival manuscripts, layered oral tradition), never caricature the online skeptics. Symbolic yes; mockery no.

## Visual Type Vocabulary

Tuned to this project. `generated-image` is promoted to the primary mode because there is no indexed footage; `b-roll` is retained but redefined for sourced museum/site imagery rather than a live library.

- `generated-image` — AI-generated mythic/cinematic stills and short-animated imagery (the dominant mode)
- `b-roll` — **sourced** real imagery: vase paintings, site photography (Troy), Linear B tablets, manuscripts, historical portraits/busts. Not a live indexed library — each must be fetched via the picture library / extractors.
- `text-overlay` — typography-driven scenes: epithet refrains, "Notice…" key-insight beats, section markers, the Achilles quote
- `graphic` — maps (seven cities, the voyage), the historical timeline, small explanatory diagrams

Target distribution for this project (weighted away from the template default because the library is empty): ~45–55% `generated-image`, ~15–20% `b-roll` (sourced), ~15–20% `text-overlay`, ~15% `graphic`. If museum sourcing underdelivers, absorb the shortfall into `generated-image`, not stock.

## Provenance

- **Descended from template:** `essay-doc-explainer-v1`, version 1 (match score 0.890 — exact genre, in-range duration, strong text overlap).

This project keeps the template's explainer-documentary spine: conversational-but-rigorous voice, educational-not-advocacy posture on a live debate, the four-mode look, section-marker discipline, and enforced visual-type variety. Three things changed for Homer specifically. First, the multi-part numbered thesis was dropped — this script runs a single controlling metaphor ("Homer is the Ithaca we never reach"), so the guide directs visual reprises of that motif instead of a "three lenses" structure. Second, the cadence phrase "here's the key insight" was replaced with the script's own recurring "Notice…/Now watch…" invitation to observe the blind poet's choices, and the "quote named modern people" move was re-pointed at the poem's own epithets and Achilles' underworld line, since the script cites Schliemann/Calvert/Ventris/Wolf for their actions but never quotes them. Third, and most consequentially, the source library is empty: the `Look` and vocabulary were rebalanced to make `generated-image` the dominant mode, redefine `b-roll` as deliberately sourced museum/site imagery, and forbid promising archival footage that doesn't exist. Pacing windows were re-proportioned to the actual 8:05 runtime rather than the template's 10-minute default.
