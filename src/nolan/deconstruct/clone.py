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


def _write_reference(extract: Dict[str, Any], dec_slug: str, store, slug: str) -> None:
    """Write reference_structure.json — the recovered beats for downstream steps
    (draft agent, Director scene hints, tempo cloning)."""
    (store.scriptgen_dir(slug) / "reference_structure.json").write_text(
        json.dumps({"deconstruction": dec_slug,
                    "video_path": extract.get("video_path"),
                    "duration": extract.get("duration"),
                    "beats": [{k: b.get(k) for k in
                               ("title", "function", "operator", "energy",
                                "pace_dir", "transition", "motion_speed",
                                "dominant_treatment", "asset_types",
                                "t0", "t1", "shot_count")}
                              for b in (extract.get("beats") or [])]},
                   indent=2, ensure_ascii=False),
        encoding="utf-8")


def _seed(extract: Dict[str, Any], dec_slug: str, store, slug: str,
          target_minutes: float) -> None:
    """Seed beatmap + reference + provenance meta on a project."""
    store.beatmap_path(slug).write_text(
        build_cloned_beatmap(extract, dec_slug, float(target_minutes)),
        encoding="utf-8")
    meta = store._load_meta(slug)
    meta["cloned_from_deconstruction"] = dec_slug
    meta["cloned_at"] = datetime.now().isoformat()
    store._save_meta(meta)
    _write_reference(extract, dec_slug, store, slug)


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
    _seed(extract, dec_slug, store, slug, target_minutes)
    return {"project_slug": slug, "beatmap": str(store.beatmap_path(slug)),
            "beats": len([b for b in (extract.get("beats") or [])
                          if b.get("function") != "other"])}


def attach_reference(extract: Dict[str, Any], dec_slug: str, project_slug: str, *,
                     replace_beatmap: bool = False,
                     store_root="projects") -> Dict[str, Any]:
    """Attach a deconstruction to an EXISTING script project.

    Seeds the same artifacts clone mode creates (constitution ``beatmap.md``,
    ``reference_structure.json``, provenance meta → the clone-aware v3/draft
    brief triggers automatically). Refuses to overwrite an existing
    ``beatmap.md`` unless ``replace_beatmap`` — a hand-written or agent-written
    beat-map is real work; overwriting must be explicit.
    """
    from pathlib import Path

    from nolan.scriptwriter import ScriptProjectStore

    store = ScriptProjectStore(Path(store_root))
    if not store.exists(project_slug):
        raise ValueError(f"script project not found: {project_slug}")
    bm = store.beatmap_path(project_slug)
    if bm.exists() and not replace_beatmap:
        raise ValueError("project already has a beatmap.md — pass "
                         "replace_beatmap=true to overwrite it")
    replaced = bm.exists()
    meta = store._load_meta(project_slug)
    _seed(extract, dec_slug, store, project_slug,
          float(meta.get("target_minutes", 8.0)))
    return {"project_slug": project_slug, "attached": dec_slug,
            "beatmap_replaced": replaced,
            "beats": len([b for b in (extract.get("beats") or [])
                          if b.get("function") != "other"])}
