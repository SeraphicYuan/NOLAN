"""Style packs — a channel's per-format design system + show bible.

Broadcast crews ship a design PACKAGE per show: this lower-third kit, this
map style, this quote treatment, this pacing — plus a narrative format (how
episodes open, recur, and end). NOLAN's umbrellas catalog everything it CAN
do; a pack curates what THIS kind of video SHOULD reach for (quality program
step 6). The taste loop stays the learned posterior around this designed
prior — packs are curation, never lock-in: "preferred" reads as prefer-with-
deviation in every consumer prompt.

One pack = one JSON file in ``style_packs/``. Only consumer-backed fields
exist (an authored field with no consumer is a bug):

- ``visual.themes_preferred``   → brief compiler (theme-rank promotion)
- ``visual.motion_preferred/avoid`` → motion_design prompt
- ``visual.templates_preferred``    → slide_designer prompt
- ``visual.transition_bias``        → tempo prompt hint
- ``visual.grade`` / ``visual.pacing`` → brief defaults when the style guide
  is silent (guide wins when it speaks)
- ``format.*``                  → retention linter (script-craft rules) +
  scriptwriter guidance via the brief

Resolution order (:func:`pack_for`): project.yaml ``style_pack`` override →
pack whose ``matches`` names the project's style template id → ``default``.
Validation is loud and registry-backed: unknown motion ids / template ids /
themes / grades fail ``validate_pack`` (tests pin every shipped pack).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]
PACKS_DIR = REPO / "style_packs"

_LINT_RULES = ("hook_question", "object_anchor", "section_out_tension")


def load_packs() -> Dict[str, Dict[str, Any]]:
    packs: Dict[str, Dict[str, Any]] = {}
    if not PACKS_DIR.exists():
        return packs
    for f in sorted(PACKS_DIR.glob("*.json")):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("style pack %s unreadable: %s", f.name, exc)
            continue
        if isinstance(p, dict) and p.get("id"):
            packs[str(p["id"])] = p
    return packs


def get_pack(pack_id: str) -> Optional[Dict[str, Any]]:
    return load_packs().get(str(pack_id))


def pack_for(project_path: Optional[Path] = None,
             template_id: Optional[str] = None) -> Dict[str, Any]:
    """Resolve the pack for a project: explicit override → template match →
    default. Always returns a pack (default ships with the repo)."""
    packs = load_packs()
    if project_path is not None:
        try:
            import yaml
            meta = yaml.safe_load((Path(project_path) / "project.yaml")
                                  .read_text(encoding="utf-8")) or {}
            override = str(meta.get("style_pack") or "").strip()
            if override:
                if override in packs:
                    return packs[override]
                logger.warning("project.yaml style_pack %r unknown — "
                               "falling through (known: %s)",
                               override, sorted(packs))
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("style_pack resolution: project.yaml unreadable: %s", exc)
    if template_id:
        for p in packs.values():
            if template_id in (p.get("matches") or []):
                return p
    return packs.get("default", {"id": "default", "visual": {}, "format": {}})


def validate_pack(pack: Dict[str, Any]) -> List[str]:
    """Loud, registry-backed validation — a pack naming a capability that
    doesn't exist is curation rot."""
    errors: List[str] = []
    if not pack.get("id"):
        errors.append("pack missing id")
    v = pack.get("visual") or {}

    from nolan.motion.registry import BY_ID
    for key in ("motion_preferred", "motion_avoid"):
        for mid in v.get(key) or []:
            if mid not in BY_ID:
                errors.append(f"{pack.get('id')}: visual.{key} names unknown "
                              f"motion effect {mid!r}")

    from nolan.layout_blocks import TEMPLATES
    for tid in v.get("templates_preferred") or []:
        if tid not in TEMPLATES:
            errors.append(f"{pack.get('id')}: templates_preferred names "
                          f"unknown layout template {tid!r}")

    themes_dir = REPO / "themes"
    for th in v.get("themes_preferred") or []:
        if not (themes_dir / th / "tokens.css").exists():
            errors.append(f"{pack.get('id')}: themes_preferred names unknown "
                          f"theme {th!r}")

    grade = v.get("grade")
    if grade is not None:
        from nolan.project_brief import GRADES
        if not isinstance(grade, dict) or grade.get("grade") not in GRADES:
            errors.append(f"{pack.get('id')}: visual.grade.grade must be one "
                          f"of {GRADES}")

    pacing = v.get("pacing")
    if pacing is not None:
        from nolan.tempo_plan import _PROFILES
        if pacing not in _PROFILES:
            errors.append(f"{pack.get('id')}: visual.pacing must be one of "
                          f"{sorted(_PROFILES)}")

    fmt = pack.get("format") or {}
    for rule in (fmt.get("lint") or {}):
        if rule not in _LINT_RULES:
            errors.append(f"{pack.get('id')}: format.lint has unknown rule "
                          f"{rule!r} (known: {_LINT_RULES})")
    return errors


# ---------------------------------------------------------------------------
# Consumer helpers (the prompt injections — generated, never hand-listed)
# ---------------------------------------------------------------------------

def motion_guidance(pack: Dict[str, Any]) -> str:
    v = pack.get("visual") or {}
    pref, avoid = v.get("motion_preferred") or [], v.get("motion_avoid") or []
    if not (pref or avoid):
        return ""
    lines = [f"\n# Style pack: {pack.get('id')} (design system for this format)"]
    if pref:
        lines.append(f"- PREFER these effects (deviate only when clearly better): "
                     f"{', '.join(pref)}")
    if avoid:
        lines.append(f"- AVOID for this format: {', '.join(avoid)}")
    rec = (pack.get("format") or {}).get("recurring") or []
    for r in rec:
        lines.append(f"- Format convention: {r}")
    return "\n".join(lines) + "\n"


def slides_guidance(pack: Dict[str, Any]) -> str:
    v = pack.get("visual") or {}
    pref = v.get("templates_preferred") or []
    if not pref:
        return ""
    return (f"\n# Style pack: {pack.get('id')}\n"
            f"- PREFER these templates for this format (deviate only when "
            f"clearly better): {', '.join(pref)}\n")


def tempo_hint(pack: Dict[str, Any]) -> str:
    bias = (pack.get("visual") or {}).get("transition_bias") or ""
    return f"Format transition bias: {bias}.\n" if bias else ""


def format_rules(pack: Dict[str, Any]) -> Dict[str, Any]:
    """The show bible slice the retention linter enforces."""
    fmt = pack.get("format") or {}
    lint = dict(fmt.get("lint") or {})
    return {"pack": pack.get("id"), "hook": fmt.get("hook"),
            "ending": fmt.get("ending"), "lint": lint}
