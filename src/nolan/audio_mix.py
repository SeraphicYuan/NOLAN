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


# --- SFX auto-cue pass (the deferred decision layer) -------------------------
# Keyword clusters -> ambient cue queries. Reference-video craft: the burning
# scroll gets fire crackle, the voyage gets distant waves — ambience carries
# period texture that stills alone can't. Deterministic; humans edit/delete
# cues in the plan (the sfx field is theirs after authoring).
_SFX_AMBIENCE = [
    (("fire", "burn", "flame", "torch", "hearth"), "fire crackling ambience"),
    (("sea", "wave", "ocean", "ship", "sail", "harbor", "voyage"),
     "ocean waves ambience"),
    (("storm", "rain",), "rain ambience distant"),
    (("thunder",), "thunder rumble distant"),
    (("wind", "desert", "plain"), "wind ambience soft"),
    (("battle", "sword", "army", "war ", "clash", "siege"),
     "distant battle metal ambience"),
    (("crowd", "procession", "forum", "market", "assembly"),
     "crowd murmur ambience"),
    (("horse", "rider", "hooves", "cavalry"), "horse hooves distant"),
    (("bell",), "church bell distant"),
    (("write", "quill", "pen ", "manuscript", "scroll", "letter"),
     "quill pen writing parchment"),
    (("footsteps", "walked", "walking"), "footsteps stone reverb"),
    (("birds", "dawn", "garden", "spring "), "birdsong ambient soft"),
]


def author_sfx_cues(plan: Dict[str, Any], *, max_per_section: int = 2,
                    min_gap_s: float = 20.0, volume: float = 0.22) -> List[tuple]:
    """AUTHOR per-scene ambient sfx cues from narration/visual content.

    The placement layer (:func:`_scene_sfx_cues`) existed with no decision
    layer feeding it — projects shipped with one transition whoosh (the
    diversity audit). Deterministic keyword mapping; discipline: visual
    scenes only, explicit human ``sfx`` always wins, <= ``max_per_section``
    cues per beat, >= ``min_gap_s`` apart, LOW volume (ambience under VO,
    never an event). Mutates the plan; returns [(scene_id, query), ...] so
    the step can report loudly.
    """
    authored: List[tuple] = []
    last_t = -1e9
    for scenes in (plan.get("sections") or {}).values():
        if not isinstance(scenes, list):
            continue
        used = 0
        for s in scenes:
            if not isinstance(s, dict):
                continue
            t0 = float(s.get("start_seconds") or 0.0)
            if s.get("sfx"):
                # a human-authored cue counts toward density spacing too —
                # ambience discipline is about the EAR, not the author
                last_t = max(last_t, t0)
                continue
            if not (s.get("matched_asset") or s.get("generated_asset")
                    or s.get("matched_clip") or s.get("rendered_clip")):
                continue                      # text/graphic scenes stay clean
            if used >= max_per_section:
                break
            if t0 - last_t < min_gap_s:
                continue
            text = " " + ((s.get("narration_excerpt") or "") + " "
                          + (s.get("visual_description") or "")).lower() + " "
            for keys, query in _SFX_AMBIENCE:
                if any(k in text for k in keys):
                    s["sfx"] = {"query": query, "at": 0.0, "volume": volume}
                    authored.append((s.get("id"), query))
                    used += 1
                    last_t = t0
                    break
    return authored


def _scene_sfx_cues(plan: Dict[str, Any]):
    """Yield ``(t_seconds, query, volume)`` from per-scene ``sfx`` cues in the plan.

    A scene may declare ``sfx`` as a string (``"coin pickup"``), a dict
    (``{"query": ..., "at": "start"|"end", "volume": ...}``), or a list of those.
    Opt-in: scenes without an ``sfx`` field contribute nothing, so the default
    soundtrack is unchanged until the Director/designer marks a beat.
    """
    for scenes in (plan.get("sections") or {}).values():
        if not isinstance(scenes, list):
            continue
        for s in scenes:
            if not isinstance(s, dict) or not s.get("sfx"):
                continue
            cue = s["sfx"]
            for it in (cue if isinstance(cue, list) else [cue]):
                if isinstance(it, str):
                    query, at, vol = it, "start", 0.7
                elif isinstance(it, dict):
                    query = it.get("query") or it.get("q") or ""
                    at, vol = it.get("at", "start"), float(it.get("volume", 0.7))
                else:
                    continue
                if not query:
                    continue
                t = (float(s.get("end_seconds") or 0) if at == "end"
                     else float(s.get("start_seconds") or 0))
                yield (round(t, 3), query, vol)


def _source_scene_sfx(plan: Dict[str, Any], provider: str = "freesound"):
    """Source each scene SFX cue via the provider layer → mix events.

    Best-effort: a cue that can't be sourced (no key / no result / offline) is
    skipped with a log, never breaking the soundtrack. Each distinct query is
    sourced once (``source_sfx`` also caches to the library).
    """
    from .sfx_search import source_sfx  # stdlib-only; lazy keeps import light
    events: List[Dict[str, Any]] = []
    cached: Dict[str, Optional[Path]] = {}
    for t, query, vol in _scene_sfx_cues(plan):
        if query not in cached:
            try:
                cached[query] = source_sfx(query, provider=provider)
            except Exception as exc:  # noqa: BLE001
                logger.warning("sfx source failed for %r: %s", query, exc)
                cached[query] = None
        path = cached[query]
        if not path:
            logger.info("sfx cue skipped (unsourced): %r", query)
            continue
        events.append({"t": t, "kind": "sfx", "query": query,
                       "file": str(path), "volume": vol, "lead": 0.0})
    return events


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


# --- authoring (the Director's soundtrack step) --------------------------------

def ensure_riser(sfx_dir: Path = None) -> Optional[Path]:
    """A rising noise swell (~2.2s) that peaks at a cut — synthesized once.

    Drop a better one into projects/_library/sfx/riser.wav to override.
    """
    sfx_dir = Path(sfx_dir) if sfx_dir else SFX_LIBRARY
    sfx_dir.mkdir(parents=True, exist_ok=True)
    dest = sfx_dir / "riser.wav"
    if dest.exists():
        return dest
    r = subprocess.run(
        [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "anoisesrc=color=pink:duration=2.2:amplitude=0.4",
         "-af", ("highpass=f=200,lowpass=f=6000,"
                 "afade=t=in:st=0:d=1.9:curve=exp,afade=t=out:st=1.9:d=0.3"),
         str(dest)], capture_output=True, text=True)
    return dest if r.returncode == 0 and dest.exists() else None


def ensure_hit(sfx_dir: Path = None) -> Optional[Path]:
    """A short low impact thump (~0.4s) for data-punch moments — synthesized once.

    Drop a better one into projects/_library/sfx/hit.wav to override.
    """
    sfx_dir = Path(sfx_dir) if sfx_dir else SFX_LIBRARY
    sfx_dir.mkdir(parents=True, exist_ok=True)
    dest = sfx_dir / "hit.wav"
    if dest.exists():
        return dest
    r = subprocess.run(
        [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=62:duration=0.4",
         "-af", "afade=t=out:st=0.03:d=0.35,volume=1.6,alimiter=limit=0.9",
         str(dest)], capture_output=True, text=True)
    return dest if r.returncode == 0 and dest.exists() else None


# scene treatments that earn a data-punch hit (numbers landing hard)
_HIT_MOTION_EFFECTS = {"stat-over", "bar-compare", "k-shape", "counter",
                       "annotate-stat"}
_HIT_TEMPLATES = {"statistic", "stat_comparison", "bar_chart", "line_chart",
                  "counter"}


def _data_punch_events(plan: Dict[str, Any], hit: Path) -> List[Dict[str, Any]]:
    """Soft impact hits where a data treatment lands on a driving beat.

    Only energetic scenes (≥0.5) qualify, at most one hit per 15s — sound
    design is punctuation, not a drum track.
    """
    events: List[Dict[str, Any]] = []
    last_t = -999.0
    scenes = [s for sc in (plan.get("sections") or {}).values()
              if isinstance(sc, list) for s in sc if isinstance(s, dict)]
    scenes.sort(key=lambda s: float(s.get("start_seconds") or 0))
    for s in scenes:
        t = float(s.get("start_seconds") or 0)
        if t - last_t < 15.0 or float(s.get("energy") or 0.5) < 0.5:
            continue
        effect = ((s.get("motion_spec") or {}).get("effect")
                  if isinstance(s.get("motion_spec"), dict) else None)
        spec = s.get("layout_spec")
        template = spec.get("template") if isinstance(spec, dict) else None
        if effect in _HIT_MOTION_EFFECTS or template in _HIT_TEMPLATES:
            events.append({"t": round(t, 3), "kind": "hit", "file": str(hit),
                           "volume": 0.5, "lead": 0.0,
                           "why": f"{s.get('id')}: {effect or template}"})
            last_t = t
    return events


def author_soundtrack(plan: Dict[str, Any], *,
                      music: Optional[Path] = None, music_gain_db: float = -12.0,
                      sfx: bool = True, mood: str = "",
                      sfx_provider: str = "freesound",
                      library: Path = None) -> Dict[str, Any]:
    """Author the soundtrack SPEC — the reviewable artifact, no audio touched.

    Chooses the track (energy-arc match, with the runner-up candidates kept in
    the spec so a human can swap without re-running selection), computes the
    SFX event placements from the beat boundaries, and records the mix
    parameters. Saved as ``soundtrack.json``; `mix_from_spec` executes it.
    """
    tracks = load_music_library(library)
    chosen = None
    candidates: List[Dict[str, Any]] = []
    if music:
        chosen = {"file": Path(music).name, "path": str(Path(music)),
                  "energy": None, "mood": "", "source": "explicit"}
    else:
        sections = section_energies(plan)
        target = (sum(e for _, _, e in sections) / len(sections)) if sections else 0.5
        pool = tracks
        if mood:
            tagged = [t for t in tracks
                      if mood.lower() in (t["mood"].lower(),
                                          *[x.lower() for x in t["tags"]])]
            if tagged:
                pool = tagged
        ranked = sorted(pool, key=lambda t: abs(t["energy"] - target))
        if not ranked:
            raise RuntimeError(
                "no music available — drop license-safe tracks into "
                f"{MUSIC_LIBRARY} (e.g. from the YouTube Audio Library)")
        chosen = {"file": ranked[0]["file"], "path": str(ranked[0]["path"]),
                  "energy": ranked[0]["energy"], "mood": ranked[0]["mood"],
                  "source": f"auto (target energy {target:.2f})"}
        candidates = [{"file": t["file"], "energy": t["energy"], "mood": t["mood"]}
                      for t in ranked[1:4]]

    events = []
    if sfx:
        whoosh = ensure_whoosh()
        sections = section_energies(plan)
        if whoosh:
            # volume 0.7: 0.5 measured INAUDIBLE under narration+duck in the
            # 2-beat test (hi-band RMS at the seam was below its neighbors)
            for start, _end, _energy in sections:
                if start > 1.0:
                    events.append({"t": round(start, 3), "kind": "whoosh",
                                   "file": str(whoosh), "volume": 0.7, "lead": 0.45})
        # risers: when the NEXT section jumps up the energy arc, a swell
        # peaking at the seam telegraphs the shift (the editor's build)
        riser = ensure_riser()
        if riser:
            for (s0, _e0, en0), (s1, _e1, en1) in zip(sections, sections[1:]):
                if en1 - en0 >= 0.2 and s1 > 2.5:
                    events.append({"t": round(s1, 3), "kind": "riser",
                                   "file": str(riser), "volume": 0.55,
                                   "lead": 2.0})
        # data punches: a soft hit where a stat/chart treatment lands on a
        # driving beat (≥0.5 energy, ≥15s apart — punctuation, not a drum track)
        hit = ensure_hit()
        if hit:
            events += _data_punch_events(plan, hit)
        # content-matched SFX: per-scene cues sourced via the provider layer
        # (Freesound/Mixkit) and landed AT the beat (lead 0.0).
        events += _source_scene_sfx(plan, provider=sfx_provider)
        events.sort(key=lambda e: e["t"])

    return {
        "version": 1,
        "track": chosen,
        "alternatives": candidates,
        "music_gain_db": music_gain_db,
        "loudnorm_lufs": -16,
        "fade_in_s": 2.0, "fade_out_s": 4.0,
        "duck": {"threshold": 0.04, "ratio": 4, "attack_ms": 25, "release_ms": 400},
        "sfx_events": events,
    }


def save_soundtrack(spec: Dict[str, Any], project_path: Path) -> Path:
    p = Path(project_path) / "soundtrack.json"
    p.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def load_soundtrack(project_path: Path) -> Optional[Dict[str, Any]]:
    p = Path(project_path) / "soundtrack.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("soundtrack.json unreadable: %s", exc)
        return None


# --- the mix -------------------------------------------------------------------

def mix_from_spec(video: Path, spec: Dict[str, Any], out: Path = None) -> Path:
    """Execute an authored soundtrack spec — mechanical, no decisions here."""
    video = Path(video)
    replace = out is None
    out = Path(out) if out else video.with_name(video.stem + ".mix.mp4")

    track = Path(spec["track"]["path"])
    if not track.exists():
        raise RuntimeError(f"soundtrack track not found: {track} "
                           "(edit soundtrack.json or the music library)")
    duration = _ffprobe_duration(video)
    gain = 10 ** (float(spec.get("music_gain_db", -12.0)) / 20.0)
    duck = spec.get("duck", {})
    fade_in = float(spec.get("fade_in_s", 2.0))
    fade_out = float(spec.get("fade_out_s", 4.0))
    lufs = float(spec.get("loudnorm_lufs", -16))

    inputs = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
              "-i", str(video), "-stream_loop", "-1", "-i", str(track)]
    fade_out_start = max(0.0, duration - fade_out)
    graph = (
        f"[1:a]atrim=0:{duration:.3f},"
        f"loudnorm=I={lufs}:TP=-2:LRA=11,volume={gain:.4f},"
        f"afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out}[mus];"
        f"[mus][0:a]sidechaincompress="
        f"threshold={duck.get('threshold', 0.04)}:ratio={duck.get('ratio', 4)}:"
        f"attack={duck.get('attack_ms', 25)}:release={duck.get('release_ms', 400)}:"
        f"makeup=1[duck]"
    )
    mix_ins = "[0:a][duck]"
    n_mix = 2

    events = [e for e in spec.get("sfx_events", [])
              if Path(e.get("file", "")).exists()][:24]
    for j, e in enumerate(events):
        inputs += ["-i", str(e["file"])]
        # whoosh transitions pre-roll (lead 0.45s) to land ON the cut; content
        # SFX carry lead 0.0 to land AT the beat. Default 0.45 keeps old specs valid.
        delay_ms = max(0, int((float(e["t"]) - float(e.get("lead", 0.45))) * 1000))
        graph += (f";[{2 + j}:a]volume={float(e.get('volume', 0.5))},"
                  f"adelay={delay_ms}|{delay_ms},"
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
    logger.info("soundtrack: %s + %d sfx -> %s",
                spec["track"]["file"], len(events), out)
    return out

def _segment_rms_db(path: Path, start: float, dur: float) -> Optional[float]:
    r = subprocess.run(
        [_ffmpeg(), "-ss", f"{max(0.0, start):.3f}", "-t", f"{dur:.3f}",
         "-i", str(path), "-af", "astats=metadata=1", "-f", "null", "-"],
        capture_output=True, text=True)
    import re as _re
    m = _re.findall(r"RMS level dB: (-?[\d.]+)", r.stderr)
    try:
        return float(m[-1]) if m else None
    except ValueError:
        return None


def measure_sfx_audibility(mixed: Path, spec: Dict[str, Any],
                           min_delta_db: float = 1.0) -> List[Dict[str, Any]]:
    """Verify-like-an-editor for the mix: is each authored SFX event audible?

    Compares RMS in the event's window against the second before it on the
    MIXED output. The 2-beat test shipped a whoosh nobody could hear and
    nothing caught it — this names inaudible events so a human (or a later
    pass) can raise volumes instead of trusting the spec.
    """
    out: List[Dict[str, Any]] = []
    for e in (spec.get("sfx_events") or [])[:24]:
        t0 = float(e["t"]) - float(e.get("lead", 0.45))
        dur = 2.2 if e.get("kind") == "riser" else 0.8
        during = _segment_rms_db(mixed, t0, dur)
        before = _segment_rms_db(mixed, t0 - 1.2, 1.0)
        delta = (during - before) if (during is not None and before is not None) else None
        audible = bool(delta is not None and delta >= min_delta_db)
        out.append({"t": e["t"], "kind": e.get("kind", "sfx"),
                    "delta_db": round(delta, 1) if delta is not None else None,
                    "audible": audible})
        if not audible:
            logger.warning("sfx %s@%.1fs measured INAUDIBLE (Δ %s dB) — raise "
                           "its volume in soundtrack.json",
                           e.get("kind"), e["t"], delta)
    return out


def mix_soundtrack(video: Path, plan: Dict[str, Any], out: Path = None, *,
                   music: Optional[Path] = None, music_gain_db: float = -12.0,
                   sfx: bool = True, mood: str = "",
                   sfx_provider: str = "freesound",
                   library: Path = None) -> Path:
    """Author + execute in one call (ad-hoc mixes, segment builder, tests).

    The Director pipeline splits this: the `soundtrack` step authors and
    checkpoints the spec (soundtrack.json — human-reviewable); the render
    step executes it with `mix_from_spec`.
    """
    spec = author_soundtrack(plan, music=music, music_gain_db=music_gain_db,
                             sfx=sfx, mood=mood, sfx_provider=sfx_provider,
                             library=library)
    return mix_from_spec(video, spec, out)


def resolve_music_config(project_path: Path) -> Dict[str, Any]:
    """Music settings: {enabled, music(path|None), gain, sfx, mood}.

    project.yaml `music:` is the human's word — a path or `auto` enables, and
    `none|false|off` disables ABSOLUTELY. When project.yaml is silent, the
    compiled brief (brief.json) enables auto selection with its music_mood —
    a pipeline project gets a bed by default instead of silence."""
    cfg = {"enabled": False, "music": None, "gain": -14.0, "sfx": True, "mood": "",
           "sfx_provider": "freesound"}
    meta: Dict[str, Any] = {}
    try:
        import yaml
        meta = yaml.safe_load(
            (Path(project_path) / "project.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    music = meta.get("music")
    if music is not None and str(music).lower() in ("none", "false", "off"):
        return cfg                              # explicit opt-out is final
    brief = None
    if not music:
        try:
            from nolan.project_brief import load_brief
            brief = load_brief(Path(project_path))
        except Exception:
            brief = None
        if brief is None:
            return cfg                          # no music key, no brief → silent
        music = "auto"                          # brief turns the bed on
    cfg["enabled"] = True
    if str(music).lower() != "auto":
        p = Path(str(music))
        cfg["music"] = p if p.is_absolute() else Path(project_path) / p
    cfg["gain"] = float(meta.get("music_gain_db", -14.0))
    cfg["sfx"] = meta.get("sfx", True) is not False
    cfg["mood"] = str(meta.get("music_mood", "") or "") or str(
        (brief or {}).get("music_mood", "") or "")
    cfg["sfx_provider"] = str(meta.get("sfx_provider", "freesound") or "freesound")
    return cfg


# --- graphical foley (meta-style program) -----------------------------------------
# The editorial-print sound signature: graphics get PHYSICAL sounds — a chart
# draws like a pencil, a stat lands like a stamp, a cutout slides like paper.
# One data table (kind -> freesound query + level), stamped as ordinary
# scene.sfx cues so the EXISTING soundtrack/mix path renders them; scenes that
# already carry an authored cue are never overwritten.

FOLEY_CUES = {
    # motion_spec effects
    "bar-compare":   {"query": "pencil writing scratch paper short", "volume": 0.5},
    "line-chart":    {"query": "pencil writing scratch paper short", "volume": 0.5},
    "bar-race":      {"query": "pencil writing scratch paper short", "volume": 0.5},
    "kinetic-text":  {"query": "typewriter single key strike",       "volume": 0.45},
    "typewriter":    {"query": "typewriter typing short burst",      "volume": 0.45},
    "stat-over":     {"query": "rubber stamp thud desk",             "volume": 0.55},
    "annotate-stat": {"query": "rubber stamp thud desk",             "volume": 0.55},
    "cutout-collage": {"query": "paper slide rustle short",          "volume": 0.45},
    # layout_spec templates
    "bar_chart":     {"query": "pencil writing scratch paper short", "volume": 0.5},
    "line_chart":    {"query": "pencil writing scratch paper short", "volume": 0.5},
    "statistic":     {"query": "rubber stamp thud desk",             "volume": 0.55},
    "counter":       {"query": "rubber stamp thud desk",             "volume": 0.55},
    "document_highlight": {"query": "marker highlighter squeak paper", "volume": 0.45},
}


def stamp_graphical_foley(plan: dict) -> int:
    """Stamp FOLEY_CUES onto matching scenes lacking an authored sfx cue
    (in place; returns count). Style packs opt in — this never runs unasked."""
    stamped = 0
    for scenes in (plan.get("sections") or {}).values():
        if not isinstance(scenes, list):
            continue
        for s in scenes:
            if not isinstance(s, dict) or s.get("sfx"):
                continue
            kind = None
            ms = s.get("motion_spec")
            if isinstance(ms, dict) and ms.get("effect") in FOLEY_CUES:
                kind = ms["effect"]
            else:
                ls = s.get("layout_spec") or {}
                if isinstance(ls, str):
                    try:
                        import json as _json
                        ls = _json.loads(ls)
                    except Exception:
                        ls = {}
                if isinstance(ls, dict) and ls.get("template") in FOLEY_CUES:
                    kind = ls["template"]
            if kind:
                s["sfx"] = {**FOLEY_CUES[kind], "at": 0.2}
                stamped += 1
    return stamped
