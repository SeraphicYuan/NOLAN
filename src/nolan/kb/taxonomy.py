"""Controlled vocabulary for KB insights — the backbone that keeps tags from sprawling.

Closed sets (like NOLAN's VISUAL_TYPES discipline): a distilled category/difficulty/
nolan_hook must normalize to one of these, LOUDLY snapping unknowns rather than
inventing new buckets.
"""
from __future__ import annotations

# The part of the video-making process a technique belongs to.
CATEGORIES = [
    "scripting-hook",            # writing, hooks, cold opens, retention scripting
    "storytelling-structure",    # narrative arcs, three-act, tension/release
    "pacing-retention",          # rhythm, watch-time, re-hooks, pattern interrupts
    "editing",                   # cuts, transitions, continuity, sequencing
    "sound-design-sfx",          # sound effects, foley, risers, whooshes
    "music",                     # scoring, needle-drops, tempo matching
    "motion-vfx",                # motion graphics, animation, compositing, effects
    "color-grade",               # color grading, LUTs, mood
    "typography-text",           # on-screen text, kinetic type, titles
    "b-roll-footage",            # b-roll strategy, coverage, shot selection
    "packaging-thumbnail-title", # thumbnails, titles, packaging, CTR
    "voiceover-narration",       # VO delivery, narration, ADR
    "research-sourcing",         # research, sourcing, fact-finding, citations
]

DIFFICULTY = ["easy", "medium", "advanced"]

# Which NOLAN capability umbrella a technique could later feed (the promotion seed).
NOLAN_HOOKS = ["editing", "motion", "sound", "pairing", "themes", "blocks",
               "script", "voice", "none"]

_CAT_ALIASES = {
    "hook": "scripting-hook", "script": "scripting-hook", "writing": "scripting-hook",
    "story": "storytelling-structure", "structure": "storytelling-structure",
    "narrative": "storytelling-structure",
    "pacing": "pacing-retention", "retention": "pacing-retention", "rhythm": "pacing-retention",
    "cut": "editing", "cuts": "editing", "transition": "editing", "transitions": "editing",
    "sfx": "sound-design-sfx", "sound": "sound-design-sfx", "sound-design": "sound-design-sfx",
    "foley": "sound-design-sfx",
    "soundtrack": "music", "score": "music", "scoring": "music",
    "motion": "motion-vfx", "vfx": "motion-vfx", "animation": "motion-vfx", "graphics": "motion-vfx",
    "color": "color-grade", "grade": "color-grade", "grading": "color-grade", "colour": "color-grade",
    "text": "typography-text", "type": "typography-text", "typography": "typography-text",
    "titles": "typography-text",
    "broll": "b-roll-footage", "b-roll": "b-roll-footage", "footage": "b-roll-footage",
    "shots": "b-roll-footage",
    "thumbnail": "packaging-thumbnail-title", "title": "packaging-thumbnail-title",
    "packaging": "packaging-thumbnail-title", "ctr": "packaging-thumbnail-title",
    "voiceover": "voiceover-narration", "vo": "voiceover-narration", "narration": "voiceover-narration",
    "research": "research-sourcing", "sourcing": "research-sourcing",
}


def normalize_category(value: str) -> str:
    """Snap a category to the closed set. Unknown → 'editing' (never invent a bucket)."""
    v = (value or "").strip().lower().replace("_", "-").replace(" ", "-")
    if v in CATEGORIES:
        return v
    if v in _CAT_ALIASES:
        return _CAT_ALIASES[v]
    # substring rescue — require a meaningful token match (no 1-2 char prefixes)
    if v:
        for c in CATEGORIES:
            tok = c.split("-")[0]
            if v in c or (len(tok) >= 4 and tok in v):
                return c
        for alias, c in _CAT_ALIASES.items():
            if len(alias) >= 4 and alias in v:
                return c
    return "editing"


def normalize_enum(value: str, allowed: list, default: str) -> str:
    v = (value or "").strip().lower()
    return v if v in allowed else default


# Insight-count guidance by substantive size (transcripts are dense → lower char tiers).
def length_guidance(n_chars: int) -> str:
    if n_chars < 3000:
        return ("This is a SHORT source (~%d chars). Extract every distinct technique — "
                "aim for at least 3 insights." % n_chars)
    if n_chars < 9000:
        return ("This is a MEDIUM source (~%d chars). Extract at least 5 insights, up to 9." % n_chars)
    if n_chars < 25000:
        return ("This is a LONG source (~%d chars). Extract at least 8 insights, up to 14." % n_chars)
    return ("This is a VERY LONG source (~%d chars). Extract at least 12 insights; do not cap "
            "artificially — one per distinct technique." % n_chars)
