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
