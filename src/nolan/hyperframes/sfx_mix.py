"""nolan.hyperframes.sfx_mix — the DUCKED SFX post-mix (NOLAN-side, no render-skill change).

The HF render mounts SFX as flat, parallel ``<audio>`` tracks: they sum with the narration,
there is no VO-ducking, so a cue over speech must be pushed HOT to cut through and can over-punch
(the data-punch that measured +4097 over VO). This is the pro alternative — render **video + VO
only**, then mix the SFX ON TOP with the VO **sidechain-ducked** under each hit, so every cue sits
at its natural (registry) level and the voice dips politely to make room.

Why a post-mix and not a render-side duck: once the renderer bakes VO + SFX into one track you can
no longer separate them to duck one under the other. So we keep SFX OUT of the render and add them
here, where an ffmpeg sidechain can duck the (VO-only) render audio against the SFX sum.

Timing is untouched — this is amplitude only. Every alignment (scene-on-word, captions, word-sync)
is driven by word timestamps and is unaffected; the VO wav plays at the exact same time, it just
dips in level for a few hundred ms under a cue. Reuses :func:`collect_scene_sfx_events` for
staging + bed-tiling; the render-mount path (:func:`apply_scene_sfx`) is the flat, no-duck
alternative and the two are mutually exclusive (don't mount AND post-mix, or you double the cues).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from nolan.sound.registry import BY_ID


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _frame_starts(audio_meta: Dict[str, Any]) -> Dict[int, float]:
    """Absolute start (s) of each frame = cumulative VO duration (narration owns duration)."""
    starts: Dict[int, float] = {}
    acc = 0.0
    for v in sorted(audio_meta.get("voices", []), key=lambda x: x.get("frame", 0)):
        starts[int(v.get("frame", 0))] = acc
        acc += float(v.get("duration_s") or 0)
    return starts


def _events_absolute(pdir: Path, audio_meta: Dict[str, Any],
                     events: List[Dict[str, Any]]) -> List[Tuple[float, Path, float]]:
    """Map frame-local sfx events → (absolute_time_s, file, volume). Volume is the REGISTRY
    (ducked-tuned) gain, NOT the hot hf_gain the render-mount path uses — the duck makes room,
    so cues play at their honest level."""
    starts = _frame_starts(audio_meta)
    out: List[Tuple[float, Path, float]] = []
    for e in events:
        fs = starts.get(int(e.get("frame", -1)))
        f = pdir / e["file"]
        if fs is None or not f.exists():
            continue
        cue = BY_ID.get(e.get("kind"))
        vol = float(cue.gain) if cue else float(e.get("volume") or 0.3)
        out.append((round(fs + float(e.get("offset_s") or 0), 3), f, vol))
    out.sort(key=lambda t: t[0])
    return out


def sfx_mix(comp: str, *, video_in: Optional[str] = None, out: Optional[str] = None,
            threshold: float = 0.06, ratio: float = 6.0, attack: float = 20.0,
            release: float = 300.0) -> Dict[str, Any]:
    """Mix the comp's scene SFX onto a VO-only render with the VO sidechain-ducked under each cue.

    ``video_in`` defaults to ``renders/video.mp4`` (must be a VO-only render — no mounted SFX),
    ``out`` to ``renders/video.sfx.mp4``. The sidechain params mirror the Director's mixer
    (gentle, fast-attack, ~300ms release). Returns ``{out, events, unresolved}``.
    """
    from nolan.hyperframes.sound import collect_scene_sfx_events

    c = collect_scene_sfx_events(comp)
    pdir: Path = c["pdir"]
    vin = Path(video_in) if video_in else pdir / "renders" / "video.mp4"
    vout = Path(out) if out else pdir / "renders" / "video.sfx.mp4"
    if not vin.exists():
        raise FileNotFoundError(f"sfx_mix: no render at {vin} — render the comp (VO only) first")

    am_path = pdir / "audio_meta.json"
    am = json.loads(am_path.read_text(encoding="utf-8")) if am_path.exists() else {}
    evs = _events_absolute(pdir, am, c["events"])
    if not evs:
        raise RuntimeError("sfx_mix: no SFX to mix — run `sfx_design --apply` first")

    ff = _ffmpeg_exe()
    inputs: List[str] = ["-i", str(vin)]
    filt: List[str] = []
    labels: List[str] = []
    for i, (t, f, v) in enumerate(evs, start=1):
        inputs += ["-i", str(f)]
        ms = max(0, int(round(t * 1000)))
        filt.append(f"[{i}:a]adelay={ms}|{ms},volume={v:.3f}[s{i}]")
        labels.append(f"[s{i}]")
    # sum the SFX, duck the VO-only render audio under that sum, then mix the SFX back on top
    filt.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0[sfx]")
    filt.append(f"[0:a][sfx]sidechaincompress=threshold={threshold}:ratio={ratio}:"
                f"attack={attack}:release={release}[duck]")
    filt.append("[duck][sfx]amix=inputs=2:normalize=0[out]")

    vout.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error", *inputs,
           "-filter_complex", ";".join(filt),
           "-map", "0:v", "-map", "[out]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
           str(vout)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"sfx_mix: ffmpeg failed (rc={r.returncode}): {(r.stderr or '')[-600:]}")
    return {"out": str(vout), "events": len(evs), "unresolved": c["unresolved"]}


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.sfx_mix",
                                 description="Ducked SFX post-mix: render VO-only, then mix SFX "
                                             "with the VO sidechain-ducked under each cue.")
    ap.add_argument("comp")
    ap.add_argument("--video", help="input VO-only render (default renders/video.mp4)")
    ap.add_argument("--out", help="output (default renders/video.sfx.mp4)")
    ap.add_argument("--ratio", type=float, default=6.0, help="duck compression ratio")
    ap.add_argument("--threshold", type=float, default=0.06, help="duck threshold")
    a = ap.parse_args(argv)
    res = sfx_mix(a.comp, video_in=a.video, out=a.out, ratio=a.ratio, threshold=a.threshold)
    print(f"ducked SFX mix → {res['out']}  ({res['events']} cues"
          + (f", {len(res['unresolved'])} unresolved" if res["unresolved"] else "") + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
