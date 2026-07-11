"""Post-assemble MEDIA step — mount video grounds + comparison video sides into a composed index.html.

Runs AFTER `assemble-index`, BEFORE `hyperframes render` (motion video can only live at the index
ROOT — archetype B — never inside a frame sub-comp):

  1. collect scenes with `ground:{kind:"video", src}` from the frame specs → root <video> clips,
     positioned on the GLOBAL timeline (frame offset from audio_meta.json + the scene's local start)
     and mounted BEHIND the frame track by inject_root_video.py.
  2. run inject_comparison_videos.py to fill the composer's comparison video-side holes.

Both injectors are idempotent, so re-running is safe.

  python -X utf8 assemble_media.py <project_dir>
"""
import json
import subprocess
import sys
from pathlib import Path


def _frame_durations(comp_dir: Path, spec_files):
    """Per-frame durations in spec order — from audio_meta.json (authoritative, = what
    sync-durations/assemble-index used) if present, else the spec's own frame dur."""
    meta = comp_dir / "audio_meta.json"
    if meta.exists():
        try:
            voices = json.loads(meta.read_text(encoding="utf-8")).get("voices", [])
            durs = [float(v.get("duration_s", 0) or 0) for v in sorted(voices, key=lambda v: v.get("frame", 0))]
            if len(durs) >= len(spec_files):
                return durs
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    out = []
    for sf in spec_files:
        spec = json.loads(sf.read_text(encoding="utf-8"))
        out.append(sum(float(fr.get("dur", 0) or 0) for fr in spec.get("frames", [])))
    return out


def collect_video_grounds(comp_dir: Path):
    """Root <video> clips for every scene whose ground is a pool clip, on the global timeline."""
    fdir = comp_dir / "compositions" / "frames"
    spec_files = sorted(fdir.glob("*.spec.json"))
    durs = _frame_durations(comp_dir, spec_files)
    clips, offset = [], 0.0
    for i, sf in enumerate(spec_files):
        spec = json.loads(sf.read_text(encoding="utf-8"))
        for fr in spec.get("frames", []):
            for sc in fr.get("scenes", []):
                g = (sc.get("data", {}) or {}).get("ground", {}) or {}
                if g.get("kind") == "video" and g.get("src"):
                    clips.append({"src": g["src"],
                                  "start": round(offset + float(sc.get("start", 0) or 0), 3),
                                  "duration": round(float(sc.get("dur", 0) or 0), 3)})
        offset += durs[i] if i < len(durs) else 0.0
    return clips


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python -X utf8 assemble_media.py <project_dir>")
    comp = Path(sys.argv[1])
    bridge = Path(__file__).resolve().parent
    index = comp / "index.html"
    if not index.exists():
        sys.exit(f"no index.html at {index} — run assemble-index first")

    clips = collect_video_grounds(comp)
    if clips:
        print(f"root video grounds: {len(clips)} → inject_root_video")
        subprocess.run([sys.executable, "-X", "utf8", str(bridge / "inject_root_video.py"),
                        "--index", str(index), "--clips", json.dumps(clips)], check=True)
    else:
        print("no ground:{kind:video} scenes")

    r = subprocess.run([sys.executable, "-X", "utf8", str(bridge / "inject_comparison_videos.py"), str(comp)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("comparison videos:", (r.stdout + r.stderr).strip()[-300:])


if __name__ == "__main__":
    main()
