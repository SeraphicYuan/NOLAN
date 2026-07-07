"""Typed @-mentions: `@[scope]token` references in human notes.

The Scenes UI autocompletes typed mentions so a human never has to remember
exact ids; this module is the SERVER half — it expands each token into an
explicit, unambiguous reference before the note reaches the revise LLM or a
dispatched Claude agent. One resolver, called at both doors
(/api/scenes/scene/revise and /api/scenes/dispatch).

Scopes (the vocabulary is shared verbatim with the scenes.html popover):
  @[asset]a1            a bound tray asset of the scene(s) in play
  @[pic]123             a picture-library asset (global scope, then project)
  @[vid]<clip id>       a saved clip from the video library
  @[motion]<slug>       a camera treatment (STILL_TREATMENTS) or a motion
                        registry effect id
  @[pool]<filename>     a project-pool media file, matched by basename

Unknown tokens are left verbatim and reported in `unresolved` — loud, never
silently dropped. The legacy bare `@a1` form is still expanded downstream by
iterate.revise.resolve_asset_mentions; this layer only handles the typed form.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

SCOPES = ("asset", "pic", "vid", "motion", "pool")

MENTION_RE = re.compile(r"@\[(%s)\]([\w./\\#:-]+)" % "|".join(SCOPES))


def _asset_ref(aid: str, a: dict) -> str:
    label = a.get("label") or os.path.basename(str(a.get("src", ""))) or aid
    kind = a.get("kind", "image")
    span = ""
    if kind in ("clip", "video") and a.get("clip_start") is not None:
        span = f", {a.get('clip_start')}-{a.get('clip_end')}s"
    return f'[asset {aid} "{label}" ({kind}{span})]'


def _resolve_asset(token: str, scenes: List[dict]) -> Optional[str]:
    for s in scenes or []:
        for a in s.get("assets") or []:
            if isinstance(a, dict) and str(a.get("id")) == token:
                return _asset_ref(token, a)
    return None


def _resolve_pic(token: str, project: Optional[str]) -> Optional[str]:
    try:
        pic_id = int(token.lstrip("#"))
    except ValueError:
        return None
    from nolan.imagelib import ImageLibrary
    scopes = [("global", None)]
    if project:
        scopes.append(("project", project))
    for scope, proj in scopes:
        try:
            lib = ImageLibrary(scope=scope, project=proj)
            a = lib.catalog.get(pic_id)
        except Exception:
            continue
        if a:
            path = (lib.base / a.path).resolve()
            return (f'[picture #{pic_id} "{a.title or path.name}" '
                    f"(imagelib {scope}) file: {path}]")
    return None


def _resolve_vid(token: str, clips: Optional[Iterable[dict]]) -> Optional[str]:
    for c in clips or []:
        if str(c.get("id")) == token:
            label = c.get("label") or c.get("video_name") or token
            return (f'[clip {token} "{label}" source: {c.get("source_video_path")} '
                    f"@ {c.get('clip_start')}-{c.get('clip_end')}s]")
    return None


def _resolve_motion(token: str) -> Optional[str]:
    from nolan.still_motion import STILL_TREATMENTS
    if token in STILL_TREATMENTS:
        return (f"[motion {token} — still-camera treatment; "
                f"lock it via scene.still_treatment]")
    from nolan.motion.registry import get_effect
    eff = get_effect(token)
    if eff:
        params = ", ".join(p.name for p in (eff.content + eff.style)) or "none"
        return (f"[motion {token} — {eff.purpose} "
                f"(motion_spec effect, backend {eff.backend}; params: {params})]")
    return None


def _resolve_pool(token: str, project_dir: Optional[Path]) -> Optional[str]:
    if not project_dir:
        return None
    from nolan.asset_pool import build_pool
    try:
        pool = build_pool(Path(project_dir))
    except Exception:
        return None
    name = os.path.basename(token.replace("\\", "/"))
    for it in pool.get("items", []):
        if it.get("name") == name or str(it.get("path", "")).endswith(token):
            return (f'[pool asset "{it.get("name")}" ({it.get("kind")}, '
                    f"status {it.get('status')}) file: {it.get('path')}]")
    return None


def resolve_mentions(note: Optional[str], *, project_dir: Optional[Path] = None,
                     project: Optional[str] = None, scenes: Optional[List[dict]] = None,
                     clips: Optional[Iterable[dict]] = None) -> Tuple[Optional[str], List[str]]:
    """Expand typed mentions in `note`. Returns (resolved_note, unresolved).

    Unresolved tokens stay verbatim in the note AND are returned so the caller
    can surface them — a mention that resolves to nothing is a user-visible
    event, not a silent no-op.
    """
    if not note or "@[" not in note:
        return note, []
    unresolved: List[str] = []

    def _sub(m: "re.Match[str]") -> str:
        scope, token = m.group(1), m.group(2)
        ref = None
        if scope == "asset":
            ref = _resolve_asset(token, scenes or [])
        elif scope == "pic":
            ref = _resolve_pic(token, project)
        elif scope == "vid":
            ref = _resolve_vid(token, clips)
        elif scope == "motion":
            ref = _resolve_motion(token)
        elif scope == "pool":
            ref = _resolve_pool(token, project_dir)
        if ref is None:
            unresolved.append(m.group(0))
            return m.group(0)
        return ref

    return MENTION_RE.sub(_sub, note), unresolved
