"""Sound design stage — music bed + VO ducking + transition SFX (SOTA #1).

The invisible half of a good essay: a music bed whose track matches the
video's energy arc (from the tempo system's per-scene energies), ducked under
the narration with a real sidechain compressor (not a constant gain), plus
gentle noise-sweep whooshes on section transitions. ONE integration point —
``mix_soundtrack(final_video, plan, ...)`` runs after assembly, so the
standard pipeline, premium mode, and the segment builder all share it.

Music library: ``projects/_library/music/`` — drop license-safe tracks there
(e.g. YouTube Audio Library). Optional ``music.json`` manifest tags tracks:
``[{"file": "name.mp3", "energy": 0.0-1.0, "mood": "...", "tags": [...]}]``;
untagged files default to energy 0.5. Selection: closest mean-energy track,
looped/trimmed to length, 2s fade-in / 4s fade-out.

Opt-in per project (zero surprise): ``project.yaml music:`` —
``auto`` (select from library) · a file path · absent/none (no music).
``music_gain_db`` (default -14) and ``sfx: false`` tune the mix.
"""

from __future__ import annotations

import json
import logging
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MUSIC_LIBRARY = Path("projects/_library/music")
SFX_LIBRARY = Path("projects/_library/sfx")


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _ffprobe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                        "-show_format", str(path)], capture_output=True, text=True)
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


# --- music library -------------------------------------------------------------

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}


def load_music_library(library: Path = None) -> List[Dict[str, Any]]:
    """Tracks in the music library, manifest-tagged where available."""
    library = Path(library) if library else MUSIC_LIBRARY
    if not library.exists():
        return []
    manifest = {}
    mpath = library / "music.json"
    if mpath.exists():
        try:
            for entry in json.loads(mpath.read_text(encoding="utf-8")):
                manifest[entry.get("file", "")] = entry
        except Exception as exc:
            logger.warning("music.json unreadable: %s", exc)
    tracks = []
    for f in sorted(library.iterdir()):
        if f.suffix.lower() not in AUDIO_EXTS:
            continue
        entry = manifest.get(f.name, {})
        tracks.append({"path": f, "file": f.name,
                       "energy": float(entry.get("energy", 0.5)),
                       "mood": entry.get("mood", ""),
                       "tags": entry.get("tags", [])})
    return tracks


def section_energies(plan: Dict[str, Any]) -> List[Tuple[float, float, float]]:
    """[(start_s, end_s, mean_energy)] per section, from aligned windows."""
    out = []
    for scenes in (plan.get("sections") or {}).values():
        if not isinstance(scenes, list) or not scenes:
            continue
        try:
            start = min(float(s.get("start_seconds") or 0) for s in scenes)
            end = max(float(s.get("end_seconds") or 0) for s in scenes)
        except (TypeError, ValueError):
            continue
        energies = [float(s.get("energy") or 0.5) for s in scenes
                    if isinstance(s, dict)]
        out.append((start, end, sum(energies) / max(1, len(energies))))
    return out


def select_track(tracks: List[Dict[str, Any]], plan: Dict[str, Any],
                 mood: str = "") -> Optional[Dict[str, Any]]:
    """Closest mean-energy track (mood filter first when given)."""
    if not tracks:
        return None
    pool = tracks
    if mood:
        tagged = [t for t in tracks
                  if mood.lower() in (t["mood"].lower(), *[x.lower() for x in t["tags"]])]
        if tagged:
            pool = tagged
    sections = section_energies(plan)
    target = (sum(e for _, _, e in sections) / len(sections)) if sections else 0.5
    return min(pool, key=lambda t: abs(t["energy"] - target))


# --- SFX -----------------------------------------------------------------------

def ensure_whoosh(sfx_dir: Path = None) -> Optional[Path]:
    """A gentle noise-sweep transition whoosh — synthesized once if absent.

    Drop better ones into projects/_library/sfx/whoosh.wav to override.
    """
    sfx_dir = Path(sfx_dir) if sfx_dir else SFX_LIBRARY
    sfx_dir.mkdir(parents=True, exist_ok=True)
    dest = sfx_dir / "whoosh.wav"
    if dest.exists():
        return dest
    # pink-ish noise, band-swept + faded: reads as air movement, not static
    r = subprocess.run(
        [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "anoisesrc=color=pink:duration=1.2:amplitude=0.35",
         "-af", ("lowpass=f=2400,highpass=f=180,"
                 "afade=t=in:st=0:d=0.55:curve=qsin,"
                 "afade=t=out:st=0.55:d=0.65:curve=qsin"),
         "-ar", "44100", str(dest)], capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        logger.warning("whoosh synthesis failed: %s", r.stderr[-200:])
        return None
    return dest


# --- the mix -------------------------------------------------------------------

def mix_soundtrack(video: Path, plan: Dict[str, Any], out: Path = None, *,
                   music: Optional[Path] = None, music_gain_db: float = -12.0,
                   sfx: bool = True, mood: str = "",
                   library: Path = None) -> Path:
    """Lay a ducked music bed (+ transition whooshes) under a finished video.

    The track is loudness-normalized (-16 LUFS) BEFORE ``music_gain_db`` is
    applied, so the gain means the same thing for every library track; the
    sidechain then ducks it moderately under the narration (audible bed, not
    wallpaper — swells in pauses). ``music``: explicit path, or None to
    auto-select from the library. Returns ``out`` (defaults to in-place
    replace). The video stream is stream-copied — never re-encoded.
    """
    video = Path(video)
    replace = out is None
    out = Path(out) if out else video.with_name(video.stem + ".mix.mp4")

    track = Path(music) if music else None
    if track is None:
        chosen = select_track(load_music_library(library), plan, mood=mood)
        if not chosen:
            raise RuntimeError(
                "no music available — drop license-safe tracks into "
                f"{MUSIC_LIBRARY} (e.g. from the YouTube Audio Library)")
        track = chosen["path"]
        logger.info("music: %s (energy %.2f)", chosen["file"], chosen["energy"])
    if not track.exists():
        raise RuntimeError(f"music track not found: {track}")

    duration = _ffprobe_duration(video)
    gain = 10 ** (music_gain_db / 20.0)

    inputs = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
              "-i", str(video), "-stream_loop", "-1", "-i", str(track)]
    # music chain: trim to length, level, fade in/out, then DUCK under the VO
    # with a real sidechain compressor keyed by the narration track.
    fade_out_start = max(0.0, duration - 4.0)
    graph = (
        f"[1:a]atrim=0:{duration:.3f},"
        f"loudnorm=I=-16:TP=-2:LRA=11,volume={gain:.4f},"
        f"afade=t=in:st=0:d=2,afade=t=out:st={fade_out_start:.3f}:d=4[mus];"
        f"[mus][0:a]sidechaincompress=threshold=0.04:ratio=4:attack=25:"
        f"release=400:makeup=1[duck]"
    )
    mix_ins = "[0:a][duck]"
    n_mix = 2

    events: List[float] = []
    if sfx:
        whoosh = ensure_whoosh()
        boundaries = [s for s, _e, _en in section_energies(plan) if s > 1.0]
        if whoosh and boundaries:
            events = sorted(boundaries)[:24]
            for j, t in enumerate(events):
                inputs += ["-i", str(whoosh)]
                delay_ms = max(0, int((t - 0.45) * 1000))   # land ON the cut
                graph += (f";[{2 + j}:a]volume=0.5,adelay={delay_ms}|{delay_ms},"
                          f"apad=whole_dur={duration:.3f}[sfx{j}]")
                mix_ins += f"[sfx{j}]"
                n_mix += 1

    graph += (f";{mix_ins}amix=inputs={n_mix}:duration=first:"
              f"dropout_transition=3:normalize=0[a]")

    cmd = inputs + ["-filter_complex", graph, "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{duration:.3f}", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"soundtrack mix failed: {r.stderr[-400:]}")

    if replace:
        out.replace(video)
        out = video
    logger.info("soundtrack: music + %d transition sfx -> %s", len(events), out)
    return out


def resolve_music_config(project_path: Path) -> Dict[str, Any]:
    """project.yaml music settings: {enabled, music(path|None), gain, sfx, mood}."""
    cfg = {"enabled": False, "music": None, "gain": -14.0, "sfx": True, "mood": ""}
    try:
        import yaml
        meta = yaml.safe_load(
            (Path(project_path) / "project.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        return cfg
    music = meta.get("music")
    if not music or str(music).lower() in ("none", "false", "off"):
        return cfg
    cfg["enabled"] = True
    if str(music).lower() != "auto":
        p = Path(str(music))
        cfg["music"] = p if p.is_absolute() else Path(project_path) / p
    cfg["gain"] = float(meta.get("music_gain_db", -14.0))
    cfg["sfx"] = meta.get("sfx", True) is not False
    cfg["mood"] = str(meta.get("music_mood", "") or "")
    return cfg
