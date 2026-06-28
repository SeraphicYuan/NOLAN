"""Resolve a `photo-story` brief into a validated motion spec.

A photo-story is the agent-facing surface for the photo-montage family. It dispatches:
  layout "grid"  -> the `photo-grid` composition (procedural fly-in + focus choreography)
  layout "free"  -> the `photo-montage-pro` composition (per-card placement + motion verbs)

Motion verbs (free layout) compile to keyframe tracks so the agent never writes `keys`:
  {"enter": "left|right|top|bottom", "at": <TimeRef>, "dur": 0.7}
  {"fade": "in|out", "at": <TimeRef>, "dur": 0.5}
  {"tilt": <deg>, "at": <TimeRef>}          in-plane rotateZ
  {"pan":  <deg>, "at": <TimeRef>}          3D rotateY swing
  {"tilt3d": <deg>, "at": <TimeRef>}        3D rotateX
  {"move": [x, y], "at": <TimeRef>}         single move to a point
  {"path": [{"to": [x, y], "at": <TimeRef>}, ...]}   multi-step path
  {"zoom": <scale>, "at": <TimeRef>}        scale to a height-fraction

Wired into the scene-edit router: a `/scenes` comment → `revise_scene` LLM returns a
`photo_brief` → resolved here against the scene's narration (see `iterate/revise.py`).
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Tuple

from .timeref import resolve_time

_ENTER_DIST = 0.42  # how far off-place a card starts, in 0..1 of the frame


def _deref(it: Any, ctx) -> Dict[str, Any]:
    """An image entry may be a path, an asset id, or {ref:<id>, ...} bound to the scene's
    asset tray. Dereference against ctx.assets; an asset's label seeds the caption."""
    def _from_asset(a: Dict[str, Any], d: Dict[str, Any]) -> Dict[str, Any]:
        d.setdefault("src", a["src"])
        if a.get("label"):
            d.setdefault("caption", a["label"])
        for k in ("place", "scale"):   # spatial control set on the asset flows through
            if a.get(k) is not None:
                d.setdefault(k, a[k])
        # photo-story renders stills; a clip/video card isn't supported yet (see TODO C)
        if a.get("kind") and a["kind"] != "image":
            ctx.warn(f"asset {a.get('id')} is a {a['kind']} — photo montage shows it as a "
                     f"static frame (video cards not yet supported)")
        return d

    if isinstance(it, str):
        if it in ctx.assets:
            return _from_asset(ctx.assets[it], {})
        return {"src": it}
    d = dict(it)
    ref = d.pop("ref", None)
    if ref is not None and str(ref) in ctx.assets:
        return _from_asset(ctx.assets[str(ref)], d)
    if ref is not None:
        ctx.warn(f"asset ref {ref!r} not bound to this scene")
    return d


def _images(brief: Dict[str, Any], ctx) -> List[Dict[str, Any]]:
    """Normalize `images` to [{src, ...}] with absolute paths; warn on missing files."""
    out: List[Dict[str, Any]] = []
    for it in brief.get("images", []) or []:
        d = _deref(it, ctx)
        if d.get("caption") is None:
            d.pop("caption", None)
        src = d.get("src")
        if not src:
            ctx.warn("image entry without 'src' skipped")
            continue
        ap = os.path.abspath(os.path.join(ctx.assets_root, src)) if not os.path.isabs(src) else src
        if not os.path.exists(ap):
            ctx.warn(f"image not found: {src}")
        d["src"] = ap
        out.append(d)
    if not out:
        ctx.warn("photo-story has no usable images")
    return out


def _parse_grid(g: Any, n: int) -> Tuple[int, int]:
    """'2x3' / [2,3] / {rows,cols} -> (rows, cols). Falls back to a near-square shape."""
    if isinstance(g, str) and "x" in g.lower():
        a, b = g.lower().split("x", 1)
        return max(1, int(a)), max(1, int(b))
    if isinstance(g, (list, tuple)) and len(g) == 2:
        return max(1, int(g[0])), max(1, int(g[1]))
    if isinstance(g, dict) and "rows" in g and "cols" in g:
        return max(1, int(g["rows"])), max(1, int(g["cols"]))
    cols = max(1, math.ceil(math.sqrt(n)))
    return max(1, math.ceil(n / cols)), cols


def _grid_spec(brief: Dict[str, Any], imgs: List[Dict[str, Any]], ctx) -> Dict[str, Any]:
    rows, cols = _parse_grid(brief.get("grid"), len(imgs))
    if rows * cols < len(imgs):
        ctx.warn(f"grid {rows}x{cols} holds {rows*cols} but {len(imgs)} images given; extra ignored")
    def _card(i: Dict[str, Any]) -> Dict[str, Any]:
        c = {"src": i["src"]}
        if i.get("caption"):
            c["caption"] = i["caption"]
        return c

    content: Dict[str, Any] = {
        "cards": [_card(i) for i in imgs],
        "cols": cols, "rows": rows,
        "background": brief.get("background", "#241016"),
    }
    style: Dict[str, Any] = {
        "order": brief.get("fly_in", brief.get("order", "one-by-one")),
        "flyFrom": brief.get("fly_from", "edges"),
        "frame": brief.get("frame", "polaroid"),
    }
    focus = brief.get("focus") or {}
    if focus:
        idx = focus.get("image", focus.get("index"))
        if idx is not None:
            content["focusIndex"] = int(idx)
        if "at" in focus:
            style["focusAt"] = round(resolve_time(focus["at"], ctx, default=ctx.duration * 0.6), 3)
        if "hold" in focus:
            style["focusHold"] = float(focus["hold"])
        if "scale" in focus:
            style["focusScale"] = float(focus["scale"])
    return {"effect": "photo-grid", "content": content, "style": style,
            "theme": brief.get("theme", "dark-editorial"),
            "duration": float(brief.get("duration", ctx.duration))}


def _compile_verbs(motion: List[Dict[str, Any]], place: List[float], base_scale: float, ctx) -> List[Dict[str, Any]]:
    """Compile motion verbs into a sorted keyframe track (each property tweens independently)."""
    px, py = float(place[0]), float(place[1])
    keys: List[Dict[str, Any]] = []
    for v in motion or []:
        at = lambda d=0.0: resolve_time(v.get("at", "start"), ctx, default=d)  # noqa: E731
        dur = float(v.get("dur", 0.6))
        if "enter" in v:
            t, d, frm = resolve_time(v.get("at", "start"), ctx), float(v.get("dur", 0.7)), v["enter"]
            sx, sy = px, py
            if frm == "left": sx = px - _ENTER_DIST
            elif frm == "right": sx = px + _ENTER_DIST
            elif frm == "top": sy = py - _ENTER_DIST
            elif frm == "bottom": sy = py + _ENTER_DIST
            keys.append({"at": t, "x": sx, "y": sy, "opacity": 0.0})
            keys.append({"at": t + d, "x": px, "y": py, "opacity": 1.0, "ease": "out"})
        elif "fade" in v:
            t = at(); mode = str(v["fade"]).lower()
            if mode in ("in", "fadein"):
                keys += [{"at": t, "opacity": 0.0}, {"at": t + dur, "opacity": 1.0, "ease": "out"}]
            else:
                keys += [{"at": t, "opacity": 1.0}, {"at": t + dur, "opacity": 0.0, "ease": "inOut"}]
        elif "tilt" in v:
            t = at(); keys += [{"at": t, "rotation": float(v.get("from", 0))},
                               {"at": t + dur, "rotation": float(v["tilt"]), "ease": "inOut"}]
        elif "pan" in v:
            t = at(); keys += [{"at": t, "rotY": float(v.get("from", 0))},
                               {"at": t + dur, "rotY": float(v["pan"]), "ease": "inOut"}]
        elif "tilt3d" in v:
            t = at(); keys += [{"at": t, "rotX": float(v.get("from", 0))},
                               {"at": t + dur, "rotX": float(v["tilt3d"]), "ease": "inOut"}]
        elif "move" in v:
            t = at(); to = v["move"]
            keys += [{"at": t, "x": px, "y": py}, {"at": t + dur, "x": float(to[0]), "y": float(to[1]), "ease": "inOut"}]
            px, py = float(to[0]), float(to[1])
        elif "path" in v:
            for i, pt in enumerate(v["path"]):
                tt = resolve_time(pt.get("at", "start"), ctx)
                keys.append({"at": tt, "x": float(pt["to"][0]), "y": float(pt["to"][1]),
                             "ease": "out" if i == 0 else "inOut"})
            if v["path"]:
                px, py = float(v["path"][-1]["to"][0]), float(v["path"][-1]["to"][1])
        elif "zoom" in v:
            t = at(); keys += [{"at": t, "scale": float(v.get("from", base_scale))},
                               {"at": t + dur, "scale": float(v["zoom"]), "ease": "inOut"}]
        else:
            ctx.warn(f"unknown motion verb {list(v)!r}; skipped")
    keys.sort(key=lambda k: k["at"])
    return keys


def _free_spec(brief: Dict[str, Any], imgs: List[Dict[str, Any]], ctx) -> Dict[str, Any]:
    cards: List[Dict[str, Any]] = []
    for im in imgs:
        place = im.get("place", [0.5, 0.5])
        base_scale = float(im.get("scale", 0.46))
        card: Dict[str, Any] = {"src": im["src"], "x": float(place[0]), "y": float(place[1]),
                                "scale": base_scale}
        for k in ("rotation", "caption", "frame", "shadow"):
            if im.get(k) is not None:
                card[k] = im[k]
        keys = _compile_verbs(im.get("motion", []), place, base_scale, ctx)
        if keys:
            card["keys"] = keys
        cards.append(card)
    return {"effect": "photo-montage-pro",
            "content": {"cards": cards, "background": brief.get("background", "#241016")},
            "style": {"vignette": float(brief.get("vignette", 0.5))},
            "theme": brief.get("theme", "dark-editorial"),
            "duration": float(brief.get("duration", ctx.duration))}


def resolve(brief: Dict[str, Any], ctx) -> Dict[str, Any]:
    """photo-story -> motion spec (pre-validation)."""
    imgs = _images(brief, ctx)
    layout = brief.get("layout")
    if not layout:
        layout = "free" if any(isinstance(i, dict) and ("place" in i or "motion" in i)
                               for i in (brief.get("images") or [])) else "grid"
    if layout == "free":
        return _free_spec(brief, imgs, ctx)
    return _grid_spec(brief, imgs, ctx)


# kinds this module handles
RESOLVERS = {"photo-story": resolve, "photo-grid": resolve, "photo-montage": resolve}
