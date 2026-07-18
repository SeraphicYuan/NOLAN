"""Render-time executor for the effects umbrella (backend-agnostic emit helpers).

Turns a scene's authored `treatments: [...]` (validated by nolan.effects.registry) into the two
things a browser-rendered frame needs:
  - filter_chain(): ONE composed CSS `filter:` string for all css_filter (colour) treatments — stacks
    like a real adjustment-layer stack (sepia + contrast compose in order). "" when none.
  - overlay_layers(): a list of full-inset `class="clip"` HTML layers for the blend_overlay treatments
    (grain/stylize/damage/element), each a procedural CSS background or a resolved library PLATE clip,
    carrying its own mix-blend-mode + opacity, on tracks ABOVE the content.

The HF compose bridge calls these from media_ground (image ground) and the video-ground assemble path;
a future Remotion executor calls filter_chain() and builds equivalent AbsoluteFill overlays. `ffmpeg_bake`
treatments are handled by the bake path (Phase 4), not here — this executor skips them.

Non-destructive + duration_preserving: an overlay rides the SAME start/dur window as the media it sits
over, so it never extends timing; a colour filter is a pure per-pixel transform.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .registry import normalize_treatments

# overlays sit above content (ground=0, scrim=1, content=2, props=4+); start here and climb so
# multiple stacked overlays keep a deterministic z-order.
OVERLAY_TRACK_BASE = 8


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def filter_chain(treatments: Any) -> str:
    """The composed CSS filter string for the css_filter (colour) treatments, in author order. "" if none.
    Stackable: `["sepia","contrast"]` -> "sepia(...) contrast(...)". Superset of the old single grade."""
    parts = [n["effect"].css for n in normalize_treatments(treatments)
             if n["effect"].method == "css_filter" and n["effect"].css]
    return " ".join(parts)


def overlay_layers(treatments: Any, sid: str, start: float, dur: float, *,
                   track_base: int = OVERLAY_TRACK_BASE,
                   resolve_plate: Optional[Callable[[str], Optional[str]]] = None) -> List[str]:
    """HTML `class="clip"` overlay fragments for the blend_overlay treatments, over media `sid`.

    - procedural (css_bg): a <div> with the CSS background + mix-blend-mode (grain/scanlines — no asset).
    - plate (element/damage): resolve_plate(tag) -> a clip src; a looping muted <video> overlay. If the
      resolver is absent or returns None (plate library not populated yet — Phase 3), the layer is
      SKIPPED (a render never depends on an asset that isn't there). NB: a <video> overlay is illegal
      inside a frame sub-comp, so the HF assemble step root-mounts plate overlays like video grounds;
      this helper emits the tag and the caller routes it.
    """
    frags: List[str] = []
    track = track_base
    for n in normalize_treatments(treatments):
        eff, op = n["effect"], n["opacity"]
        if eff.method != "blend_overlay":
            continue
        blend = eff.blend or "normal"
        common = (f'data-start="{start}" data-duration="{dur}" data-track-index="{track}" '
                  f'style="position:absolute;inset:0;pointer-events:none;'
                  f'mix-blend-mode:{blend};opacity:{op:.3f};')
        if eff.css_bg:                                   # procedural overlay (no download)
            frags.append(f'<div id="{_esc(sid)}-fx-{eff.id}" class="clip" {common}'
                         f'background:{eff.css_bg};background-size:cover;"></div>')
            track += 1
        elif eff.plate:                                  # library plate clip
            src = resolve_plate(eff.plate) if resolve_plate else None
            if not src:
                continue                                 # plate pending — skip, don't crash
            frags.append(f'<video id="{_esc(sid)}-fx-{eff.id}" class="clip" src="{_esc(src)}" '
                         f'muted playsinline loop {common}object-fit:cover;width:100%;height:100%;"></video>')
            track += 1
    return frags


def has_overlays(treatments: Any, *, resolve_plate: Optional[Callable[[str], Optional[str]]] = None) -> bool:
    """True if any treatment will emit an overlay layer (procedural always counts; a plate counts only
    if it resolves). Lets the caller decide whether to route to the root-mount path."""
    for n in normalize_treatments(treatments):
        eff = n["effect"]
        if eff.method != "blend_overlay":
            continue
        if eff.css_bg:
            return True
        if eff.plate and resolve_plate and resolve_plate(eff.plate):
            return True
    return False
