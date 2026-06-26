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
