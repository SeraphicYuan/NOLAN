"""Composition archetype registry — the SHARED layout vocabulary.

A scene's *composition archetype* is its macro layout (centered-hero, editorial-column, swiss-grid,
split-screen, full-bleed-overlay, focal-card, sidebar, framed). This module is the single accessor for
`themes/composition/archetypes.json` — read by the bespoke agent's brief, the theme selector/validator,
`/map`, and (later) the block composer, so every consumer speaks one dialect. Design + rationale:
`docs/COMPOSITION_ARCHITECTURE.md`. Gold-standard siblings: `nolan.motion.registry`, `nolan.editing`.

Selection is content-first (a beat/scene-type suggests the archetype) constrained by the theme's allowed
set and overridden by an explicit human direction — which the A/B/C/D experiments proved is the lever
that moves an LLM off its left-column default.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO / "themes" / "composition" / "archetypes.json"

# keyword -> archetype id, for parsing an explicit human direction (the proven override)
_DIRECTION_KEYWORDS = [
    (r"\bcent(er|re)", "centered-hero"),
    (r"\bfull[- ]?bleed|\bedge[- ]?to[- ]?edge|\boverlay\b", "full-bleed-overlay"),
    (r"\bsplit|\bside[- ]by[- ]side|\bversus\b|\bvs\b|\bcompar", "split-screen"),
    (r"\bgrid\b|\bmodular\b", "swiss-grid"),
    (r"\bsidebar\b|\brail\b|\bindex\b", "sidebar"),
    (r"\bframe(d)?\b|\bmargin\b", "framed"),
    (r"\bfocal|\bhero (object|subject)|\bcut ?out\b", "focal-card"),
    (r"\bleft[- ]column\b|\beditorial column\b", "editorial-column"),
]
_DEFAULT = "centered-hero"   # the no-signal fallback: full-canvas + symmetric, NOT the left default


@lru_cache(maxsize=1)
def _registry() -> Dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def archetypes() -> Dict[str, Dict[str, Any]]:
    """id -> archetype spec (intent, when_to_use, serves_beats, anchor, balance, density, blocks, exemplar)."""
    return _registry()["archetypes"]


# the module's public REGISTRY handle (what /map's _umbrellas() imports to make the umbrella 'live')
REGISTRY = archetypes()


def grid() -> Dict[str, Any]:
    """The substrate grid every archetype places against (columns, rule-of-thirds bands, safe areas)."""
    return _registry()["grid"]


def get(archetype_id: str) -> Optional[Dict[str, Any]]:
    return archetypes().get(archetype_id)


def ids() -> List[str]:
    return list(archetypes().keys())


# Blocks that are legitimately archetype-AGNOSTIC (no fixed layout): `raw` is the bespoke escape hatch —
# its layout is whatever the agent authors, so it carries a per-scene `meta.archetype`, not a catalog one.
# The coverage honesty test exempts these; everything else must be classified (test_composition.py).
ARCHETYPE_EXEMPT_BLOCKS = frozenset({"raw"})


@lru_cache(maxsize=1)
def _block_map() -> Dict[str, str]:
    """block/scene-type -> archetype id, derived from each archetype's `blocks[]` (the SINGLE source, so
    block<->archetype can't drift into two dialects). First archetype that claims a block wins."""
    out: Dict[str, str] = {}
    for aid, a in archetypes().items():
        for b in a.get("blocks", []):
            out.setdefault(b, aid)
    return out


def block_archetype(block_type: str) -> Optional[str]:
    """The archetype a compose.py block/component belongs to (e.g. stat -> centered-hero). None for the
    archetype-agnostic `raw` escape hatch (use the scene's own meta.archetype there)."""
    return _block_map().get(block_type)


def _beat_archetype(beat: str) -> Optional[str]:
    """Match a beat label against each archetype's serves_beats (substring, both directions)."""
    b = (beat or "").lower()
    if not b:
        return None
    for aid, a in archetypes().items():
        for sb in a.get("serves_beats", []):
            if sb in b or b in sb:
                return aid
    return None


def _direction_archetype(direction: str) -> Optional[str]:
    """An explicit human direction that names an archetype or a layout keyword (the proven override)."""
    d = (direction or "").lower()
    if not d:
        return None
    for aid in archetypes():
        if aid in d:
            return aid
    for pat, aid in _DIRECTION_KEYWORDS:
        if re.search(pat, d):
            return aid
    return None


def resolve(scene_type: Optional[str] = None, beat: str = "", direction: str = "",
            allowed: Optional[List[str]] = None) -> str:
    """Resolve a scene's composition archetype, content-first:
      1. explicit human `direction` (names an archetype / layout keyword) — the proven override;
      2. the scene's `scene_type` (its block, e.g. stat -> centered-hero) — the strongest content signal;
      3. the `beat` label vs serves_beats;
      4. else the fallback (centered-hero — full-canvas, never the left default).
    `allowed` (the theme's allowed set, if it declares one) CONSTRAINS: a resolved id outside `allowed`
    falls back to the theme's first-allowed. `allowed=None` (theme has no composition field yet) = no
    constraint. Returns a valid archetype id, always."""
    cand = (_direction_archetype(direction)
            or (block_archetype(scene_type) if scene_type else None)
            or _beat_archetype(beat)
            or (allowed[0] if allowed else _DEFAULT))
    if cand not in archetypes():
        cand = _DEFAULT
    if allowed and cand not in allowed:
        cand = allowed[0] if allowed[0] in archetypes() else _DEFAULT
    return cand


def exemplar(archetype_id: str) -> Optional[Dict[str, Any]]:
    """The promoted/hand-authored few-shot exemplar for an archetype ({archetype, note, html, tl}), or
    None if not yet seeded. The single biggest LLM-quality lever."""
    a = get(archetype_id) or {}
    rel = a.get("exemplar")
    if not rel:
        return None
    f = REGISTRY_PATH.parent / rel
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def brief_section(archetype_id: str, *, include_exemplar: bool = True) -> str:
    """A ready-to-inject markdown block describing an archetype for an authoring agent — intent, grid
    anchor, balance, density, safe areas, and (optionally) the inline exemplar. This is the LLM-facing
    surface: named archetype + intent + regions, not pixels (what the A/B/C/D experiments proved works)."""
    a = get(archetype_id)
    if not a:
        return ""
    g = grid()
    lines = [
        f"## Composition — the layout archetype: **{archetype_id}**",
        f"- Intent: {a['intent']}",
        f"- Layout (grid guidance, NOT pixels): {a['anchor']}",
        f"- Balance: {a['balance']} · density: {a['density']}",
        f"- Grid: {g['columns']} columns, rule-of-thirds bands {g['bands']}; primary weight near {g['optical_center']}.",
        f"- Safe areas: {g['safe_areas']['caption_keep_out']}; {g['safe_areas']['title_safe']}.",
        "- Compose WITHIN this archetype — it fixes the macro layout; you own the visual design + motion.",
    ]
    if include_exemplar:
        ex = exemplar(archetype_id)
        if ex:
            html = ex.get("html") or []
            tl = ex.get("tl") or []
            lines += [
                "",
                f"### Exemplar (a proven `{archetype_id}` scene — pattern-match its composition, don't copy the content)",
                f"note: {ex.get('note', '')}",
                "```html",
                "\n".join(html)[:1400],
                "```",
                "```js",
                "\n".join(tl)[:900],
                "```",
            ]
    return "\n".join(lines)
