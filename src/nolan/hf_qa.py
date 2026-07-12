"""HyperFrames render QA — the deterministic half of "the gate stops at the SPEC, not the pixels."

The style-contract linter scores compositions/frames/*.spec.json; it never inspects the render. This
module inspects the RENDER (and the assets it will mount), catching defects a passing lint can't see.

Shipped first (no deps, ffmpeg only):
  - FREEZE guard   — every video ground / comparison video-side clip must be AT LEAST as long as the
                     scene window it fills, or it freezes on its last frame for the remainder.
  - AUDIO integrity— the final render must have an audio stream, and the audio must run the full length
                     (audio_dur ≈ video_dur) — no silent tail, no truncated narration.

Perceptual checks (not-blank / text-contrast / temporal-drift) + the labeled contact sheet land in a
follow-up; this is the cheap deterministic backstop the author was running by hand every time.

  python -X utf8 -m nolan.hf_qa <comp_dir>
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_TIME_RE = re.compile(r"time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _ffmpeg() -> str:
    """The bundled imageio-ffmpeg binary (Windows-side, same one the renderer/verify use)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


@dataclass
class MediaInfo:
    duration: float = 0.0            # container duration (s)
    has_audio: bool = False
    audio_duration: float = 0.0      # decoded audio-stream duration (s), 0 if none


def probe(path: Path, ffmpeg: Optional[str] = None) -> MediaInfo:
    """Container duration + audio presence (fast, from `-i`); audio-stream duration via a null decode."""
    ff = ffmpeg or _ffmpeg()
    p = str(Path(path))
    info = MediaInfo()
    r = subprocess.run([ff, "-i", p], capture_output=True, text=True, encoding="utf-8", errors="replace")
    txt = r.stderr or ""
    m = _DUR_RE.search(txt)
    if m:
        h, mm, s = m.groups()
        info.duration = int(h) * 3600 + int(mm) * 60 + float(s)
    info.has_audio = bool(re.search(r"Stream #\S+: Audio:", txt))
    if info.has_audio:                # decode just the audio stream to get its true length
        r2 = subprocess.run([ff, "-i", p, "-map", "0:a:0", "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        times = _TIME_RE.findall(r2.stderr or "")
        if times:
            h, mm, s = times[-1]
            info.audio_duration = int(h) * 3600 + int(mm) * 60 + float(s)
    return info


# --- what to check --------------------------------------------------------------------------------
@dataclass
class VideoUse:
    frame: str
    scene: str
    src: str                          # comp-relative
    window: float                     # seconds the clip is on screen (= scene dur)
    kind: str                         # "ground" | "comparison"


def video_uses(comp_dir: Path) -> List[VideoUse]:
    """Every place a video actually plays: a `ground:{kind:video}` or a comparison side `type:video`."""
    fdir = Path(comp_dir) / "compositions" / "frames"
    out: List[VideoUse] = []
    for sf in sorted(fdir.glob("*.spec.json")):
        try:
            spec = json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for fr in spec.get("frames", []):
            for sc in fr.get("scenes", []):
                data = sc.get("data", {}) or {}
                win = float(sc.get("dur", 0) or 0)
                g = data.get("ground", {}) or {}
                if g.get("kind") == "video" and g.get("src"):
                    out.append(VideoUse(fr.get("id", sf.stem), sc.get("id", "?"), g["src"], win, "ground"))
                for side in ("left", "right"):
                    s = data.get(side, {}) or {}
                    if isinstance(s, dict) and s.get("type") == "video" and s.get("src"):
                        out.append(VideoUse(fr.get("id", sf.stem), sc.get("id", "?"), s["src"], win, "comparison"))
    return out


def check_freeze(comp_dir: Path, probe_fn: Callable[[Path], MediaInfo] = probe, tol: float = 0.15) -> List[Dict]:
    """A clip shorter than its on-screen window freezes on its last frame — flag it."""
    comp_dir = Path(comp_dir)
    rows = []
    for u in video_uses(comp_dir):
        clip = (comp_dir / u.src)
        healed = clip.with_name(clip.stem + ".filled.mp4")   # assemble_media's pre-render freeze-heal writes this
        if healed.exists():                                   # probe what actually RENDERS, not the pre-heal short clip
            clip = healed
        dur = probe_fn(clip).duration if clip.exists() else 0.0
        ok = clip.exists() and dur + tol >= u.window
        rows.append({"frame": u.frame, "scene": u.scene, "src": u.src, "kind": u.kind,
                     "clip_dur": round(dur, 2), "window": round(u.window, 2), "exists": clip.exists(),
                     "healed": clip == healed, "ok": ok})
    return rows


def check_render(mp4: Path, expected_total: Optional[float] = None,
                 probe_fn: Callable[[Path], MediaInfo] = probe, tol: float = 0.5) -> Dict:
    """The final render must carry audio for its full length (no silent tail / truncated VO)."""
    info = probe_fn(Path(mp4))
    audio_matches_video = info.has_audio and abs(info.audio_duration - info.duration) <= max(tol, info.duration * 0.01)
    length_ok = expected_total is None or abs(info.duration - expected_total) <= max(tol, expected_total * 0.01)
    return {"has_audio": info.has_audio, "video_dur": round(info.duration, 2),
            "audio_dur": round(info.audio_duration, 2), "audio_matches_video": audio_matches_video,
            "length_ok": length_ok, "ok": info.has_audio and audio_matches_video and length_ok}


def qa(comp_dir: Path, probe_fn: Callable[[Path], MediaInfo] = probe) -> Dict:
    comp_dir = Path(comp_dir)
    freeze = check_freeze(comp_dir, probe_fn)
    total = None
    meta = comp_dir / "audio_meta.json"
    if meta.exists():
        try:
            total = json.loads(meta.read_text(encoding="utf-8")).get("total_s")
        except (json.JSONDecodeError, OSError):
            total = None
    renders = sorted((comp_dir / "renders").glob("*.mp4")) if (comp_dir / "renders").is_dir() else []
    render = check_render(renders[-1], total, probe_fn) if renders else None
    freeze_ok = all(r["ok"] for r in freeze)
    render_ok = render["ok"] if render else True
    return {"comp": comp_dir.name, "freeze": freeze, "render": render,
            "render_file": renders[-1].name if renders else None,
            "overall_pass": freeze_ok and render_ok,
            "n_fail": sum(1 for r in freeze if not r["ok"]) + (0 if render_ok else 1)}


def format_report(rep: Dict) -> str:
    lines = [f"HF QA — {rep['comp']} — {'PASS' if rep['overall_pass'] else str(rep['n_fail']) + ' FAIL'}"]
    lines.append("  FREEZE guard (clip ≥ scene window):")
    if not rep["freeze"]:
        lines.append("    · no video grounds / comparison video sides")
    for r in rep["freeze"]:
        mark = "✓" if r["ok"] else "✗"
        why = "" if r["ok"] else (" — MISSING" if not r["exists"] else f" — clip {r['clip_dur']}s < window {r['window']}s (freezes)")
        lines.append(f"    {mark} {r['frame']}/{r['scene']} [{r['kind']}] {r['src']}{why}")
    if rep["render"]:
        r = rep["render"]
        mark = "✓" if r["ok"] else "✗"
        lines.append(f"  AUDIO integrity ({rep['render_file']}): {mark} "
                     f"audio={r['has_audio']} video_dur={r['video_dur']}s audio_dur={r['audio_dur']}s "
                     f"match={r['audio_matches_video']} length_ok={r['length_ok']}")
    else:
        lines.append("  AUDIO integrity: · no render yet")
    return "\n".join(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hf_qa", description="Deterministic HyperFrames render QA")
    ap.add_argument("comp", help="composition dir (…/videos/<slug>)")
    a = ap.parse_args()
    rep = qa(Path(a.comp))
    print(format_report(rep))
    raise SystemExit(0 if rep["overall_pass"] else 1)


if __name__ == "__main__":
    main()
