"""The ONE executor: a resolved camera plan -> GSAP lines for the composer's paused timeline.

Every camera tween in the compose-first path comes from here. `media_ground`, `_data_ground`,
`_layout_cell` and `carousel` used to hand-write their own — which is how `_layout_cell` ended up with
`duration:6`, a literal that freezes on a long beat and is cut mid-stride on a short one.

TIMING CONTRACT (the composer's, not ours):
  * narration owns duration — a move is a fraction of `dur`, never a literal number of seconds;
  * a cue beats a spread — with an arrival cue the move DECELERATES INTO the spoken word and holds
    after it, which is what makes a camera feel edited rather than animated;
  * seek-safe — absolute times, explicit durations, no repeat/yoyo/random. The renderer seeks; it
    never plays.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# Ease by intent. Linear ("none") is the PowerPoint tell — a real camera accelerates and settles.
EASE_FREE = "power1.inOut"      # no cue: breathe across the whole beat
EASE_ARRIVE = "power2.out"      # a cue: decelerate into the word
EASE_PUNCH = "power3.out"       # a step accent
MIN_MOVE = 0.8                  # a move shorter than this reads as a glitch, not a camera


def _fmt(v) -> str:
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def _props(kf: Dict, extra: str = "") -> str:
    body = ",".join(f"{k}:{_fmt(v)}" for k, v in kf.items() if v is not None)
    return "{" + body + (("," + extra) if extra else "") + "}"


def emit(selector: str, plan: Dict, start: float, dur: float, *, cue: Optional[float] = None,
         ease: Optional[str] = None) -> List[str]:
    """GSAP lines for `plan` (from `camera.solve`) on `selector`, inside [start, start+dur].

    With `cue`, the move ARRIVES there: it runs from the scene's start and eases to a stop on the word,
    then holds. Without one, it spans the beat. Either way it is one `fromTo` — a single tween is
    seek-exact at any frame the renderer asks for.
    """
    if not plan or plan.get("move") == "hold":
        return []
    frm, to = plan.get("from"), plan.get("to")
    if not frm or not to:
        return []
    end = start + max(0.0, float(dur))
    if cue is not None and start < float(cue) <= end:
        move_dur = max(MIN_MOVE, float(cue) - start)
        move_dur = min(move_dur, end - start)
        e = ease or EASE_ARRIVE
    else:
        move_dur = max(MIN_MOVE, end - start)
        e = ease or EASE_FREE
    line = (f'tl.fromTo("{selector}",{_props(frm)},'
            f'{_props(to, f"duration:{move_dur:.2f},ease:\"{e}\"")},{start:.2f});')
    return [line]


def emit_punch(selector: str, plan: Dict, at: float, *, hit: float = 0.35) -> List[str]:
    """A step push at a single word — deliberately not the same shape as `emit`."""
    if not plan or not plan.get("from"):
        return []
    return [f'tl.fromTo("{selector}",{_props(plan["from"])},'
            f'{_props(plan["to"], f"duration:{hit:.2f},ease:\"{EASE_PUNCH}\"")},{at:.2f});']


def emit_blur(selector: str, start: float, dur: float, *, from_px: float = 16.0, to_px: float = 0.0,
              cue: Optional[float] = None) -> List[str]:
    """Focus moves are a FILTER, not a transform — the one family that breaks `transform_only`, which
    is why the registry declares it per-move instead of assuming it globally."""
    end = start + max(0.0, float(dur))
    d = max(MIN_MOVE, (float(cue) - start) if (cue is not None and start < float(cue) <= end)
            else min(2.2, end - start))
    return [f'tl.fromTo("{selector}",{{filter:"blur({from_px:g}px)"}},'
            f'{{filter:"blur({to_px:g}px)",duration:{d:.2f},ease:"{EASE_ARRIVE}"}},{start:.2f});']


def emit_style(plan: Dict) -> str:
    """Extra inline style the element needs for this plan (long-axis pans re-size the ground)."""
    if plan.get("mode") == "long-axis" and plan.get("element_height"):
        # The full image is present vertically (so the pan reveals real content, not a crop sliding
        # around), and the element is a touch WIDER than the canvas with a matching negative offset, so
        # the source's own border stays outside the frame.
        return (f"height:{plan['element_height']:.0f}px;"
                f"width:{plan.get('element_width', 1920):.0f}px;"
                f"left:{plan.get('element_left', 0):.0f}px;right:auto;"
                f"background-size:100% auto;")
    return ""
