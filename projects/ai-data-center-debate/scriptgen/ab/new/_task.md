# NOLAN script AUTO task: "AI Data Center Debate"

Run the whole grounded pipeline end to end — **you choose the angle** — and produce a
finished draft. No human gate.

## Inputs
- **Brief:** `projects/ai-data-center-debate/scriptgen/brief.md`  ·  **Style:** `script_styles/channel-stickman-talks/style_guide.md`
- **Sources manifest:** `projects/ai-data-center-debate/scriptgen/sources/sources.md`  ·  **Fetched text:** `projects/ai-data-center-debate/scriptgen/sources/raw/*.md`

## Subject
AI Data Center Debate

## Step — Fetch any pending sources
These are URLs not yet fetched. Use WebFetch to retrieve each and save the cleaned
text to `projects/ai-data-center-debate/scriptgen/sources/raw/<ID>-<slug>.md`. If one fails, note it and continue.
  - (none)

## Step — Ground the facts → `projects/ai-data-center-debate/scriptgen/facts.md`
Read `projects/ai-data-center-debate/scriptgen/sources/sources.md` first. For any source flagged **⚠ LARGE** (e.g. a
parsed book), DO NOT paste it whole — **chunk-read** it (Read in offset windows) and
extract facts progressively; the draft will consume `facts.md`, not the raw book.
Build a fact sheet grouped by the script's beats. Tag EVERY factual claim (dates, names, numbers, attributions, events) like:
`- <the fact> — src:[S1] · purpose:proof · beat:context · conf:verified · role:supports`
- **src**: `[S1]`, `[S2,S3]` (a fetched source) OR `[needs-check]` (your own knowledge, unverified — allowed, must carry this tag).
- **purpose** (why it earns screen time): `hook` | `proof` | `humanize` | `contrast` | `authority` | `transition`.
- **beat** (where it belongs): `hook` | `context` | `evidence` | `turn` | `close`.
- **conf**: `verified` (source-backed) | `claimed` (asserted, thin) | `disputed`.
- **role** vs the intended argument: `supports` | `challenges` | `context`.
Prefer source-backed facts; never invent a citation. Keep at least a few `challenges` facts so the script can steelman, not cheerlead.

## Step — Propose thesis / angles → `projects/ai-data-center-debate/scriptgen/angles.md`
From the grounded facts, propose **3–5 candidate angles** (a thesis is a *debatable
claim*, not a summary). For each, write:
- **Angle N — <one-line thesis>**
- *supported by:* `[S#, …]` (the facts that carry it) · *tension:* the counter it must handle
- *why compelling:* one sentence (surprise / stakes / reframe)
Vary the angles (cause→effect, comparison, reframe, hidden-detail pivot, contrarian).
Then **choose the strongest angle yourself** (auto mode): mark it with `**[CHOSEN]**` and one sentence of why it wins on evidence + resonance.

## Step — Draft the script → `projects/ai-data-center-debate/scriptgen/drafts/draft-<NN>.md`
**Angle:** use the `**[CHOSEN]**` angle from angles.md.
Write the voiceover using `script_styles/channel-stickman-talks/style_guide.md`'s **How to Apply**
block as your system prompt, drawing facts from `projects/ai-data-center-debate/scriptgen/facts.md` (and raw sources for
detail). Save to `projects/ai-data-center-debate/scriptgen/drafts/draft-<NN>.md` (next unused number — never overwrite an
existing draft or `script.md`).
**Output contract (Director-ready), exactly this shape:**
```
# Video Script

**Total Duration:** M:SS

---

## <Beat name> [0:00 - 0:??]

<voiceover prose>
```
Rules: map the style's beats to `## ` headings; target **~1200 words**
(8.0 min at 150 wpm) and set Total Duration = words/150 as M:SS; timecodes are
estimates by section word-count; every claim must trace to a line in `facts.md`; weave
in at least one `challenges` fact honestly ("some argue… but…").

## Step — Fact-check → `projects/ai-data-center-debate/scriptgen/factcheck.md` + `projects/ai-data-center-debate/scriptgen/citations.md`
For each factual claim in the draft, one row: `claim → [S#] "supporting quote"` **or**
`claim → [needs-check] (model knowledge, unverified)`. List anything unsupported. Write
the full source list + quotes to `projects/ai-data-center-debate/scriptgen/citations.md`. **Never present an unverified
claim as certain** in the script — soften ("it's generally held…") or cut it.

## Step — Write the run report → `projects/ai-data-center-debate/scriptgen/report.md`
A well-formatted summary a producer can read at a glance:
```
# Script run report — <name>

- **Mode:** auto|semi   **Style:** <style_id>   **Target:** <M> min (~<words> words)
- **Sources used:** [S1] title (N words) · [S2] …
- **Angle chosen:** <the thesis>   (rejected: <one-line each>)
- **Draft:** scriptgen/drafts/draft-<NN>.md — <word count> words → <M:SS>
- **Fact-check:** <X claims source-backed, Y flagged needs-check, Z cut>

## Notes
<anything the producer should know: gaps, weak sources, risky claims>
```

Finally (auto mode only): copy your finished draft to `projects/ai-data-center-debate/script.md` so it's
Director-ready.

## Policy (grounded but graceful)
Style governs *voice and structure*; sources govern *facts* — don't let the style's
drama invent facts. Model-knowledge is allowed only if flagged `[needs-check]`. Persist
everything (facts, angles, drafts, report) — never clobber a prior artifact.
