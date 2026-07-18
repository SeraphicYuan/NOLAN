"""Clip-driven FRAME transitions for the compose-first HyperFrames pipeline — a matte or reveal CLIP
wipes between two rendered frame clips at the concat seam (an ffmpeg TWO-CLIP composite). Distinct from
the within-frame GSAP transitions in compose.TRANSITIONS (transform/opacity only, reveal-by-uncover):
those never composite two scenes' pixels; the only place two rendered clips meet as pixels is
incremental.concat_clips (the frame boundary). So clip transitions are FRAME-to-FRAME only.

  - type "luma"   (ink/liquid matte): maskedmerge(A, B, matte-luma) — B revealed where the matte → white.
  - type "chroma" (green-screen reveal, e.g. a fire that burns and reveals a green gate): B revealed
                  through the green region, with the keyed foreground (the fire) screened on top.

The transition CLIPS live in projects/_library/transitions/ + a transitions.json manifest (the registry):
each a named kind carrying {file, type, chroma?, dur, provenance}. Repo-anchored (NOT cwd). Mirrors the
overlay-plate library; a fresh clone repopulates via `nolan effects fetch-plates` siblings later.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[3]                 # src/nolan/hyperframes/transitions.py -> repo
TRANS_LIBRARY = REPO / "projects" / "_library" / "transitions"
_MANIFEST = "transitions.json"
_VENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]


def _ffmpeg() -> str:
    from nolan.ffmpeg_utils import FFMPEG
    return FFMPEG


def load_transitions(library: Path = None) -> List[Dict[str, Any]]:
    """Every clip-driven transition kind in the library (manifest merged with a dir scan). Each:
    {kind, file, path, type(luma|chroma), chroma, dur, desc, when_to_use, license, source, url}."""
    library = Path(library) if library else TRANS_LIBRARY
    if not library.exists():
        return []
    manifest: Dict[str, Dict[str, Any]] = {}
    mpath = library / _MANIFEST
    if mpath.exists():
        try:
            for e in json.loads(mpath.read_text(encoding="utf-8")):
                manifest[e.get("file", "")] = e
        except (json.JSONDecodeError, OSError):
            pass
    out: List[Dict[str, Any]] = []
    for f in sorted(library.iterdir()):
        if f.suffix.lower() not in {".mp4", ".mov", ".webm"}:
            continue
        e = manifest.get(f.name, {})
        out.append({"kind": e.get("kind", f.stem.split("-")[0]), "file": f.name, "path": f,
                    "type": e.get("type", "luma"), "chroma": e.get("chroma"), "invert": e.get("invert", False),
                    "clip_len": e.get("clip_len"), "dur": e.get("dur", 1.0),
                    "desc": e.get("desc", ""), "when_to_use": e.get("when_to_use", ""),
                    "license": e.get("license", ""), "source": e.get("source", ""), "url": e.get("url")})
    return out


def resolve(kind: str, library: Path = None) -> Optional[Dict[str, Any]]:
    for t in load_transitions(library):
        if t["kind"] == kind:
            return t
    return None


def transition_kinds(library: Path = None) -> List[str]:
    return [t["kind"] for t in load_transitions(library)]


def transition_segment(prev_clip, next_clip, kind, out, *, dur: float = 1.0,
                       size=(1920, 1080), fps: int = 30, library: Path = None) -> Path:
    """Render the DUR-second transition SEGMENT that replaces the seam: the tail of `prev_clip` wiping to
    the head of `next_clip`, driven by the transition clip. luma → maskedmerge; chroma → reveal-through-
    green + the keyed foreground screened on top. Returns `out` (encoded to match the frame clips)."""
    e = resolve(kind, library)
    if not e:
        raise ValueError(f"unknown transition kind {kind!r} (have: {', '.join(transition_kinds(library))})")
    W, H = size
    ff, matte = _ffmpeg(), str(e["path"])
    clen = float(e.get("clip_len") or dur) or dur
    sp = dur / clen                                            # speed the matte's FULL sweep into `dur`
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},setpts=PTS-STARTPTS"
    mpts = f"setpts={sp:.4f}*(PTS-STARTPTS)"                   # matte time-remap so its whole reveal fills the window
    if e["type"] == "luma":                                    # B revealed where the matte luma → white
        # work in gbrp so the (gray) matte is a luma mask replicated across R=G=B — else maskedmerge
        # desaturates the colour inputs to the gray mask. `invert` negates for clips that sweep white→black.
        neg = ",negate" if e.get("invert") else ""
        fc = (f"[0:v]{fit},format=gbrp[a];[1:v]{fit},format=gbrp[b];"
              f"[2:v]scale={W}:{H},fps={fps},{mpts},format=gray{neg},format=gbrp[m];"
              f"[a][b][m]maskedmerge,format=yuv420p[v]")
    else:                                                      # chroma reveal (green gate → B, fire on top)
        col = e.get("chroma") or "0x00b140"
        # derive a GREEN mask → maskedmerge A/B through it (the proven luma path), then screen the fire.
        fc = (f"[0:v]{fit},format=gbrp[a];[1:v]{fit},format=gbrp[b];"
              f"[2:v]scale={W}:{H},fps={fps},{mpts},split[t1][t2];"
              f"[t1]chromakey={col}:0.20:0.08,format=rgba,alphaextract,negate,format=gbrp[gmask];"  # white where GREEN
              f"[a][b][gmask]maskedmerge[wipe];"                                         # A where not-green, B where green
              f"[t2]chromakey={col}:0.20:0.08[k2];"                                      # fire opaque, green transparent
              f"color=black:s={W}x{H}:d={dur}:r={fps}[blk];[blk][k2]overlay=format=auto[fb];"  # fire on black (green dropped)
              f"[fb]format=gbrp[fg];[wipe][fg]blend=all_mode=screen,format=yuv420p[v]")  # screen fire (RGB) on top
    cmd = [ff, "-y", "-sseof", f"-{dur:.3f}", "-t", f"{dur:.3f}", "-i", str(prev_clip),   # prev's TAIL
           "-t", f"{dur:.3f}", "-i", str(next_clip), "-i", matte,   # whole matte; `mpts` speeds it to `dur`
           "-filter_complex", fc, "-map", "[v]", "-t", f"{dur:.3f}", "-r", str(fps), *_VENC, str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not Path(out).exists() or Path(out).stat().st_size == 0:
        err = (r.stderr or "")
        line = next((ln for ln in err.splitlines() if "rror" in ln or "nvalid" in ln or "o such" in ln), "")
        raise RuntimeError(f"transition_segment failed: {line or err[-400:]}")
    return Path(out)
