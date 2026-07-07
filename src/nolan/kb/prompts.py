"""The distillation prompt — turns a raw video-craft source into structured insights.

Adapted from HERMES's youtube_v2 structure (analyst persona → TLDR → atomic
insights → source-quality) but re-domained to VIDEO-MAKING CRAFT: each insight is
a reusable technique with how-to / why-it-works / when-to-use, not a finance idea.
Outputs strict JSON (OpenRouter/qwen has no schema enforcement, so we ask for JSON
and repair leniently downstream).
"""
from __future__ import annotations

from .taxonomy import CATEGORIES, NOLAN_HOOKS

SYSTEM = (
    "You are a master video editor and video-essayist. You extract REUSABLE CRAFT "
    "TECHNIQUES from tutorials, breakdowns, and talks so another creator could apply "
    "them. You are precise, never pad, and never invent facts not in the source. You "
    "output only valid JSON."
)

DISTILL_PROMPT = """Extract the reusable video-making techniques from the source below.

The reader is a video-essay creator who wants ACTIONABLE craft they can apply — not a
summary of what the video said. Every insight must be a single technique they could
practice tomorrow.

## Transcript / source rules
- Expect conversational tone, filler, sponsor reads, and CTAs — IGNORE promotional
  filler ("link in the description", "check out my kit", sponsorships). Extract craft only.
- The creator often circles back to a technique with new examples. Merge ONLY when it is
  literally the same technique — fold the examples into one rich insight.
- Do NOT over-merge. Two related-but-distinct techniques are SEPARATE insights. The test:
  could a creator apply one WITHOUT the other? If yes, split them.
- Reconstruct a technique that is introduced, digressed from, then returned to later.
- Prefer MORE insights over fewer. If you wrote "also" or "additionally" inside one
  technique, split it.

## Hard rules
- Respect every length hint. Be concrete, not generic ("cut on the peak of the motion so
  the eye never lands on the seam", NOT "use good transitions").
- NEVER invent. If a field isn't supported by the source, write "NOT_SPECIFIED".
- `category` MUST be exactly one of: {categories}
- `nolan_hook` MUST be exactly one of: {nolan_hooks}
- `difficulty` MUST be one of: easy, medium, advanced

{length_guidance}

## Output — a single JSON object, no prose, no code fences:
{{
  "tldr": "3-5 sentences: who the creator is, the through-line of the video, and the 2-3 most useful techniques. Under 700 chars.",
  "insights": [
    {{
      "title": "max 8 words, specific (e.g. 'Flow cut on continued motion')",
      "category": "one of the allowed categories",
      "technique": "the named method in 3-6 words",
      "core_idea": "2-3 sentences: what the technique IS. One technique only.",
      "how_to_apply": "2-4 sentences of concrete steps a creator follows to do it.",
      "why_it_works": "1-3 sentences: the perceptual/story principle behind it.",
      "when_to_use": "1-2 sentences: the moment/situation it serves.",
      "when_not": "1 sentence: when it backfires or is overused (or NOT_SPECIFIED).",
      "example": "the specific example the source gave (quote/scene), or NOT_SPECIFIED.",
      "tools_or_assets": "software/assets needed (e.g. 'any NLE; a whoosh SFX'), or NOT_SPECIFIED.",
      "difficulty": "easy | medium | advanced",
      "tags": ["2-5 short lowercase keyword tags"],
      "nolan_hook": "one of the allowed hooks — which capability umbrella this could feed, or 'none'"
    }}
  ],
  "source_quality": {{
    "creator_credibility": "1-2 sentences: who they are and why they're worth learning from (or NOT_SPECIFIED).",
    "argument_quality": "STRONG | MODERATE | WEAK",
    "freshness": "EVERGREEN | RECENT | TREND"
  }}
}}

## Source content
Title: {title}
{content}
"""


def build_prompt(title: str, content: str, length_guidance: str) -> str:
    return DISTILL_PROMPT.format(
        categories=", ".join(CATEGORIES),
        nolan_hooks=", ".join(NOLAN_HOOKS),
        length_guidance=length_guidance,
        title=title or "(untitled)",
        content=content,
    )
