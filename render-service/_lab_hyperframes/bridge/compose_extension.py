"""Tier-2 extension blocks for the HyperFrames composer — deliberately kept OUT of compose.py so the
core block library stays lean. compose.py merges ``EXT_BLOCKS`` into ``BLOCKS`` at import time;
``catalog.json`` documents each (``check_catalog.py`` enforces parity, ``author.py`` gates on the
catalog). To add an extension block: write the fn here, add it to EXT_BLOCKS, add a catalog entry
with matching ``fn``, ship a honesty test.

``spotlight`` — the generalized "subject + flanking label" pattern promoted from the SpaceX/Falcon-9
reels (Tier-2 of the Clips→HyperFrames effect adaptation; a per-scene ``raw`` clone was Tier-1). A
background-removed SUBJECT is placed **center | left | right**, and a two-part (or single) LABEL
responds to that position:
  - subject CENTER → label splits to BOTH sides, sitting BEHIND the subject (its body overlaps the
    inner glyphs, exactly like the reference);
  - subject LEFT/RIGHT → the label is one block on the OPPOSITE side (side-by-side, no overlap).
The hard part is DETERMINISTIC and lives here, not in hand-authored HTML: each label is region-
bounded and ``data-fit`` auto-shrinks it so it never overflows its side (the "words resize / don't
overlap" requirement), z-order is computed (label track 2 behind, subject track 4 in front), and the
reveal is seek-safe (label spreads/slides in, subject fades + rises on top). The agent picks only
``{subject, position, words, motion}``.

data: {
  subject: "assets/x.png"|"assets/x.mp4"   # bg-removed image OR video (required)
  position: "center"|"left"|"right"         # default center
  words: ["激励","计划"] | "激励计划" | "Incentive"   # 2-list, or split automatically
  kicker?: "Incentive Plan"                 # optional small overline, centered top
  behind?: true                             # label behind the subject (default true; center-only effect)
  motion?: "rise"|"fade"                     # subject entrance (default rise)

  # ---- center-subject label placement (all optional; the "clear" mode is asset-aware) ----
  label_layout?: "overlap"|"clear"          # default "overlap" = the reel look (words vertically centered,
                                            #   47% each side, the subject BODY overlapping the inner glyphs).
                                            # "clear" = auto-place the words in the subject's CLEAR zone (moved
                                            #   UP and OUTSIDE the silhouette). Placement is MEASURED from the
                                            #   cutout's own alpha (per-row profile, mapped through the CSS
                                            #   contain/bottom-anchor transform), so it ADAPTS to any asset
                                            #   shape — swap a wider/narrower/taller cutout and the words
                                            #   recompute. Deterministic (baked at compose), seek-safe.
                                            #   Falls back LOUDLY to overlap if the asset can't be measured
                                            #   (video subject, no alpha, or no clear band exists).
  label_valign?: "auto"|"top"|"center"|<0..1>  # clear-mode only. Vertical band for the words. auto (default)
                                            #   = the narrowest row in the upper half (biased upward); a float
                                            #   is a fraction of the silhouette height from its top.
  clearance?: <float>                       # clear-mode only. Margin multiplier between word and silhouette
                                            #   (default 1.0; >1 pushes words further out, <1 tucks them in).
  subject_scale?: <0..1>                    # clear-mode only. Shrink the hero (default 1.0) to open a clear
                                            #   band when the subject would otherwise fill the frame.
}
"""
from __future__ import annotations

import compose  # sibling module; safe because compose imports THIS module last (all helpers defined)

CANVAS_W, CANVAS_H = 1920, 1080
_VIDEO_EXT = ("mp4", "webm", "mov", "m4v")


def _is_cjk(s: str) -> bool:
    return any("一" <= c <= "鿿" for c in str(s))


def _norm_words(words, position: str):
    """(left, right) for a center subject; (block, '') for a left/right subject. `words` may be a
    2-list, or a string auto-split at its midpoint (by CJK char, else by word)."""
    if isinstance(words, (list, tuple)):
        parts = [str(w).strip() for w in words if str(w).strip()]
    else:
        s = str(words or "").strip()
        parts = [s] if s else []
    if position != "center":
        if not parts:
            return "", ""
        joiner = "" if _is_cjk("".join(parts)) else " "
        return joiner.join(parts), ""
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    if not parts:
        return "", ""
    s = parts[0]
    if _is_cjk(s):
        toks = [c for c in s if not c.isspace()]
        joiner = ""
    else:
        toks = s.split(" ")
        joiner = " "
    mid = (len(toks) + 1) // 2
    return joiner.join(toks[:mid]), joiner.join(toks[mid:])


def _subject_media(sid: str, subj: str, position: str, scale: float = 1.0) -> str:
    esc = compose.esc
    ext = str(subj).lower().rsplit(".", 1)[-1] if "." in str(subj) else ""
    # center: cap the WIDTH too so the flanking labels stay visible beside the subject (a full-width
    # cutout would bury them); left/right: cap height so the opposite-side label has room. `scale` (clear
    # mode's subject_scale) shrinks the hero to open a clear band — kept in lockstep with _subject_footprint.
    if position == "center":
        dims = f"height:{92 * scale:.4g}%;max-width:{58 * scale:.4g}%"
    else:
        dims = "height:90%;max-width:100%"
    common = f'style="{dims};object-fit:contain;filter:drop-shadow(0 14px 34px rgba(0,0,0,.55))"'
    if ext in _VIDEO_EXT:
        return (f'<video id="{sid}-subj" src="{esc(subj)}" muted playsinline autoplay loop '
                f'{common}></video>')
    return f'<img id="{sid}-subj" src="{esc(subj)}" alt="" {common}/>'


# ---------------------------------------------------------------------------------------------------
# Asset-aware CLEAR-mode label placement. The hard part is deterministic and lives here: we MEASURE
# the cutout's own alpha silhouette and place the two flanking words in its clear zone (up + outside
# the body), so the layout adapts to ANY subject shape instead of assuming a fixed box. Everything is
# baked into fixed frame-px at compose time (seek-safe); PIL/numpy are imported lazily so a missing
# dependency can never break the compose path — it just falls back to the overlap layout.

def _resolve_asset(subj: str):
    """Absolute path to a subject asset at compose time, or None. compose._ASSET_BASE (the comp dir) is
    set by author.py from --out-dir; during --validate-only there is no out-dir, so this returns None and
    the caller falls back — validation never needs the real pixels."""
    from pathlib import Path
    base = getattr(compose, "_ASSET_BASE", None)
    if not base:
        return None
    try:
        p = (Path(base) / subj).resolve()
        return p if p.is_file() else None
    except Exception:
        return None


def _subject_footprint(iw: int, ih: int, scale: float):
    """The displayed-image rectangle (L, T, R, B in 1920x1080 frame px) + (disp_w, disp_h) for a CENTER
    subject of intrinsic size (iw, ih). Mirrors the CSS exactly: height:92%*scale + max-width:58%*scale,
    object-fit:contain, wrap bottom-anchored (align-items:flex-end) and horizontally centered."""
    hbox = CANVAS_H * 0.92 * scale
    maxw = CANVAS_W * 0.58 * scale
    s = min(maxw / iw, hbox / ih)
    dw, dh = iw * s, ih * s
    left = (CANVAS_W - dw) / 2.0                       # element + image both horizontally centered
    top = (CANVAS_H - hbox) + (hbox - dh) / 2.0        # element bottom-anchored; image centered within it
    return left, top, left + dw, top + dh, dw, dh


def _clear_label_geometry(asset_abs, valign, clearance: float, scale: float, top_floor: float = 0.0):
    """Measure the subject silhouette and return placement for the two flanking words in its CLEAR zone,
    or None to fall back. Result: {y, band_h, left:(x0,x1), right:(x0,x1)} in frame px. Adapts to shape:
    the word band is the narrowest row (auto) mapped to frame space, and each region hugs just outside the
    silhouette AT THAT BAND (not a global bbox — an arms-out figure is narrow at the head, so the words
    slot in high and close). `top_floor` (frame px) keeps the band clear of the kicker on tall subjects:
    if the auto band would rise above it, we clamp down and RE-MEASURE the silhouette at the lower band."""
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return None
    try:
        im = Image.open(asset_abs)
        if im.mode != "RGBA":
            return None                                # opaque asset: no silhouette to measure
        iw, ih = im.size
        mask = np.asarray(im.split()[-1]) > 24         # alpha over a small floor = "solid" pixel
    except Exception:
        return None

    ys = np.nonzero(mask.any(axis=1))[0]
    if len(ys) == 0:
        return None
    top_y, bot_y = int(ys[0]), int(ys[-1])
    sil_h = (bot_y - top_y) or 1
    left, top, right, bottom, dw, dh = _subject_footprint(iw, ih, scale)

    def extent(y0, y1):                                # silhouette [min,max] col-fraction over rows [y0,y1]
        y0, y1 = max(0, int(y0)), min(ih, int(y1) + 1)
        sub = mask[y0:y1]
        cols = np.nonzero(sub.any(axis=0))[0]
        return (cols[0] / iw, cols[-1] / iw) if len(cols) else None

    def halfw(y):
        e = extent(y, y)
        return max(abs(e[0] - 0.5), abs(e[1] - 0.5)) if e else 0.0

    # choose the word band's center row (image space)
    if valign == "center":
        target = top_y + 0.5 * sil_h
    elif valign == "top":
        target = top_y + 0.10 * sil_h
    elif isinstance(valign, (int, float)) and not isinstance(valign, bool):
        target = top_y + max(0.0, min(1.0, float(valign))) * sil_h
    else:                                              # auto: narrowest row in the upper half, biased upward
        zone = [y for y in range(top_y, int(top_y + 0.55 * sil_h) + 1) if extent(y, y)]
        if not zone:
            return None
        mn = min(halfw(y) for y in zone)
        target = next(y for y in zone if halfw(y) <= mn * 1.15 + 1e-6)

    band_frame = 158.0                                 # the word's line box in frame px (font 150 * ~1.05)
    band_img = band_frame * ih / dh                    # same span back in image rows
    y_center = top + (target / ih) * dh
    if y_center - band_frame / 2 < top_floor:          # clamp below the kicker on tall subjects, then
        y_center = top_floor + band_frame / 2          #   re-derive the band row so we re-measure there
        target = (y_center - top) / dh * ih
    ext = extent(target - band_img / 2, target + band_img / 2)
    if not ext:
        return None
    sil_l = left + ext[0] * dw
    sil_r = left + ext[1] * dw
    margin = max(0.0, clearance) * 0.02 * CANVAS_W
    lx1 = sil_l - margin
    rx0 = sil_r + margin
    min_region = 0.12 * CANVAS_W                       # a word needs at least this much side room
    if lx1 < min_region or (CANVAS_W - rx0) < min_region:
        return None                                    # silhouette too wide here → honest fallback
    return {"y": y_center, "band_h": band_frame,
            "left": (0.0, lx1), "right": (rx0, float(CANVAS_W))}


def _clear_label(sid: str, which: str, text: str, x0: float, x1: float, y: float, band_h: float,
                 align: str, fit_origin: str) -> str:
    """A CLEAR-mode band label: an absolutely-placed box [x0..x1] centered on frame-y `y`, `band_h` tall,
    with the word aligned to hug the subject side. data-fit shrinks the word to never exceed the box."""
    esc = compose.esc
    justify = "flex-start" if align == "left" else "flex-end"
    pad = "padding-left:1.5%;" if align == "left" else "padding-right:1.5%;"
    usable = int((x1 - x0) * 0.94)
    return (
        f'<div id="{sid}-lab{which}" class="clip" data-start="{{start}}" data-duration="{{dur}}" '
        f'data-track-index="{{txt_track}}" style="position:absolute;left:{x0:.1f}px;'
        f'top:{y - band_h / 2:.1f}px;width:{x1 - x0:.1f}px;height:{band_h:.1f}px;display:flex;'
        f'align-items:center;justify-content:{justify};{pad}box-sizing:border-box;pointer-events:none">'
        f'<span id="{sid}-txt{which}" data-fit data-fit-w="{usable}" data-fit-origin="{fit_origin}" '
        f'style="font-family:var(--font-display-en),\'Arial Black\',Impact,sans-serif;font-weight:900;'
        f'font-size:150px;line-height:0.92;color:var(--accent);letter-spacing:1px;white-space:nowrap;'
        f'text-align:{align};text-shadow:0 4px 26px rgba(0,0,0,.45)">{esc(text)}</span></div>'
    )


def _label(sid: str, which: str, text: str, region_pct: float, align: str, fit_origin: str, side: str) -> str:
    """A region-bounded, auto-fit label. `which` = id suffix ('l'|'r'|'b'); `side` = which canvas edge
    the region hugs ('left'|'right'); `align` = text alignment within it (independent of side — a
    right-hugging region can still be left-aligned so it reads outward from the subject). region_pct =
    container width % of canvas. Positioning is by flex (NOT transform, so GSAP animates x/opacity on
    the inner span freely); data-fit shrinks the span to never exceed its usable width."""
    esc = compose.esc
    justify = {"left": "flex-start", "right": "flex-end", "center": "center"}[align]
    side_css = "left:0;" if side == "left" else "right:0;"
    usable = int(CANVAS_W * region_pct / 100 * 0.92)   # minus inner padding
    pad = "padding-left:3%;" if align == "left" else ("padding-right:3%;" if align == "right" else "")
    return (
        f'<div id="{sid}-lab{which}" class="clip" data-start="{{start}}" data-duration="{{dur}}" '
        f'data-track-index="{{txt_track}}" style="position:absolute;{side_css}top:0;height:100%;'
        f'width:{region_pct:.1f}%;display:flex;align-items:center;justify-content:{justify};{pad}'
        f'box-sizing:border-box;pointer-events:none">'
        f'<span id="{sid}-txt{which}" data-fit data-fit-w="{usable}" data-fit-origin="{fit_origin}" '
        f'style="font-family:var(--font-display-en),\'Arial Black\',Impact,sans-serif;font-weight:900;'
        f'font-size:150px;line-height:0.92;color:var(--accent);letter-spacing:1px;white-space:nowrap;'
        f'text-align:{align};text-shadow:0 4px 26px rgba(0,0,0,.45)">{esc(text)}</span></div>'
    )


def spotlight(sid, sc):
    """Reusable BLOCK — bg-removed subject (center|left|right) + a position-responsive label that
    sits behind a centered subject (split both sides) or opposite a left/right subject. Deterministic
    layout (region-bounded + data-fit auto-resize + computed z-order), seek-safe GSAP reveal.
    See the module docstring for the data contract."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc = compose.esc
    subj = d.get("subject") or d.get("src") or ""
    position = str(d.get("position") or "center").lower()
    if position not in ("center", "left", "right"):
        position = "center"
    behind = bool(d.get("behind", True))
    motion = str(d.get("motion") or "rise").lower()
    left_txt, right_txt = _norm_words(d.get("words", d.get("label", "")), position)
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    # center-subject label placement: "overlap" (default reel look) vs asset-aware "clear" (words up + out)
    label_layout = str(d.get("label_layout") or "overlap").lower()
    label_valign = d.get("label_valign", "auto")
    clearance = float(d.get("clearance", 1.0) or 1.0)
    subj_scale = float(d.get("subject_scale", 1.0) or 1.0)
    clear_geo = None
    if position == "center" and label_layout == "clear":
        asset = _resolve_asset(subj) if str(subj).lower().rsplit(".", 1)[-1] not in _VIDEO_EXT else None
        # reserve the kicker band (top:7% + its ~26px cap + margin) so words never ride over the overline
        top_floor = (0.07 * CANVAS_H + 52.0) if d.get("kicker") else 0.02 * CANVAS_H
        clear_geo = (_clear_label_geometry(asset, label_valign, clearance, subj_scale, top_floor)
                     if asset else None)

    subj_track = 4
    txt_track = 2 if behind else 6            # behind (default) => under the subject on track 4
    ground = ("radial-gradient(ellipse 82% 72% at 50% 46%,#2c2823 0%,#17130f 55%,#0a0807 100%)"
              if dark else
              "radial-gradient(ellipse 82% 72% at 50% 46%,#f4eee2 0%,#e6ddca 60%,#d6c9ad 100%)")

    frag = [f'<div id="{sid}-bg" class="clip" data-start="{start}" data-duration="{dur}" '
            f'data-track-index="0" style="position:absolute;inset:0;background:{ground}"></div>']
    tl = [f'tl.fromTo("#{sid}-bg",{{opacity:0}},{{opacity:1,duration:0.6,ease:"power2.out"}},{start:.2f});']

    # optional kicker (small centered overline)
    if d.get("kicker"):
        frag.append(f'<div id="{sid}-kick" class="clip" data-start="{start}" data-duration="{dur}" '
                    f'data-track-index="{txt_track+1}" style="position:absolute;left:0;right:0;top:7%;'
                    f'text-align:center;font-family:var(--font-body);font-weight:600;font-size:26px;'
                    f'letter-spacing:0.32em;text-transform:uppercase;color:var(--text-2,#999)">'
                    f'{esc(d["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-kick",{{opacity:0,y:-10}},{{opacity:1,y:0,duration:0.5,'
                  f'ease:"power2.out"}},{start+0.15:.2f});')

    # ---- labels (position-responsive) ----
    def emit_label(html):
        frag.append(html.format(start=start, dur=dur, txt_track=txt_track))

    if position == "center":
        if label_layout == "clear" and not clear_geo:
            # requested clear placement but couldn't measure (video/no-alpha/no clear band) — fall back to
            # overlap, LOUDLY (a visible marker in the HTML, not a silent downgrade).
            frag.append(f"<!-- spotlight[{sid}]: label_layout='clear' fell back to 'overlap' "
                        f"(subject not measurable: video, opaque, or no clear band) -->")
        if clear_geo:                                  # asset-aware: words in the subject's clear zone
            if left_txt:
                lx0, lx1 = clear_geo["left"]
                emit_label(_clear_label(sid, "l", left_txt, lx0, lx1, clear_geo["y"], clear_geo["band_h"],
                                        "right", "right center"))
                tl.append(f'tl.fromTo("#{sid}-txtl",{{opacity:0,x:-90}},{{opacity:1,x:0,duration:0.8,'
                          f'ease:"power3.out"}},{start+0.3:.2f});')
            if right_txt:
                rx0, rx1 = clear_geo["right"]
                emit_label(_clear_label(sid, "r", right_txt, rx0, rx1, clear_geo["y"], clear_geo["band_h"],
                                        "left", "left center"))
                tl.append(f'tl.fromTo("#{sid}-txtr",{{opacity:0,x:90}},{{opacity:1,x:0,duration:0.8,'
                          f'ease:"power3.out"}},{start+0.3:.2f});')
        else:                                          # overlap (default reel look): centered, 47% each side
            if left_txt:
                emit_label(_label(sid, "l", left_txt, 47.0, "right", "right center", side="left"))
                tl.append(f'tl.fromTo("#{sid}-txtl",{{opacity:0,x:-90}},{{opacity:1,x:0,duration:0.8,'
                          f'ease:"power3.out"}},{start+0.3:.2f});')
            if right_txt:
                emit_label(_label(sid, "r", right_txt, 47.0, "left", "left center", side="right"))
                tl.append(f'tl.fromTo("#{sid}-txtr",{{opacity:0,x:90}},{{opacity:1,x:0,duration:0.8,'
                          f'ease:"power3.out"}},{start+0.3:.2f});')
        justify = "center"
    else:
        # subject on one side, single label block on the OPPOSITE side (side-by-side, no overlap)
        if left_txt:
            if position == "left":     # subject left -> label on the RIGHT, reading rightward
                emit_label(_label(sid, "b", left_txt, 52.0, "left", "left center", side="right"))
                tl.append(f'tl.fromTo("#{sid}-txtb",{{opacity:0,x:70}},{{opacity:1,x:0,duration:0.75,'
                          f'ease:"power3.out"}},{start+0.35:.2f});')
            else:                      # subject right -> label on the LEFT, reading leftward
                emit_label(_label(sid, "b", left_txt, 52.0, "right", "right center", side="left"))
                tl.append(f'tl.fromTo("#{sid}-txtb",{{opacity:0,x:-70}},{{opacity:1,x:0,duration:0.75,'
                          f'ease:"power3.out"}},{start+0.35:.2f});')
        justify = "flex-start" if position == "left" else "flex-end"

    # ---- subject (in front of the labels when behind=True) ----
    # center: subject spans the frame (justify center). left/right: BOUND the subject to its ~47% half
    # so the opposite-side label (52%) never collides with it — deterministic side-by-side, no overlap.
    if position == "center":
        wrap_geo = "inset:0"
    elif position == "left":
        wrap_geo = "left:1%;top:0;bottom:0;width:47%"
    else:
        wrap_geo = "right:1%;top:0;bottom:0;width:47%"
    frag.append(f'<div id="{sid}-subjwrap" class="clip" data-start="{start}" data-duration="{dur}" '
                f'data-track-index="{subj_track}" style="position:absolute;{wrap_geo};display:flex;'
                f'align-items:flex-end;justify-content:center;pointer-events:none">'
                f'{_subject_media(sid, subj, position, subj_scale)}</div>')
    if motion == "fade":
        tl.append(f'tl.fromTo("#{sid}-subj",{{opacity:0}},{{opacity:1,duration:0.8,ease:"power2.out"}},'
                  f'{start+0.5:.2f});')
    else:  # rise (default) — fade + scale + move up, then a slow seek-safe float
        tl.append(f'tl.fromTo("#{sid}-subj",{{opacity:0,scale:0.9,y:48}},{{opacity:1,scale:1,y:0,'
                  f'duration:0.9,ease:"power3.out"}},{start+0.5:.2f});')
        if dur > 2.0:
            tl.append(f'tl.to("#{sid}-subj",{{y:-12,duration:{dur-1.2:.2f},ease:"sine.inOut"}},'
                      f'{start+1.1:.2f});')

    return frag, tl


EXT_BLOCKS = {"spotlight": spotlight}
