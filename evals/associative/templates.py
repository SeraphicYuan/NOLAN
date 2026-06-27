"""Prompt templates for the associative-visual eval spike.

Four templates under test/iteration:
- GEN: line -> associative comfyui_prompt (2a)
- EXPAND: line -> ranked associative search concepts (2b)
- LITERAL_GEN / LITERAL_EXPAND: the current-behaviour baselines
- JUDGE_PAIRWISE / JUDGE_RUBRIC: the (different-model) judge

These are DRAFTS — the whole point of the spike is to iterate them from failures.
"""

from __future__ import annotations

from typing import List, Tuple


def _fewshot_block(pairs: List[Tuple[str, str]]) -> str:
    if not pairs:
        return "(none provided)"
    return "\n".join(f'- LINE: "{said}"  →  SHOWN: {shown}' for said, shown in pairs)


# ---------- (2a) generation ------------------------------------------------

GEN_ASSOCIATIVE = """You are the visual director for a video in the "{style_name}" style.
STYLE LOOK: {look}
RELATIONSHIP TARGET: ASSOCIATIVE — the image must evoke the line's IDEA or MOOD,
NOT literally depict its nouns. Use metaphor, synecdoche, or atmosphere.

How this creator turns non-literal lines into single images:
{fewshot}

LINE: "{line}"
SURROUNDING CONTEXT: "{context}"

Write ONE concrete, cinematic image prompt for a SINGLE shot that conveys the line
associatively and could be generated or sourced. Rules:
- One clear image, not a list. No on-screen text or captions.
- Evoke the concept/feeling; do NOT show the literal subject of the sentence.
- Avoid the first, most obvious cliché for this idea.
- Match the STYLE LOOK (palette, lighting, framing).
Output ONLY the image prompt, one line."""

LITERAL_GEN = """You are the visual director for a video in the "{style_name}" style.
STYLE LOOK: {look}
Write ONE concrete, cinematic image prompt for a SINGLE shot that directly and
literally depicts what this line describes. One clear image, no on-screen text.
LINE: "{line}"
Output ONLY the image prompt, one line."""


# ---------- (2b) retrieval expansion ---------------------------------------

EXPAND_ASSOCIATIVE = """You are sourcing b-roll for a video in the "{style_name}" style.
STYLE LOOK: {look}
LINE: "{line}"
CONTEXT: "{context}"

Give 3 DISTINCT *associative* visual concepts that evoke this line's idea/mood and
plausibly EXIST as stock/library footage — objects, places, atmospheres, NOT the
literal subject. For each, output exactly:
  <3-6 word search phrase> :: <one-line why it evokes the line>
Rank them by how likely real footage exists (most findable first). Output only the 3 lines."""

LITERAL_EXPAND = """Give a 3-6 word stock-footage search phrase that literally matches
this line, then two backups. One per line, phrase only.
LINE: "{line}\""""


# ---------- judge (different model) ----------------------------------------

JUDGE_PAIRWISE = """You are a senior film editor judging which visual better serves a
narration line in the "{style_name}" style (LOOK: {look}).
The relationship goal for non-literal lines is to evoke the idea/mood, not show the
nouns. For concrete lines, a clear literal image is perfectly fine.

LINE: "{line}"   CONTEXT: "{context}"

VISUAL A: {a}
VISUAL B: {b}

Which serves the line better in this style? Reply as JSON:
{{"winner": "A"|"B"|"tie", "reason": "<one sentence>"}}
Judge on: does it convey the line's meaning/feeling, fit the style, and avoid cliché.
Do not prefer a visual merely for being literal or for being abstract — prefer the
one that actually works for THIS line."""

JUDGE_RUBRIC = """Rate this visual proposal for the line, in the "{style_name}" style
(LOOK: {look}). LINE: "{line}".
VISUAL: {visual}
Reply as JSON with integer 1-5 scores:
{{"evokes_concept": n, "on_style": n, "non_cliche": n, "coherence": n, "note": "<short>"}}
- evokes_concept: does it convey the line's idea/mood?
- on_style: matches the look?
- non_cliche: 5 = fresh, 1 = the most overused choice for this idea.
- coherence: a single realizable shot (for retrieval: does the described clip fit)?"""
