# Scene-Plan Structure Template: Essay Thesis-Evidence

A 7-section narrative arc for video essays that argue a position by walking the viewer from a hook through historical/contextual setup, an explicit thesis, multiple parallel pieces of evidence, and a synthesizing conclusion. The dominant shape behind most current-events explainer documentaries.

> **Adaptation note:** This template specifies a *shape*, not content. The Director and `script_to_scenes` fill in topic-specific narrative beats. Section count, evidence-section count, and pacing windows are all tunable.

## Narrative shape

```
Hook → Context → Thesis → Evidence₁ → Evidence₂ → … → Evidenceₙ → Conclusion
```

Default `n = 3` (the "three lenses" pattern). Acceptable range: `n ∈ {2, 3, 4, 5}`. Below 2 the argument feels thin; above 5 the runtime balloons and viewers lose track of the through-line.

## Section purposes

| Section | Purpose | Default duration | Pacing |
|---------|---------|------------------|--------|
| **Hook** | Open on a paradox, arresting fact, or contrast that frames the central question. Establish stakes. | 5–10% of runtime | Fast (5–7s scenes) |
| **Context** | Background the viewer needs to understand the rest. Usually historical or definitional. | 12–18% | Standard (8–11s) |
| **Thesis** | Name the question explicitly and announce the structure of the answer ("we'll examine this through three lenses..."). | 8–12% | Standard (8–11s) |
| **Evidence (each)** | One lens / cause / pillar of the argument. Returns to the thesis at the end. | 15–22% each | Standard (8–12s) |
| **Conclusion** | Synthesize the evidence sections; restate the thesis with the case now made; end on reflection or call to action. | 12–18% | Slower (12–15s) |

These percentages should sum to ~100% — adjust with evidence count.

## Beat patterns within sections

### Hook
- Open with a visually arresting moment (often a paradox or contrast — what the viewer doesn't expect)
- Insert a human-stakes beat (quote from a real named person, or a small character moment) within the first 30 seconds
- Pose the central question explicitly toward the end of the section
- Transition into Context with a brief "to understand this, we need to look back" or equivalent bridge

### Context
- Chronological or topical setup; the viewer leaves this section knowing what they need for the argument
- Use historical/contextual visuals heavily here (maps, timelines, archival)
- Avoid lingering — context is in service of the thesis, not its own destination

### Thesis
- A clear single sentence stating what the video argues
- Explicit numbering of the structure ("first... second... third...") if the argument is multi-part
- Optional disclaimer about scope ("this isn't a [partisan/comprehensive/final] take, it's an analysis of X")
- Brief preview of each evidence lens

### Evidence (each section)
- **Opening beat:** name the lens and reference the thesis number visually (e.g., a graphic card "Cause #2: Oil Dependency")
- **Body beats:** present the case, mixing narration with the look's visual modes
- **Closing beat:** return to the thesis — "and that's how X contributed to the divide"
- Pacing tightens slightly mid-section, releases at section end

### Conclusion
- Restate the thesis with the evidence now backing it
- Synthesize across evidence sections (not just summarize each)
- End on reflection, open question, or call to action — match the project's voice (advocacy vs. analysis)
- Final beat is often slowest (12–15s) — let the closing image breathe

## Pacing arc

```
fast    ┐ Hook
        │
medium  ┼── Context, Thesis, Evidence sections (slight ramp from medium to medium-slow)
        │
slow    ┘ Conclusion
```

Variety enforcement (passed to `script_to_scenes` and `clip_selector`):
- No more than 2 consecutive scenes of the same `visual_type`
- Each section break gets a distinct visual marker scene (text-overlay or graphic)

## Adaptation notes for the Director

When generating a project's `scene_plan.json` from this template:

- Pick `n` (evidence section count) from the script's argument structure. If the script has 4 parallel causes, use `n=4`; don't force into 3.
- Adjust default duration percentages proportionally if the runtime target differs from ~10 minutes.
- The Hook's visual paradox / human-stakes beats are mandatory; the rest of the beat patterns are strong defaults but can be adapted.
- If the project's voice is advocacy-leaning rather than analytical, soften or remove the "this isn't a partisan statement" disclaimer in the Thesis section.
- Record the adaptation summary in the project's Provenance section.
