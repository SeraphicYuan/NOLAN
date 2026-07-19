"""HyperFrames SFX — turn scene cue-kinds into ``audio_meta.sfx[]`` entries.

The compose-first finish step (the Phase-3 executor) reads ``scene.data.sfx``
from the ALIGNED frame specs, computes each cue's frame-local offset
(``scene.start + at``), and calls the two helpers here to add SFX to
``audio_meta`` — using the SAME shared resolver the Director mix path uses
(`nolan.sound.resolve`), so HF and the Director pick sounds identically.

The one hard rule: **merge, never regenerate** ``audio_meta`` — rebuilding it
from the engine's neutral sidecar drops ``voices[]`` and silently kills the
bridged VO (the known bgm-wipes-voices incident). ``merge_sfx_into_audio_meta``
refuses to proceed if ``voices[]`` would be lost.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from nolan.sound.resolve import resolve_cue, sfx_event_for_cue, hf_gain
from nolan.sound.registry import validate_scene_sound

# a cue tuple: (frame, offset_s, kind[, gain])
Cue = Tuple[Any, float, str]


def _frame_number(frame_id: Any, index: int) -> int:
    """The 1-based frame number (matches audio_meta voices[].frame / assemble-index
    startOfFrameNumber): the frame id's leading digits (``02-…`` → 2), else order."""
    m = re.match(r"0*(\d+)", str(frame_id))
    return int(m.group(1)) if m else index + 1


def build_audio_meta_sfx(cues: Iterable[Sequence[Any]], *,
                         exclude: tuple = ()) -> List[Dict[str, Any]]:
    """Resolve ``(frame, offset_s, kind[, gain])`` cues → ``audio_meta.sfx[]``.

    A cue whose kind the bank can't resolve is dropped (the caller logs the
    capability gap) rather than placing silence.
    """
    out: List[Dict[str, Any]] = []
    for c in cues:
        frame, offset_s, kind = c[0], c[1], c[2]
        gain = c[3] if len(c) > 3 else None
        ev = sfx_event_for_cue(kind, frame=frame, offset_s=offset_s,
                               gain=gain, exclude=exclude)
        if ev:
            out.append(ev)
    return out


def merge_sfx_into_audio_meta(audio_meta: Dict[str, Any],
                              sfx_events: List[Dict[str, Any]], *,
                              replace: bool = True) -> Dict[str, Any]:
    """MERGE ``sfx_events`` into ``audio_meta['sfx']``, preserving voices[]/bgm.

    Never regenerates ``audio_meta`` (the bgm-wipes-voices guard): raises if
    ``voices[]`` is absent/empty so a stale/neutral sidecar can't silently drop
    the bridged VO. ``replace=True`` clears prior sfx (idempotent re-runs);
    voices and bgm are carried through untouched either way.
    """
    if not isinstance(audio_meta, dict) or not audio_meta.get("voices"):
        raise ValueError(
            "audio_meta must already carry voices[] — refusing to build one "
            "(that would drop the bridged VO; merge, never regenerate)")
    meta = dict(audio_meta)  # shallow copy carries voices[]/bgm through
    meta["sfx"] = (list(sfx_events) if replace
                   else [*(audio_meta.get("sfx") or []), *sfx_events])
    return meta


def apply_scene_sfx(comp: str) -> Dict[str, Any]:
    """THE compose-first SFX executor (finish DAG step, after word-sync).

    Reads ``scene.data.sfx`` off every frame's ALIGNED spec, resolves each cue to
    a curated bank file, **stages it into ``<comp>/assets/sfx/``** (assemble-index
    mounts by a project-relative path that must exist on disk), and MERGES the
    events into ``audio_meta.sfx[]`` — preserving ``voices[]`` (never regenerated).
    Idempotent: re-running replaces the scene-authored sfx (cue_id-tagged) and
    keeps any node-authored sfx. Unresolved cues are reported LOUD (capability gap),
    not silently dropped.

    Returns ``{events, staged, unresolved, invalid}``.
    """
    from nolan.hyperframes import edit as _edit  # lazy (patchable) — avoids import cycle

    pdir = Path(_edit._project_dir(comp))
    sfx_dir = pdir / "assets" / "sfx"
    sfx_dir.mkdir(parents=True, exist_ok=True)

    events: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    invalid: List[str] = []
    staged: Dict[str, str] = {}

    for idx, fr in enumerate(_edit.list_frames(comp)):
        fid = fr.get("id") if isinstance(fr, dict) else fr
        num = _frame_number(fid, idx)
        spec, info = _edit.load_frame_spec(comp, fid)
        frame = spec["frames"][info["i"]]
        for sc in frame.get("scenes", []):
            invalid.extend(validate_scene_sound(sc))          # loud authoring gate
            data = sc.get("data") or {}
            cues = data.get("sfx")
            if not cues:
                continue
            start = float(sc.get("start") or 0)               # frame-local, post-align
            for it in (cues if isinstance(cues, list) else [cues]):
                kind = it.get("cue") if isinstance(it, dict) else None
                if not kind:
                    continue
                at = float(it.get("at", 0) or 0) if isinstance(it, dict) else 0.0
                gain = it.get("gain") if isinstance(it, dict) else None
                r = resolve_cue(kind)
                if not r:
                    unresolved.append({"frame": fid, "scene": sc.get("id"), "cue": kind})
                    continue
                src = Path(r["file"])
                if src.name not in staged:
                    dest = sfx_dir / src.name
                    if src.exists() and not dest.exists():
                        shutil.copy2(src, dest)
                    staged[src.name] = f"assets/sfx/{src.name}"
                events.append({
                    "frame": num, "file": staged[src.name],
                    "offset_s": round(start + at, 3),
                    "duration_s": r.get("duration"),
                    "volume": float(gain if gain is not None else hf_gain(kind)),
                    "kind": kind, "cue_id": r.get("id"),
                })

    am_path = pdir / "audio_meta.json"
    am = json.loads(am_path.read_text(encoding="utf-8")) if am_path.exists() else {}
    keep = [e for e in (am.get("sfx") or []) if not e.get("cue_id")]  # non-scene sfx survives
    merged = merge_sfx_into_audio_meta(am, keep + events, replace=True)
    am_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"events": len(events), "staged": len(staged),
            "unresolved": unresolved, "invalid": invalid}
