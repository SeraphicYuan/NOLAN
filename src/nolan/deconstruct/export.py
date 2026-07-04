"""Export a deconstruction as a Director scene-plan template.

A deconstructed video's beat structure is a PROVEN skeleton: beat order,
functions, durations, pacing shape. This converter promotes it into
``assets/templates/scene_plans/<id>/`` (meta.json + skeleton.json + template.md)
in the exact shape ``orchestrator.template_match`` scores — so the structure
becomes matchable by ``match_and_adapt_style`` for NEW projects.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_DEST = Path("assets/templates/scene_plans")


def _pacing(energy: float) -> str:
    if energy >= 0.6:
        return "fast"
    if energy < 0.4:
        return "slow"
    return "standard"


def _sections(extract: Dict[str, Any]) -> List[Dict[str, Any]]:
    duration = max(1.0, float(extract.get("duration") or 1.0))
    sections = []
    for b in extract.get("beats") or []:
        length = max(0.5, (b.get("t1", 0) or 0) - (b.get("t0", 0) or 0))
        pct = length / duration * 100
        shots = max(1, int(b.get("shot_count") or 1))
        mean_shot = length / shots
        sections.append({
            "name": b.get("title") or "Beat",
            "purpose": (f"{b.get('function', 'beat')} beat — pairs narration via the "
                        f"'{b.get('operator', 'literal')}' operator"
                        + (f"; dominant motion: {b['dominant_treatment']}"
                           if b.get("dominant_treatment") else "")),
            "duration_pct": [max(1, round(pct * 0.8)),
                             max(max(1, round(pct * 0.8)), round(pct * 1.2))],
            "pacing": _pacing(float(b.get("energy") or 0.5)),
            "scene_duration_hint_seconds": [max(1, round(mean_shot * 0.7)),
                                            max(2, round(mean_shot * 1.3))],
            "beat_count_hint": [max(1, round(shots * 0.75)), max(1, round(shots * 1.25))],
        })
    return sections


def export_scene_plan_template(extract: Dict[str, Any], slug: str, title: str,
                               dest_root: Path = DEFAULT_DEST,
                               genres: List[str] | None = None) -> Dict[str, Any]:
    """Write the template dir; returns {"id", "path", "sections"}."""
    template_id = f"decon-{slug[:48].rstrip('-')}-v1"
    duration = int(float(extract.get("duration") or 600))
    beats = extract.get("beats") or []
    operators = sorted({b.get("operator") for b in beats if b.get("operator")})
    functions = [b.get("function") for b in beats]
    has_ad = "other" in functions

    dest = Path(dest_root) / template_id
    dest.mkdir(parents=True, exist_ok=True)

    meta = {
        "id": template_id,
        "kind": "scene_plan",
        "version": 1,
        "name": f"Deconstructed: {title[:60]}",
        "genres": genres or ["documentary", "explainer", "history", "mythology"],
        # The skeleton is %-based, so the structure scales to any runtime —
        # don't lock the range to the SOURCE video's length (that would make
        # e.g. an 8-min project unmatchable against a 30-min reference).
        "duration_range": [max(180, int(duration * 0.25)), int(duration * 1.5)],
        "tags": ([f"op-{o}" for o in operators]
                 + [f"beats-{len(beats)}", "recovered-structure"]
                 + (["sponsor-slot"] if has_ad else [])),
        "summary": (f"Structure recovered from a real video ({len(beats)} beats, "
                    f"{duration}s). Function arc: "
                    f"{' → '.join(dict.fromkeys(functions))}. Dominant pairing "
                    f"operators: {', '.join(operators) or 'n/a'}."),
        "provenance": {
            "derived_from_deconstruction": slug,
            "video_path": extract.get("video_path"),
            "promoted_at": datetime.now().date().isoformat(),
        },
    }
    skeleton = {
        "template_id": template_id,
        "default_runtime_seconds": duration,
        "runtime_range_seconds": [int(duration * 0.7), int(duration * 1.3)],
        "sections": _sections(extract),
    }
    (dest / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
    (dest / "skeleton.json").write_text(json.dumps(skeleton, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    (dest / "template.md").write_text(
        f"# {meta['name']}\n\n{meta['summary']}\n\n"
        f"Recovered by NOLAN video deconstruction from `{extract.get('video_path')}`.\n"
        f"See `video_deconstructions/{slug}/breakdown.md` for the editorial analysis.\n",
        encoding="utf-8")
    return {"id": template_id, "path": str(dest), "sections": len(skeleton["sections"])}
