"""TimeRef — symbolic time that resolves against scene context.

A TimeRef is how the broll-design stage expresses *when* something happens without
knowing seconds. It is deliberately small and reusable: any timed effect (a photo
focusing, an annotation drawing on, a counter starting) can anchor to it.

Accepted forms (all resolve to seconds on the scene-local timeline, clamped to
[0, duration]):
  3.2                      absolute seconds
  "start" | "end" | "mid"  scene anchors
  "keyword"                a bare string is treated as a spoken cue (its start)
  {"cue": "keyword"}       when the VO says it (default = the cue's start)
  {"cue": "keyword", "at": "end"}   when the VO finishes saying it
  {"frac": 0.5}            a fraction of the scene duration
  {"after": <TimeRef>, "delay": 0.5}   relative to another anchor
"""
from __future__ import annotations

from typing import Any


def resolve_time(ref: Any, ctx, default: float | None = None) -> float:
    dur = ctx.duration

    def clamp(t: float) -> float:
        return max(0.0, min(dur, float(t)))

    if ref is None:
        return clamp(default if default is not None else dur / 2)

    if isinstance(ref, bool):  # guard: bool is an int subclass
        ctx.warn(f"time ref was a bool ({ref!r}); using midpoint")
        return clamp(dur / 2)

    if isinstance(ref, (int, float)):
        return clamp(ref)

    if isinstance(ref, str):
        key = ref.strip().lower()
        if key in ("start", "begin", "in", "0"):
            return 0.0
        if key in ("end", "out", "finish"):
            return dur
        if key in ("mid", "middle", "center", "centre"):
            return clamp(dur / 2)
        return _cue(ref, "start", ctx, default)  # bare string == cue phrase

    if isinstance(ref, dict):
        if "cue" in ref:
            return _cue(ref["cue"], ref.get("at", "start"), ctx, default)
        if "frac" in ref or "fraction" in ref:
            return clamp(float(ref.get("frac", ref.get("fraction"))) * dur)
        if "after" in ref:
            base = resolve_time(ref["after"], ctx, default)
            return clamp(base + float(ref.get("delay", 0.0)))
        if "at" in ref:
            return resolve_time(ref["at"], ctx, default)
        if "seconds" in ref or "sec" in ref:
            return clamp(ref.get("seconds", ref.get("sec")))

    ctx.warn(f"unrecognized time ref {ref!r}; using midpoint")
    return clamp(dur / 2)


def _cue(phrase: str, side: Any, ctx, default: float | None) -> float:
    span = ctx.find_cue(phrase)
    if span is None:
        fallback = 0.0 if default is None else float(default)
        ctx.warn(f"cue {phrase!r} not found in narration; using {fallback:.2f}s")
        return max(0.0, min(ctx.duration, fallback))
    start, end = span
    return start if str(side).lower() in ("start", "begin", "in") else end
