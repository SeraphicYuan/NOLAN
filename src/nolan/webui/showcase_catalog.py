"""The showcase catalog — the authorable motion/block vocabulary, derived.

The showcase page is a *view of what the pipeline can actually author*. It is
built here from the two authoring registries (never a hand-listed copy — that
is the pitfall the wiring checklist calls "catalog-blind"):

  - ``nolan.motion.registry.REGISTRY``   → the 20 motion effects (kind="motion")
  - ``nolan.layout_blocks.TEMPLATES``    → the block authoring templates (kind="block")

Each entry carries its ``purpose`` + ``when_to_use`` + params straight from the
registry, plus a ``preview`` clip path (``render-service/public/previews/<id>.mp4``)
when the preview harness has rendered one. ``authorable`` is False only for a
block template with no adapter (an entry that would silently no-op) — surfaced,
not hidden.

Honesty-tested by ``tests/test_showcase_catalog.py``: every registry id must
appear, so the catalog cannot rot behind the registries.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

_PREVIEW_EXTS = (".mp4", ".webm")

# remotion-lib blocks that are hosts/structure or belong to a non-block flow —
# they legitimately have no Director block-template adapter.
_STRUCTURAL = {"Chapter", "EndCard", "Captions", "Surface", "Montage", "Showcase"}
_ART_FLOW = {"ArtworkStage", "DetailLoupe", "Flashback", "PaperFigure"}

# One-line descriptions for the reverse-orphans (render but not authorable).
_ORPHAN_DESC = {
    "ArchetypeCards": "Three archetype cards, each maxed on one axis and crashed on the rest.",
    "Distribution": "A histogram over a numeric axis — the shape of the data.",
    "Formula": "A single large centered KaTeX equation with a write-on entrance.",
    "Heatmap": "Grid of cells colored by value on a sequential scale (matrices).",
    "LottieIcon": "A designer Lottie asset recolored to the live theme.",
    "UnlockGrid": "A big stamped value beside a grid that unlocks tile-by-tile.",
    "ValueLadder": "A value growing across a time/sequence axis with milestones.",
    "WebVsBoxes": "Sealed 'boxes' vs a self-drawing node graph (left/right contrast).",
}


def library_orphans(repo_root: Path) -> list[str]:
    """remotion-lib blocks that RENDER but no Director path can author.

    Computed = every blocks/library component, minus those a layout_blocks
    adapter produces, minus motion-comp-hosted ones, minus structural/flow
    hosts. Surfaced (not hidden) so the gap is visible; pinned by
    tests/test_block_selectability.py so it can only shrink, never grow silently.
    """
    import re
    lib_ts = (repo_root / "render-service/remotion-lib/src/blocks/library/index.ts").read_text(encoding="utf-8")
    names: set[str] = set()
    for grp in re.findall(r"import \{ ([^}]+) \}", lib_ts):
        names |= {n.strip() for n in grp.split(",")}
    lb = (repo_root / "src/nolan/layout_blocks.py").read_text(encoding="utf-8")
    comps = (repo_root / "render-service/remotion-lib/src/comps.ts").read_text(encoding="utf-8")
    motion_hosted = set(re.findall(r'from "\./([A-Z][a-zA-Z]+)"', comps))
    via_adapter = {c for c in names if re.search(r"[\"']" + c + r"[\"']", lb)}
    orphans = names - via_adapter - motion_hosted - _STRUCTURAL - _ART_FLOW
    return sorted(orphans)


def _humanize(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _param_dict(p) -> Dict[str, Any]:
    return {
        "name": p.name,
        "type": p.type,
        "doc": p.doc,
        "required": bool(p.required),
        "default": p.default,
        "values": p.values,
    }


def _preview_for(previews_dir: Path, entry_id: str) -> Optional[str]:
    """Return the preview clip basename for this entry, or None if unrendered."""
    for ext in _PREVIEW_EXTS:
        if (previews_dir / f"{entry_id}{ext}").exists():
            return f"{entry_id}{ext}"
    return None


def build_showcase_catalog(repo_root: Path) -> Dict[str, Any]:
    """Assemble the authorable-vocabulary catalog from the live registries."""
    from nolan.motion.registry import REGISTRY, SHARED
    from nolan.layout_blocks import TEMPLATES, ADAPTERS

    previews_dir = repo_root / "render-service" / "public" / "previews"

    effects: List[Dict[str, Any]] = []

    # ---- motion effects (spec system) -------------------------------------
    for e in REGISTRY:
        params = [_param_dict(p) for p in e.content] + [_param_dict(p) for p in e.style]
        for name in e.shared:
            sp = SHARED.get(name)
            if sp:
                d = _param_dict(sp)
                d["shared"] = True
                params.append(d)
        effects.append({
            "id": e.id,
            "name": _humanize(e.id),
            "kind": "motion",
            "category": e.category,
            "backend": e.backend,
            "target": e.target,
            "description": e.purpose,
            "when_to_use": e.when_to_use,
            "params": params,
            "preview": _preview_for(previews_dir, e.id),
            "authorable": True,
        })

    # ---- block authoring templates (layout_blocks) ------------------------
    for tid, meta in TEMPLATES.items():
        effects.append({
            "id": tid,
            "name": _humanize(tid),
            "kind": "block",
            "category": "block",
            "backend": "block",
            "target": tid,
            "description": meta.get("purpose", ""),
            "when_to_use": meta.get("when_to_use", ""),
            "params": [],
            "preview": _preview_for(previews_dir, tid),
            "authorable": tid in ADAPTERS,
        })

    # ---- reverse-orphans: render but not authorable (surfaced, not hidden) --
    for name in library_orphans(repo_root):
        effects.append({
            "id": name,
            "name": _humanize(name),
            "kind": "orphan",
            "category": "orphan",
            "backend": "block",
            "target": name,
            "description": _ORPHAN_DESC.get(name, "A remotion-lib block with no authoring path."),
            "when_to_use": "Not currently authorable — renders but no Director block template reaches it. Wire a block template + adapter, or remove.",
            "params": [],
            "preview": _preview_for(previews_dir, name),
            "authorable": False,
        })

    categories = sorted({e["category"] for e in effects})
    return {
        "effects": effects,
        "categories": categories,
        "kinds": ["motion", "block", "orphan"],
        "counts": {
            "total": len(effects),
            "motion": sum(1 for e in effects if e["kind"] == "motion"),
            "block": sum(1 for e in effects if e["kind"] == "block"),
            "orphan": sum(1 for e in effects if e["kind"] == "orphan"),
            "with_preview": sum(1 for e in effects if e["preview"]),
        },
    }
