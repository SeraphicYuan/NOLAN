"""Project asset pool — the media-bin view over a project's visual assets.

The NLE concept (Premiere's project panel, Resolve's media pool) as a
DERIVED view: nothing here is new storage. The pool is computed at request
time from artifacts that already exist — the scene plan (matched/pinned/
tray/shots/candidates), shortlist.json, the render manifest, the project's
asset directories, attribution licensing — so it can never drift from the
truth (the /map philosophy).

Status ladder (highest wins), with the usage rule the user set — ONLY the
render step changes usage:

    in-video     in output/render_manifest.json (written solely by render)
    selected     referenced by the plan (matched/generated/pinned/tray/shot)
    candidate    an agent runner-up (scene.asset_candidates)
    shortlisted  in the human selects pool (shortlist.json)
    unused       sitting in assets/** with no reference anywhere

Each item carries scene links with ROLES ({scene_id: [matched, pin, tray,
shot, candidate, rendered]}) so the UI filters by scene and answers "where
is this used" bidirectionally.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif",
               ".mp4", ".mov", ".webm", ".m4v"}
_ASSET_DIRS = ("assets/art", "assets/broll", "assets/broll_video",
               "assets/generated", "assets/rendered")

_STATUS_RANK = {"unused": 0, "shortlisted": 1, "candidate": 2,
                "selected": 3, "in-video": 4}


def _norm(p, project_path: Path) -> Optional[str]:
    """Canonical absolute path string for any plan/manifest path value."""
    if not p:
        return None
    try:
        pp = Path(str(p))
        if not pp.is_absolute():
            pp = project_path / pp
        return str(pp.resolve())
    except OSError:
        return None


def build_pool(project_path: Path) -> Dict[str, Any]:
    """The derived pool: {items: [...], counts: {...}, scenes: [ids]}."""
    project_path = Path(project_path).resolve()
    items: Dict[str, Dict[str, Any]] = {}

    def item(path: str) -> Dict[str, Any]:
        it = items.get(path)
        if it is None:
            pp = Path(path)
            it = items[path] = {
                "path": path,
                "name": pp.name,
                "kind": "video" if pp.suffix.lower() in
                        (".mp4", ".mov", ".webm", ".m4v") else "image",
                "exists": pp.is_file(),
                "status": "unused",
                "scenes": {},               # scene_id -> [roles]
                "license": None,
                "source": None,
                "title": None,
                "shortlist_key": None,
                "scene_hint": None,
            }
        return it

    def link(path: Optional[str], scene_id: Optional[str], role: str,
             status: str) -> None:
        if not path:
            return
        it = item(path)
        if scene_id:
            roles = it["scenes"].setdefault(scene_id, [])
            if role not in roles:
                roles.append(role)
        if _STATUS_RANK[status] > _STATUS_RANK[it["status"]]:
            it["status"] = status

    # 1. every media file physically in the project's asset dirs
    for rel in _ASSET_DIRS:
        d = project_path / rel
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in _MEDIA_EXTS:
                item(str(f.resolve()))

    # 2. plan references (selected) + candidates + licensing
    plan = {}
    plan_path = project_path / "scene_plan.json"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("pool: scene_plan unreadable: %s", exc)
    scene_ids: List[str] = []
    for scenes in (plan.get("sections") or {}).values():
        if not isinstance(scenes, list):
            continue
        for s in scenes:
            if not isinstance(s, dict):
                continue
            sid = s.get("id")
            scene_ids.append(sid)
            link(_norm(s.get("matched_asset"), project_path), sid,
                 "matched", "selected")
            if s.get("generated_asset"):
                link(_norm(f"assets/generated/{s['generated_asset']}",
                           project_path), sid, "generated", "selected")
            if s.get("rendered_clip"):
                link(_norm(s.get("rendered_clip"), project_path), sid,
                     "rendered-clip", "selected")
            mc = s.get("matched_clip")
            if isinstance(mc, dict) and mc.get("video_path"):
                link(_norm(mc["video_path"], project_path), sid,
                     "clip", "selected")
            pin = s.get("pinned_asset")
            if isinstance(pin, dict) and pin.get("src"):
                link(_norm(pin["src"], project_path), sid, "pin", "selected")
            for a in (s.get("assets") or []):
                if isinstance(a, dict) and a.get("src"):
                    link(_norm(a["src"], project_path), sid, "tray", "selected")
            for sh in (s.get("shots") or []):
                if isinstance(sh, dict) and sh.get("src"):
                    link(_norm(sh["src"], project_path), sid, "shot", "selected")
            for c in (s.get("asset_candidates") or []):
                if isinstance(c, dict) and c.get("src"):
                    link(_norm(c["src"], project_path), sid,
                         "candidate", "candidate")
            lic = s.get("asset_license")
            if isinstance(lic, dict):
                tgt = _norm(s.get("matched_asset"), project_path)
                if tgt and tgt in items:
                    items[tgt]["license"] = lic.get("license")
                    items[tgt]["source"] = lic.get("source")
                    items[tgt]["title"] = lic.get("title")

    # 3. human shortlist (shortlisted; scene_hint links the scene)
    try:
        from nolan import shortlist as _shortlist
        for it in _shortlist.load(project_path):
            pl = it.get("payload") or {}
            path = None
            if pl.get("source") == "clip" and pl.get("source_video_path"):
                path = _norm(pl["source_video_path"], project_path)
            elif pl.get("source") == "path" and pl.get("path"):
                path = _norm(pl["path"], project_path)
            elif str(it.get("key", "")).startswith("img:"):
                try:
                    from nolan.imagelib import ImageLibrary
                    _, iid, scope = str(it["key"]).split(":", 2)
                    lib = ImageLibrary(scope, project=pl.get("scope_project"))
                    a = lib.catalog.get(int(iid))
                    if a:
                        path = str(lib.abs_path(a))
                except Exception:
                    path = None
            if path:
                link(path, it.get("scene_hint"), "shortlist", "shortlisted")
                items[path]["shortlist_key"] = it.get("key")
                items[path]["scene_hint"] = it.get("scene_hint")
                if it.get("note"):
                    items[path]["note"] = it["note"]

    except Exception as exc:
        logger.warning("pool: shortlist unreadable: %s", exc)

    # 4. render manifest — the ONLY source of "in-video"
    man_path = project_path / "output" / "render_manifest.json"
    if man_path.exists():
        try:
            man = json.loads(man_path.read_text(encoding="utf-8"))
            for sid, paths in (man.get("scenes") or {}).items():
                for p in paths:
                    link(_norm(p, project_path), sid, "rendered", "in-video")
        except Exception as exc:
            logger.warning("pool: render manifest unreadable: %s", exc)

    out = sorted(items.values(),
                 key=lambda it: (-_STATUS_RANK[it["status"]], it["name"]))
    counts: Dict[str, int] = {}
    for it in out:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    return {"project": project_path.name, "items": out, "counts": counts,
            "scenes": scene_ids,
            "has_manifest": man_path.exists()}
