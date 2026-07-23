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


def data_table(sid, sc):
    """A-P3 — a dataset as a full TABLE with ONE cell SPOTLIGHTED: a beat that names a single number shows
    the ENTIRE series, that cell highlighted, so the value reads IN CONTEXT (not a bare stat). Bind a dataset
    (`data.dataset`+`query`+`encode`) and the resolver fills `columns`/`rows` from real cells + resolves a
    `highlight:{where:{col:val}}` to a row/col; numbers therefore carry provenance. Rows reveal across the
    window; the spotlighted row lifts and its cell pulses at its cue."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc = compose.esc
    cols = [str(c) for c in (d.get("columns") or [])]
    rows = d.get("rows") or []
    hl = d.get("highlight") or {}
    hr = hl.get("row")
    hc = hl.get("col", 0) if hl else None
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    faint = "rgba(243,239,230,0.16)" if dark else "rgba(28,28,25,0.12)"
    n = len(rows)
    times = compose._reveal_times(n, start, dur, [None] * n) if n else []

    def _cell(txt, i, j, head=False):
        tag = "th" if head else "td"
        hit = (not head and i == hr and (hc is None or j == hc))
        idp = f' id="{sid}-c{i}-{j}"' if hit else ""
        style = ("padding:0.7cqw 1.4cqw;text-align:%s;font-variant-numeric:tabular-nums;"
                 "white-space:nowrap;border-bottom:1px solid %s;" % ("left" if j == 0 else "right", faint))
        if head:
            style += "font-weight:800;letter-spacing:0.02em;opacity:0.72;font-size:1.05cqw;text-transform:uppercase;"
        else:
            style += "font-size:1.55cqw;font-weight:%s;" % ("800" if hit else "500")
        if hit:
            style += "color:var(--accent-ink,%s);background:var(--accent);border-radius:8px;" % ink
        return f'<{tag}{idp} style="{style}">{esc(str(txt))}</{tag}>'

    head = "".join(_cell(c, -1, j, head=True) for j, c in enumerate(cols))
    body_rows = []
    for i, r in enumerate(rows):
        cells = r if isinstance(r, list) else [r.get(c, "") for c in cols]
        tds = "".join(_cell(v, i, j) for j, v in enumerate(cells))
        body_rows.append(f'<tr id="{sid}-r{i}" style="opacity:0">{tds}</tr>')
    kick = (f'<div style="font-family:var(--font-body);font-weight:600;font-size:0.95cqw;letter-spacing:0.28em;'
            f'text-transform:uppercase;color:var(--text-2,#8a8a80);margin-bottom:0.6cqw">{esc(d["kicker"])}</div>'
            if d.get("kicker") else "")
    title = ""
    if d.get("title"):
        t = esc(d["title"])
        if d.get("titleHi"):
            t = t.replace(esc(d["titleHi"]), f'<span style="color:var(--accent)">{esc(d["titleHi"])}</span>')
        title = (f'<div data-fit data-fit-w="52cqw" style="font-family:var(--font-display);font-weight:800;'
                 f'font-size:3cqw;letter-spacing:-0.01em;line-height:1.05;color:{ink};margin-bottom:1.6cqw">{t}</div>')
    frag = [f'<div id="{sid}-wrap" class="clip" data-start="{start}" data-duration="{dur}" data-track-index="1" '
            f'style="position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;'
            f'align-items:center;container-type:size;padding:0 8cqw;color:{ink}">'
            f'{kick}{title}<table style="border-collapse:collapse;color:{ink}">'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(body_rows)}</tbody></table></div>']
    tl = []
    for i in range(n):
        tl.append(f'tl.fromTo("#{sid}-r{i}",{{opacity:0,y:8}},{{opacity:1,y:0,duration:0.4,ease:"power2.out"}},{times[i]:.2f});')
    if hr is not None and 0 <= hr < n:                              # spotlight pulse at the highlighted row's cue
        cue = times[hr] if hr < len(times) else start
        tl.append(f'tl.fromTo("#{sid}-r{hr}",{{scale:1}},{{scale:1.04,duration:0.3,ease:"back.out(2)",'
                  f'transformOrigin:"center"}},{cue + 0.15:.2f});')
        tl.append(f'tl.to("#{sid}-r{hr}",{{scale:1,duration:0.3}},{cue + 0.55:.2f});')
    return frag, tl


def _plot_box():
    """The shared plot rectangle (px) for the A-P4 marks — matches the chart block's margins."""
    return 300, 1620, 220, 900          # PX0, PX1 (x span), PY0(top), PY1(bottom)


def trajectory(sid, sc):
    """A-P4 — a CONNECTED SCATTER: points in 2-D (x,y) joined by a path, revealed IN ORDER — a trajectory
    THROUGH a space over time (inflation vs unemployment by year; loss vs step). The line draws point→point;
    each dot pops with its label as the draw reaches it. Bind a dataset (encode x/y/label)."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc = compose.esc
    pts = d.get("points") or []
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    PX0, PX1, PY0, PY1 = _plot_box()
    xs = [float(p.get("x", 0)) for p in pts] or [0.0]
    ys = [float(p.get("y", 0)) for p in pts] or [0.0]
    xlo, xhi = min(xs), max(xs) or 1.0
    ylo, yhi = min(ys), max(ys) or 1.0
    sx = lambda v: PX0 + (PX1 - PX0) * ((v - xlo) / ((xhi - xlo) or 1))
    sy = lambda v: PY1 - (PY1 - PY0) * ((v - ylo) / ((yhi - ylo) or 1))
    XY = [(sx(float(p.get("x", 0))), sy(float(p.get("y", 0)))) for p in pts]
    n = len(XY)
    times = compose._reveal_times(n, start, dur, compose._reveal_cues(pts, start)) if n else []
    frag = [f'<div id="{sid}-wrap" class="clip" data-start="{start}" data-duration="{dur}" data-track-index="1" '
            f'style="position:absolute;inset:0;color:{ink}">']
    if d.get("title"):
        frag.append(f'<div style="position:absolute;left:300px;top:110px;font-family:var(--font-display);'
                    f'font-weight:800;font-size:44px;color:{ink}">{esc(d["title"])}</div>')
    if d.get("xlabel"):
        frag.append(f'<div style="position:absolute;left:{PX1-260}px;top:{PY1+18}px;font-size:22px;'
                    f'opacity:0.6">{esc(d["xlabel"])} →</div>')
    if d.get("ylabel"):
        frag.append(f'<div style="position:absolute;left:{PX0-60}px;top:{PY0-40}px;font-size:22px;'
                    f'opacity:0.6">↑ {esc(d["ylabel"])}</div>')
    path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in XY)
    frag.append(f'<svg viewBox="0 0 1920 1080" preserveAspectRatio="none" style="position:absolute;inset:0;'
                f'width:100%;height:100%"><path id="{sid}-path" d="{path}" fill="none" stroke="var(--accent)" '
                f'stroke-width="4" stroke-linejoin="round"/></svg>')
    for i, (x, y) in enumerate(XY):
        frag.append(f'<div id="{sid}-d{i}" style="position:absolute;left:{x-9:.0f}px;top:{y-9:.0f}px;width:18px;'
                    f'height:18px;border-radius:50%;background:var(--accent);opacity:0"></div>')
        lab = esc(str(pts[i].get("label", "")))
        if lab:
            frag.append(f'<div id="{sid}-l{i}" style="position:absolute;left:{x+14:.0f}px;top:{y-14:.0f}px;'
                        f'font-size:22px;font-weight:700;opacity:0;color:{ink}">{lab}</div>')
    frag.append('</div>')
    ldur = round(max(1.2, (times[-1] - times[0] + 0.5) if n else dur), 2)
    tl = [f'(function(){{var p=document.getElementById("{sid}-path"),L=p.getTotalLength();'
          f'p.style.strokeDasharray=L;p.style.strokeDashoffset=L;'
          f'tl.fromTo(p,{{strokeDashoffset:L}},{{strokeDashoffset:0,duration:{ldur},ease:"power1.inOut"}},{times[0] if n else start:.2f});}})();']
    for i in range(n):
        tl.append(f'tl.fromTo("#{sid}-d{i}",{{scale:0}},{{scale:1,opacity:1,duration:0.35,ease:"back.out(2)"}},{times[i]:.2f});')
        tl.append(f'tl.to("#{sid}-l{i}",{{opacity:1,duration:0.3}},{times[i]+0.1:.2f});')
    return frag, tl


def stream(sid, sc):
    """A-P4 — a STACKED AREA / streamgraph: several series stacked into bands over an x axis, each a filled
    area, revealed by a left→right sweep — shows a COMPOSITION changing over time. `series:[{label,values:[]}]`
    + `x:[labels]`; provide value_source or bind a dataset for the gate."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc = compose.esc
    series = d.get("series") or []
    xlabs = d.get("x") or []
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    PX0, PX1, PY0, PY1 = _plot_box()
    nx = max((len(s.get("values", [])) for s in series), default=0)
    totals = [sum(float(s.get("values", [0] * nx)[i]) for s in series) for i in range(nx)]
    ymax = max(totals) or 1.0
    step = (PX1 - PX0) / max(1, nx - 1)
    xat = lambda i: PX0 + i * step
    yat = lambda v: PY1 - (PY1 - PY0) * (v / ymax)
    frag = [f'<div id="{sid}-wrap" class="clip" data-start="{start}" data-duration="{dur}" data-track-index="1" '
            f'style="position:absolute;inset:0;color:{ink}">']
    if d.get("title"):
        frag.append(f'<div style="position:absolute;left:300px;top:110px;font-family:var(--font-display);'
                    f'font-weight:800;font-size:44px;color:{ink}">{esc(d["title"])}</div>')
    cum = [0.0] * nx
    bands = []
    for s in series:
        vals = [float(v) for v in s.get("values", [0] * nx)]
        top = [cum[i] + vals[i] for i in range(nx)]
        up = " L ".join(f"{xat(i):.1f} {yat(top[i]):.1f}" for i in range(nx))
        down = " L ".join(f"{xat(i):.1f} {yat(cum[i]):.1f}" for i in range(nx - 1, -1, -1))
        bands.append((s.get("label", ""), f"M {up} L {down} Z"))
        cum = top
    op = ["0.9", "0.72", "0.56", "0.42", "0.3", "0.22"]
    svg = [f'<svg viewBox="0 0 1920 1080" preserveAspectRatio="none" style="position:absolute;inset:0;'
           f'width:100%;height:100%"><clipPath id="{sid}-clip"><rect id="{sid}-wipe" x="{PX0}" y="0" '
           f'width="0" height="1080"/></clipPath><g clip-path="url(#{sid}-clip)">']
    for bi, (lab, path) in enumerate(bands):
        svg.append(f'<path d="{path}" fill="var(--accent)" fill-opacity="{op[bi % len(op)]}"/>')
    svg.append('</g></svg>')
    frag += svg
    for bi, (lab, _p) in enumerate(bands):                              # legend
        if lab:
            frag.append(f'<div style="position:absolute;left:{PX1+20}px;top:{PY0+bi*34}px;font-size:22px;'
                        f'font-weight:700;opacity:{op[bi%len(op)]}">■ {esc(str(lab))}</div>')
    frag.append('</div>')
    tl = [f'tl.fromTo("#{sid}-wipe",{{attr:{{width:0}}}},{{attr:{{width:{PX1-PX0+4:.0f}}},duration:{round(max(1.4,dur*0.7),2)},ease:"power1.inOut"}},{start+0.2:.2f});']
    return frag, tl


def bar_race(sid, sc):
    """A-P4 — a BAR RACE: horizontal bars for categories that GROW and REORDER across time steps, with a big
    period ticker — the classic 'who's ahead over time'. `series:[{label,values:[v per step]}]` + `steps:[..]`.
    Each bar tweens its width AND its y (rank slot) between consecutive steps; provenance via value_source/dataset."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc = compose.esc
    series = d.get("series") or []
    steps = d.get("steps") or []
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    ns = max((len(s.get("values", [])) for s in series), default=0)
    if not steps:
        steps = [str(i + 1) for i in range(ns)]
    ns = min(ns, len(steps))
    rows = min(len(series), 8)                                          # top-N bars visible
    X0, W, TOP, RH = 360, 1160, 300, 78
    gmax = max((float(v) for s in series for v in s.get("values", [0])[:ns]), default=1.0) or 1.0
    st = round((dur - 0.6) / max(1, ns), 2)                            # seconds per step
    frag = [f'<div id="{sid}-wrap" class="clip" data-start="{start}" data-duration="{dur}" data-track-index="1" '
            f'style="position:absolute;inset:0;color:{ink}">']
    if d.get("title"):
        frag.append(f'<div style="position:absolute;left:{X0}px;top:150px;font-family:var(--font-display);'
                    f'font-weight:800;font-size:44px;color:{ink}">{esc(d["title"])}</div>')
    frag.append(f'<div id="{sid}-period" style="position:absolute;right:200px;bottom:160px;'
                f'font-family:var(--font-display);font-weight:800;font-size:120px;opacity:0.16;color:{ink}">'
                f'{esc(str(steps[0]))}</div>')
    for si, s in enumerate(series):
        frag.append(f'<div id="{sid}-b{si}" style="position:absolute;left:{X0}px;top:{TOP}px;height:{RH-14}px;'
                    f'width:8px;background:var(--accent);border-radius:8px;opacity:0.92;transform-origin:left center">'
                    f'<span style="position:absolute;left:14px;top:50%;transform:translateY(-50%);font-weight:800;'
                    f'font-size:26px;color:var(--accent-ink,{ink});white-space:nowrap">{esc(str(s.get("label","")))}</span>'
                    f'<span id="{sid}-v{si}" style="position:absolute;right:-70px;top:50%;transform:translateY(-50%);'
                    f'font-weight:800;font-size:24px;color:{ink}">0</span></div>')
    frag.append('</div>')
    tl = []
    for k in range(ns):
        t = round(start + 0.3 + k * st, 2)
        ranked = sorted(range(len(series)), key=lambda i: -float(series[i].get("values", [0])[k] if k < len(series[i].get("values", [])) else 0))
        rank = {si: r for r, si in enumerate(ranked)}
        tl.append(f'tl.set("#{sid}-period",{{textContent:{compose.json.dumps(str(steps[k]))}}},{t:.2f});')
        for si, s in enumerate(series):
            v = float(s.get("values", [0])[k]) if k < len(s.get("values", [])) else 0.0
            w = max(8.0, W * (v / gmax))
            y = TOP + rank[si] * RH
            vis = 1 if rank[si] < rows else 0
            tl.append(f'tl.to("#{sid}-b{si}",{{width:{w:.0f},y:{y-TOP:.0f},opacity:{0.92*vis:.2f},duration:{min(1.1,st*0.5):.2f},ease:"power2.inOut"}},{t:.2f});')
            tl.append(f'tl.set("#{sid}-v{si}",{{textContent:{compose.json.dumps(compose._num(v) if isinstance(v,float) else v)}}},{t:.2f});')
    return frag, tl


def split_view(sid, sc):
    """B-P3 — SPLIT SCREEN: one side a document page (cropped to a region so it tracks the narrative), the
    other any content — a video clip, a still, a text block, or a stat. `paper:{source,page_size,focus_rect}`
    (bind via data.document/page/focus, resolved upstream) + `right:{kind:image|video|text|stat, ...}` +
    `split` (left fraction, default 0.5) + `paper_side` (left|right). The two halves slide in from their edges."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc = compose.esc
    paper = d.get("paper") or {}
    right = d.get("right") or {}
    W, H = 1920, 1080
    ps = min(0.75, max(0.25, float(d.get("split", 0.5))))
    paper_left = str(d.get("paper_side", "left")) == "left"
    pw = int(W * ps)
    px, cx, cw = (0, pw, W - pw) if paper_left else (W - pw, 0, W - pw)
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"

    # FIT the paper (or its focus region) into a box that PRESERVES ITS ASPECT RATIO — never stretch it to
    # fill the panel. Centre the box in the panel with a margin (a sheet on a ground), so it keeps its shape.
    fr = paper.get("focus_rect")
    psz = paper.get("page_size") or [1000.0, 1294.0]
    pageW, pageH = (float(psz[0]) or 1.0), (float(psz[1]) or 1.0)
    if fr:
        fx0, fy0, fw, fh = [float(v) for v in fr]
        reg_asp = (fw * pageW) / max(1e-6, fh * pageH)
    else:
        fx0, fy0, fw, fh = 0.0, 0.0, 1.0, 1.0
        reg_asp = pageW / max(1e-6, pageH)
    marg = 0.9
    aw, ah = pw * marg, H * marg
    bw, bh = (ah * reg_asp, ah) if (aw / ah > reg_asp) else (aw, aw / reg_asp)
    bx, by = px + (pw - bw) / 2, (H - bh) / 2
    bgw, bgh = bw / max(1e-6, fw), bh / max(1e-6, fh)      # box aspect == region aspect ⇒ page scales uniformly
    frag = [f'<div id="{sid}-paper" class="clip" data-start="{start}" data-duration="{dur}" data-track-index="1" '
            f'style="position:absolute;left:{bx:.0f}px;top:{by:.0f}px;width:{bw:.0f}px;height:{bh:.0f}px;background-color:#fff;'
            f'background-image:url(\'{esc(paper.get("source",""))}\');background-repeat:no-repeat;'
            f'background-size:{bgw:.0f}px {bgh:.0f}px;background-position:-{fx0*bgw:.0f}px -{fy0*bgh:.0f}px;'
            f'border-radius:8px;box-shadow:0 14px 44px rgba(0,0,0,.30);opacity:0;"></div>']
    # content panel
    kind = str(right.get("kind", "text"))
    inner = ""
    if kind in ("image", "video"):
        src = esc(right.get("src", ""))
        inner = (f'<video src="{src}" muted playsinline autoplay loop style="width:100%;height:100%;object-fit:cover"></video>'
                 if kind == "video" else
                 f'<img src="{src}" alt="" style="width:100%;height:100%;object-fit:cover">')
        cbg = "#000"
    else:
        cbg = ("#17130f" if dark else "#f4eee2")
        if kind == "stat":
            inner = (f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%">'
                     f'<div style="font-family:var(--font-display);font-weight:800;font-size:9cqw;color:var(--accent)">{esc(str(right.get("value","")))}</div>'
                     f'<div style="font-size:1.8cqw;font-weight:700;color:{ink};margin-top:1cqw">{esc(str(right.get("label","")))}</div></div>')
        else:   # text
            lines = right.get("lines") or ([right.get("text")] if right.get("text") else [])
            ttl = f'<div style="font-family:var(--font-display);font-weight:800;font-size:3.2cqw;color:{ink};margin-bottom:1.4cqw">{esc(str(right.get("title","")))}</div>' if right.get("title") else ""
            body = "".join(f'<div style="font-size:2cqw;line-height:1.35;color:{ink};margin:0.5cqw 0">{esc(str(x))}</div>' for x in lines)
            inner = (f'<div style="display:flex;flex-direction:column;justify-content:center;height:100%;padding:0 5cqw;'
                     f'container-type:size">{ttl}{body}</div>')
    frag.append(f'<div id="{sid}-content" class="clip" data-start="{start}" data-duration="{dur}" data-track-index="2" '
                f'style="position:absolute;left:{cx}px;top:0;width:{cw}px;height:{H}px;background:{cbg};'
                f'container-type:size;overflow:hidden;opacity:0;">{inner}</div>')
    frag.append(f'<div id="{sid}-div" class="clip" data-start="{start}" data-duration="{dur}" data-track-index="3" '
                f'style="position:absolute;left:{(px+pw) if paper_left else cx+cw}px;top:0;width:4px;height:{H}px;'
                f'background:var(--accent);opacity:0;"></div>')
    tl = [f'tl.fromTo("#{sid}-paper",{{opacity:0,x:{-60 if paper_left else 60}}},{{opacity:1,x:0,duration:0.6,ease:"power3.out"}},{start+0.2:.2f});',
          f'tl.fromTo("#{sid}-content",{{opacity:0,x:{60 if paper_left else -60}}},{{opacity:1,x:0,duration:0.6,ease:"power3.out"}},{start+0.35:.2f});',
          f'tl.to("#{sid}-div",{{opacity:0.9,duration:0.4}},{start+0.5:.2f});']
    return frag, tl


def _dataviz_head(sid, sc, ink):
    """Shared kicker+title fragment/timeline for a data-viz block (matches the chart block's head)."""
    d, start = sc["data"], sc["start"]
    esc = compose.esc
    frag, tl = [], []
    if d.get("kicker"):
        frag.append(f'<div id="{sid}-k" style="position:absolute;left:300px;top:96px;font-family:var(--font-mono,monospace);'
                    f'font-size:20px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);opacity:0">{esc(d["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.1:.2f});')
    if d.get("title"):
        t, op = d["title"], d.get("titleHi", "")
        html_t = (f'{esc(t.split(op,1)[0])}<span style="color:var(--accent)">{esc(op)}</span>{esc(t.split(op,1)[1])}'
                  if op and op in t else esc(t))
        frag.append(f'<div id="{sid}-t" style="position:absolute;left:300px;top:128px;font-family:var(--font-display);'
                    f'font-weight:800;font-size:46px;letter-spacing:-.01em;color:{ink};opacity:0">{html_t}</div>')
        tl.append(f'tl.fromTo("#{sid}-t",{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{start+0.2:.2f});')
    return frag, tl


def slope(sid, sc):
    """A SLOPE chart — each series is a line from its START value (left axis) to its END value (right axis).
    Rank REVERSALS / crossings are the reveal: who overtook whom between two moments (2016 vs 2024, before
    vs after). The classic two-point form. Lines DRAW left→right, staggered; the emphasised series is the
    accent, the rest recede. Bind a dataset (encode {label, start, end}).
    data: {series:[{label, start, end}], cols?:[leftLabel, rightLabel], prefix?, suffix?,
           highlight?(int index → accent, others muted), kicker?, title?, titleHi?, ground?}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc, num = compose.esc, compose._num
    series = d.get("series") or []
    n = len(series)
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    muted = "rgba(243,239,230,0.40)" if dark else "rgba(28,28,25,0.34)"
    pre, suf = d.get("prefix", ""), d.get("suffix", "")
    cols = (d.get("cols") or ["", ""])[:2] + [""] * (2 - len(d.get("cols") or []))
    hl = d.get("highlight")
    hl = int(hl) if isinstance(hl, (int, float)) and 0 <= int(hl) < n else None
    starts = [float(s.get("start", 0)) for s in series] or [0.0]
    ends = [float(s.get("end", 0)) for s in series] or [0.0]
    allv = starts + ends
    vlo, vhi = min(allv), max(allv)
    span = (vhi - vlo) or 1.0
    LX, RX, TY, BY = 640, 1280, 250, 900                 # left axis x, right axis x, top y, bottom y
    yof = lambda v: BY - (v - vlo) / span * (BY - TY)
    frag = [f'<div id="{sid}-wrap" class="clip blk-slope" data-start="{start}" data-duration="{dur}" '
            f'data-track-index="1" style="position:absolute;inset:0;color:{ink};background:{esc(compose._page_bg())}">']
    hf, ht = _dataviz_head(sid, sc, ink)
    frag += hf
    # column headers + the two vertical axes
    for cx, cl, al in ((LX, cols[0], "right"), (RX, cols[1], "left")):
        if cl:
            off = -420 if al == "right" else 20
            frag.append(f'<div style="position:absolute;left:{cx+off:.0f}px;top:{TY-64:.0f}px;width:400px;'
                        f'text-align:{al};font-weight:700;font-size:24px;color:{muted}">{esc(cl)}</div>')
        frag.append(f'<div style="position:absolute;left:{cx:.0f}px;top:{TY}px;width:2px;height:{BY-TY}px;background:{muted}"></div>')
    times = compose._reveal_times(n, start, dur, compose._reveal_cues(series, start)) if n else []
    # the slope lines (SVG, drawn)
    svg = ['<svg viewBox="0 0 1920 1080" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%">']
    for i in range(n):
        y0, y1 = yof(starts[i]), yof(ends[i])
        on = hl is None or i == hl
        col = "var(--accent)" if on else muted
        sw = 6 if (hl is not None and i == hl) else 3
        svg.append(f'<path id="{sid}-ln{i}" d="M {LX} {y0:.1f} L {RX} {y1:.1f}" fill="none" stroke="{col}" '
                   f'stroke-width="{sw}" stroke-linecap="round"/>')
    svg.append('</svg>')
    frag += svg
    # end dots + name/value labels (left: right-aligned before LX; right: left-aligned after RX)
    for i, s in enumerate(series):
        y0, y1 = yof(starts[i]), yof(ends[i])
        on = hl is None or i == hl
        col = "var(--accent)" if on else muted
        lc = ink if on else muted
        lab = esc(str(s.get("label", "")))
        frag.append(f'<div id="{sid}-ld{i}" style="position:absolute;left:{LX-8:.0f}px;top:{y0-8:.0f}px;width:16px;'
                    f'height:16px;border-radius:50%;background:{col};opacity:0"></div>')
        frag.append(f'<div id="{sid}-ll{i}" style="position:absolute;left:{LX-440:.0f}px;top:{y0-19:.0f}px;width:400px;'
                    f'text-align:right;font-size:26px;font-weight:{800 if on else 600};color:{lc};opacity:0">'
                    f'{lab} <span style="opacity:.62">{esc(pre)}{num(starts[i])}{esc(suf)}</span></div>')
        frag.append(f'<div id="{sid}-rd{i}" style="position:absolute;left:{RX-8:.0f}px;top:{y1-8:.0f}px;width:16px;'
                    f'height:16px;border-radius:50%;background:{col};opacity:0"></div>')
        frag.append(f'<div id="{sid}-rl{i}" style="position:absolute;left:{RX+24:.0f}px;top:{y1-19:.0f}px;width:400px;'
                    f'text-align:left;font-size:26px;font-weight:{800 if on else 600};color:{lc};opacity:0">'
                    f'<span style="opacity:.62">{esc(pre)}{num(ends[i])}{esc(suf)}</span> {lab}</div>')
    frag.append('</div>')
    tl = list(ht)
    for i in range(n):
        t = times[i]
        tl.append(f'(function(){{var p=document.getElementById("{sid}-ln{i}"),L=p.getTotalLength();'
                  f'p.style.strokeDasharray=L;p.style.strokeDashoffset=L;'
                  f'tl.fromTo(p,{{strokeDashoffset:L}},{{strokeDashoffset:0,duration:0.7,ease:"power1.inOut"}},{t:.2f});}})();')
        tl.append(f'tl.fromTo("#{sid}-ld{i}",{{scale:0}},{{scale:1,opacity:1,duration:0.3,ease:"back.out(2)"}},{t:.2f});')
        tl.append(f'tl.to("#{sid}-ll{i}",{{opacity:1,duration:0.3}},{t+0.05:.2f});')
        tl.append(f'tl.fromTo("#{sid}-rd{i}",{{scale:0}},{{scale:1,opacity:1,duration:0.3,ease:"back.out(2)"}},{t+0.55:.2f});')
        tl.append(f'tl.to("#{sid}-rl{i}",{{opacity:1,duration:0.3}},{t+0.6:.2f});')
    return frag, tl


def isotype(sid, sc):
    """A PICTOGRAM / UNIT chart — a quantity drawn as a grid of unit icons (each icon = N units), so a big
    number becomes TANGIBLE and a comparison is countable. Icons fill in, staggered (the count-up). The
    Isotype/Neurath tradition. data: {items:[{label, value}], per?(units per icon; auto if omitted),
    unit?(what one icon represents), icon?("square"|"circle"), prefix?, suffix?, kicker?, title?, titleHi?,
    ground?}. Bind a dataset (encode {value, label})."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc, num = compose.esc, compose._num
    items = d.get("items") or []
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    pre, suf, unit = d.get("prefix", ""), d.get("suffix", ""), d.get("unit", "")
    vals = [float(it.get("value", 0)) for it in items] or [0.0]
    vmax = max(vals) or 1.0
    per = float(d.get("per") or max(1.0, round(vmax / 44.0)))
    br = {"square": "5px", "circle": "50%", "dot": "50%"}.get(d.get("icon", "square"), "5px")
    ISZ, GAP, PERROW, X0 = 26, 8, 40, 300
    frag = [f'<div id="{sid}-wrap" class="clip blk-isotype" data-start="{start}" data-duration="{dur}" '
            f'data-track-index="1" style="position:absolute;inset:0;color:{ink};background:{esc(compose._page_bg())}">']
    hf, ht = _dataviz_head(sid, sc, ink)
    frag += hf
    if unit or per != 1:
        frag.append(f'<div style="position:absolute;left:{X0}px;top:196px;font-size:22px;opacity:0.72">each '
                    f'<span style="display:inline-block;width:18px;height:18px;background:var(--accent);'
                    f'border-radius:{br};vertical-align:-3px"></span> = {num(per)}{esc((" " + unit) if unit else "")}</div>')
    y = 250
    plan = []                                            # (item_index, n_icons, grid_y)
    for i, it in enumerate(items):
        v = float(it.get("value", 0))
        nic = min(max(0, round(v / per)), PERROW * 4)    # cap at 4 rows/item
        lab = esc(str(it.get("label", "")))
        frag.append(f'<div style="position:absolute;left:{X0}px;top:{y}px;font-size:24px;font-weight:700">'
                    f'{lab} <span style="opacity:.6">{esc(pre)}{num(v)}{esc(suf)}</span></div>')
        gy = y + 40
        for k in range(nic):
            ix = X0 + (k % PERROW) * (ISZ + GAP)
            iy = gy + (k // PERROW) * (ISZ + GAP)
            frag.append(f'<div id="{sid}-i{i}-{k}" style="position:absolute;left:{ix}px;top:{iy}px;'
                        f'width:{ISZ}px;height:{ISZ}px;background:var(--accent);border-radius:{br};opacity:0"></div>')
        nlines = max(1, (nic + PERROW - 1) // PERROW)
        y = gy + nlines * (ISZ + GAP) + 34
        plan.append((i, nic))
    frag.append('</div>')
    tl = list(ht)
    total = sum(p[1] for p in plan) or 1
    win0, win, done = start + 0.6, max(0.5, dur - 1.2), 0
    for i, nic in plan:
        for k in range(nic):
            cue = win0 + win * (done / total)
            done += 1
            tl.append(f'tl.to("#{sid}-i{i}-{k}",{{opacity:1,duration:0.22,ease:"power1.out"}},{cue:.2f});')
    return frag, tl


def dumbbell(sid, sc):
    """A DUMBBELL / dot-plot — two values per category joined by a bar; the GAP between them is the point
    (rich vs poor, promise vs reality, before vs after, men vs women). Horizontal rows, each with a start
    dot and an end dot; the connecting bar GROWS from start→end (the gap opening). Bind a dataset
    (encode {label, start, end}). data: {items:[{label, start, end}], cols?:[startLabel, endLabel],
    prefix?, suffix?, sort?(bool: by gap), kicker?, title?, titleHi?, ground?}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc, num = compose.esc, compose._num
    items = list(d.get("items") or [])
    if d.get("sort"):
        items.sort(key=lambda it: abs(float(it.get("end", 0)) - float(it.get("start", 0))), reverse=True)
    n = len(items)
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    muted = "rgba(243,239,230,0.5)" if dark else "rgba(28,28,25,0.42)"
    pre, suf = d.get("prefix", ""), d.get("suffix", "")
    cols = (d.get("cols") or ["", ""])[:2] + [""] * (2 - len(d.get("cols") or []))
    starts = [float(it.get("start", 0)) for it in items] or [0.0]
    ends = [float(it.get("end", 0)) for it in items] or [0.0]
    allv = starts + ends
    vlo, vhi = min(allv), max(allv)
    span = (vhi - vlo) or 1.0
    X0, X1, TY, ROWH = 620, 1620, 300, 0
    xof = lambda v: X0 + (v - vlo) / span * (X1 - X0)
    rowh = min(120, max(56, int((900 - TY) / max(1, n))))
    frag = [f'<div id="{sid}-wrap" class="clip blk-dumbbell" data-start="{start}" data-duration="{dur}" '
            f'data-track-index="1" style="position:absolute;inset:0;color:{ink};background:{esc(compose._page_bg())}">']
    hf, ht = _dataviz_head(sid, sc, ink)
    frag += hf
    if cols[0] or cols[1]:                                   # a color LEGEND (dots are placed by value, so a
        dot = 'display:inline-block;width:16px;height:16px;border-radius:50%;vertical-align:-2px'
        frag.append(f'<div style="position:absolute;left:300px;top:200px;font-size:21px;color:{ink}">'  # positional header would mislabel)
                    f'<span style="{dot};background:{muted}"></span> {esc(cols[0])}'
                    f'<span style="display:inline-block;width:34px"></span>'
                    f'<span style="{dot};background:var(--accent)"></span> {esc(cols[1])}</div>')
    times = compose._reveal_times(n, start, dur, compose._reveal_cues(items, start)) if n else []
    for i, it in enumerate(items):
        y = TY + i * rowh
        xs, xe = xof(starts[i]), xof(ends[i])
        lo, hi = min(xs, xe), max(xs, xe)
        lab = esc(str(it.get("label", "")))
        frag.append(f'<div style="position:absolute;left:{X0-440:.0f}px;top:{y-17:.0f}px;width:410px;'
                    f'text-align:right;font-size:25px;font-weight:700;color:{ink}">{lab}</div>')
        # connecting bar (grows from the start dot toward the end dot)
        frag.append(f'<div id="{sid}-bar{i}" style="position:absolute;left:{lo:.0f}px;top:{y-4:.0f}px;'
                    f'width:{hi-lo:.0f}px;height:8px;border-radius:4px;background:var(--accent);'
                    f'transform-origin:{"left" if xe>=xs else "right"} center;opacity:0.9"></div>')
        # start dot (muted) + end dot (accent)
        frag.append(f'<div id="{sid}-s{i}" style="position:absolute;left:{xs-11:.0f}px;top:{y-11:.0f}px;width:22px;'
                    f'height:22px;border-radius:50%;background:{muted};opacity:0"></div>')
        frag.append(f'<div id="{sid}-e{i}" style="position:absolute;left:{xe-13:.0f}px;top:{y-13:.0f}px;width:26px;'
                    f'height:26px;border-radius:50%;background:var(--accent);opacity:0"></div>')
        frag.append(f'<div id="{sid}-sv{i}" style="position:absolute;left:{xs-70:.0f}px;top:{y-52:.0f}px;width:140px;'
                    f'text-align:center;font-size:21px;color:{muted};opacity:0">{esc(pre)}{num(starts[i])}{esc(suf)}</div>')
        frag.append(f'<div id="{sid}-ev{i}" style="position:absolute;left:{xe-70:.0f}px;top:{y+16:.0f}px;width:140px;'
                    f'text-align:center;font-size:23px;font-weight:800;color:var(--accent);opacity:0">{esc(pre)}{num(ends[i])}{esc(suf)}</div>')
    frag.append('</div>')
    tl = list(ht)
    for i in range(n):
        t = times[i]
        tl.append(f'tl.fromTo("#{sid}-s{i}",{{scale:0}},{{scale:1,opacity:1,duration:0.3,ease:"back.out(2)"}},{t:.2f});')
        tl.append(f'tl.to("#{sid}-sv{i}",{{opacity:1,duration:0.25}},{t+0.05:.2f});')
        tl.append(f'tl.fromTo("#{sid}-bar{i}",{{scaleX:0}},{{scaleX:1,duration:0.5,ease:"power2.out"}},{t+0.2:.2f});')
        tl.append(f'tl.fromTo("#{sid}-e{i}",{{scale:0}},{{scale:1,opacity:1,duration:0.35,ease:"back.out(2.4)"}},{t+0.55:.2f});')
        tl.append(f'tl.to("#{sid}-ev{i}",{{opacity:1,duration:0.25}},{t+0.6:.2f});')
    return frag, tl


def small_multiples(sid, sc):
    """SMALL MULTIPLES — a grid of tiny same-scale mini bar charts, one per panel, so the eye compares the
    SHAPE across many categories at once ("the same pattern everywhere / everywhere but here"). All panels
    share ONE y-scale (the whole point). Panels reveal staggered; bars grow. Bind a dataset (encode
    {panel, x, y} — the resolver groups rows into panels). data: {panels:[{label, series:[{label,value}]}],
    prefix?, suffix?, kicker?, title?, titleHi?, ground?}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc, num = compose.esc, compose._num
    panels = d.get("panels") or []
    n = len(panels)
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    rule = "rgba(243,239,230,0.22)" if dark else "rgba(28,28,25,0.16)"
    pre, suf = d.get("prefix", ""), d.get("suffix", "")
    allvals = [float(pt.get("value", 0)) for p in panels for pt in (p.get("series") or [])] or [0.0]
    ymax = max(allvals) * 1.1 or 1.0
    cols = min(3, max(1, n))
    rowsn = (n + cols - 1) // cols
    AX0, AY0, AW, AH = 300, 268, 1320, 620
    cw, ch = AW / cols, AH / max(1, rowsn)
    frag = [f'<div id="{sid}-wrap" class="clip blk-small_multiples" data-start="{start}" data-duration="{dur}" '
            f'data-track-index="1" style="position:absolute;inset:0;color:{ink};background:{esc(compose._page_bg())}">']
    hf, ht = _dataviz_head(sid, sc, ink)
    frag += hf
    times = compose._reveal_times(n, start, dur, [None] * n) if n else []
    tl = list(ht)
    for pi, p in enumerate(panels):
        cx = AX0 + (pi % cols) * cw
        cy = AY0 + (pi // cols) * ch
        pad, titleh = 26, 46
        chx, chy = cx + pad, cy + titleh
        chw, chh = cw - pad * 2, ch - titleh - 30
        pid = f"{sid}-p{pi}"
        frag.append(f'<div id="{pid}" style="position:absolute;left:{cx:.0f}px;top:{cy:.0f}px;width:{cw:.0f}px;'
                    f'height:{ch:.0f}px;opacity:0">')
        frag.append(f'<div style="position:absolute;left:{pad}px;top:8px;font-size:23px;font-weight:800;'
                    f'color:{ink}">{esc(str(p.get("label", "")))}</div>')
        frag.append(f'<div style="position:absolute;left:{pad}px;top:{titleh+chh:.0f}px;width:{chw:.0f}px;'
                    f'height:2px;background:{rule}"></div>')                       # baseline
        series = p.get("series") or []
        m = max(1, len(series))
        bw = chw / m * 0.66
        for bi, pt in enumerate(series):
            v = float(pt.get("value", 0))
            bh = max(2.0, v / ymax * chh)
            bx = pad + bi * (chw / m) + (chw / m - bw) / 2
            by = titleh + chh - bh
            frag.append(f'<div id="{pid}-b{bi}" style="position:absolute;left:{bx:.0f}px;top:{by:.0f}px;'
                        f'width:{bw:.0f}px;height:{bh:.0f}px;background:var(--accent);transform-origin:bottom center;'
                        f'transform:scaleY(0)"></div>')
            frag.append(f'<div style="position:absolute;left:{bx-(chw/m-bw)/2:.0f}px;top:{titleh+chh+6:.0f}px;'
                        f'width:{chw/m:.0f}px;text-align:center;font-size:15px;color:{ink};opacity:.55">'
                        f'{esc(str(pt.get("label", "")))}</div>')
        frag.append('</div>')
        t = times[pi]
        tl.append(f'tl.to("#{pid}",{{opacity:1,duration:0.35}},{t:.2f});')
        for bi in range(len(series)):
            tl.append(f'tl.fromTo("#{pid}-b{bi}",{{scaleY:0}},{{scaleY:1,duration:0.5,ease:"power2.out"}},{t+0.1+bi*0.04:.2f});')
    frag.append('</div>')
    return frag, tl


def histogram(sid, sc):
    """A HISTOGRAM / distribution — the SHAPE of a spread (bars touching, no gaps), with an optional
    `marker` value ("where you fall / where the average sits"). Bars rise left→right (the distribution
    builds), then the marker drops in. Bind a dataset (encode {value} — the resolver bins the raw column).
    data: {bins:[{x0, x1, count}] | [{label, count}], marker?(a value on the axis), marker_label?,
    unit?, prefix?, suffix?, kicker?, title?, titleHi?, ground?}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc, num = compose.esc, compose._num
    bins = d.get("bins") or []
    n = len(bins)
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    rule = "rgba(243,239,230,0.30)" if dark else "rgba(28,28,25,0.22)"
    pre, suf, unit = d.get("prefix", ""), d.get("suffix", ""), d.get("unit", "")
    counts = [float(b.get("count", 0)) for b in bins] or [0.0]
    cmax = max(counts) * 1.12 or 1.0
    edges = [b.get("x0") for b in bins if b.get("x0") is not None]
    x0v = bins[0].get("x0") if bins and bins[0].get("x0") is not None else 0
    x1v = bins[-1].get("x1") if bins and bins[-1].get("x1") is not None else n
    dom = (x1v - x0v) or 1
    PX0, PX1, PY0, PY1 = 320, 1600, 300, 860
    pw = PX1 - PX0
    frag = [f'<div id="{sid}-wrap" class="clip blk-histogram" data-start="{start}" data-duration="{dur}" '
            f'data-track-index="1" style="position:absolute;inset:0;color:{ink};background:{esc(compose._page_bg())}">']
    hf, ht = _dataviz_head(sid, sc, ink)
    frag += hf
    frag.append(f'<div style="position:absolute;left:{PX0}px;top:{PY1}px;width:{pw}px;height:2px;background:{rule}"></div>')
    bw = pw / max(1, n)
    for i, b in enumerate(bins):
        c = float(b.get("count", 0))
        bh = max(2.0, c / cmax * (PY1 - PY0))
        bx = PX0 + i * bw
        frag.append(f'<div id="{sid}-b{i}" style="position:absolute;left:{bx+1:.0f}px;top:{PY1-bh:.0f}px;'
                    f'width:{bw-2:.0f}px;height:{bh:.0f}px;background:var(--accent);transform-origin:bottom center;'
                    f'transform:scaleY(0)"></div>')
    # x-axis endpoints + midpoint labels
    for frac, val in ((0.0, x0v), (0.5, (x0v + x1v) / 2), (1.0, x1v)):
        lx = PX0 + frac * pw
        frag.append(f'<div style="position:absolute;left:{lx-80:.0f}px;top:{PY1+12:.0f}px;width:160px;'
                    f'text-align:center;font-size:20px;color:{ink};opacity:.6">{esc(pre)}{num(val)}{esc(suf)}</div>')
    if unit:
        frag.append(f'<div style="position:absolute;left:{PX1-260:.0f}px;top:{PY1+48:.0f}px;font-size:20px;'
                    f'opacity:.5">{esc(unit)} →</div>')
    tl = list(ht)
    times = compose._reveal_times(n, start, dur, [None] * n) if n else []
    for i in range(n):
        tl.append(f'tl.fromTo("#{sid}-b{i}",{{scaleY:0}},{{scaleY:1,duration:0.4,ease:"power2.out"}},{times[i]:.2f});')
    # optional marker ("where you fall") — a vertical line + label that drops in after the bars
    mk = d.get("marker")
    if mk is not None:
        mx = PX0 + max(0.0, min(1.0, (float(mk) - x0v) / dom)) * pw
        mt = round((times[-1] if n else start) + 0.4, 2)
        frag.append(f'<div id="{sid}-mk" style="position:absolute;left:{mx:.0f}px;top:{PY0-30:.0f}px;width:3px;'
                    f'height:{PY1-PY0+30:.0f}px;background:{ink};opacity:0"></div>')
        frag.append(f'<div id="{sid}-mkl" style="position:absolute;left:{mx-140:.0f}px;top:{PY0-64:.0f}px;width:280px;'
                    f'text-align:center;font-size:23px;font-weight:800;color:{ink};opacity:0">'
                    f'{esc(d.get("marker_label") or (str(pre)+num(float(mk))+str(suf)))}</div>')
        tl.append(f'tl.fromTo("#{sid}-mk",{{scaleY:0,transformOrigin:"top center"}},{{scaleY:1,opacity:1,duration:0.4,ease:"power3.out"}},{mt});')
        tl.append(f'tl.fromTo("#{sid}-mkl",{{opacity:0,y:-8}},{{opacity:1,y:0,duration:0.35}},{mt+0.1:.2f});')
    frag.append('</div>')
    return frag, tl


def gauge(sid, sc):
    """A GAUGE / progress ring — one (or a few) value(s) against a max, drawn as a SWEEPING radial arc with
    the number in the centre + an optional target tick. 'We're 73% of the way / used 40 of 50 / the clock at
    90 seconds'. Bind a dataset (encode {value, label}). data: {items:[{value, label}] | value+label,
    max?(default 100), target?, unit?, prefix?, suffix?, kicker?, title?, titleHi?, ground?}."""
    import math
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc, num = compose.esc, compose._num
    items = d.get("items") or ([{"value": d.get("value", 0), "label": d.get("label", "")}]
                               if d.get("value") is not None else [])
    n = max(1, len(items))
    mx = float(d.get("max", 100) or 100)
    tgt = d.get("target")
    pre, suf = d.get("prefix", ""), d.get("suffix", "")
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    track = "rgba(243,239,230,0.16)" if dark else "rgba(28,28,25,0.12)"
    R = 168 if n == 1 else (132 if n == 2 else 106)
    SW = 26 if n == 1 else (20 if n == 2 else 16)
    C = 2 * math.pi * R
    cy = 580
    xs = [960] if n == 1 else [960 - 620 + i * (1240 / (n - 1)) for i in range(n)]
    frag = [f'<div id="{sid}-wrap" class="clip blk-gauge" data-start="{start}" data-duration="{dur}" '
            f'data-track-index="1" style="position:absolute;inset:0;color:{ink};background:{esc(compose._page_bg())}">']
    hf, ht = _dataviz_head(sid, sc, ink)
    frag += hf
    svg = ['<svg viewBox="0 0 1920 1080" style="position:absolute;inset:0;width:100%;height:100%">']
    tl = list(ht)
    for i, it in enumerate(items):
        v = float(it.get("value", 0))
        fill = max(0.0, min(1.0, v / mx))
        cx = xs[i]
        svg.append(f'<circle cx="{cx:.0f}" cy="{cy}" r="{R}" fill="none" stroke="{track}" stroke-width="{SW}"/>')
        svg.append(f'<circle id="{sid}-arc{i}" cx="{cx:.0f}" cy="{cy}" r="{R}" fill="none" stroke="var(--accent)" '
                   f'stroke-width="{SW}" stroke-linecap="round" transform="rotate(-90 {cx:.0f} {cy})" '
                   f'style="stroke-dasharray:{C:.1f};stroke-dashoffset:{C:.1f}"/>')
        if tgt is not None:
            ang = -math.pi / 2 + (float(tgt) / mx) * 2 * math.pi
            tx, ty = cx + R * math.cos(ang), cy + R * math.sin(ang)
            svg.append(f'<circle cx="{tx:.0f}" cy="{ty:.0f}" r="{SW*0.42:.0f}" fill="{ink}"/>')
        frag.append(f'<div id="{sid}-v{i}" style="position:absolute;left:{cx-180:.0f}px;top:{cy-46:.0f}px;width:360px;'
                    f'text-align:center;font-family:var(--font-display);font-weight:800;font-size:{72 if n<=2 else 52}px;'
                    f'color:{ink};opacity:0">{esc(pre)}{num(v)}{esc(suf)}</div>')
        frag.append(f'<div style="position:absolute;left:{cx-200:.0f}px;top:{cy+R+18:.0f}px;width:400px;'
                    f'text-align:center;font-size:26px;font-weight:700;color:{ink};opacity:.72">{esc(str(it.get("label","")))}</div>')
        off = C * (1 - fill)
        t = start + 0.4 + i * 0.25
        tl.append(f'tl.fromTo("#{sid}-arc{i}",{{strokeDashoffset:{C:.1f}}},{{strokeDashoffset:{off:.1f},'
                  f'duration:1.1,ease:"power2.out"}},{t:.2f});')
        tl.append(f'tl.to("#{sid}-v{i}",{{opacity:1,duration:0.4}},{t+0.2:.2f});')
    svg.append('</svg>')
    frag += svg
    frag.append('</div>')
    return frag, tl


def process(sid, sc):
    """A PROCESS FLOW — linear STEPS connected by arrows, revealed in order (step 1 → 2 → 3): an OPEN chain
    (a pipeline / how-it-works), distinct from cycle (a closed loop), diagram (a tree) or sankey (magnitude).
    Bind a dataset (encode {label, sub?}). data: {steps:[{label, sub?}], direction?(horizontal|vertical),
    kicker?, title?, titleHi?, ground?}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc = compose.esc
    steps = d.get("steps") or []
    n = len(steps)
    horizontal = str(d.get("direction", "horizontal")) != "vertical"
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    card = "rgba(243,239,230,0.07)" if dark else "rgba(28,28,25,0.05)"
    frag = [f'<div id="{sid}-wrap" class="clip blk-process" data-start="{start}" data-duration="{dur}" '
            f'data-track-index="1" style="position:absolute;inset:0;color:{ink};background:{esc(compose._page_bg())}">']
    hf, ht = _dataviz_head(sid, sc, ink)
    frag += hf
    times = compose._reveal_times(n, start, dur, [None] * n) if n else []
    tl = list(ht)
    if horizontal:
        AX0, AX1, cy = 200, 1720, 560
        gap = (AX1 - AX0) / max(1, n)
        bw = min(300, gap * 0.72)
        bh = 150
        for i, s in enumerate(steps):
            cx = AX0 + gap * (i + 0.5)
            bx = cx - bw / 2
            nid = f"{sid}-n{i}"
            frag.append(f'<div id="{nid}" style="position:absolute;left:{bx:.0f}px;top:{cy-bh/2:.0f}px;width:{bw:.0f}px;'
                        f'height:{bh}px;background:{card};border:2px solid var(--accent);border-radius:14px;'
                        f'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;opacity:0">'
                        f'<div style="position:absolute;left:-16px;top:-16px;width:44px;height:44px;border-radius:50%;'
                        f'background:var(--accent);color:var(--surface,#fff);font-weight:800;font-size:22px;'
                        f'display:flex;align-items:center;justify-content:center">{i+1}</div>'
                        f'<div style="font-size:27px;font-weight:800;text-align:center;padding:0 14px">{esc(str(s.get("label","")))}</div>'
                        + (f'<div style="font-size:19px;opacity:.62;text-align:center;padding:0 14px">{esc(str(s.get("sub","")))}</div>' if s.get("sub") else "")
                        + '</div>')
            if i < n - 1:
                ax = cx + bw / 2
                aw = gap - bw
                frag.append(f'<div id="{sid}-a{i}" style="position:absolute;left:{ax:.0f}px;top:{cy-3:.0f}px;'
                            f'width:{aw:.0f}px;height:6px;background:var(--accent);transform-origin:left center;'
                            f'transform:scaleX(0)"></div>')
                frag.append(f'<div id="{sid}-ah{i}" style="position:absolute;left:{ax+aw-6:.0f}px;top:{cy-13:.0f}px;'
                            f'width:0;height:0;border-left:16px solid var(--accent);border-top:10px solid transparent;'
                            f'border-bottom:10px solid transparent;opacity:0"></div>')
            t = times[i]
            tl.append(f'tl.fromTo("#{nid}",{{opacity:0,y:18}},{{opacity:1,y:0,duration:0.45,ease:"back.out(1.6)"}},{t:.2f});')
            if i < n - 1:
                tl.append(f'tl.fromTo("#{sid}-a{i}",{{scaleX:0}},{{scaleX:1,duration:0.3,ease:"power2.out"}},{t+0.35:.2f});')
                tl.append(f'tl.to("#{sid}-ah{i}",{{opacity:1,duration:0.15}},{t+0.6:.2f});')
    else:
        AY0, cx = 250, 560
        rh = min(150, (860 - AY0) / max(1, n))
        bw, bh = 620, min(112, rh - 34)
        for i, s in enumerate(steps):
            cy = AY0 + rh * i
            nid = f"{sid}-n{i}"
            frag.append(f'<div id="{nid}" style="position:absolute;left:{cx:.0f}px;top:{cy:.0f}px;width:{bw}px;'
                        f'height:{bh:.0f}px;background:{card};border:2px solid var(--accent);border-radius:14px;'
                        f'display:flex;align-items:center;gap:18px;padding:0 22px;opacity:0">'
                        f'<div style="width:44px;height:44px;flex:none;border-radius:50%;background:var(--accent);'
                        f'color:var(--surface,#fff);font-weight:800;font-size:22px;display:flex;align-items:center;justify-content:center">{i+1}</div>'
                        f'<div><div style="font-size:27px;font-weight:800">{esc(str(s.get("label","")))}</div>'
                        + (f'<div style="font-size:19px;opacity:.62">{esc(str(s.get("sub","")))}</div>' if s.get("sub") else "")
                        + '</div></div>')
            if i < n - 1:
                frag.append(f'<div id="{sid}-a{i}" style="position:absolute;left:{cx+30:.0f}px;top:{cy+bh:.0f}px;'
                            f'width:4px;height:{rh-bh:.0f}px;background:var(--accent);transform-origin:top center;'
                            f'transform:scaleY(0)"></div>')
            t = times[i]
            tl.append(f'tl.fromTo("#{nid}",{{opacity:0,x:-18}},{{opacity:1,x:0,duration:0.45,ease:"back.out(1.6)"}},{t:.2f});')
            if i < n - 1:
                tl.append(f'tl.fromTo("#{sid}-a{i}",{{scaleY:0}},{{scaleY:1,duration:0.25,ease:"power2.out"}},{t+0.35:.2f});')
    frag.append('</div>')
    return frag, tl


_LAYOUT_CELL_KINDS = ("media", "text", "stat", "chart")
_LAYOUT_ARRANGES = ("split", "triptych", "hero-rail", "grid", "stack")


def _layout_boxes(arrange, n, direction, ratio):
    """The bounding box (x,y,w,h px) per slot for a curated arrangement — the runtime of the composition
    archetypes. Content area sits below the title band. Boxes are the ONLY geometry a cell sees (cells are
    container-relative), so the same cell drops into any slot."""
    X0, Y0, X1, Y1, PAD = 160, 250, 1760, 942, 40
    AW, AH = X1 - X0, Y1 - Y0
    b = []
    if arrange == "stack" or (arrange == "split" and direction == "vertical"):
        m = max(1, n)
        ch = (AH - (m - 1) * PAD) / m
        b = [(X0, Y0 + i * (ch + PAD), AW, ch) for i in range(m)]
    elif arrange == "split":
        m = max(1, n)
        if m == 2 and ratio and ratio != 0.5:                 # honour a left/right ratio on a 2-up split
            lw = AW * float(ratio) - PAD / 2
            b = [(X0, Y0, lw, AH), (X0 + lw + PAD, Y0, AW - lw - PAD, AH)]
        else:
            cw = (AW - (m - 1) * PAD) / m
            b = [(X0 + i * (cw + PAD), Y0, cw, AH) for i in range(m)]
    elif arrange == "triptych":
        cw = (AW - 2 * PAD) / 3
        b = [(X0 + i * (cw + PAD), Y0, cw, AH) for i in range(3)]
    elif arrange == "hero-rail":
        hw = AW * float(ratio or 0.62) - PAD / 2
        b = [(X0, Y0, hw, AH)]
        rn = max(1, n - 1)
        rx, rw = X0 + hw + PAD, AW - hw - PAD
        rhh = (AH - (rn - 1) * PAD) / rn
        b += [(rx, Y0 + i * (rhh + PAD), rw, rhh) for i in range(rn)]
    elif arrange == "grid":
        cols = 2
        rows = max(1, (n + 1) // 2)
        cw = (AW - (cols - 1) * PAD) / cols
        ch = (AH - (rows - 1) * PAD) / rows
        b = [(X0 + (i % cols) * (cw + PAD), Y0 + (i // cols) * (ch + PAD), cw, ch) for i in range(n)]
    else:
        cw = (AW - (max(1, n) - 1) * PAD) / max(1, n)
        b = [(X0 + i * (cw + PAD), Y0, cw, AH) for i in range(max(1, n))]
    return b[:n] if len(b) >= n else b + [b[-1]] * (n - len(b))


def _layout_cell(sid, i, cell, box, t0):
    """Render ONE curated cell (media|text|stat|chart) into its box (container-relative). Returns (frag, tl).
    This small fixed vocabulary is the deliberate boundary — NOT arbitrary block nesting."""
    esc, num = compose.esc, compose._num
    x, y, w, h = box
    kind = cell.get("kind", "text")
    cid = f"{sid}-c{i}"
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    frag, tl = [], []
    kick = (f'<div style="font-family:var(--font-mono,monospace);font-size:{max(13,h*0.045):.0f}px;'
            f'letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-bottom:6px">{esc(cell["kicker"])}</div>'
            if cell.get("kicker") else "")
    if kind == "media":
        src = str(cell.get("src", ""))
        frag.append(f'<div id="{cid}" style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;width:{w:.0f}px;'
                    f'height:{h:.0f}px;overflow:hidden;border-radius:12px;background:#000;opacity:0">')
        if src.lower().endswith((".mp4", ".webm", ".mov")):
            frag.append(f'<video src="{esc(src)}" muted playsinline preload="auto" '
                        f'style="width:100%;height:100%;object-fit:cover"></video>')
        else:
            frag.append(f'<img id="{cid}-img" src="{esc(src)}" style="width:100%;height:100%;object-fit:cover">')
            tl.append(f'tl.fromTo("#{cid}-img",{{scale:1}},{{scale:1.08,duration:6,ease:"none"}},{t0:.2f});')
        if cell.get("label") or cell.get("caption"):
            frag.append(f'<div style="position:absolute;left:0;bottom:0;width:100%;box-sizing:border-box;'
                        f'padding:{max(12,h*0.05):.0f}px {max(14,w*0.04):.0f}px;color:#fff;'
                        f'background:linear-gradient(transparent,rgba(0,0,0,.78));font-size:{max(16,h*0.05):.0f}px;'
                        f'font-weight:700">{esc(cell.get("label") or cell.get("caption"))}</div>')
        frag.append('</div>')
        tl.append(f'tl.fromTo("#{cid}",{{opacity:0,scale:0.96}},{{opacity:1,scale:1,duration:0.6,ease:"power3.out"}},{t0:.2f});')
    elif kind == "stat":
        v = cell.get("value", "")
        val = f'{esc(cell.get("prefix",""))}{num(v) if isinstance(v,(int,float)) else esc(str(v))}{esc(cell.get("suffix",""))}'
        fs = min(h * 0.42, w * 0.46, 168)
        frag.append(f'<div id="{cid}" style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;width:{w:.0f}px;'
                    f'height:{h:.0f}px;display:flex;flex-direction:column;align-items:center;justify-content:center;'
                    f'gap:8px;text-align:center;opacity:0">{kick}'
                    f'<div style="font-family:var(--font-display);font-weight:800;font-size:{fs:.0f}px;line-height:0.86;'
                    f'color:var(--accent)">{val}</div>'
                    f'<div style="font-size:{max(18,h*0.062):.0f}px;font-weight:600;color:{ink};opacity:.82;'
                    f'max-width:86%">{esc(cell.get("label",""))}</div></div>')
        tl.append(f'tl.fromTo("#{cid}",{{opacity:0,y:16}},{{opacity:1,y:0,duration:0.55,ease:"back.out(1.5)"}},{t0:.2f});')
    elif kind == "text":
        lines = cell.get("lines") or ([cell["text"]] if cell.get("text") else [])
        op = cell.get("operative", "")
        fs = min(h * 0.15, w * 0.085, 62)
        body = [kick]
        for ln in lines:
            html_ln = (f'{esc(ln.split(op,1)[0])}<span style="color:var(--accent)">{esc(op)}</span>{esc(ln.split(op,1)[1])}'
                       if op and op in ln else esc(ln))
            body.append(f'<div style="font-family:var(--font-display);font-weight:800;font-size:{fs:.0f}px;'
                        f'line-height:1.06;color:{ink}">{html_ln}</div>')
        frag.append(f'<div id="{cid}" style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;width:{w:.0f}px;'
                    f'height:{h:.0f}px;display:flex;flex-direction:column;justify-content:center;gap:4px;'
                    f'opacity:0">{"".join(body)}</div>')
        tl.append(f'tl.fromTo("#{cid}",{{opacity:0,y:14}},{{opacity:1,y:0,duration:0.5,ease:"power3.out"}},{t0:.2f});')
    elif kind == "chart":
        series = cell.get("series") or []
        m = max(1, len(series))
        vals = [float(s.get("value", 0)) for s in series] or [0.0]
        ymax = max(vals) * 1.15 or 1.0
        top, base = h * 0.14, h - max(30, h * 0.13)
        ph = base - top
        cw = w / m
        bw = cw * 0.58
        inner = [kick] if kick else []
        for bi, s in enumerate(series):
            v = float(s.get("value", 0))
            bh = max(2.0, v / ymax * ph)
            bx = bi * cw + (cw - bw) / 2
            inner.append(f'<div id="{cid}-b{bi}" style="position:absolute;left:{bx:.0f}px;top:{base-bh:.0f}px;'
                         f'width:{bw:.0f}px;height:{bh:.0f}px;background:var(--accent);transform-origin:bottom center;'
                         f'transform:scaleY(0)"></div>')
            inner.append(f'<div style="position:absolute;left:{bi*cw:.0f}px;top:{base+6:.0f}px;width:{cw:.0f}px;'
                         f'text-align:center;font-size:{max(13,h*0.045):.0f}px;color:{ink};opacity:.6">{esc(str(s.get("label","")))}</div>')
        inner.append(f'<div style="position:absolute;left:0;top:{base:.0f}px;width:{w:.0f}px;height:2px;'
                     f'background:{ink};opacity:.2"></div>')
        frag.append(f'<div id="{cid}" style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;width:{w:.0f}px;'
                    f'height:{h:.0f}px;opacity:0">{"".join(inner)}</div>')
        tl.append(f'tl.to("#{cid}",{{opacity:1,duration:0.3}},{t0:.2f});')
        for bi in range(m):
            tl.append(f'tl.fromTo("#{cid}-b{bi}",{{scaleY:0}},{{scaleY:1,duration:0.4,ease:"power2.out"}},{t0+0.1+bi*0.05:.2f});')
    return frag, tl


def layout(sid, sc):
    """A LAYOUT container — a CURATED arrangement (split | triptych | hero-rail | grid | stack) of a fixed
    cell vocabulary (media | text | stat | chart). The runtime of the composition archetypes: pick an
    arrangement, fill named slots. One beat, staggered slot reveal. NOT arbitrary block nesting — the bounded
    set is the point (easy to choose, can't rot into a dashboard). Generalises comparison/juxtaposition/
    split_view. data: {arrange, slots:[{kind, ...cell fields}], direction?(for split), ratio?(0..1 for
    split/hero-rail), kicker?, title?, titleHi?, ground?}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    esc = compose.esc
    slots = d.get("slots") or []
    n = len(slots)
    dark = getattr(compose, "_POLARITY", "light") == "dark"
    ink = "#f3efe6" if dark else "#1c1c19"
    arrange = d.get("arrange", "split")
    boxes = _layout_boxes(arrange, n, d.get("direction", "horizontal"), d.get("ratio"))
    frag = [f'<div id="{sid}-wrap" class="clip blk-layout" data-start="{start}" data-duration="{dur}" '
            f'data-track-index="1" style="position:absolute;inset:0;color:{ink};background:{esc(compose._page_bg())}">']
    hf, ht = _dataviz_head(sid, sc, ink)
    frag += hf
    tl = list(ht)
    times = compose._reveal_times(n, start, dur, [None] * n) if n else []
    for i, cell in enumerate(slots):
        cf, ct = _layout_cell(sid, i, cell, boxes[i], times[i])
        frag += cf
        tl += ct
    frag.append('</div>')
    return frag, tl


EXT_BLOCKS = {"spotlight": spotlight, "data_table": data_table,
              "trajectory": trajectory, "stream": stream, "bar_race": bar_race,
              "split_view": split_view, "slope": slope, "isotype": isotype, "dumbbell": dumbbell,
              "small_multiples": small_multiples, "histogram": histogram,
              "gauge": gauge, "process": process, "layout": layout}
