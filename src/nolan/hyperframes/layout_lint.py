"""Deterministic layout linter — the composition gate v2 (the "measure like an editor" pass).

The archetype (composition module) gets a scene into the right *zone*; it can't guarantee the
elements don't OVERLAP, dip into the caption band, or fall off the canvas. This linter is that
enforcement: it reads a composed frame's (or a raw agent scene's) DECLARED geometry and checks it
against the archetype registry's machine-readable safe-areas + anchor zone — deterministically, with
no headless render. It is the cheap structural pass that runs BEFORE the VLM render-gate and the
human LOOK (which stay the perceptual/semantic passes).

Why static declared-geometry, not a seek render: HyperFrames reveals are transform/opacity that
resolve to the element's declared resting position (seek-safe), so the declared box IS the final
layout. `cqw`/`cqh` are always canvas-relative (container-type lives on #root = the 1920x1080 canvas),
so an element's offsets resolve to canvas fractions regardless of nesting depth; only the positioned
ANCESTOR's origin has to be accumulated. Content-sized text (a corner declared, extent left to the
font) can only be checked at its anchor — extent overflow is `hyperframes inspect`'s job, semantics
are the VLM's. This linter owns: caption-band collision, out-of-bounds, element OVERLAP, anchor drift.

Consumers (one tool, two gates — the consolidation of v2-gate-(a) and bespoke-P1):
  - compose-first / composed frames: lint_composition(comp_dir) / lint_frame_html(...)
  - bespoke + agent raw-scene edits: lint_raw_scene(html_list, archetype, ...)
CLI: python -m nolan.hyperframes.layout_lint <comp_dir | frame.html> [--no-captions] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from nolan import composition as _comp

# ── thresholds (tunable in one place) ───────────────────────────────────────
_EPS = 0.006                 # slack on every edge test (declared values are ~integer cqw/cqh)
_OVERLAP_MIN = 0.34          # intersection / min(area) above this = an OVERLAP error
_ANCHOR_COINCIDE = 0.045     # two anchors within this (both axes) = a possible-stack hint
_FULLSPAN = 0.90             # an element covering ≥ this fraction of an axis is a WRAPPER (skip bounds)
_FBG_AREA = 0.75             # a GROUND covering ≥ this fraction of the canvas = a full-bleed scene (drift-exempt)
_ANCHOR_DRIFT_FRAC = 0.60    # < this fraction of a scene's content mass inside the archetype zone = drift


# ── geometry ────────────────────────────────────────────────────────────────
@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    x_anchor: bool = False   # x-extent is content-sized (only a corner declared)
    y_anchor: bool = False

    @property
    def w(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def h(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def anchor_only(self) -> bool:
        return self.x_anchor and self.y_anchor

    def covers_axis(self, frac: float) -> bool:
        return self.w >= frac and self.h >= frac


_LEN_RE = re.compile(r"^(-?\d*\.?\d+)(cqw|cqh|cqmin|cqmax|vw|vh|vmin|vmax|%|px|rem|em)?$")


def _len_frac(val: str, axis: str) -> Optional[float]:
    """A CSS length → fraction of the canvas along `axis` ('x' or 'y'). None if unresolvable.

    cqw/vw/% are width-relative, cqh/vh height-relative; a bare `%` / `vmin` resolves by axis.
    px is /1920 (x) or /1080 (y). em/rem are content-scaled and unresolvable here → None.
    """
    val = (val or "").strip().lower()
    if val in ("0", "0px", "0%"):
        return 0.0
    m = _LEN_RE.match(val)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2) or "%"
    if unit in ("cqw", "vw"):
        return num / 100.0
    if unit in ("cqh", "vh"):
        return num / 100.0
    if unit in ("%", "vmin", "vmax", "cqmin", "cqmax"):
        return num / 100.0
    if unit == "px":
        return num / (1920.0 if axis == "x" else 1080.0)
    return None  # em/rem — extent is font-driven, not a static geometry fact


def _split_style(style: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for decl in (style or "").split(";"):
        if ":" not in decl:
            continue
        k, v = decl.split(":", 1)
        out[k.strip().lower()] = v.strip()
    return out


# The composer positions most content via CSS CLASSES in a <style> block (`.stmt{left:5.5cqw;bottom:16cqh}`),
# not inline styles — so the linter must resolve single-class positioning rules or it sees nothing on a
# composed frame. Only these props affect the box (max-/min-width don't give a definite extent → ignored).
_POS_PROPS = {"left", "right", "top", "bottom", "inset", "width", "height", "position"}


def _class_pos_rules(css: str) -> Dict[str, Dict[str, str]]:
    """{class -> position props} from BARE single-class rules (`.stmt{...}`) in the frame's <style>.
    Compound/descendant selectors (`.dg-dark .dgnode`) are skipped — they almost always restyle colour,
    not geometry, and matching them needs a full CSS engine. Later source rules win (cascade-ish)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules: Dict[str, Dict[str, str]] = {}
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel, body = m.group(1).strip(), m.group(2)
        props = {}
        for decl in body.split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                k = k.strip().lower()
                if k in _POS_PROPS:
                    props[k] = v.strip()
        if not props:
            continue
        for one in sel.split(","):
            mm = re.fullmatch(r"\.([\w-]+)", one.strip())
            if mm:
                rules.setdefault(mm.group(1), {}).update(props)
    return rules


def _extract_css(html: str) -> str:
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))


def _inset_parts(v: str) -> Dict[str, str]:
    """CSS `inset` shorthand → {top,right,bottom,left}."""
    toks = v.split()
    if len(toks) == 1:
        t = r = b = l = toks[0]
    elif len(toks) == 2:
        t = b = toks[0]; r = l = toks[1]
    elif len(toks) == 3:
        t, (r, l), b = toks[0], (toks[1], toks[1]), toks[2]
    elif len(toks) >= 4:
        t, r, b, l = toks[0], toks[1], toks[2], toks[3]
    else:
        return {}
    return {"top": t, "right": r, "bottom": b, "left": l}


def _resolve_box(style: Dict[str, str], parent: Box) -> Optional[Box]:
    """Resolve an element's box in canvas fractions from its declared offsets, positioned inside
    `parent` (its nearest positioned-ancestor box). Returns None when the element declares no
    absolute position at all (it is flow content — measured via its positioned ancestor instead)."""
    s = dict(style)
    if "inset" in s:
        for k, val in _inset_parts(s["inset"]).items():
            s.setdefault(k, val)

    left = _len_frac(s["left"], "x") if "left" in s else None
    right = _len_frac(s["right"], "x") if "right" in s else None
    top = _len_frac(s["top"], "y") if "top" in s else None
    bottom = _len_frac(s["bottom"], "y") if "bottom" in s else None
    width = _len_frac(s["width"], "x") if "width" in s else None
    height = _len_frac(s["height"], "y") if "height" in s else None

    positioned = any(k in s for k in ("left", "right", "top", "bottom", "inset"))
    if not positioned:
        return None

    px0, py0, pw, ph = parent.x0, parent.y0, parent.w, parent.h

    # X
    x_anchor = False
    if left is not None and right is not None:
        x0, x1 = px0 + left, (parent.x1) - right
    elif left is not None and width is not None:
        x0, x1 = px0 + left, px0 + left + width
    elif right is not None and width is not None:
        x1 = parent.x1 - right; x0 = x1 - width
    elif left is not None:
        x0 = x1 = px0 + left; x_anchor = True
    elif right is not None:
        x0 = x1 = parent.x1 - right; x_anchor = True
    else:
        x0, x1 = px0, parent.x1  # spans parent horizontally

    # Y  (bottom is measured up from the parent's bottom edge)
    y_anchor = False
    if top is not None and bottom is not None:
        y0, y1 = py0 + top, parent.y1 - bottom
    elif top is not None and height is not None:
        y0, y1 = py0 + top, py0 + top + height
    elif bottom is not None and height is not None:
        y1 = parent.y1 - bottom; y0 = y1 - height
    elif top is not None:
        y0 = y1 = py0 + top; y_anchor = True
    elif bottom is not None:
        y0 = y1 = parent.y1 - bottom; y_anchor = True
    else:
        y0, y1 = py0, parent.y1

    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return Box(x0, y0, x1, y1, x_anchor=x_anchor, y_anchor=y_anchor)


# ── HTML tree ───────────────────────────────────────────────────────────────
_VOID = {"br", "img", "hr", "input", "meta", "link", "source", "use", "path", "circle",
         "rect", "line", "ellipse", "polygon", "stop", "col"}


@dataclass
class El:
    tag: str
    attrs: Dict[str, str]
    children: List["El"] = field(default_factory=list)
    parent: Optional["El"] = None
    text: str = ""

    @property
    def style(self) -> Dict[str, str]:
        return _split_style(self.attrs.get("style", ""))

    @property
    def classes(self) -> List[str]:
        return (self.attrs.get("class", "") or "").split()


class _DOM(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = El("#doc", {})
        self._stack = [self.root]

    def handle_starttag(self, tag, attrs):
        el = El(tag.lower(), {k.lower(): (v or "") for k, v in attrs}, parent=self._stack[-1])
        self._stack[-1].children.append(el)
        if tag.lower() not in _VOID:
            self._stack.append(el)

    def handle_startendtag(self, tag, attrs):
        el = El(tag.lower(), {k.lower(): (v or "") for k, v in attrs}, parent=self._stack[-1])
        self._stack[-1].children.append(el)

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag.lower():
                del self._stack[i:]
                break

    def handle_data(self, data):
        if data.strip():
            self._stack[-1].text += data


def _parse(html: str) -> El:
    p = _DOM()
    p.feed(html)
    return p.root


def _walk(el: El):
    yield el
    for c in el.children:
        yield from _walk(c)


def _own_text(el: El) -> str:
    return " ".join((el.text + " " + " ".join(c.text for c in el.children)).split())[:80]


# ── classification ──────────────────────────────────────────────────────────
def _track(el: El) -> Optional[int]:
    v = el.attrs.get("data-track-index")
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _is_ground(el: El) -> bool:
    cls = el.classes
    return (_track(el) in (0, 1)) or any(c in cls for c in ("scrim", "gnd", "nhbg"))


def _clip_window(el: El) -> Optional[Tuple[float, float]]:
    """The [start, start+dur) frame-absolute window of the nearest ancestor .clip (incl. self)."""
    node: Optional[El] = el
    while node is not None:
        if "data-start" in node.attrs:
            try:
                s = float(node.attrs.get("data-start", "0"))
                d = float(node.attrs.get("data-duration", "1e9"))
                return (s, s + d)
            except ValueError:
                return None
        node = node.parent
    return None


def _dom_archetype(el: El) -> Optional[str]:
    """The scene archetype stamped on the composed frame (compose.py stamps data-archetype on the
    track-2 content root) — so the linter reads the archetype straight from the artifact, no sidecar."""
    node: Optional[El] = el
    while node is not None:
        a = node.attrs.get("data-archetype")
        if a:
            return a
        node = node.parent
    return None


# ── measured content element ──────────────────────────────────────────────────
@dataclass
class Item:
    box: Box
    text: str
    window: Tuple[float, float]
    sel: str
    allow_overflow: bool = False   # element (or an ancestor) opted out via data-layout-allow-overflow
    furniture: bool = False        # broadcast furniture (lower-third) — exempt from the caption check
    archetype: Optional[str] = None  # data-archetype stamped by compose.py on the scene's content root


def _allow_overflow(el: El) -> bool:
    node: Optional[El] = el
    while node is not None:
        if "data-layout-allow-overflow" in node.attrs:
            return True
        node = node.parent
    return False


# self-contained artifact blocks own their INTERNAL layout (a chart's axis labels, an svg diagram's
# nodes) — the linter checks the block's placement, not its innards.
_ARTIFACT_CLS = ("chart", "ch-", "diagram", "dg-", "code", "hljs", "table", "geo", "us-", "world",
                 "spark", "flow-", "node", "d3-", "axis")
# broadcast furniture is deliberately at the lower edge (its own scrim); captions are stacked/placed
# by the assembler, so exempt it from the caption-band check (still checked for bounds + overlap). This
# includes a block's OWN caption/source line (doc-caption, prop-cap) — a designed low element with its
# own scrim, not free content that VO captions would occlude.
_FURNITURE_CLS = ("lt-bar", "ltwrap", "lower_third", "lower-third", "lt-", "chyron", "namestrip",
                  "doc-caption", "prop-cap", "capbar")


def _inside_artifact(el: El) -> bool:
    node: Optional[El] = el
    while node is not None:
        if node.tag == "svg":
            return True
        cls = node.classes
        if any(any(c.startswith(a) or a in c for a in _ARTIFACT_CLS) for c in cls):
            return True
        node = node.parent
    return False


def _is_furniture(el: El) -> bool:
    node: Optional[El] = el
    while node is not None:
        if any(any(f in c for f in _FURNITURE_CLS) for c in node.classes):
            return True
        node = node.parent
    return False


def _eff_style(el: El, class_rules: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    """The element's effective position style: its matched single-class rules merged (source order),
    with the inline style overlaid (inline wins) — the composer's class-based positioning made visible."""
    st: Dict[str, str] = {}
    for c in el.classes:
        r = class_rules.get(c)
        if r:
            st.update(r)
    st.update(el.style)
    return st


def _measure(root: El, class_rules: Optional[Dict[str, Dict[str, str]]] = None) -> "Tuple[List[Item], set]":
    """Every positioned, non-ground CONTENT element with a resolvable box, in canvas fractions.
    `class_rules` ({class -> position props}) lets the composer's CSS-class positioning resolve, not
    just inline styles."""
    class_rules = class_rules or {}
    # resolve each element's positioned-ancestor box top-down
    canvas = Box(0.0, 0.0, 1.0, 1.0)
    boxes: Dict[int, Box] = {id(root): canvas}
    items: List[Item] = []
    fbg_windows: set = set()                   # clip-windows that carry a full-bleed ground (drift-exempt)
    for el in _walk(root):
        if el is root:
            continue
        # nearest positioned ancestor box already computed (walk is pre-order → parents first)
        panc = el.parent
        pbox = canvas
        while panc is not None:
            if id(panc) in boxes:
                pbox = boxes[id(panc)]
                break
            panc = panc.parent
        b = _resolve_box(_eff_style(el, class_rules), pbox)
        if b is not None:
            boxes[id(el)] = b
        if b is None or _is_ground(el):
            if b is not None and _is_ground(el) and b.area >= _FBG_AREA:   # a canvas-filling ground → full-bleed scene
                fbg_windows.add(_clip_window(el) or (0.0, 1e9))
            continue
        if b.covers_axis(_FULLSPAN):          # a full-span wrapper — its children carry the content
            continue
        # a full-HEIGHT column that WRAPS text-bearing children is a flex/flow WRAPPER too — its box
        # edges are the CONTAINER's, not where the text sits (a `left:x;top:0;bottom:0` column reports
        # bottom y=1.0 while its text is vertically centered), so measuring it yields PHANTOM caption
        # hits. Skip it — its children are measured on their own. Gated on child-text so a genuine
        # placed label is never skipped (a real bottom label is SHORT, not full-height — e.g. `.cmp-txt`).
        if b.h >= _FULLSPAN and any(_own_text(c) for c in el.children):
            continue
        if _inside_artifact(el):              # chart/diagram/svg internals own their own layout
            continue
        # a large positioned ZONE that wraps text-bearing children (a split-screen half, a full
        # column) lays its content out by flex/flow — NOT statically locatable, so the render/VLM
        # pass owns it. Skip the zone rather than flag its edges. Discrete positioned labels (small
        # boxes / corner anchors) are what this linter reliably checks.
        if b.area > 0.20 and any(_own_text(c) for c in el.children):
            continue
        txt = _own_text(el)
        if not txt:                           # TEXT is the failure surface (stacks / caption dips /
            continue                          # off-canvas). Media/panels bleed by design → skip.
        win = _clip_window(el) or (0.0, 1e9)
        items.append(Item(box=b, text=txt, window=win,
                          sel=el.attrs.get("id") or (el.tag + "." + ".".join(el.classes[:2])),
                          allow_overflow=_allow_overflow(el), furniture=_is_furniture(el),
                          archetype=_dom_archetype(el)))
    return items, fbg_windows


# ── violations ────────────────────────────────────────────────────────────────
@dataclass
class Violation:
    kind: str            # caption_collision | out_of_bounds | overlap | anchor_drift
    severity: str        # error | advisory
    scene: str
    detail: str
    where: Optional[List[float]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "severity": self.severity, "scene": self.scene,
                "detail": self.detail, "where": self.where}


def _windows_overlap(a: Tuple[float, float], b: Tuple[float, float]) -> bool:
    return a[0] < b[1] - 1e-6 and b[0] < a[1] - 1e-6


def _iou_min(a: Box, b: Box) -> float:
    ix = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    iy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    inter = ix * iy
    denom = min(a.area, b.area)
    return inter / denom if denom > 1e-9 else 0.0


def _check_items(items: List[Item], scene: str, archetype: Optional[str],
                 captions_on: bool, overlap_hard: bool, has_full_bleed_ground: bool = False) -> List[Violation]:
    grid = _comp.grid()
    sa = grid.get("safe_areas", {})
    cap_y = float(sa.get("caption_keep_out_y", 0.85))
    out: List[Violation] = []

    for it in items:
        b = it.box
        if it.allow_overflow:            # designer opted this element out of edge/caption checks
            continue
        # caption-band collision — a content box whose bottom dips below the keep-out line
        # (broadcast furniture is exempt: it owns the lower edge, captions are placed around it)
        if captions_on and not it.furniture and b.y1 > cap_y + _EPS:
            out.append(Violation("caption_collision", "error", scene,
                                 f"{it.sel!r} bottom at y={b.y1:.2f} dips into the caption keep-out "
                                 f"(content must stay above y={cap_y})", [b.x0, b.y0, b.x1, b.y1]))
        # off-canvas — a content box that extends beyond the frame edges (clipped). Only genuine bleed
        # (coords <0 or >1); the title-safe inset is a nicety the composer respects, not a gate. The axis
        # an element intentionally spans (anchor / full-bleed) isn't a false "off the right/bottom".
        edges = []
        if b.x0 < -_EPS:
            edges.append(f"left={b.x0:.2f}")
        if b.x1 > 1 + _EPS and not b.x_anchor:
            edges.append(f"right={b.x1:.2f}")
        if b.y0 < -_EPS:
            edges.append(f"top={b.y0:.2f}")
        if b.y1 > 1 + _EPS and not b.y_anchor:
            edges.append(f"bottom={b.y1:.2f}")
        if edges:
            out.append(Violation("out_of_bounds", "error", scene,
                                 f"{it.sel!r} extends off-canvas ({', '.join(edges)})",
                                 [b.x0, b.y0, b.x1, b.y1]))

    # overlap — pairwise, only for elements visible at overlapping times
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, c = items[i], items[j]
            if not _windows_overlap(a.window, c.window):
                continue
            ab, cb = a.box, c.box
            if ab.anchor_only and cb.anchor_only:
                if abs(ab.cx - cb.cx) < _ANCHOR_COINCIDE and abs(ab.cy - cb.cy) < _ANCHOR_COINCIDE:
                    out.append(Violation("overlap", "advisory", scene,
                                         f"{a.sel!r} and {c.sel!r} share an anchor "
                                         f"(~{ab.cx:.2f},{ab.cy:.2f}) — likely stacked text", None))
                continue
            if ab.anchor_only or cb.anchor_only:
                continue  # one side has no real extent — not a reliable overlap
            frac = _iou_min(ab, cb)
            if frac > _OVERLAP_MIN:
                out.append(Violation("overlap", "error" if overlap_hard else "advisory", scene,
                                     f"{a.sel!r} and {c.sel!r} overlap ({frac:.0%} of the smaller box)",
                                     [max(ab.x0, cb.x0), max(ab.y0, cb.y0),
                                      min(ab.x1, cb.x1), min(ab.y1, cb.y1)]))

    # anchor drift — advisory: does the scene's content MASS sit where the archetype expects it?
    # Weight by box area (a small floor so anchor-only text still counts a little) so a dominant hero
    # decides, and a legit upper-third eyebrow / corner label can't outvote it.
    # A full-bleed media-ground scene legitimately carries its mass across the whole canvas (the ground IS
    # the composition; text is a deliberate overlay that can sit anywhere) — the editorial-column zone check
    # doesn't apply, so skip it rather than false-flag "0% of content mass in zone" (post-mortem L1).
    spec = _comp.get(archetype) if archetype else None
    zone = (spec or {}).get("zone")
    if zone and items and not has_full_bleed_ground:
        zx, zy = zone.get("x", [0, 1]), zone.get("y", [0, 1])
        floor = 0.004
        tot = ins = 0.0
        for it in items:
            w = max(it.box.area, floor)
            tot += w
            if zx[0] - _EPS <= it.box.cx <= zx[1] + _EPS and zy[0] - _EPS <= it.box.cy <= zy[1] + _EPS:
                ins += w
        frac = ins / tot if tot else 1.0
        if frac < _ANCHOR_DRIFT_FRAC:
            out.append(Violation("anchor_drift", "advisory", scene,
                                 f"only {frac:.0%} of content mass sits in the {archetype} zone "
                                 f"x{zx} y{zy} — layout may not read as its archetype", None))
    return out


# ── public API ────────────────────────────────────────────────────────────────
def lint_raw_scene(html_list: List[str], archetype: Optional[str] = None, *,
                   captions_on: bool = True, scene: str = "raw") -> List[Violation]:
    """Lint one bespoke/agent `raw` scene (its `data.html` list). Overlap is ADVISORY here — a raw
    scene's simultaneity is set by its `tl`, which static parse can't resolve, so coincident anchors
    are a hint, not a hard error."""
    joined = "".join(html_list)
    root = _parse("<div>" + joined + "</div>")
    items, fbg_windows = _measure(root, _class_pos_rules(_extract_css(joined)))
    return _check_items(items, scene, archetype, captions_on, overlap_hard=False,
                        has_full_bleed_ground=bool(fbg_windows))


def lint_frame_html(html: str, *, scene_archetypes: Optional[Dict[str, str]] = None,
                    captions_on: bool = True, frame: str = "frame") -> List[Violation]:
    """Lint a composed frame's HTML. Clips carry explicit data-start windows, so overlap is a HARD
    error. `scene_archetypes` maps a scene/clip id → archetype for the anchor-drift advisory."""
    root = _parse(html)
    items, fbg_windows = _measure(root, _class_pos_rules(_extract_css(html)))
    # group by clip window so overlap + drift are scoped to simultaneously-visible content
    groups: Dict[Tuple[float, float], List[Item]] = {}
    for it in items:
        groups.setdefault(it.window, []).append(it)
    out: List[Violation] = []
    for win, its in sorted(groups.items()):
        # prefer the archetype stamped in the composed DOM (compose.py data-archetype); fall back to the
        # spec sidecar mapping when linting a frame that predates the stamp.
        arche = next((i.archetype for i in its if i.archetype), None)
        if not arche and scene_archetypes:
            for sel in (i.sel for i in its):
                for sid, a in scene_archetypes.items():
                    if sid and sid in sel:
                        arche = a
                        break
                if arche:
                    break
        label = f"{frame}@{win[0]:.1f}s"
        out.extend(_check_items(its, label, arche, captions_on, overlap_hard=True,
                                has_full_bleed_ground=(win in fbg_windows)))
    return out


def lint_composition(comp_dir: Path, *, captions_on: bool = True) -> Dict[str, Any]:
    """Walk a HyperFrames comp's frames, lint each, aggregate. Resolves each scene's archetype from
    its spec sidecar (meta.archetype or block_archetype(type)) when present."""
    comp_dir = Path(comp_dir)
    frames_dir = comp_dir / "compositions" / "frames"
    results: List[Dict[str, Any]] = []
    n_err = n_adv = 0
    for html_path in sorted(frames_dir.glob("*.html")) if frames_dir.exists() else []:
        scene_arche = _scene_archetypes_for(html_path)
        vios = lint_frame_html(html_path.read_text(encoding="utf-8", errors="replace"),
                               scene_archetypes=scene_arche, captions_on=captions_on,
                               frame=html_path.stem)
        errs = [v for v in vios if v.severity == "error"]
        n_err += len(errs)
        n_adv += len(vios) - len(errs)
        if vios:
            results.append({"frame": html_path.name, "violations": [v.as_dict() for v in vios]})
    return {"comp": str(comp_dir), "captions_on": captions_on,
            "errors": n_err, "advisories": n_adv, "frames": results, "ok": n_err == 0}


def _scene_archetypes_for(html_path: Path) -> Dict[str, str]:
    """Read the frame's spec sidecar (if any) → {scene_id: archetype}."""
    spec = html_path.with_suffix(".spec.json")
    out: Dict[str, str] = {}
    if not spec.exists():
        return out
    try:
        data = json.loads(spec.read_text(encoding="utf-8"))
    except Exception:
        return out
    for sc in data.get("scenes", []) if isinstance(data, dict) else []:
        sid = sc.get("id") or sc.get("scene_id")
        if not sid:
            continue
        a = (sc.get("meta") or {}).get("archetype") or _comp.block_archetype(sc.get("type", ""))
        if a:
            out[sid] = a
    return out


# ── CLI ────────────────────────────────────────────────────────────────────────
def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic composition layout linter.")
    ap.add_argument("target", help="a comp dir, or a single frame .html")
    ap.add_argument("--no-captions", action="store_true", help="captions are off (skip caption-band check)")
    ap.add_argument("--archetype", default=None, help="archetype for a single-frame/raw lint")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)
    captions_on = not args.no_captions
    p = Path(args.target)

    if p.is_dir():
        rep = lint_composition(p, captions_on=captions_on)
    elif p.suffix == ".html":
        vios = lint_frame_html(p.read_text(encoding="utf-8", errors="replace"),
                               scene_archetypes=_scene_archetypes_for(p),
                               captions_on=captions_on, frame=p.stem)
        errs = [v for v in vios if v.severity == "error"]
        rep = {"frame": p.name, "errors": len(errs), "advisories": len(vios) - len(errs),
               "violations": [v.as_dict() for v in vios], "ok": not errs}
    else:
        print(f"unknown target {p}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_report(rep)
    return 0 if rep.get("ok", True) else 1


def _print_report(rep: Dict[str, Any]) -> None:
    icon = {"error": "✗", "advisory": "·"}
    def show(vs, indent=""):
        for v in vs:
            print(f"{indent}{icon.get(v['severity'],'?')} [{v['kind']}] {v['scene']}: {v['detail']}")
    if "frames" in rep:
        print(f"composition {rep['comp']} — {rep['errors']} errors, {rep['advisories']} advisories")
        for fr in rep["frames"]:
            print(f"  {fr['frame']}")
            show(fr["violations"], "    ")
    else:
        print(f"{rep['frame']} — {rep['errors']} errors, {rep['advisories']} advisories")
        show(rep["violations"], "  ")
    print("OK" if rep.get("ok", True) else "FAIL — layout errors above")


if __name__ == "__main__":
    raise SystemExit(_main())
