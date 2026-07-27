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
         amount: Optional[float] = None, canvas=(solve.CANVAS_W, solve.CANVAS_H), content=None) -> Dict:
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
        out = solve.solve_pan(dur=dur, direction=direction, amount=amount, img=img, canvas=canvas,
                              content=content)
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
            # Width-fit, so the factor is canvas_w/img_w — measured on the CONTENT, since a source whose
            # picture is 80% of the file is upscaled by the surround it is about to crop away. Judged
            # against the SAME mush floor as cover, for the same reason: a 600x800 portrait pays 3.2x
            # standing still under cover-fit, so "narrower than the canvas" was never the camera's fault.
            cw = (content[2] - content[0]) if content else 1.0
            fit = canvas[0] / max(1, img[0] * max(0.05, cw))
            why = (f"source {img[0]}x{img[1]} is {fit:.2f}x width-fit (mush floor {solve.MUSH_FACTOR:.2f}x)"
                   if fit > solve.MUSH_FACTOR else None)
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
