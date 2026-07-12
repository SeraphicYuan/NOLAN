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
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .edit import _comp_dir, _frames_dir, _scaffold_preview, list_frames, load_frame_spec


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
    """Root <video class=clip> tags (track-index 0 = behind the frame) for a frame's grounds."""
    return "".join(
        f'<video class="clip" src="{g["src"]}" data-start="{g["start"]}" data-duration="{g["dur"]}" '
        f'data-track-index="0" muted playsinline></video>' for g in grounds)


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


def render_one(comp: str, frame_id: str) -> Optional[Path]:
    """Render ONE frame to a ground+voice-accurate clip (compositions/frames/<id>.clip.mp4)."""
    pdir = _scaffold_preview(comp, frame_id)               # frame HTML + voice + assets (no grounds yet)
    idx = pdir / "index.html"
    idx.write_text(inject_grounds(idx.read_text(encoding="utf-8"), frame_grounds(comp, frame_id)), encoding="utf-8")
    clip = _frames_dir(comp) / f"{frame_id}.clip.mp4"
    subprocess.run(["npx", "--yes", "hyperframes@latest", "render", str(pdir), "--output", str(clip)],
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
    subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(listf), "-c:v", "libx264",
                    "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(stitched)],
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


def render_incremental(comp: str, only: Optional[List[str]] = None, bgm: bool = True) -> Dict:
    """Render each frame to a clip (skipping unchanged via a sig cache), concat → renders/<comp>.mp4, re-lay BGM.
    `only` forces a re-render of those frame ids even if their sig is unchanged."""
    cdir = _comp_dir(comp)
    frames = [f["id"] if isinstance(f, dict) else f for f in list_frames(comp)]
    cache_f = cdir / "compositions" / "_preview" / "clip_cache.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    only = set(only or [])
    clips, rendered, reused = [], 0, 0
    for fid in frames:
        sig = frame_sig(comp, fid)
        clip = _frames_dir(comp) / f"{fid}.clip.mp4"
        if clip.exists() and cache.get(fid) == sig and fid not in only:
            reused += 1
        else:
            if not render_one(comp, fid):
                raise RuntimeError(f"incremental render: frame {fid} failed to render")
            cache[fid] = sig
            rendered += 1
        clips.append(clip)
    cache_f.parent.mkdir(parents=True, exist_ok=True)
    cache_f.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    out = cdir / "renders" / f"{comp}.mp4"
    ok = concat_clips(clips, out, cdir, bgm)
    print(f"incremental render: {rendered} rendered, {reused} reused, {len(clips)} stitched → {out}")
    return {"ok": ok, "mp4": str(out), "rendered": rendered, "reused": reused}


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan hf-render", description="Incremental final render (per-frame clips → stitch).")
    ap.add_argument("comp")
    ap.add_argument("--only", help="comma-separated frame ids to force-re-render (edit just these)")
    ap.add_argument("--no-bgm", action="store_true")
    a = ap.parse_args()
    render_incremental(a.comp, only=(a.only.split(",") if a.only else None), bgm=not a.no_bgm)


if __name__ == "__main__":
    main()
