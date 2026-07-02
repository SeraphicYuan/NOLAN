"""Task brief handed to the dispatched script-writing agent.

Mirrors ``webui.operations._style_synthesis_task``: a self-contained markdown
brief the agent reads and executes. Encodes the grounded-but-graceful policy and
the Director-ready ``script.md`` output contract.
"""

from __future__ import annotations

from .store import ScriptProjectStore


def write_script_task(slug: str, store: ScriptProjectStore) -> str:
    """Build the markdown task brief for writing one project's script."""
    meta = store.get(slug)
    base = f"projects/{slug}"
    sg = f"{base}/scriptgen"
    style_id = meta["style_id"]
    target_words = int(meta.get("target_minutes", 8.0) * 150)

    pending = [s for s in meta.get("sources", []) if s.get("status") == "pending"]
    pending_lines = "\n".join(
        f"  - [{s['id']}] {s.get('url') or s.get('title')}" for s in pending
    ) or "  - (none)"

    return f"""# NOLAN script-writing task: "{meta['name']}"

Write a **grounded** voiceover script on the subject below, in the project's
chosen narrative style, and save it as a Director-ready `script.md`.

## Inputs
- **Brief:** `{sg}/brief.md`  (subject, angle, hidden-detail pivot, length)
- **Narrative style guide (voice):** `script_styles/{style_id}/style_guide.md`
  — follow its **How to Apply** block as your system prompt.
- **Sources manifest:** `{sg}/sources/sources.md`
- **Fetched source text:** `{sg}/sources/raw/*.md`

## Subject
{meta['subject']}

## Step 1 — Fetch any pending sources
These sources are URLs not yet fetched. Use WebFetch to retrieve each, and save
the cleaned text to `{sg}/sources/raw/<ID>-<slug>.md`:
{pending_lines}

If a fetch fails, note it and continue — do not block the script on one source.

## Step 2 — Ground the facts → `{sg}/facts.md`
Build a fact sheet for the script. Every factual claim (dates, names, dimensions,
attributions, events) gets a tag:
- `[S1]`, `[S2,S3]` — backed by a fetched source (cite the source id).
- `[model: needs-check]` — from your own knowledge, no source yet. **Allowed**,
  but it must carry this tag so it can be verified.
Group facts by the script's beats. Prefer source-backed facts; never invent a
citation.

## Step 3 — Draft the script → `{base}/script.md`
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
- Target **~{target_words} words** ({meta.get('target_minutes', 8)} min at 150 wpm).
  Set `**Total Duration:**` to `words / 150` rounded to M:SS.
- Bracketed timecodes are estimates; allocate them by section word count.
- Every factual claim in the script must trace to a line in `facts.md`.

## Step 4 — Fact-check → `{sg}/factcheck.md`
For each factual claim in the script, write one row:
`claim → [S#] supporting quote` **or** `claim → [needs-check] (model knowledge, unverified)`.
List any claim you could not support. Then list sources in `{sg}/citations.md`.

## Policy (grounded but graceful)
- Prefer source-backed claims; model-knowledge claims are allowed **only** if
  flagged `[needs-check]` in facts.md and factcheck.md.
- **Never present an unverified claim as certain** in the script — soften it
  ("it's generally held that…") or cut it.
- Style governs *voice and structure*; sources govern *facts*. Don't let the
  style's drama invent facts.

When done, `{base}/script.md` is the deliverable; the grounding artifacts stay in
`{sg}/` for the producer's audit.
"""


# ============================================================================
# v3 pipeline building blocks (rich grounding + angle gate + persisted drafts).
# Shared by prep_task / draft_task / v3_task below. The one-shot
# write_script_task above is retained as an A/B baseline (/write).
# ============================================================================

_FACTS_LEGEND = """Tag EVERY factual claim (dates, names, numbers, attributions, events) like:
`- <the fact> — src:[S1] · purpose:proof · beat:context · conf:verified · role:supports`
- **src**: `[S1]`, `[S2,S3]` (a fetched source) OR `[needs-check]` (your own knowledge, unverified — allowed, must carry this tag).
- **purpose** (why it earns screen time): `hook` | `proof` | `humanize` | `contrast` | `authority` | `transition`.
- **beat** (where it belongs): `hook` | `context` | `evidence` | `turn` | `close`.
- **conf**: `verified` (source-backed) | `claimed` (asserted, thin) | `disputed`.
- **role** vs the intended argument: `supports` | `challenges` | `context`.
Prefer source-backed facts; never invent a citation. Keep at least a few `challenges` facts so the script can steelman, not cheerlead."""


def _fetch_block(sg: str, pending_lines: str) -> str:
    return f"""## Step — Fetch any pending sources
These are URLs not yet fetched. Use WebFetch to retrieve each and save the cleaned
text to `{sg}/sources/raw/<ID>-<slug>.md`. If one fails, note it and continue.
{pending_lines}"""


def _ground_block(sg: str) -> str:
    return f"""## Step — Ground the facts → `{sg}/facts.md`
Read `{sg}/sources/sources.md` first. For any source flagged **⚠ LARGE** (e.g. a
parsed book), DO NOT paste it whole — **chunk-read** it (Read in offset windows) and
extract facts progressively; the draft will consume `facts.md`, not the raw book.
Build a fact sheet grouped by the script's beats. {_FACTS_LEGEND}"""


def _factcheck_block(sg: str) -> str:
    return f"""## Step — Fact-check → `{sg}/factcheck.md` + `{sg}/citations.md`
For each factual claim in the draft, one row: `claim → [S#] "supporting quote"` **or**
`claim → [needs-check] (model knowledge, unverified)`. List anything unsupported. Write
the full source list + quotes to `{sg}/citations.md`. **Never present an unverified
claim as certain** in the script — soften ("it's generally held…") or cut it."""


def _report_block(sg: str, base: str) -> str:
    return f"""## Step — Write the run report → `{sg}/report.md`
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
```"""


def _policy() -> str:
    return """## Policy (grounded but graceful)
Style governs *voice and structure*; sources govern *facts* — don't let the style's
drama invent facts. Model-knowledge is allowed only if flagged `[needs-check]`. Persist
everything (facts, angles, drafts, report) — never clobber a prior artifact."""


def prep_task(slug: str, store: "ScriptProjectStore") -> str:
    """Semi-auto STEP 1 (and the front half of auto): fetch → ground → propose angles."""
    meta = store.get(slug)
    base, sg = f"projects/{slug}", f"projects/{slug}/scriptgen"
    pending = [s for s in meta.get("sources", []) if s.get("status") == "pending"]
    pending_lines = "\n".join(f"  - [{s['id']}] {s.get('url') or s.get('title')}"
                              for s in pending) or "  - (none)"
    return f"""# NOLAN script PREP task: "{meta['name']}"

Research + ground + propose angles for a grounded voiceover script. **Stop after
`angles.md`** — the human picks the angle, then a separate draft task runs.

## Inputs
- **Brief:** `{sg}/brief.md`  (subject, angle hint, pivot, length)
- **Sources manifest:** `{sg}/sources/sources.md`  ·  **Fetched text:** `{sg}/sources/raw/*.md`

## Subject
{meta['subject']}

{_fetch_block(sg, pending_lines)}

{_ground_block(sg)}

{_angles_v3_block(sg, meta['style_id'], meta.get('angle') or '')}

{_policy()}

When done, `{sg}/facts.md` and `{sg}/angles.md` exist and you STOP. Do not draft yet.
"""


def draft_task(slug: str, store: "ScriptProjectStore") -> str:
    """Semi-auto STEP 2 (v3): beat-map the chosen angle onto the guide → draft → fact-check → report."""
    meta = store.get(slug)
    base, sg = f"projects/{slug}", f"projects/{slug}/scriptgen"
    style_id = meta["style_id"]
    minutes = meta.get("target_minutes", 8)
    tw = int(float(minutes) * 150)
    chosen = meta.get("chosen_angle") or "(none set — use the `**[CHOSEN]**` angle in angles.md)"
    return f"""# NOLAN script DRAFT task: "{meta['name']}"

Draft the script to the chosen angle, faithful to the style guide's retention structure, then
fact-check and report. Facts are in `{sg}/facts.md`; angles in `{sg}/angles.md`.

**Chosen angle (the spine — write to THIS):** {chosen}

{_beatmap_block(sg, style_id)}

{_draft_v3_block(base, sg, style_id, tw, minutes)}

{_factcheck_block(sg)}

{_report_block(sg, base)}

{_policy()}

Deliverables: `{sg}/beatmap.md`, a new `{sg}/drafts/draft-<NN>.md`, `{sg}/factcheck.md`,
`{sg}/citations.md`, `{sg}/report.md`. The producer promotes a draft to `{base}/script.md`.
"""


# ---------------------------------------------------------------------------
# v3 auto: grounding + angle gate, with the STYLE GUIDE as the constitution.
# Resonance is required; the SPINE TYPE is inferred from the guide (not fixed);
# the angle is threaded through the guide's proven retention structure/pacing.
# ---------------------------------------------------------------------------

def _spine_infer(style_id: str) -> str:
    return (f"FIRST, read `script_styles/{style_id}/style_guide.md` and INFER the **spine type** "
            "this channel builds its videos on — from its Narrative Structure, Devices, Hook "
            "Patterns, and exemplars. (Is it a central human/thematic contrast? a biographical "
            "braid? a mystery? a mechanism/\"how it works\"? a data-grounded both-sides argument?) "
            "State the inferred spine type in one line at the top of angles.md.")


def _angles_v3_block(sg: str, style_id: str, given_angle: str = "") -> str:
    if given_angle:
        return f"""## Step — Confirm the supplied angle (or improve it) → `{sg}/angles.md`
{_spine_infer(style_id)}
The human SUPPLIED this angle: "{given_angle}". Treat it as the intended spine. Check it is
(a) OF the inferred spine type and (b) resonant + style-fit. If it fits, **adopt it** — write it
as `**[CHOSEN]**` (one line of why, plus one alternative angle for the record). ONLY if it clearly
violates the guide's spine type or is low-resonance should you propose a stronger angle of the
right type and mark THAT `**[CHOSEN]**`, noting why you overrode the human's. Do not burn effort
re-deriving what's already given."""
    return f"""## Step — Propose angles (resonant + right-type + style-fit) → `{sg}/angles.md`
{_spine_infer(style_id)}

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
on why it wins on **resonance + style-fit**."""


def _beatmap_block(sg: str, style_id: str) -> str:
    return f"""## Step — Beat-map the angle onto the guide's structure → `{sg}/beatmap.md`
Plan the retention curve BEFORE drafting, using the selected guide as the CONSTITUTION. Treat
`script_styles/{style_id}/style_guide.md`'s **Hook Patterns**, **Narrative Structure**, **Pacing
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
Each line: `## <beat> · pace:<a/d> · covers:[S#] · serves-spine:<how>`."""


def _draft_v3_block(base: str, sg: str, style_id: str, target_words: int, minutes) -> str:
    return f"""## Step — Draft to the beat-map → `{sg}/drafts/draft-<NN>.md`
Write the voiceover following `{sg}/beatmap.md` and `script_styles/{style_id}/style_guide.md`'s
**How to Apply** block as your system prompt. The guide governs hook, structure, pacing, sentence
craft, transitions, and the close — obey it as written. Land the angle as the script's coherent
core. Keep the **back third story/emotion-forward** (the guide's close). Target **~{target_words}
words** ({minutes} min) — stay within ~10%. Director-ready format (`# Video Script` /
`**Total Duration:** M:SS` / `## <Beat> [t]`). Braid, don't chapter; every claim traces to
`facts.md`; save to `{sg}/drafts/draft-<NN>.md` (next unused number)."""


def v3_task(slug: str, store: "ScriptProjectStore") -> str:
    """v3 (auto): grounded + resonant, right-type angle + retention true to the style guide."""
    meta = store.get(slug)
    base, sg = f"projects/{slug}", f"projects/{slug}/scriptgen"
    style_id = meta["style_id"]
    minutes = meta.get("target_minutes", 8)
    tw = int(float(minutes) * 150)
    pending = [s for s in meta.get("sources", []) if s.get("status") == "pending"]
    pending_lines = "\n".join(f"  - [{s['id']}] {s.get('url') or s.get('title')}"
                              for s in pending) or "  - (none)"
    return f"""# NOLAN script V3 task: "{meta['name']}"

Grounded + a resonant, *right-type* angle + retention that is TRUE TO THE STYLE GUIDE. The guide
is the constitution — it encodes this channel's proven YouTube retention pattern AND implies the
kind of spine its videos are built on. The angle is a resonant spine threaded through the guide;
it must never reorganize the guide's structure.

## Inputs
- **Brief:** `{sg}/brief.md`  ·  **Style (the constitution):** `script_styles/{style_id}/style_guide.md`
- **Sources manifest:** `{sg}/sources/sources.md`  ·  **Fetched text:** `{sg}/sources/raw/*.md`

## Subject
{meta['subject']}

{_fetch_block(sg, pending_lines)}

{_ground_block(sg)}
(A counter-source is *grounding material* + a possible hook — NOT automatically the thesis.)

{_angles_v3_block(sg, style_id, meta.get('angle') or '')}

{_beatmap_block(sg, style_id)}

{_draft_v3_block(base, sg, style_id, tw, minutes)}

{_factcheck_block(sg)}

{_report_block(sg, base)}

Finally: copy your finished draft to `{base}/script.md` so it's Director-ready.

{_policy()}
"""
