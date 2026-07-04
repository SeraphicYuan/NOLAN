"""Clone mode — seed a script project with a recovered structure.

The full inverse→forward loop: a deconstructed video's beat structure becomes
the CONSTITUTION for writing a NEW script on a new subject. We create a
normal scriptwriter project (``ScriptProjectStore``) and pre-seed its
``scriptgen/beatmap.md`` with the recovered beats — titles, functions,
pace tags derived from measured energy, and word budgets scaled to the new
target length. The standard v3 flow (add sources → prep → draft) continues
unchanged; the draft agent finds an explicit directive to treat the seeded
beat-map as the structural constitution instead of re-deriving one.

Sponsor beats (``function == "other"``) are excluded from the cloned
structure and noted as an optional slot.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

WORDS_PER_MIN = 150


def _pace_tag(energy: float) -> str:
    return "accelerate" if (energy or 0.5) >= 0.5 else "decelerate"


def build_cloned_beatmap(extract: Dict[str, Any], dec_slug: str,
                         target_minutes: float) -> str:
    """Render the recovered beats as a scriptwriter beatmap.md."""
    beats = [b for b in (extract.get("beats") or []) if b.get("function") != "other"]
    ads = [b for b in (extract.get("beats") or []) if b.get("function") == "other"]
    total = sum(max(0.5, (b.get("t1", 0) or 0) - (b.get("t0", 0) or 0)) for b in beats) or 1.0
    budget = target_minutes * WORDS_PER_MIN

    lines = [
        f"# Beat-map — CLONED STRUCTURE (constitution)",
        "",
        f"SOURCE: recovered from deconstruction `{dec_slug}` "
        f"(`{extract.get('video_path')}`). **Treat THIS beat structure as the",
        "constitution — do NOT re-derive it.** Map the chosen angle onto these",
        "beats; keep their order, functions, and pacing shape. Word budgets are",
        f"scaled to ~{target_minutes:g} min at {WORDS_PER_MIN} wpm.",
        "",
    ]
    for b in beats:
        length = max(0.5, (b.get("t1", 0) or 0) - (b.get("t0", 0) or 0))
        words = int(round(budget * length / total))
        pace = _pace_tag(float(b.get("energy") or 0.5))
        op = b.get("operator") or "literal"
        treat = b.get("dominant_treatment") or "hold"
        lines.append(
            f"## {b.get('title', 'Beat')} · pace:{pace} · ~{words} words · "
            f"function:{b.get('function', 'evidence')}"
        )
        lines.append(
            f"- pairing: `{op}` — visuals relate to narration this way; "
            f"dominant motion: `{treat}`; energy {b.get('energy')}"
        )
        if b.get("said"):
            lines.append(f"- reference narration (for FLAVOR, not content): "
                         f"\"{b['said'][:140]}…\"")
        lines.append("")
    if ads:
        lines.append("_The source video carries a sponsor slot at the analogous "
                     "position (~{:.0%} in); keep or drop as needed._".format(
                         (ads[0].get("t0", 0) or 0) / max(1.0, extract.get("duration") or 1)))
        lines.append("")
    return "\n".join(lines)


def clone_to_script_project(extract: Dict[str, Any], dec_slug: str, *,
                            subject: str, style_id: str,
                            target_minutes: float = 8.0,
                            store_root="projects") -> Dict[str, Any]:
    """Create a script project pre-seeded with the recovered structure."""
    from pathlib import Path

    from nolan.scriptwriter import ScriptProjectStore

    store = ScriptProjectStore(Path(store_root))
    slug = store.create(
        subject, subject=subject, style_id=style_id,
        target_minutes=float(target_minutes),
        description=(f"{subject} — structure cloned from deconstruction "
                     f"'{dec_slug}'"))

    # seed the constitution
    store.beatmap_path(slug).write_text(
        build_cloned_beatmap(extract, dec_slug, float(target_minutes)),
        encoding="utf-8")

    # record provenance in meta (and keep the store's derived fields intact)
    meta = store._load_meta(slug)
    meta["cloned_from_deconstruction"] = dec_slug
    meta["cloned_at"] = datetime.now().isoformat()
    store._save_meta(meta)

    # reference copy of the recovered beats for the draft agent
    (store.scriptgen_dir(slug) / "reference_structure.json").write_text(
        json.dumps({"deconstruction": dec_slug,
                    "video_path": extract.get("video_path"),
                    "beats": [{k: b.get(k) for k in
                               ("title", "function", "operator", "energy",
                                "pace_dir", "transition", "motion_speed",
                                "dominant_treatment", "t0", "t1", "shot_count")}
                              for b in (extract.get("beats") or [])]},
                   indent=2, ensure_ascii=False),
        encoding="utf-8")
    return {"project_slug": slug, "beatmap": str(store.beatmap_path(slug)),
            "beats": len([b for b in (extract.get("beats") or [])
                          if b.get("function") != "other"])}
