"""The camera umbrella — Ken Burns for the compose-first HyperFrames path.

  registry  what moves exist, what each needs, how each degrades
  solve     the amplitude law + a transform pair that can never expose an edge
  emit      the ONE executor: a plan -> GSAP on the composer's paused timeline
  select    which move, when the author didn't say
  target    where to aim: rembg saliency, then a VLM box when relevance matters

`plan()` is the front door both composers use.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from . import emit as _emit
from . import registry, select, solve

MOVES = registry.MOVES


def plan(move: str, *, dur: float, target=None, box=None, img: Optional[Tuple[int, int]] = None,
         amount: Optional[float] = None, canvas=(solve.CANVAS_W, solve.CANVAS_H)) -> Dict:
    """Resolve a move id + inputs into a geometry plan for `emit`.

    Always returns a dict carrying `move` and `notes` — a caller can render it blind, and anything the
    geometry had to limit is named rather than silently applied.
    """
    m = registry.get(move) or registry.get("push-in")
    mid = m.id
    notes = []
    out: Dict

    if mid == "hold":
        out = {"mode": "cover", "from": None, "to": None, "clamped": []}
    elif mid in ("pan-right", "pan-left", "pan-down", "pan-up", "parallax-pan"):
        direction = {"pan-right": "right", "pan-left": "left", "pan-down": "down",
                     "pan-up": "up"}.get(mid, "right")
        out = solve.solve_pan(dur=dur, direction=direction, amount=amount, img=img, canvas=canvas)
    elif mid in ("push-to-detail", "read-along", "scan-column") and box:
        out = solve.solve_box(dur=dur, box=box, canvas=canvas)
    elif mid == "pull-out":
        out = solve.solve_push(dur=dur, target=target, amount=amount, reverse=True, canvas=canvas)
    elif mid == "drift":
        out = solve.solve_push(dur=dur, target=target, amount=(amount if amount is not None else 0.02),
                               canvas=canvas)
    elif mid in ("blur-in", "blur-out", "rack-focus"):
        out = {"mode": "filter", "from": None, "to": None, "clamped": []}
    else:                                              # push-in / punch-in / settle / parallax / …
        out = solve.solve_push(dur=dur, target=target, amount=amount, canvas=canvas)

    if out.get("to") and img:
        if out.get("mode") == "long-axis":
            # width-fit, not cover: the requirement is that the source is at least canvas-WIDE. The
            # cover formula would read a 1000x3000 poster as a 1.9x upscale and hold on a move that is
            # actually the honest one for it.
            why = (f"source {img[0]}x{img[1]} is narrower than the {canvas[0]}px canvas"
                   if img[0] < canvas[0] * 0.98 else None)
        else:
            why = solve.resolution_floor(img, float(out["to"].get("scale", 1.0)), canvas)
        if why:
            notes.append(why + " — held instead")
            out = {"mode": "cover", "from": None, "to": None, "clamped": out.get("clamped", [])}
            mid = "hold"
    out["move"] = mid
    out["notes"] = notes + [f"clamped: {c}" for c in out.get("clamped", [])]
    return out


def emit_for(plan: Dict, selector: str, start: float, dur: float, *, cue: Optional[float] = None):
    """The ONE dispatch from a plan to GSAP — punch, filter or tween.

    This lived in the composer seam for one commit, which is one commit too long: choosing the emitter
    from the move is registry knowledge, and a second consumer (the legacy path, `detail_zoom`) would
    have had to reimplement it. That is the two-dialect pitfall inside the module built to prevent it.
    """
    move = (plan or {}).get("move")
    if move == "punch-in":
        return _emit.emit_punch(selector, plan, cue if cue is not None else start + 0.4)
    if move in ("blur-in", "blur-out", "rack-focus"):
        kw = {"from_px": 0.0, "to_px": 18.0} if move == "blur-out" else {}
        return _emit.emit_blur(selector, start, dur, cue=cue, **kw)
    return _emit.emit(selector, plan, start, dur, cue=cue)


emit = _emit.emit
emit_punch = _emit.emit_punch
emit_blur = _emit.emit_blur
emit_style = _emit.emit_style

__all__ = ["MOVES", "plan", "emit", "emit_for", "emit_punch", "emit_blur", "emit_style",
           "registry", "select", "solve"]
