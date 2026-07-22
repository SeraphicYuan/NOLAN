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

    fr = paper.get("focus_rect")
    if fr:
        fx0, fy0, fw, fh = [float(v) for v in fr]
        bgw, bgh = pw / max(1e-3, fw), H / max(1e-3, fh)
        bg = f'background-size:{bgw:.0f}px {bgh:.0f}px;background-position:-{fx0*bgw:.0f}px -{fy0*bgh:.0f}px;'
    else:
        bg = 'background-size:cover;background-position:center top;'
    frag = [f'<div id="{sid}-paper" class="clip" data-start="{start}" data-duration="{dur}" data-track-index="1" '
            f'style="position:absolute;left:{px}px;top:0;width:{pw}px;height:{H}px;background-color:#fff;'
            f'background-image:url(\'{esc(paper.get("source",""))}\');background-repeat:no-repeat;{bg}opacity:0;"></div>']
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


EXT_BLOCKS = {"spotlight": spotlight, "data_table": data_table,
              "trajectory": trajectory, "stream": stream, "bar_race": bar_race,
              "split_view": split_view}
