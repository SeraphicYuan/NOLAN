# Style Template: Essay-Doc Explainer

A polished, accessible-but-rigorous video essay format for current-events, history, or social-issue topics. Written for a general audience that wants depth without academic distance. Think: explainer-documentary hybrid.

> **Adaptation note:** This template is a starting point, not a snapshot. Replace specific examples (creator names, topical phrasings) with the project's own. The structural moves are reusable; the surface details are not.

## Voice

Conversational essayist. Addresses the viewer directly ("we're going to explore," "you might think"). Walks the line between accessible and rigorous — complex subject matter made approachable through plain language and recurring structural cues. Educational posture rather than advocacy: analyze causes, do not prescribe.

Recurring rhetorical moves:
- Open on a paradox, contrast, or arresting fact
- Insert short quotes from named real people for human texture (use sparingly — once or twice per video)
- Number the thesis explicitly when multi-part ("we'll examine this through three lenses: first... second... finally")
- Adopt a recurring cadence phrase to signal key takeaways (e.g., "here's the key insight"). Pick one per project and use it consistently.
- End on reflection or open-ended call to action, not partisan conclusion

## Look

Cinematic, color-graded, premium-feel. Combine four modes:

- **Real footage from the indexed library** — archival, drone, news, contemporary documentary
- **AI-generated conceptual imagery** for moments where library footage doesn't exist, or where a symbolic composition lands harder than literal footage
- **Text overlays** for direct quotes, key-insight beats, and section markers — typography-driven, clean
- **Information graphics** for historical context, data, comparisons — maps, timelines, charts

Generation prompts lean cinematic and photorealistic. Avoid stock-footage-look b-roll where the project has access to real archival material.

## Pacing

Target 5–20 minute runtime; this template is tuned around ~10 minutes. Average scene length 8–12 seconds, varied by section:

- **Hook** — faster (5–7s) to grab attention; ~8 scenes in the first ~50 seconds
- **Context / Thesis / Evidence** — standard pacing (~10s avg) for explanatory work
- **Conclusion** — slightly slower (~12–15s) when synthesis needs to land

Visual-type variety is enforced: no more than 2 consecutive scenes of the same `visual_type`. Section breaks get a distinct visual marker (text-overlay or graphic).

## Editorial

- Use named real people's quotes once or twice per video for human stakes; do not over-rely
- Historical/contextual sections lean on maps, timelines, and graphics — use existing infographic templates
- Mark key-insight moments visually with dedicated text-overlay scenes, not just narration
- If the thesis is multi-part (3 lenses, 5 causes, etc.), echo the structure visually at each section opening — a small graphic card naming the section
- Avoid sustained talking-heads — always intercut with imagery
- Match visual register to the script: if the narration avoids partisan framing, visuals should too. Symbolic compositions yes; political caricature no.

## Visual Type Vocabulary

The default vocabulary for this template. Projects can extend or substitute (e.g., a tech-explainer might add `screen-recording` and `code-walkthrough`).

- `b-roll` — real footage from the indexed library
- `generated-image` — AI-generated still or short-animated imagery
- `text-overlay` — typography-driven scenes (quotes, key insights, section markers)
- `graphic` — information graphics (maps, timelines, charts, comparisons)

Reasonable starting distribution: 40–50% b-roll, 20–30% generated-image, 15–20% text-overlay, 10–15% graphic. Tune to source-library availability.

## Adaptation Notes for the Director

When generating a project's `style_guide.md` from this template:

- Replace the cadence phrase ("here's the key insight") if it doesn't fit the project's tone or if the user has signaled a different one
- Adjust the visual_type vocabulary to match available source material — extend it for genres that need new types (tech, personal narrative, etc.); drop ones that won't be used
- Tune pacing windows to actual script duration — proportional, not absolute
- Ground every "Look" specification in what the project's source library actually contains; don't promise archival footage that doesn't exist
- Record the adaptation summary in the project's Provenance section (one short paragraph: what stayed, what changed, why)
