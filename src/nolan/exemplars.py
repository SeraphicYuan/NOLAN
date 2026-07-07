"""Exemplar briefs — "it should feel like THIS" as a project input.

Editors start from pull lists: reference videos whose pacing, texture mix,
and structure the new piece should emulate. NOLAN already deconstructs
library videos (nolan.deconstruct: beats + shots with measured facts); this
module turns those deconstructions into COMPACT, DETERMINISTIC guidance the
authoring prompts consume — study-the-reference becomes a project.yaml line:

    exemplars:
      - the-odyssey-explained-in-25-minutes-best-greek-mythology-documentary

Guidance is measured, not vibes: beat count/length, hook span, function
sequence, texture (asset_type) mix, cut cadence, camera-motion share. An
exemplar named but not deconstructed reports itself loudly instead of
vanishing.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _project_exemplars(project_path: Path) -> List[str]:
    try:
        import yaml
        meta = yaml.safe_load((Path(project_path) / "project.yaml")
                              .read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    ex = meta.get("exemplars")
    if isinstance(ex, str):
        ex = [ex]
    return [str(e).strip() for e in (ex or []) if str(e).strip()]


def _resolve_slug(store, name: str) -> Optional[str]:
    if store.exists(name):
        return name
    low = name.lower()
    for m in store.list():
        if low in str(m.get("slug", "")).lower() \
                or low in str(m.get("title", "")).lower():
            return m.get("slug")
    return None


def summarize_extract(ex: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic pattern summary of one deconstruction extract."""
    beats = ex.get("beats") or []
    shots = ex.get("shots") or []
    dur = float(ex.get("duration") or 0) or 1.0
    hook = next((b for b in beats if (b.get("function") or "") == "hook"), None)
    textures = Counter((s.get("asset_type") or "footage") for s in shots)
    total_shots = max(1, len(shots))
    static = sum(1 for s in shots if (s.get("camera_motion") or "") == "static")
    return {
        "duration_s": round(dur, 1),
        "beats": len(beats),
        "avg_beat_s": round(dur / max(1, len(beats)), 1),
        "hook_s": round(float(hook["t1"]), 1) if hook and hook.get("t1") else None,
        "functions": [b.get("function") or "?" for b in beats],
        "texture_mix": {t: round(100 * n / total_shots)
                        for t, n in textures.most_common(5)},
        "cuts_per_min": round(60 * total_shots / dur, 1),
        "static_share": round(100 * static / total_shots),
    }


def exemplar_guidance(project_path: Path) -> str:
    """The prompt section: one measured paragraph per exemplar (or '')."""
    names = _project_exemplars(project_path)
    if not names:
        return ""
    try:
        from nolan.deconstruct.store import DeconstructionStore
        store = DeconstructionStore()
    except Exception as exc:
        return (f"\n# Exemplars\n- declared but the deconstruction store is "
                f"unavailable: {exc}\n")
    lines = ["\n# Exemplars (deconstructed references — emulate the MEASURED "
             "patterns, not the content)"]
    for name in names:
        slug = _resolve_slug(store, name)
        ex = store.read_extract(slug) if slug else None
        if not ex:
            lines.append(f"- {name}: NOT DECONSTRUCTED yet — run the "
                         "/deconstruct lab on it first (guidance skipped)")
            continue
        s = summarize_extract(ex)
        fn = " → ".join(s["functions"][:8]) + (" → …" if len(s["functions"]) > 8 else "")
        tex = ", ".join(f"{t} {p}%" for t, p in s["texture_mix"].items())
        hook = (f"hook resolves by {s['hook_s']}s; " if s["hook_s"] else "")
        lines.append(
            f"- {slug}: {s['beats']} beats over {s['duration_s']}s "
            f"(avg {s['avg_beat_s']}s); {hook}"
            f"structure {fn}; texture mix {tex}; "
            f"{s['cuts_per_min']} cuts/min, {s['static_share']}% static shots "
            f"— match the RHYTHM and texture VARIETY, at this cadence")
    return "\n".join(lines) + "\n"
