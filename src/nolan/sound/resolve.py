"""Resolve a cue-kind to a curated bank sound — the shared primitive.

Both the Director mix path (`audio_mix._source_scene_sfx`) and the HyperFrames
finish step turn a `cue` (a registry kind) into an actual file + placement
metadata through here, so the curated bank is preferred over a live website
search and BOTH pipelines pick the same way. Deterministic: highest-rated file
of the kind, round-robining among the top tier so the same whoosh doesn't
repeat within a render. Repo-root-anchored (usable from a bridge/sub-dir).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from nolan.sound.crawl import library_dir      # repo-anchored bank dir
from nolan.sound.registry import BY_ID

_MANIFEST = "sfx.json"
_rr_idx: Dict[str, int] = {}                    # per-kind round-robin (process-local)


def _bank(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    lib = Path(root) if root else library_dir()
    p = lib / _MANIFEST
    if not p.exists():
        return []
    try:
        return [e for e in json.loads(p.read_text(encoding="utf-8")) if e.get("curated")]
    except Exception:
        return []


def candidates(kind: str, *, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Curated files for a kind, best-first (rating desc, then downloads)."""
    items = [e for e in _bank(root) if e.get("kind") == kind]
    items.sort(key=lambda e: (e.get("rating", 0), e.get("num_downloads", 0)), reverse=True)
    return items


def resolve_cue(kind: str, *, root: Optional[Path] = None,
                exclude: tuple = (), vary: bool = True) -> Optional[Dict[str, Any]]:
    """Pick a curated sound for `kind`. Returns a dict with an ABSOLUTE ``file``
    path + placement metadata (gain from the registry default, lead_silence,
    attribution), or None if the bank has none for this kind.

    ``vary`` round-robins among the top-rated tier (variety within a render);
    ``exclude`` skips specific ids or filenames.
    """
    if kind not in BY_ID:
        return None
    lib = Path(root) if root else library_dir()
    items = [e for e in candidates(kind, root=root)
             if e.get("file") not in exclude and str(e.get("id")) not in exclude]
    if not items:
        return None
    best = items[0].get("rating", 0)
    top = [e for e in items if e.get("rating", 0) == best]
    if vary and len(top) > 1:
        key = f"{lib}:{kind}"
        i = _rr_idx.get(key, 0) % len(top)
        _rr_idx[key] = i + 1
        chosen = top[i]
    else:
        chosen = items[0]
    cue = BY_ID[kind]
    return {
        "kind": kind,
        "file": str((lib / chosen["file"]).resolve()),
        "id": chosen.get("id"),
        "title": chosen.get("title"),
        "duration": chosen.get("duration"),
        "gain": cue.gain,                       # registry default for the kind
        "lead_silence_s": chosen.get("lead_silence_s", 0.0),
        "license": chosen.get("license"),
        "attribution": chosen.get("attribution"),
        "family": cue.family,
    }


# HyperFrames renders SFX as separate <audio> tracks with NO VO-ducking (unlike
# the Director's sidechain mix), so a cue that lands over narration needs a hotter
# level than the ducked registry `gain`. Boost by family: content one-shots cut
# through; transitions ride a gap so stay subtle; beds stay low (they're beds).
_HF_GAIN_FACTOR = {"transition": 1.3, "one-shot": 2.5, "loop": 1.8, "bed": 1.4}


def hf_gain(kind: str) -> float:
    """The gain for the un-ducked HyperFrames render (louder than the ducked `gain`)."""
    c = BY_ID.get(kind)
    return round(min(0.9, c.gain * _HF_GAIN_FACTOR.get(c.family, 2.0)), 3) if c else 0.3


def sfx_event_for_cue(kind: str, *, frame: Any, offset_s: float,
                      root: Optional[Path] = None, exclude: tuple = (),
                      gain: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Build a HyperFrames ``audio_meta.sfx[]`` entry for a cue-kind.

    Shape matches what ``assemble-index.mjs`` mounts on track 20+i:
    ``{frame, file, offset_s, duration_s, volume}`` (+ kind/cue_id for trace).
    ``offset_s`` is frame-local seconds (compute it from the ALIGNED scene
    start). Returns None if the bank can't resolve the kind — so the HF merge
    step logs a capability gap instead of placing silence.
    """
    r = resolve_cue(kind, root=root, exclude=exclude)
    if not r:
        return None
    return {
        "frame": frame,
        "file": r["file"],
        "offset_s": round(float(offset_s), 3),
        "duration_s": r.get("duration"),
        "volume": float(gain if gain is not None else hf_gain(kind)),
        "kind": kind,
        "cue_id": r.get("id"),
    }
