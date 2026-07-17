"""Incremental final render — re-render only CHANGED frames, then stitch, instead of the 10-min monolith.

Frames map 1:1 to VO sections, so the final IS the per-frame clips concatenated. render_frame's
scaffold already mounts a frame's voice; this adds the frame's VIDEO GROUNDS to the scaffold so each
per-frame clip is ground-accurate, renders each (skipping frames whose content hash is unchanged since
the last build), concatenates them, and re-lays the BGM bed over the whole. A one-frame edit then costs
one frame render + a fast concat, not all 14,069 frames.

  python -X utf8 -m nolan.hyperframes.incremental <comp> [--only NN-slug,...]

Pure helpers (sig / ground-tag injection / concat-list) are unit-testable; the render itself is npx.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .edit import BRIDGE, _comp_dir, _frames_dir, _scaffold_preview, list_frames, load_frame_spec


def _ffmpeg() -> str:
    from nolan.hf_qa import _ffmpeg as ff
    return ff()


def frame_grounds(comp: str, frame_id: str) -> List[Dict]:
    """This frame's video-ground clips with LOCAL (frame-relative) start/dur (from the retimed spec). A scene
    contributes a root video from EITHER a `media_ground` video (`data.ground` kind=video) OR a VIDEO-valued
    `data.backdrop` (social_card etc. — a CSS background-image can't play a video, so the block leaves it
    transparent and the video is root-injected here, behind the scene)."""
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    out = []
    for sc in fr.get("scenes", []):
        d = sc.get("data", {}) or {}
        g = d.get("ground", {}) or {}
        src = g["src"] if (g.get("kind") == "video" and g.get("src")) else None
        if not src:
            bd = d.get("backdrop")
            if isinstance(bd, str) and bd.lower().endswith((".mp4", ".mov", ".webm")):
                src = bd
        if src:
            out.append({"src": src, "start": round(float(sc.get("start", 0) or 0), 3),
                        "dur": round(float(sc.get("dur", 0) or 0), 3)})
    return out


def ground_tags(grounds: List[Dict]) -> str:
    """Root <video class=clip> tags (track-index 0 = behind the frame) for a frame's grounds. The
    object-fit:cover + inset:0 style is REQUIRED — it's what the monolith's inject_root_video applies;
    without it the ground renders at native size/position instead of full-bleed (a big visual diff)."""
    return "".join(
        f'<video class="clip" src="{g["src"]}" data-start="{g["start"]}" data-duration="{g["dur"]}" '
        f'data-track-index="0" muted playsinline '
        f'style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;"></video>' for g in grounds)


def inject_grounds(index_html: str, grounds: List[Dict]) -> str:
    """Insert the ground tags BEHIND the frame scene div (archetype B: root-level video)."""
    tags = ground_tags(grounds)
    return index_html.replace('<div class="scene"', tags + '<div class="scene"', 1) if tags else index_html


def _asset_stem(src: str) -> str:
    """Basename of an asset path minus its directory, extension, and known post-process suffixes, so a
    freeze-HEALED index ground (`s01n03_00.filled.mp4`) matches its raw spec src (`s01n03_00.mp4`) — that
    match is how an UNCHANGED ground keeps its heal while an edited one is driven from the spec."""
    base = re.split(r"[\\/]", src.strip())[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    for suf in (".filled", ".trim", ".fit", ".heal", ".mux", ".vid", ".silid", ".orig"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
    return stem


# Bump when the render LOGIC changes (not just content) so clips cached by an OLD code path aren't reused
# (the spec→windowed change produced an identical content hash but different pixels — a stale-clip hazard).
_CACHE_VERSION = "2-windowed"


def frame_sig(comp: str, frame_id: str) -> str:
    """Content hash of WHAT ACTUALLY RENDERS for a frame — the frame HTML + the windowed index elements the
    render mounts (grounds / comparison / audio), or the spec grounds when there's no assembled index
    (fallback). The per-frame cache key for 'unchanged → reuse the clip'."""
    h = hashlib.sha1()
    html = _frames_dir(comp) / f"{frame_id}.html"
    h.update(html.read_bytes() if html.exists() else b"")
    _, kids = _index_children(comp)
    if kids:
        _, elems = _window_children(kids, frame_id)        # windowed path: hash the mounted NON-ground elems
        h.update("".join(elems).encode())
    for g in _merged_grounds(comp, frame_id, kids):        # grounds that ACTUALLY render (spec-driven + heal),
        h.update(f"{g['src']}|{g['start']}|{g['dur']}".encode())   # so a dropped/swapped ground invalidates
    return h.hexdigest()[:16]


def frame_offset(comp: str, frame_id: str) -> float:
    """Global start time of a frame = sum of PRIOR frame (VO section) durations."""
    cdir = _comp_dir(comp)
    meta = {}
    mp = cdir / "audio_meta.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    durs = {v.get("frame"): float(v.get("duration_s", 0) or 0) for v in meta.get("voices", [])}
    m = re.match(r"(\d+)", frame_id)
    n = int(m.group(1)) if m else 1
    return round(sum(durs.get(i, 0.0) for i in range(1, n)), 3)


def _caption_natural_dur(cap_path: Path) -> Optional[float]:
    """The caption comp's OWN root duration (data-duration on data-composition-id='captions'). A sub-comp
    mounted at anything other than its natural duration is TIME-SCALED by the runtime — 427s of captions
    crammed into a 55s window plays ~8x too fast, so at any instant the caption is mid-transition/blank.
    A windowed render must mount captions at THIS value and rely on data-start=-offset to land the slice."""
    txt = cap_path.read_text(encoding="utf-8")
    m = (re.search(r'data-composition-id="captions"[^>]*?data-duration="([0-9.]+)"', txt)
         or re.search(r'data-duration="([0-9.]+)"[^>]*?data-composition-id="captions"', txt))
    return float(m.group(1)) if m else None


def _scaffold_captions(comp: str) -> Optional[Path]:
    """Wrap captions.html in a TRANSPARENT, full-duration root so `hyperframes render` can produce a
    standalone alpha overlay. captions.html is a sub-comp fragment — rendered alone it fails with
    'Composition has zero duration'; it needs a root with a main timeline (mirrors _scaffold_preview,
    but transparent-bg + full duration + only the caption sub-comp)."""
    cdir = _comp_dir(comp)
    cap = cdir / "compositions" / "captions.html"
    if not cap.exists():
        return None
    total = _caption_natural_dur(cap) or 0.0
    if total <= 0:
        return None
    pdir = cdir / "compositions" / "_preview" / "_captions"
    (pdir / "compositions").mkdir(parents=True, exist_ok=True)
    (pdir / "compositions" / "captions.html").write_text(cap.read_text(encoding="utf-8"), encoding="utf-8")
    vend = cdir / "vendor"
    if not vend.is_dir():
        vend = BRIDGE / "vendor"
    if vend.is_dir():
        (pdir / "vendor").mkdir(exist_ok=True)
        for f in vend.glob("*"):
            if f.is_file():
                (pdir / "vendor" / f.name).write_bytes(f.read_bytes())
    (pdir / "index.html").write_text(
        '<!doctype html><html><head><meta charset="UTF-8"/>'
        '<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>'
        '<style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:1920px;height:1080px;'
        'overflow:hidden;background:transparent}#root{position:relative;width:1920px;height:1080px;'
        'overflow:hidden}.scene{position:absolute;inset:0}</style></head><body>'
        f'<div id="root" data-composition-id="main" data-start="0" data-duration="{total}" '
        'data-width="1920" data-height="1080">'
        '<div class="scene" data-composition-id="captions" data-composition-src="compositions/captions.html" '
        f'data-start="0" data-duration="{total}" data-track-index="0"></div></div>'
        '<script>window.__timelines=window.__timelines||{};var tl=gsap.timeline({paused:true});'
        f'tl.to({{}},{{duration:{total}}},0);window.__timelines["main"]=tl;</script></body></html>',
        encoding="utf-8")
    return pdir


def render_caption_overlay(comp: str, quality: str = "high") -> Optional[Path]:
    """Render captions ONCE to a transparent (alpha) overlay — captions are a full-length LAYER, not
    per-frame (a 427s caption comp can't nest inside a single-frame window; and keeping clips caption-free
    lets the concat stay a stream-copy). Cached by the caption HTML's content hash so a one-frame edit
    reuses it. Returns the .webm (VP9, alpha) or None if there's no caption comp."""
    cdir = _comp_dir(comp)
    cap = cdir / "compositions" / "captions.html"
    if not cap.exists():
        return None
    overlay = cdir / "renders" / "captions_overlay.webm"   # VP9 alpha: transparent + far smaller than ProRes
    sig = hashlib.sha1(cap.read_bytes()).hexdigest()[:16]
    sig_f = cdir / "renders" / ".captions_overlay.sig"
    if overlay.exists() and sig_f.exists() and sig_f.read_text(encoding="utf-8").strip() == sig:
        return overlay                                     # captions unchanged → reuse the cached overlay
    overlay.parent.mkdir(parents=True, exist_ok=True)
    pdir = _scaffold_captions(comp)                        # wrap the fragment in a renderable transparent root
    if not pdir:
        return None
    subprocess.run(["npx", "--yes", "hyperframes@latest", "render", str(pdir),
                    "--format", "webm", "--quality", quality, "--output", str(overlay)],
                   cwd=str(pdir), capture_output=True, text=True, encoding="utf-8", errors="replace",
                   shell=(os.name == "nt"))
    if not overlay.exists():
        return None
    # SAFETY: only use the overlay if it actually has an ALPHA channel. HyperFrames webm on this host
    # currently renders opaque yuv420p (captions on black) — compositing that would occlude the whole
    # video, so skip captions instead. (Alpha caption render is a known follow-up; captions are optional.)
    probe = subprocess.run([_ffmpeg(), "-i", str(overlay)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    if "yuva" not in (probe.stdout + probe.stderr):
        print("  ⚠ caption overlay has no alpha (opaque) — skipping captions so the video isn't occluded.")
        overlay.unlink(missing_ok=True)
        return None
    sig_f.write_text(sig, encoding="utf-8")
    return overlay


def composite_captions(video: Path, overlay: Path, out: Path) -> bool:
    """Overlay the transparent caption layer onto the concatenated video — ONE full-length re-encode at high
    quality (crf 15, ~visually lossless), audio copied. Per-frame clips + the concat stay caption-free/copy."""
    ff = _ffmpeg()
    subprocess.run([ff, "-y", "-i", str(video), "-i", str(overlay),
                    "-filter_complex", "[0:v][1:v]overlay=format=auto[v]", "-map", "[v]", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "15", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", str(out)], capture_output=True)
    return out.exists() and out.stat().st_size > 1000


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _index_children(comp: str):
    """Parse the ASSEMBLED index.html → (root data-duration, [[tag, attrs_list], ...] direct children of
    #root). Returns (None, None) if there's no assembled index (caller falls back to spec-reconstruction).
    Uses stdlib html.parser so multi-line elements (the <audio>/<div> mounts) are handled correctly."""
    from html.parser import HTMLParser
    idx = _comp_dir(comp) / "index.html"
    if not idx.exists():
        return None, None

    class _P(HTMLParser):
        def __init__(s):
            super().__init__()
            s.din = 0
            s.inr = False
            s.kids = []
            s.rootdur = None

        def handle_starttag(s, tag, attrs):
            d = dict(attrs)
            if tag == "div" and d.get("id") == "root":
                s.inr = True
                s.rootdur = d.get("data-duration")
                return
            if s.inr:
                if s.din == 0:
                    s.kids.append([tag, attrs])          # a DIRECT child of #root
                s.din += 1

        def handle_endtag(s, tag):
            if s.inr:
                if s.din == 0:
                    s.inr = False                        # </div> closing #root
                else:
                    s.din -= 1

    p = _P()
    p.feed(idx.read_text(encoding="utf-8"))
    return p.rootdur, p.kids


def _shift_elem(tag, attrs, delta: float) -> str:
    """Re-serialize a root child with its data-start shifted by `delta` (into frame-local time)."""
    parts = []
    for k, v in attrs:
        if k == "data-start" and v is not None:
            fv = _f(v)
            if fv is not None:
                v = f"{round(fv + delta, 3)}"
        parts.append(k if v is None else f'{k}="{v}"')
    return f'<{tag} {" ".join(parts)}></{tag}>'


def _window_children(kids, frame_id: str):
    """PURE: given the assembled index's root children, return (frame_dur, [element_html]) for ONE frame's
    window — the frame's own sub-comp (shifted to local 0) + every root clip (grounds / comparison videos /
    voice / bgm / sfx) that OVERLAPS [frame_start, frame_end], all shifted to local time. OTHER frames'
    sub-comps and the caption sub-comp are excluded (captions = the separate full-length overlay)."""
    S = dur = None
    for tag, attrs in kids:
        d = dict(attrs)
        if tag == "div" and d.get("data-composition-id") == frame_id:
            S, dur = _f(d.get("data-start")) or 0.0, _f(d.get("data-duration"))
    if S is None or dur is None or dur <= 0:
        return None, []
    E = S + dur
    out = []
    for tag, attrs in kids:
        d = dict(attrs)
        cid = d.get("data-composition-id")
        if cid == "captions":
            continue                                     # captions → separate overlay
        if tag == "div" and cid and cid != frame_id:
            continue                                     # a different frame's sub-comp
        if tag == "video" and d.get("data-track-index") == "0":
            continue                                     # a GROUND → reconstructed from the current spec, not
                                                         # inherited from the (possibly stale) assembled index
        st, du = _f(d.get("data-start")), _f(d.get("data-duration"))
        if cid == frame_id:                              # this frame's sub-comp
            out.append(_shift_elem(tag, attrs, -S))
        elif st is not None and du is not None and st < E and st + du > S:   # a root clip overlapping the window
            out.append(_shift_elem(tag, attrs, -S))
    return dur, out


def _window_grounds(kids, frame_id: str) -> List[Dict]:
    """This frame's track-0 VIDEO grounds AS BAKED INTO the assembled index (freeze-healed `.filled.mp4`),
    shifted to frame-local time: [{src, start, dur}]. Source of the healed src that `_merged_grounds` keeps
    for an UNCHANGED ground; empty when there's no assembled index."""
    S = dur = None
    for tag, attrs in kids or []:
        d = dict(attrs)
        if tag == "div" and d.get("data-composition-id") == frame_id:
            S, dur = _f(d.get("data-start")) or 0.0, _f(d.get("data-duration"))
    if S is None or dur is None or dur <= 0:
        return []
    E = S + dur
    out = []
    for tag, attrs in kids or []:
        d = dict(attrs)
        if tag != "video" or d.get("data-track-index") != "0":
            continue
        st, du = _f(d.get("data-start")), _f(d.get("data-duration"))
        if st is None or du is None or not (st < E and st + du > S):
            continue
        out.append({"src": d.get("src", ""), "start": round(st - S, 3), "dur": round(du, 3)})
    return out


def _merged_grounds(comp: str, frame_id: str, kids) -> List[Dict]:
    """The frame's grounds TO RENDER — driven by the current SPEC (which ground plays, at the current timing),
    borrowing the freeze-HEALED src from the assembled index for any ground that is UNCHANGED (same asset in
    the same window). A newly-dropped or swapped ground renders from its raw spec src (heal re-applies at the
    next full assemble); a removed ground vanishes (not in the spec → not rendered). This is what makes an
    edited ground appear on the very next incremental render instead of waiting for a full re-assemble."""
    spec_g = frame_grounds(comp, frame_id)
    index_g = _window_grounds(kids, frame_id)
    used, merged = set(), []
    for sg in spec_g:
        src = sg["src"]
        for i, ig in enumerate(index_g):
            if i in used:
                continue
            if (ig["start"] < sg["start"] + sg["dur"] and ig["start"] + ig["dur"] > sg["start"]
                    and _asset_stem(ig["src"]) == _asset_stem(sg["src"])):
                src, _ = ig["src"], used.add(i)          # unchanged ground → keep the healed index src
                break
        merged.append({"src": src, "start": sg["start"], "dur": sg["dur"]})
    return merged


def _index_html(dur: float, body: str) -> str:
    """A renderable per-frame root (same shape as _scaffold_preview) hosting the windowed index elements."""
    return ('<!doctype html><html><head><meta charset="UTF-8"/>'
            '<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>'
            '<style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:1920px;height:1080px;'
            'overflow:hidden;background:#000}#root{position:relative;width:1920px;height:1080px;overflow:hidden}'
            '.scene{position:absolute;inset:0}.clip{position:absolute;inset:0}</style></head><body>'
            f'<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" '
            f'data-width="1920" data-height="1080">{body}</div>'
            '<script>window.__timelines=window.__timelines||{};var tl=gsap.timeline({paused:true});'
            f'tl.to({{}},{{duration:{dur}}},0);window.__timelines["main"]=tl;</script></body></html>')


def _scaffold_from_index(comp: str, frame_id: str) -> Optional[Path]:
    """Build a per-frame render dir by WINDOWING the assembled index.html — so grounds, freeze-heal,
    comparison videos, bgm + sfx and theme are INHERITED from hf-finish's assembly (steps 6–7), not
    reconstructed. Returns None if there's no assembled index (caller falls back to spec-reconstruction)."""
    _, kids = _index_children(comp)
    if not kids:
        return None
    dur, elems = _window_children(kids, frame_id)        # NON-ground elems (frame sub-comp / comparison / audio)
    if dur is None:
        return None
    pdir = _scaffold_preview(comp, frame_id)             # reuse for file setup (frame HTML, vendor, assets, voice)
    # grounds are track-0 (bottom layer) → prepend them so they sit BEHIND the frame sub-comp. Prepending
    # (not inject_grounds' `<div class="scene"` anchor) is robust to the index div's attribute order.
    body = ground_tags(_merged_grounds(comp, frame_id, kids)) + "".join(elems)
    (pdir / "index.html").write_text(_index_html(dur, body), encoding="utf-8")
    return pdir


def _frame_window(comp: str, frame_id: str, fps: int = 30):
    """(global_start, dur) for a frame from audio_meta voices (narration owns duration)."""
    meta = {}
    mp = _comp_dir(comp) / "audio_meta.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    durs = {v.get("frame"): float(v.get("duration_s", 0) or 0) for v in meta.get("voices", [])}
    m = re.match(r"(\d+)", frame_id)
    n = int(m.group(1)) if m else 1
    return round(sum(durs.get(i, 0.0) for i in range(1, n)), 3), durs.get(n, 0.0)


def _grid_frames(start: float, dur: float, fps: int = 30) -> int:
    """Frames this window occupies on the monolith's CUMULATIVE frame grid. Using round(end*fps)-round(start*fps)
    (not round(dur*fps)) is what makes it drift-free: per-frame rounding accumulates, cumulative rounding cancels."""
    return round((start + dur) * fps) - round(start * fps)


def _trim_to_grid(comp: str, frame_id: str, clip: Path, fps: int = 30) -> None:
    """Trim a clip to the frame count its window occupies in the monolith (_grid_frames). The renderer rounds
    each clip's duration UP ~1 frame; matching the monolith's cumulative grid stops that from accumulating into
    timeline drift (+0.27s over 8 frames → seams misalign). Stream-copy: HyperFrames renders -bf 0, so a -t cut
    on a frame boundary is frame-exact. No-op if audio_meta is missing."""
    start, dur = _frame_window(comp, frame_id, fps)
    if dur <= 0:
        return
    n = _grid_frames(start, dur, fps)
    if n <= 0:
        return
    trimmed = clip.with_name(clip.stem + ".trim.mp4")
    # cut at the MIDPOINT past frame n-1 ((n-0.5)/fps): -t keeps whole frames straddling the cut, so aiming
    # at n/fps leaves the extra frame; (n-0.5)/fps drops it → exactly n frames survive.
    subprocess.run([_ffmpeg(), "-y", "-i", str(clip), "-t", f"{(n - 0.5) / fps:.4f}", "-c", "copy", str(trimmed)],
                   capture_output=True)
    if trimmed.exists() and trimmed.stat().st_size > 1000:
        trimmed.replace(clip)


def _comparison_panels(comp: str, frame_id: str) -> List[Dict]:
    """Comparison video panels of a frame — scene-local rect + [sstart, sdur] window + src, from the frame
    HTML. Feeds the black-panel verify gate: the renderer intermittently DROPS a root <video> (a decode /
    timing race, worst on the last frame under audio-export contention), leaving that panel BLACK."""
    fh = _frames_dir(comp) / f"{frame_id}.html"
    if not fh.exists():
        return []
    html = fh.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r'<div\b[^>]*\bdata-cmp-video="[^"]*"[^>]*>', html):
        tag = m.group(0)

        def _a(n, _t=tag):
            mm = re.search(r'\b' + n + r'="([^"]*)"', _t)
            return mm.group(1) if mm else None

        rect = _a("data-cmp-rect")
        if not rect:
            continue
        try:
            x, y, w, h = (int(float(v)) for v in rect.split(","))
        except ValueError:
            continue
        ss, sd = _a("data-cmp-sstart"), _a("data-cmp-sdur")
        out.append({"src": _a("data-cmp-video"), "x": x, "y": y, "w": w, "h": h,
                    "sstart": float(ss) if ss else 0.0, "sdur": float(sd) if sd else 0.0})
    return out


def _region_luma(path: Path, t: float, crop: str, ff: str) -> Optional[int]:
    """Mean luma (0..255) of a crop region at time t, as one 1x1 gray pixel via ffmpeg. None on failure."""
    r = subprocess.run([ff, "-ss", f"{max(0.0, t):.3f}", "-i", str(path), "-vf",
                        f"crop={crop},scale=1:1,format=gray", "-frames:v", "1", "-f", "rawvideo", "-"],
                       capture_output=True)
    return r.stdout[0] if r.stdout else None


def _panel_dropped_black(clip: Path, comp: str, panel: Dict, ff: str) -> bool:
    """True when a comparison panel rect is (near) BLACK across its whole window while its SOURCE clip is
    NOT — i.e. the renderer dropped the root video, as opposed to a genuinely-dark clip. Samples 3 points."""
    dur = panel["sdur"] or 3.0
    crop = f"{panel['w']}:{panel['h']}:{panel['x']}:{panel['y']}"
    fr = (0.3, 0.5, 0.7)
    pl = [v for v in (_region_luma(clip, panel["sstart"] + dur * f, crop, ff) for f in fr) if v is not None]
    if not pl or max(pl) > 10:                           # the panel shows something → not a dropped video
        return False
    src = _comp_dir(comp) / (panel["src"] or "")
    if not src.exists():
        return max(pl) < 6                               # can't compare to the source → flag only near-total black
    sl = [v for v in (_region_luma(src, dur * f, "iw:ih:0:0", ff) for f in fr) if v is not None]
    return max(pl) < 6 and (max(sl) if sl else 255) > max(pl) + 12


def _render_one_once(comp: str, frame_id: str, quality: str) -> Optional[Path]:
    """One render attempt → the frame clip (windowed from the assembled index). See render_one for the gate."""
    pdir = _scaffold_from_index(comp, frame_id)
    if pdir is None:                                     # no assembled index → spec-reconstruction fallback
        pdir = _scaffold_preview(comp, frame_id)
        idx = pdir / "index.html"
        idx.write_text(inject_grounds(idx.read_text(encoding="utf-8"), frame_grounds(comp, frame_id)),
                       encoding="utf-8")
    clip = _frames_dir(comp) / f"{frame_id}.clip.mp4"
    _npx_render(pdir, clip, quality)
    wants_voice = _voice_track_src((pdir / "index.html").read_text(encoding="utf-8")) is not None
    if not clip.exists():
        # The HyperFrames renderer can die in AUDIO-assembly ("audioPadTrim … audio.aac No such file")
        # for some frames — notably the FINAL frame, whose window ends at the exact timeline end. The
        # VIDEO capture succeeds; only the mux fails. Self-heal: render VIDEO-ONLY (strip the voice track)
        # and mux the section wav ourselves, at the renderer's native audio params (48 kHz stereo) so the
        # clip concatenates cleanly with the rest.
        if not _render_audio_fallback(pdir, clip, quality):
            return None
    elif wants_voice and not _has_audio(clip):
        # SAME audio-assembly failure, DIFFERENT outcome: the renderer writes a VIDEO-ONLY clip (no audio
        # stream) WITHOUT crashing, so `clip.exists()` is true and the crash-path above never fires — the
        # frame would ship SILENT and the concat would drop its (missing) audio track. The video is fine
        # (the comparison panel is often better here — audio-export contention is what blacks it out), so
        # just mux the voice INTO the existing clip (no re-render). Fall back to a fresh video-only render
        # only if that mux can't be done.
        if not _mux_voice(clip, pdir) and not _render_audio_fallback(pdir, clip, quality):
            return None
    _trim_to_grid(comp, frame_id, clip)                  # frame-grid-exact → no cumulative timeline drift
    return clip


def _render_one_video_only(comp: str, frame_id: str, quality: str) -> Optional[Path]:
    """Render a frame VIDEO-ONLY (strip the voice track) then mux its section voice — the RELIABLE path for a
    frame whose comparison root <video> blacks out in the normal audio-present render. Verified: with the
    voice track present the last frame's comparison video renders BLACK (an audio-export/decode race), but
    the identical scaffold rendered video-only shows the video every time; the voice is muxed back losslessly."""
    pdir = _scaffold_from_index(comp, frame_id)
    if pdir is None:                                     # no assembled index → spec-reconstruction fallback
        pdir = _scaffold_preview(comp, frame_id)
        idx = pdir / "index.html"
        idx.write_text(inject_grounds(idx.read_text(encoding="utf-8"), frame_grounds(comp, frame_id)),
                       encoding="utf-8")
    clip = _frames_dir(comp) / f"{frame_id}.clip.mp4"
    if not _render_audio_fallback(pdir, clip, quality):  # strip voice → render video-only → mux the section wav
        return None
    _trim_to_grid(comp, frame_id, clip)
    return clip


def _recompose(comp: str, frame_id: str) -> None:
    """Rebuild the frame HTML from its CURRENT spec before rendering, so a render always reflects the latest
    edit even when the edit path didn't recompose (or recomposed then went stale). Deterministic (same spec →
    byte-identical HTML) so it never thrashes the sig cache; best-effort — a bespoke frame that can't gate
    keeps its existing HTML rather than crashing the render."""
    try:
        from .edit import recompose_frame
        recompose_frame(comp, frame_id)
    except Exception as e:                                # pragma: no cover - defensive
        print(f"  ⚠ {frame_id}: recompose skipped ({e}); rendering the existing frame HTML")


def render_one(comp: str, frame_id: str, quality: str = "high", verify: bool = True) -> Optional[Path]:
    """Render ONE frame to a clip (compositions/frames/<id>.clip.mp4) by WINDOWING the assembled index.html
    (inherits grounds/freeze-heal/comparison/bgm/sfx from hf-finish). Falls back to spec-reconstruction if
    there's no assembled index. CAPTION-FREE — captions are the separate overlay; the clip stays stream-copy-able.

    `quality` matches `hf-finish` ("high" = x264 slow/CRF15) so a per-frame clip is per-pixel identical
    to that frame's window in the monolith — the precondition for the sliced render being canonical.

    BLACK-PANEL GATE (`verify`): the renderer can drop a comparison root <video> — with the voice track
    present, the LAST frame's comparison panel renders BLACK (an audio-export/decode race), while an identical
    video-only render shows it every time. So after the normal render we sample each comparison panel's rect
    over its window; if one is BLACK while its source clip is not, re-render VIDEO-ONLY + voice-mux (the proven
    path). If it STILL blacks out, warn LOUDLY rather than ship silently (invariant: failures are loud)."""
    _recompose(comp, frame_id)                            # render reflects the current spec (defensive for direct calls)
    clip = _render_one_once(comp, frame_id, quality)
    if clip is None or not verify:
        return clip
    ff = _ffmpeg()
    black = [p for p in _comparison_panels(comp, frame_id) if _panel_dropped_black(clip, comp, p, ff)]
    if not black:
        return clip
    print(f"  ⚠ {frame_id}: {len(black)} comparison panel(s) rendered BLACK in the audio pass "
          f"(last-frame decode race) — re-rendering VIDEO-ONLY + voice-mux")
    vo = _render_one_video_only(comp, frame_id, quality)
    if vo is None:
        print(f"  ⚠ {frame_id}: video-only re-render FAILED — keeping the audio clip (still has a black panel)")
        return clip
    if any(_panel_dropped_black(vo, comp, p, ff) for p in _comparison_panels(comp, frame_id)):
        print(f"  ⚠ {frame_id}: comparison panel STILL BLACK after the video-only re-render — investigate "
              f"(shipping the video-only clip; not silently accepting the black one)")
    return vo


def _npx_render(pdir: Path, out: Path, quality: str) -> subprocess.CompletedProcess:
    return subprocess.run(["npx", "--yes", "hyperframes@latest", "render", str(pdir),
                           "--quality", quality, "--output", str(out)],
                          cwd=str(pdir), capture_output=True, text=True, encoding="utf-8", errors="replace",
                          shell=(os.name == "nt"))


def _voice_track_src(html: str) -> Optional[str]:
    """`src` of the root voice track (data-track-index=10), matched ORDER-AGNOSTICALLY — the src attribute
    can appear before OR after data-track-index in the tag (it precedes it in the assembled index). A single
    `data-track-index="10"...src="..."` regex misses the before case → the voice mux is skipped → a SILENT
    clip that drops the frame's narration. None when there is no voice track."""
    am = re.search(r'<audio\b[^>]*\bdata-track-index="10"[^>]*>', html)
    sm = re.search(r'\bsrc="([^"]+)"', am.group(0)) if am else None
    return sm.group(1) if sm else None


def _has_audio(path: Path) -> bool:
    """Whether a media file has an audio stream. The renderer can write a VIDEO-ONLY clip (audio-assembly
    failed but the video muxed) — that clip 'exists' yet would ship silent and break the concat's audio."""
    r = subprocess.run([_ffmpeg(), "-i", str(path)], capture_output=True, text=True, errors="replace")
    return "Audio:" in (r.stdout + r.stderr)


def _ensure_audio(clip: Path, ff: str) -> Path:
    """A clip GUARANTEED to have an audio stream. If it has none, write a sibling with a silent 48 kHz-stereo
    track spanning its video (an audio-less clip makes the concat demuxer drop audio for the whole TAIL, and
    the re-encode guard can't recover audio that isn't there). Normal clips are returned untouched."""
    if _has_audio(clip):
        return clip
    fixed = clip.with_name(clip.stem + ".silid.mp4")
    subprocess.run([ff, "-y", "-i", str(clip), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "194k",
                    "-shortest", str(fixed)], capture_output=True)
    return fixed if (fixed.exists() and fixed.stat().st_size > 1000) else clip


def _mux_voice(clip: Path, pdir: Path) -> bool:
    """Mux the scaffold's voice track INTO an existing (silent) video clip, in place, at 48 kHz stereo — the
    same params the renderer uses, so the fixed clip concatenates cleanly with the rest. No re-render: the
    already-captured video (a good comparison panel) is kept via `-c:v copy`. False if there's no voice wav."""
    src = _voice_track_src((pdir / "index.html").read_text(encoding="utf-8"))
    voice = (pdir / src) if src else None
    if not (voice and voice.exists()):
        return False
    tmp = clip.with_name(clip.stem + ".mux.mp4")
    subprocess.run([_ffmpeg(), "-y", "-i", str(clip), "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "194k", "-shortest",
                    str(tmp)], capture_output=True)
    if tmp.exists() and tmp.stat().st_size > 1000:
        tmp.replace(clip)
        return True
    tmp.unlink(missing_ok=True)
    return False


def _render_audio_fallback(pdir: Path, clip: Path, quality: str) -> bool:
    """VIDEO-ONLY render + our own voice mux, for frames the renderer can't assemble audio for. Reads the
    voice wav from the scaffold index's root voice track (data-track-index=10), strips it so the render is
    audio-free (no audioPadTrim), renders video, then muxes the voice at 48 kHz stereo. Returns True on success."""
    idx = pdir / "index.html"
    html = idx.read_text(encoding="utf-8")
    src = _voice_track_src(html)
    voice = (pdir / src) if src else None
    idx.write_text(re.sub(r'<audio\b[^>]*\bdata-track-index="10"[^>]*>(?:.*?</audio>)?', "", html, flags=re.DOTALL),
                   encoding="utf-8")
    vclip = clip.with_name(clip.stem + ".vid.mp4")
    _npx_render(pdir, vclip, quality)
    if not vclip.exists():
        return False
    if not (voice and voice.exists()):                   # no voice → the silent video IS the clip
        vclip.replace(clip)
        return clip.exists()
    ff = _ffmpeg()
    subprocess.run([ff, "-y", "-i", str(vclip), "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "194k", "-shortest",
                    str(clip)], capture_output=True)
    vclip.unlink(missing_ok=True)
    return clip.exists()


def _av_durations(path: Path, ff: str) -> tuple:
    """(video_container_dur, decoded_audio_dur) in seconds. audio_dur << video_dur means a stream-copy
    concat silently DROPPED a clip's audio (incompatible audio params). Video dur is read from the
    container (instant); audio is decoded to null (fast, ~real-time÷1000) for its true length."""
    def _hms(t: str) -> float:
        try:
            h, m, s = t.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            return 0.0
    info = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True)
    txt = info.stdout + info.stderr
    vdur = next((_hms(ln.split("Duration:")[1].split(",")[0].strip()) for ln in txt.splitlines() if "Duration:" in ln), 0.0)
    dec = subprocess.run([ff, "-i", str(path), "-map", "0:a:0", "-f", "null", "-"], capture_output=True, text=True)
    times = [ln for ln in (dec.stdout + dec.stderr).splitlines() if "time=" in ln]
    adur = _hms(times[-1].split("time=")[1].split()[0]) if times else 0.0
    return vdur, adur


def concat_clips(clips: List[Path], out: Path, comp_dir: Path, bgm: bool = True) -> bool:
    """Concat the per-frame clips → out, then (soft) re-lay the BGM bed under the concatenated voice."""
    ff = _ffmpeg()
    listf = out.parent / "_concat.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    # DEFENSIVE: a clip with NO audio stream makes the concat demuxer drop audio for the whole tail (and the
    # re-encode guard below can't recover audio that isn't there). Give any audio-less clip a silent track.
    clips = [_ensure_audio(Path(c), ff) for c in clips]
    listf.write_text("".join(f"file '{Path(c).resolve().as_posix()}'\n" for c in clips), encoding="utf-8")
    stitched = out.with_name(out.stem + ".nobgm.mp4") if bgm else out
    # STREAM-COPY the per-frame clips (same renderer → identical codec params) so the stitch adds ZERO
    # generational loss — the frame clips ARE high-quality, the concat must not re-encode them.
    subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(listf), "-c", "copy", str(stitched)],
                   capture_output=True)
    # AUDIO-INTEGRITY GUARD: a stream-copy concat SILENTLY drops a clip's audio when its params differ
    # (e.g. a fallback-muxed clip at 24 kHz mono among 48 kHz-stereo clips) — the file looks valid but the
    # tail is silent. Detect the shortfall and re-normalize the audio uniformly (video stays a copy).
    if stitched.exists() and stitched.stat().st_size > 1000:
        vdur, adur = _av_durations(stitched, ff)
        if vdur > 0 and adur + 1.0 < vdur:
            print(f"  ⚠ concat dropped audio (audio {adur:.1f}s < video {vdur:.1f}s) — re-normalizing audio")
            subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(listf), "-c:v", "copy",
                            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "194k", str(stitched)],
                           capture_output=True)
            v2, a2 = _av_durations(stitched, ff)
            if a2 + 1.0 < v2:
                print(f"  ⚠ audio STILL short ({a2:.1f}s < {v2:.1f}s) — clips have incompatible audio params")
    if not stitched.exists() or stitched.stat().st_size < 1000:   # rare param mismatch → safe re-encode at high quality
        subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(listf), "-c:v", "libx264",
                        "-preset", "medium", "-crf", "15", "-pix_fmt", "yuv420p", "-c:a", "aac", str(stitched)],
                       capture_output=True)
    if not stitched.exists():
        return False
    if not bgm:
        return True
    meta = {}
    mp = comp_dir / "audio_meta.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    b = meta.get("bgm") or {}
    bpath = (comp_dir / b["path"]) if b.get("path") else None
    if bpath and bpath.exists():
        vol = float(b.get("volume", 0.2) or 0.2)
        subprocess.run([ff, "-y", "-i", str(stitched), "-stream_loop", "-1", "-i", str(bpath),
                        "-filter_complex", f"[1:a]volume={vol}[bg];[0:a][bg]amix=inputs=2:duration=first[a]",
                        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)],
                       capture_output=True)
        stitched.unlink(missing_ok=True)
        return out.exists()
    stitched.replace(out)                                  # no bed → the concat IS the final
    return out.exists()


def render_incremental(comp: str, only: Optional[List[str]] = None, bgm: bool = True,
                       quality: str = "high", captions: bool = True, out: Optional[Path] = None,
                       log=None) -> Dict:
    """Render each frame to a clip (skipping unchanged via a sig cache), concat → renders/<comp>.mp4, re-lay
    BGM, and (if `captions`) composite the full-length caption overlay. `only` forces a re-render of those
    frame ids even if their sig is unchanged. `quality` is passed to each per-frame render ("high" for a
    canonical/deliverable stitch, "draft" for a fast preview loop). `captions=False` skips the overlay for a
    faster iteration loop (captions are optional — YouTube auto-captions cover the baseline). `log` is an
    optional callback (line:str) -> None for per-frame progress — the /jobs page passes job.log so a render
    isn't a silent black box (it recorded nothing before)."""
    _log = log or (lambda _m: None)
    cdir = _comp_dir(comp)
    frames = [f["id"] if isinstance(f, dict) else f for f in list_frames(comp)]
    cache_f = cdir / "compositions" / "_preview" / "clip_cache.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    only = set(only or [])
    clips, rendered, reused = [], 0, 0
    for i, fid in enumerate(frames):
        _recompose(comp, fid)                                        # spec → fresh HTML BEFORE the sig, so an
        key = f"{_CACHE_VERSION}:{quality}:{frame_sig(comp, fid)}"   # edit-without-recompose still invalidates

        clip = _frames_dir(comp) / f"{fid}.clip.mp4"                 # or an old-logic clip must not be reused
        if clip.exists() and cache.get(fid) == key and fid not in only:
            reused += 1
            _log(f"[{i + 1}/{len(frames)}] reused {fid} (unchanged)")
        else:
            _log(f"[{i + 1}/{len(frames)}] rendering {fid}…")
            if not render_one(comp, fid, quality=quality):
                _log(f"[{i + 1}/{len(frames)}] FAILED {fid}")
                raise RuntimeError(f"incremental render: frame {fid} failed to render")
            cache[fid] = key
            rendered += 1
            _log(f"[{i + 1}/{len(frames)}] rendered {fid} ✓")
        clips.append(clip)
    cache_f.parent.mkdir(parents=True, exist_ok=True)
    cache_f.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    out = Path(out) if out else (cdir / "renders" / f"{comp}.mp4")
    _log(f"stitching {len(clips)} clip(s){' + BGM' if bgm else ''}{' + captions' if captions else ''}…")
    ok = concat_clips(clips, out, cdir, bgm)
    cap_used = False
    if ok and captions:                                    # captions = ONE full-length transparent overlay
        overlay = render_caption_overlay(comp, quality=quality)
        if overlay:
            capped = out.with_name(out.stem + ".capped.mp4")
            if composite_captions(out, overlay, capped):
                capped.replace(out)
                cap_used = True
    msg = (f"incremental render: {rendered} rendered, {reused} reused, {len(clips)} stitched"
           f"{' + captions' if cap_used else ''} → {out}")
    print(msg)
    _log(msg if ok else "stitch FAILED (is index.html built? run hf-finish once)")
    return {"ok": ok, "mp4": str(out), "rendered": rendered, "reused": reused, "captions": cap_used}


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan hf-render", description="Incremental final render (per-frame clips → stitch).")
    ap.add_argument("comp")
    ap.add_argument("--only", help="comma-separated frame ids to force-re-render (edit just these)")
    ap.add_argument("--no-bgm", action="store_true")
    ap.add_argument("--quality", default="high", choices=["draft", "standard", "high"],
                    help="per-frame render quality (default high = canonical; draft = fast preview loop)")
    ap.add_argument("--no-captions", action="store_true", help="skip the caption overlay (faster iteration)")
    a = ap.parse_args()
    render_incremental(a.comp, only=(a.only.split(",") if a.only else None), bgm=not a.no_bgm,
                       quality=a.quality, captions=not a.no_captions)


if __name__ == "__main__":
    main()
