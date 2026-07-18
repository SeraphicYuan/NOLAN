"""Overlay-plate library resolver for the effects umbrella — the shared projects/_library/overlays store
of element/damage PLATE clips (fire, rain, smoke, …) that `blend_overlay` element effects composite over
media at assemble time. Mirrors nolan.audio_mix.load_music_library (a JSON manifest sibling to the media,
merged with a dir scan). Repo-anchored (NOT cwd-relative) so it resolves the same from the compose bridge
or the repo root — the holbein library-CWD lesson ([[project_hf_pipeline_hardening]])."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[3]                 # src/nolan/effects/library.py -> repo root
OVERLAY_LIBRARY = REPO / "projects" / "_library" / "overlays"
OVERLAY_EXTS = {".mp4", ".webm", ".mov"}
_MANIFEST = "overlays.json"


def load_overlay_library(library: Path = None) -> List[Dict[str, Any]]:
    """Every plate clip in the library, manifest-tagged where available. Each: {path, file, effect, blend,
    loop, tags, license, source}. Unmanifested files default effect=<stem-before-dash>, blend=screen."""
    library = Path(library) if library else OVERLAY_LIBRARY
    if not library.exists():
        return []
    manifest: Dict[str, Dict[str, Any]] = {}
    mpath = library / _MANIFEST
    if mpath.exists():
        try:
            for entry in json.loads(mpath.read_text(encoding="utf-8")):
                manifest[entry.get("file", "")] = entry
        except (json.JSONDecodeError, OSError):
            pass
    out: List[Dict[str, Any]] = []
    for f in sorted(library.iterdir()):
        if f.suffix.lower() not in OVERLAY_EXTS:
            continue
        e = manifest.get(f.name, {})
        out.append({"path": f, "file": f.name, "effect": e.get("effect", f.stem.split("-")[0]),
                    "blend": e.get("blend", "screen"), "loop": e.get("loop", True),
                    "tags": e.get("tags", []), "license": e.get("license", ""), "source": e.get("source", "")})
    return out


def resolve_plate(effect_tag: str, library: Path = None) -> Optional[str]:
    """Absolute path (str) of the first library plate whose `effect` matches `effect_tag`, else None
    (element effect not yet stocked — the executor/assembler then skips it, no crash)."""
    if not effect_tag:
        return None
    for p in load_overlay_library(library):
        if p["effect"] == effect_tag:
            return str(p["path"])
    return None


def stocked_effects(library: Path = None) -> set:
    """The set of effect tags that HAVE a plate in the library (for honest UI/gating)."""
    return {p["effect"] for p in load_overlay_library(library)}


def add_plate(src_file, effect: str, *, blend: str = "screen", provenance: Optional[Dict[str, Any]] = None,
              replace: bool = True, library: Path = None) -> Dict[str, Any]:
    """Add / REPLACE the overlay PLATE for `effect` from a local video file. Copies it into the library as
    `<effect>-<pixabay_id|stem>.<ext>`, adds/updates its overlays.json entry (merging the `provenance` dict
    — url/source/tags/license/pixabay_id/w/h/duration — so `nolan effects fetch-plates` can repopulate it),
    and returns the entry. Filesystem-only (the CLI handles URL/id download + probe + provenance lookup);
    `replace` removes any prior plate file+entry for the same effect. This is the seam for expanding the fx
    list — one call per new plate."""
    import shutil
    library = Path(library) if library else OVERLAY_LIBRARY
    library.mkdir(parents=True, exist_ok=True)
    src_file = Path(src_file)
    prov = dict(provenance or {})
    tag = prov.get("pixabay_id") or src_file.stem
    fname = f"{effect}-{tag}{src_file.suffix.lower()}"
    dst = library / fname
    manifest = library / _MANIFEST
    entries = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    if replace:
        for old in [e for e in entries if e.get("effect") == effect]:
            of = library / old.get("file", "")
            if of.exists() and of.resolve() not in (src_file.resolve(), dst.resolve()):
                of.unlink()
        entries = [e for e in entries if e.get("effect") != effect]
    if src_file.resolve() != dst.resolve():
        shutil.copy2(src_file, dst)
    entry = {"file": fname, "effect": effect, "blend": blend, "loop": True, **prov}
    entries.append(entry)
    manifest.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return entry
