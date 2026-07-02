# NOLAN script V3 task: "AI Data Center Debate"

Grounded + a resonant, *right-type* angle + retention that is TRUE TO THE STYLE GUIDE. The guide
is the constitution — it encodes this channel's proven YouTube retention pattern AND implies the
kind of spine its videos are built on. The angle is a resonant spine threaded through the guide;
it must never reorganize the guide's structure.

## Inputs
- **Brief:** `projects/ai-data-center-debate/scriptgen/brief.md`  ·  **Style (the constitution):** `script_styles/channel-stickman-talks/style_guide.md`
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
(A counter-source is *grounding material* + a possible hook — NOT automatically the thesis.)

## Step — Propose angles (resonant + right-type + style-fit) → `projects/ai-data-center-debate/scriptgen/angles.md`
FIRST, read `script_styles/channel-stickman-talks/style_guide.md` and INFER the **spine type** this channel
builds its videos on — from its Narrative Structure, Devices, Hook Patterns, and exemplars. (Is
it a central human/thematic contrast? a biographical-mirroring braid? a mystery? a mechanism/
"how it works"? an argument?) State the inferred spine type in one line at the top of angles.md.

Then propose **3–5 candidate angles OF THAT TYPE** (a coherent, *felt* through-line — not a topic,
not a meta-question). For each:
- **Angle N — <one-line thesis in the channel's spine form>**
- *core:* the contrast/mystery/mechanism it turns on · *supported by:* [S#] · *why a viewer cares:* one sentence
Score each 1–5 on THREE axes and SHOW the scores:
- **Resonance** — will a general viewer *feel* it and care? (the constant requirement)
- **Evidence** — source-backed?
- **Style-fit** — deliverable *through* this guide's arc + pacing, WITHOUT isolated meta/lecture beats?
**Penalize** angles that are low-resonance OR of a type this guide does NOT use (e.g. a dry
"is it real / who wrote it" debate when the guide's spine is human-thematic). Such material is
*grounding* + a possible hook, not the spine. Mark the winner `**[CHOSEN]**` with one sentence
on why it wins on **resonance + style-fit**.

## Step — Beat-map the angle onto the guide's structure → `projects/ai-data-center-debate/scriptgen/beatmap.md`
Plan the retention curve BEFORE drafting, using the selected guide as the CONSTITUTION. Treat
`script_styles/channel-stickman-talks/style_guide.md`'s **Hook Patterns**, **Narrative Structure**, **Pacing
& Rhythm**, and **DON'T** sections as HARD constraints — this is the channel's *proven* retention
pattern; do NOT import generic retention advice that conflicts with it. Produce a beat list that:
- Opens with one of the guide's sanctioned **HOOK** types in the first 1–3 sentences; if a source
  holds a genuine shock/controversy, prefer it AS the cold-open hook, then pivot within two
  sentences to the work + the spine.
- Follows the guide's beat sequence, **braided** — each fact cashed out against the angle.
- Tags each beat `pace: accelerate|decelerate` per the guide (accelerate on fact clusters;
  decelerate for emotion/philosophy).
- Deploys any counter-source/controversy as the HOOK or an **accelerated fact-cluster**, NEVER as
  an isolated argue-it-out lecture beat.
- Obeys the DON'Ts: no isolated analysis-only sections, no numbered signposting.
Each line: `## <beat> · pace:<a/d> · covers:[S#] · serves-spine:<how>`.

## Step — Draft to the beat-map → `projects/ai-data-center-debate/scriptgen/drafts/draft-<NN>.md`
Write the voiceover following `projects/ai-data-center-debate/scriptgen/beatmap.md` and `script_styles/channel-stickman-talks/style_guide.md`'s
**How to Apply** block as your system prompt. The guide governs hook, structure, pacing, sentence
craft, transitions, and the close — obey it as written. Land the angle as the script's coherent
core. Keep the **back third story/emotion-forward** (the guide's close). Target **~1200
words** (8.0 min) — stay within ~10%. Director-ready format (`# Video Script` /
`**Total Duration:** M:SS` / `## <Beat> [t]`). Braid, don't chapter; every claim traces to
`facts.md`; save to `projects/ai-data-center-debate/scriptgen/drafts/draft-<NN>.md` (next unused number).

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

Finally: copy your finished draft to `projects/ai-data-center-debate/script.md` so it's Director-ready.

## Policy (grounded but graceful)
Style governs *voice and structure*; sources govern *facts* — don't let the style's
drama invent facts. Model-knowledge is allowed only if flagged `[needs-check]`. Persist
everything (facts, angles, drafts, report) — never clobber a prior artifact.
