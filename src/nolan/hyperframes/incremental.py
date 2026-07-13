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
    """This frame's video-ground clips with LOCAL (frame-relative) start/dur (from the retimed spec)."""
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    out = []
    for sc in fr.get("scenes", []):
        g = (sc.get("data", {}) or {}).get("ground", {}) or {}
        if g.get("kind") == "video" and g.get("src"):
            out.append({"src": g["src"], "start": round(float(sc.get("start", 0) or 0), 3),
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


def frame_sig(comp: str, frame_id: str) -> str:
    """Content hash of the frame HTML + its ground srcs — the cache key for 'unchanged → reuse the clip'."""
    h = hashlib.sha1()
    html = _frames_dir(comp) / f"{frame_id}.html"
    h.update(html.read_bytes() if html.exists() else b"")
    for g in frame_grounds(comp, frame_id):
        h.update(f"{g['src']}|{g['start']}|{g['dur']}".encode())
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


def render_one(comp: str, frame_id: str, quality: str = "high") -> Optional[Path]:
    """Render ONE frame to a ground+voice clip (compositions/frames/<id>.clip.mp4). CAPTION-FREE — captions
    are a separate full-length overlay composited at assembly (render_caption_overlay/composite_captions);
    keeping the clip caption-free lets the concat stay a stream-copy.

    `quality` matches `hf-finish` ("high" = x264 slow/CRF15) so a per-frame clip is per-pixel identical
    to that frame's window in the monolith — the precondition for the sliced render being canonical."""
    pdir = _scaffold_preview(comp, frame_id)               # frame HTML + voice + assets
    idx = pdir / "index.html"
    idx.write_text(inject_grounds(idx.read_text(encoding="utf-8"), frame_grounds(comp, frame_id)),
                   encoding="utf-8")
    clip = _frames_dir(comp) / f"{frame_id}.clip.mp4"
    subprocess.run(["npx", "--yes", "hyperframes@latest", "render", str(pdir),
                    "--quality", quality, "--output", str(clip)],
                   cwd=str(pdir), capture_output=True, text=True, encoding="utf-8", errors="replace",
                   shell=(os.name == "nt"))
    return clip if clip.exists() else None


def concat_clips(clips: List[Path], out: Path, comp_dir: Path, bgm: bool = True) -> bool:
    """Concat the per-frame clips → out, then (soft) re-lay the BGM bed under the concatenated voice."""
    ff = _ffmpeg()
    listf = out.parent / "_concat.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    listf.write_text("".join(f"file '{Path(c).resolve().as_posix()}'\n" for c in clips), encoding="utf-8")
    stitched = out.with_name(out.stem + ".nobgm.mp4") if bgm else out
    # STREAM-COPY the per-frame clips (same renderer → identical codec params) so the stitch adds ZERO
    # generational loss — the frame clips ARE high-quality, the concat must not re-encode them.
    subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(listf), "-c", "copy", str(stitched)],
                   capture_output=True)
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
                       quality: str = "high", captions: bool = True) -> Dict:
    """Render each frame to a clip (skipping unchanged via a sig cache), concat → renders/<comp>.mp4, re-lay
    BGM, and (if `captions`) composite the full-length caption overlay. `only` forces a re-render of those
    frame ids even if their sig is unchanged. `quality` is passed to each per-frame render ("high" for a
    canonical/deliverable stitch, "draft" for a fast preview loop). `captions=False` skips the overlay for a
    faster iteration loop (captions are optional — YouTube auto-captions cover the baseline)."""
    cdir = _comp_dir(comp)
    frames = [f["id"] if isinstance(f, dict) else f for f in list_frames(comp)]
    cache_f = cdir / "compositions" / "_preview" / "clip_cache.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    only = set(only or [])
    clips, rendered, reused = [], 0, 0
    for fid in frames:
        key = f"{quality}:{frame_sig(comp, fid)}"          # quality is part of the cache key: a draft clip
        clip = _frames_dir(comp) / f"{fid}.clip.mp4"        # must not be reused when a high stitch is asked for
        if clip.exists() and cache.get(fid) == key and fid not in only:
            reused += 1
        else:
            if not render_one(comp, fid, quality=quality):
                raise RuntimeError(f"incremental render: frame {fid} failed to render")
            cache[fid] = key
            rendered += 1
        clips.append(clip)
    cache_f.parent.mkdir(parents=True, exist_ok=True)
    cache_f.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    out = cdir / "renders" / f"{comp}.mp4"
    ok = concat_clips(clips, out, cdir, bgm)
    cap_used = False
    if ok and captions:                                    # captions = ONE full-length transparent overlay
        overlay = render_caption_overlay(comp, quality=quality)
        if overlay:
            capped = out.with_name(out.stem + ".capped.mp4")
            if composite_captions(out, overlay, capped):
                capped.replace(out)
                cap_used = True
    print(f"incremental render: {rendered} rendered, {reused} reused, {len(clips)} stitched"
          f"{' + captions' if cap_used else ''} → {out}")
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
