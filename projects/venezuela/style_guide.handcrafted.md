# Style Guide: Venezuela Documentary

## Voice

Conversational essayist. Addresses the viewer directly ("we're going to explore," "you might think"). Walks the line between accessible and rigorous: complex history made approachable through plain language and recurring structural cues. Educational posture, not advocacy — the script is explicit that it analyzes causes rather than prescribes politics ("Now, this isn't a political statement — it is an analysis of the causes behind the crisis").

Recurring rhetorical moves:
- Open on a paradox or contrast (rich-in-oil-but-poor)
- Insert short quotes from named real people for human texture (e.g., Maria Rodriguez, a Caracas resident). Use sparingly — once or twice per video.
- Number the thesis explicitly ("we'll examine this through three lenses: first... second... finally")
- Use **"here's the key insight"** as a recurring cadence beat to signal an important takeaway. This phrase is part of the project's voice — keep it consistent.
- End on a reflective, open-ended call to action ("educate ourselves and take action"), not a partisan conclusion

## Look

Cinematic, color-graded, premium-feel. Mixes four visual modes:

- **Real footage from the indexed library** — drone shots of Venezuelan landscapes (Angel Falls, Los Roques), archival news clips of historical figures (Chavez, Bolívar-era reenactments), street footage of contemporary Caracas
- **AI-generated conceptual imagery** for moments where library footage doesn't exist or where a symbolic composition lands harder than literal footage. Examples used: "tropical postcard torn in half to reveal a gritty urban slum underneath," historical scenes of caudillos, the 1989 Caracazo
- **Text overlays** for direct quotes and "key insight" beats — typography-driven, clean
- **Information graphics** for historical and economic context — maps of Venezuela, oil-price timelines, GDP/inflation charts

Generation prompts lean cinematic — "8k photorealistic," dramatic lighting, cinematic color grading. Avoid stock-footage-look b-roll where possible.

## Pacing

Target 9:50 total runtime, 56 scenes, ~10s average per scene.

- **Hook** (0:00–0:52, 8 scenes): faster cuts (~6.5s avg) — opening grabs attention with the rich-but-poor paradox
- **Context, Thesis, Evidence sections** (0:52–8:19): standard ~10s pacing for explanatory work
- **Conclusion** (8:19–9:50): slightly slower (~12s) when synthesis needs to land

Visual-type variety is enforced: no more than 2 consecutive scenes of the same visual_type. Mix b-roll, generated-image, text-overlay, and graphic across each section.

Section breaks (Hook→Context, Thesis→Evidence 1, etc.) get a distinct visual marker — typically a text-overlay with the section name or a graphic — so the structure is felt, not just heard.

## Editorial

- **Quotes as human stakes:** named real people quoted directly (Maria Rodriguez). Treat these as narrative anchors, not filler — dedicate a scene with text-overlay attribution.
- **Historical depth via maps and timelines:** Context section leans on these. Use the existing infographic templates (timeline, map-overlay).
- **"Here's the key insight" → text-overlay:** these moments are not just narration; they get a dedicated text-overlay scene so they visually stand out.
- **Three-lens thesis structure should be visually echoed:** when each Evidence section opens, briefly reference the lens (e.g., a graphic card "Cause #2: Oil Dependency") before diving in.
- **Avoid talking-heads back-to-back:** intercut sustained interview clips with archival or generated imagery between cuts.
- **Don't moralize visually:** the script avoids partisan framing; the visuals should too. Symbolic compositions are fine; political caricature is not.

## Visual Type Vocabulary

This project's declared `visual_type` values (used by `script_to_scenes` and `clip_selector`):

- `b-roll` — real footage from the indexed library, matched by `clip_selector`
- `generated-image` — AI-generated still or short-animated imagery from ComfyUI
- `text-overlay` — typography-driven scenes (quotes, key insights, section markers)
- `graphic` — information graphics (maps, timelines, charts, comparison tables)

Distribution observed in the current scene_plan: b-roll 43%, generated-image 27%, text-overlay 18%, graphic 12%.

## Provenance

Authored by hand for the Venezuela project (2026-01) and reverse-engineered into prose form 2026-04-26.

Candidate for promotion to the `essay-doc-explainer-v1` style template after the project ships, since the structural moves here generalize to any current-events / history / social-issue explainer documentary.
