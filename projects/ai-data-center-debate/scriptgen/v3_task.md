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
Preserve the TEXTURE the draft will need — a fact sheet that abstracts away color yields bland prose:
- Keep any VIVID concrete comparator a source gives ("≈ a city the size of X", "vs a 500-job plant", "the size of Central Park") — do NOT reduce it to a bare number.
- When a claim carries a source-given rebuttal/counter ("the company says it's within limits"), keep it ON THE SAME LINE, so in-beat steel-manning survives into the draft instead of being stranded in one weighing section.
- List the `hook`-beat facts CONCRETE-FIRST: a documented, dated, quotable event before any rhetoric/opinion — the first hook fact usually becomes the cold open.
(A counter-source is *grounding material* + a possible hook — NOT automatically the thesis.)

## Step — Propose angles (resonant + right-type + style-fit) → `projects/ai-data-center-debate/scriptgen/angles.md`
FIRST, read `script_styles/channel-stickman-talks/style_guide.md` and INFER the **spine type** this channel builds its videos on — from its Narrative Structure, Devices, Hook Patterns, and exemplars. (Is it a central human/thematic contrast? a biographical braid? a mystery? a mechanism/"how it works"? a data-grounded both-sides argument?) State the inferred spine type in one line at the top of angles.md.

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
Plan the retention curve BEFORE drafting, using `script_styles/channel-stickman-talks/style_guide.md` as the
CONSTITUTION — and read it in FULL, not just its structure.

**Craft vs. clothing — a style guide mixes four layers; handle the last one differently.**
- **SKELETON** — Narrative Structure, Hook types, Close types, the Pacing arc. Positional; honor fully.
- **MUSCLE** — Rhetorical Devices + Sentence-level Style + Transition mechanics. The *movement* (rhetorical-question clusters, in-beat rebuttals, scene-setting, historical precedent, long/short alternation). This is what usually gets lost — honor it fully.
- **SKIN** — Diction and register: the word-choice texture. Honor by ear.
- **CLOTHING** — channel-identity furniture: sponsor reads + coded URLs, the persona label (e.g. an on-screen mascot / "I'm just a ___"), the catchphrase sign-off, membership/newsletter plugs, named recurring segments.
Honor SKELETON + MUSCLE + SKIN in full. Do NOT copy CLOTHING verbatim: **sponsor read + coded URL → SKIP**; persona label / catchphrase sign-off / recurring-segment names → take the FUNCTION (e.g. self-deprecation = disarm-before-a-take) and ADAPT to a neutral equivalent, or SKIP — never claim the channel's literal identity. The guide's **Exemplar Lines** are topic-specific — use them ONLY as a cadence tuning-fork, never transplant.

Treat the guide's **Hook Patterns**, **Narrative Structure**, **Pacing & Rhythm**, and **DON'T**
sections as the SKELETON (hard constraints — the channel's *proven* retention pattern), and mine its
**Rhetorical Devices** + **Sentence-level Style** sections as the MUSCLE every beat must move with.
Do NOT import generic retention advice that conflicts with the guide.

At the TOP of beatmap.md, record once:
- **Spine + arc** — the chosen angle and the guide's beat sequence it rides.
- **Clothing decisions** — how each channel-identity element is handled (sponsor SKIPPED; persona
  label / catchphrase / coded URLs ADAPTED to a neutral functional equivalent, or SKIPPED).

Then a braided beat list. Open with one of the guide's sanctioned **HOOK** types in the first 1–3
sentences; if a source holds a genuine shock/controversy, prefer it AS the cold-open hook, then pivot
within two sentences to the work + the spine. Order the HOOK candidates by CONCRETENESS — a
documented, dated, quotable event beats rhetoric, and the first-listed hook usually becomes the cold
open, so lead with the strongest concrete anchor. Deploy any counter-source/controversy as the HOOK
or an accelerated fact-cluster, NEVER an isolated argue-it-out lecture. Obey the DON'Ts (no isolated
analysis-only sections, no numbered signposting).

Commit BONE + MUSCLE + COLOR on every beat line, so nothing is left to draft-time recall:
`## <beat> · pace:<a/d> · covers:[S#] · serves-spine:<how> · devices:<1–3 named from the guide's
Rhetorical-Devices / Sentence-level catalog that FIT this beat> · anchors:<the specific vivid facts /
quotes / numbers this beat fires — include any verbatim quote to read aloud and the concrete
comparator>` (accelerate on fact clusters; decelerate for emotion/philosophy, per the guide).

## Step — Draft to the beat-map → `projects/ai-data-center-debate/scriptgen/drafts/draft-<NN>.md`
Write the voiceover following `projects/ai-data-center-debate/scriptgen/beatmap.md` and `script_styles/channel-stickman-talks/style_guide.md`'s
**How to Apply** block as your system prompt. The guide governs hook, structure, pacing, sentence
craft, transitions, and the close — obey it as written. For EACH beat, actually deploy the `devices:`
and `anchors:` the beat-map committed: the named devices are a palette + a floor (in service of the
content, never stuffed in for their own sake), and the anchors — vivid comparators and verbatim
quotes — MUST reach the page; do not summarize them back into bare numbers. Obey the craft-vs-clothing
layers from the beat-map: SKIP the sponsor; ADAPT-or-SKIP any channel-identity content (persona label,
catchphrase, coded URLs) — never claim the channel's literal identity; use the guide's **Exemplar
Lines** only as a cadence tuning-fork, never transplant. Land the angle as the script's coherent
core. Keep the **back third story/emotion-forward** (the guide's close). Target **~1200
words** (8.0 min) — stay within ~10%. Director-ready format (`# Video Script` /
`**Total Duration:** M:SS` / `## <Beat> [t]`). Braid, don't chapter; every claim traces to
`facts.md`; save to `projects/ai-data-center-debate/scriptgen/drafts/draft-<NN>.md` (next unused number).

## Step — Fact-check → `projects/ai-data-center-debate/scriptgen/factcheck.md` + `projects/ai-data-center-debate/scriptgen/citations.md`
For each factual claim in the draft, one row: `claim → [S#] "supporting quote"` **or**
`claim → [needs-check] (model knowledge, unverified)`. List anything unsupported. Write
the full source list + quotes to `projects/ai-data-center-debate/scriptgen/citations.md`. **Never present an unverified
claim as certain** in the script — soften ("it's generally held…") or cut it.

## Step — Voice pass (the style twin of the fact-check) → `projects/ai-data-center-debate/scriptgen/stylecheck.md`
Facts get checked; now check STYLE by ear — MUSCLE silently vanishes when left to draft-time recall,
so verify it landed. Read the finished draft against the guide and record a short table in
`projects/ai-data-center-debate/scriptgen/stylecheck.md`:
- **Devices** — for each device the guide labels **[universal]** (plus the key [common] ones), note
  WHERE it lands in the draft, or mark `missing → added` after you fix it. If a beat flattened into
  generic-explainer voice, revise it toward the guide's **Exemplar Lines** cadence (match the rhythm,
  don't transplant the line).
- **Do / Don't** — confirm each DON'T holds; flag and fix any violation.
- **Clothing** — confirm NO channel-identity content was copied verbatim (sponsor skipped; persona /
  catchphrase / coded URLs adapted or skipped); note each decision.
The device budget is a palette and a FLOOR, not a quota — if a beat reads better without a device, say
so. Revise the draft in place; `stylecheck.md` records what changed.

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
