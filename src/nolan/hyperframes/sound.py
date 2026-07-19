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

from typing import Any, Dict, Iterable, List, Sequence, Tuple

from nolan.sound.resolve import sfx_event_for_cue

# a cue tuple: (frame, offset_s, kind[, gain])
Cue = Tuple[Any, float, str]


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
