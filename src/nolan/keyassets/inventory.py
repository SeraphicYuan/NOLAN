"""P3 — surface the collected HERO assets into the inventory the HyperFrames author reads.

The author reads `capture/extracted/asset-descriptions.md` as its ONLY asset menu (the product-launch /
website skills: "read only asset-descriptions.md"), and `scripts/lib/assets.mjs` stages a named basename
from `capture/assets{,/videos}` into the project. So to make a hero USABLE (not a phantom) we:
  1. copy each collected key asset from capture/keyassets/ into capture/assets{,/videos}/ (where staging
     looks — no change to the 6 vendored assets.mjs copies), and
  2. prepend a marker-delimited HERO section to asset-descriptions.md referencing `assets/<base>` with the
     entity's narrative role + spoken anchors, so the author places the REAL logo/portrait/chart at the
     beat that NAMES it — preferring it over generic b-roll.

Idempotent (marker block replaced in place) so it survives the acquisition step re-writing the file — call
this AFTER acquisition. Honesty-tested: every listed hero has a basename that exists under capture/assets.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

HERO_START = "<!-- KEY-ASSETS HERO START -->"
HERO_END = "<!-- KEY-ASSETS HERO END -->"
_VIDEO_EXT = (".mp4", ".mov", ".webm")


def _load_canonical(project_dir: Path) -> Optional[dict]:
    p = Path(project_dir) / "key_assets.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _hero_line(entity: dict, asset: dict, ref: str) -> str:
    role = (entity.get("narrative_role") or "").strip()
    anchors = "; ".join(f'"{m}"' for m in (entity.get("mentions") or [])[:2])
    variant = asset.get("variant", "original")
    rel = " ~related" if asset.get("relevance") == "related" else ""
    vmark = " ✓verified" if asset.get("verified") else ""
    place = f" — place at: {anchors}" if anchors else ""
    return (f"- `{ref}` — {entity.get('name', '?')}: {role} "
            f"[{entity.get('kind', '?')}/{asset.get('type', '?')}/{variant}{rel}{vmark}]{place}  "
            f"_(hero; {asset.get('source') or '?'}; {asset.get('license') or 'license?'})_")


def stage_heroes(project_dir: Path) -> List[Tuple[str, dict, dict]]:
    """Copy each collected hero into capture/assets{,/videos} (where staging looks). Returns
    [(ref, entity, asset)] for each file that exists — ref is `assets/<base>` / `assets/videos/<base>`."""
    project_dir = Path(project_dir)
    data = _load_canonical(project_dir)
    if not data:
        return []
    assets_dir = project_dir / "capture" / "assets"
    (assets_dir / "videos").mkdir(parents=True, exist_ok=True)
    out: List[Tuple[str, dict, dict]] = []
    for e in data.get("entities", []):
        for a in e.get("resolved", []) or []:
            if not a.get("selected", True):              # refine-scope: only the human's FINAL pool
                continue
            src = project_dir / a.get("file", "")
            if not a.get("file") or not src.exists():
                continue
            is_video = src.suffix.lower() in _VIDEO_EXT
            base = src.name
            dest = (assets_dir / "videos" / base) if is_video else (assets_dir / base)
            try:
                shutil.copyfile(src, dest)
            except OSError:
                continue
            ref = f"assets/videos/{base}" if is_video else f"assets/{base}"
            out.append((ref, e, a))
    return out


def write_hero_section(project_dir: Path, log=print) -> int:
    """Stage heroes into capture/assets + prepend/replace the HERO block in asset-descriptions.md."""
    project_dir = Path(project_dir)
    staged = stage_heroes(project_dir)
    lines = [_hero_line(e, a, ref) for ref, e, a in staged]
    ex = project_dir / "capture" / "extracted"
    ex.mkdir(parents=True, exist_ok=True)
    inv = ex / "asset-descriptions.md"
    existing = inv.read_text(encoding="utf-8") if inv.exists() else ""
    if HERO_START in existing and HERO_END in existing:      # idempotent: drop any prior block
        pre, _, rest = existing.partition(HERO_START)
        _, _, post = rest.partition(HERO_END)
        existing = (pre.rstrip() + "\n" + post.lstrip("\n")).lstrip("\n")
    block = ""
    if lines:
        block = (HERO_START + "\n"
                 "# KEY ASSETS — HERO POOL (place these FIRST at the beat that names them; "
                 "prefer over generic b-roll)\n\n" + "\n".join(lines) + "\n" + HERO_END + "\n\n")
    inv.write_text(block + existing, encoding="utf-8")
    log(f"  hero inventory: {len(lines)} asset(s) staged + listed → {inv}")
    return len(lines)


def hero_coverage(project_dir: Path) -> dict:
    """Soft reliability check: which named HERO ENTITIES did the author actually depict in the composition?

    Heroes are an OFFER, not a mandate — the agent may legitimately skip one that doesn't earn a frame
    (a hero named once in passing shouldn't force a logo). The headline is per-ENTITY: an entity counts as
    PLACED if ANY of its selected assets' basenames appears in a composed frame — so placing De Beers' logo
    marks De Beers depicted even if its cutout/footage alternates go unused (they're variants, not misses).
    Per-FILE detail rides along in each entity's `assets`. `composed` is False before authoring runs
    (nothing to measure yet). Returns {composed, total, used, unused, entities:[{entity,kind,placed,assets}]}."""
    project_dir = Path(project_dir)
    data = _load_canonical(project_dir)

    blobs: List[str] = []
    fdir = project_dir / "compositions" / "frames"
    if fdir.is_dir():
        for html in sorted(fdir.glob("*.html")):
            try:
                blobs.append(html.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                pass
    idx = project_dir / "index.html"
    if idx.exists():
        try:
            blobs.append(idx.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    haystack = "\n".join(blobs)
    composed = bool(blobs)

    entities: List[dict] = []
    for e in (data.get("entities", []) if data else []):
        assets = []
        for a in e.get("resolved", []) or []:
            if not a.get("selected", True):
                continue
            f = a.get("file") or ""
            if not f:
                continue
            base = Path(f).name
            assets.append({"base": base, "type": a.get("type", "?"),
                           "used": bool(composed and base in haystack)})
        if not assets:                                   # entity with no selected asset → nothing to place
            continue
        entities.append({"entity": e.get("name", "?"), "kind": e.get("kind", "?"),
                         "placed": any(a["used"] for a in assets), "assets": assets})
    used = sum(1 for e in entities if e["placed"])
    return {"composed": composed, "total": len(entities), "used": used,
            "unused": len(entities) - used, "entities": entities}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.keyassets.inventory",
                                 description="P3 — stage heroes + write the HERO section into asset-descriptions.md")
    ap.add_argument("--project", required=True, help="project dir holding key_assets.json")
    a = ap.parse_args()
    write_hero_section(Path(a.project))


if __name__ == "__main__":
    main()
