# NOLAN script-writing task: "AI Data Center Debate"

Write a **grounded** voiceover script on the subject below, in the project's
chosen narrative style, and save it as a Director-ready `script.md`.

## Inputs
- **Brief:** `projects/ai-data-center-debate/scriptgen/brief.md`  (subject, angle, hidden-detail pivot, length)
- **Narrative style guide (voice):** `script_styles/channel-stickman-talks/style_guide.md`
  — follow its **How to Apply** block as your system prompt.
- **Sources manifest:** `projects/ai-data-center-debate/scriptgen/sources/sources.md`
- **Fetched source text:** `projects/ai-data-center-debate/scriptgen/sources/raw/*.md`

## Subject
AI Data Center Debate

## Step 1 — Fetch any pending sources
These sources are URLs not yet fetched. Use WebFetch to retrieve each, and save
the cleaned text to `projects/ai-data-center-debate/scriptgen/sources/raw/<ID>-<slug>.md`:
  - (none)

If a fetch fails, note it and continue — do not block the script on one source.

## Step 2 — Ground the facts → `projects/ai-data-center-debate/scriptgen/facts.md`
Build a fact sheet for the script. Every factual claim (dates, names, dimensions,
attributions, events) gets a tag:
- `[S1]`, `[S2,S3]` — backed by a fetched source (cite the source id).
- `[model: needs-check]` — from your own knowledge, no source yet. **Allowed**,
  but it must carry this tag so it can be verified.
Group facts by the script's beats. Prefer source-backed facts; never invent a
citation.

## Step 3 — Draft the script → `projects/ai-data-center-debate/script.md`
Write the voiceover using the style guide's **How to Apply** instructions.
**Output contract (Director-ready), exactly this shape:**
```
# Video Script

**Total Duration:** M:SS

---

## <Beat name> [0:00 - 0:??]

<voiceover prose>

## <Next beat> [0:?? - ?:??]

<voiceover prose>
```
Rules:
- Map the style's beats to `## ` section headings (e.g. Hook, Context, Reveal,
  Interpretations, Close). Keep prose continuous and speakable within each.
- Target **~1200 words** (8.0 min at 150 wpm).
  Set `**Total Duration:**` to `words / 150` rounded to M:SS.
- Bracketed timecodes are estimates; allocate them by section word count.
- Every factual claim in the script must trace to a line in `facts.md`.

## Step 4 — Fact-check → `projects/ai-data-center-debate/scriptgen/factcheck.md`
For each factual claim in the script, write one row:
`claim → [S#] supporting quote` **or** `claim → [needs-check] (model knowledge, unverified)`.
List any claim you could not support. Then list sources in `projects/ai-data-center-debate/scriptgen/citations.md`.

## Policy (grounded but graceful)
- Prefer source-backed claims; model-knowledge claims are allowed **only** if
  flagged `[needs-check]` in facts.md and factcheck.md.
- **Never present an unverified claim as certain** in the script — soften it
  ("it's generally held that…") or cut it.
- Style governs *voice and structure*; sources govern *facts*. Don't let the
  style's drama invent facts.

When done, `projects/ai-data-center-debate/script.md` is the deliverable; the grounding artifacts stay in
`projects/ai-data-center-debate/scriptgen/` for the producer's audit.
