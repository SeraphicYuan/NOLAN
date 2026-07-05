"""Premium render mode — each beat is ONE Remotion Chapter with baked VO.

Phase 3 FLOW convergence (decision D2): instead of rendering scenes to
independent MP4s and assembling them over the narration, a premium render
treats every scene-plan SECTION as a Chapter composition — the same driver
FLOW uses — with per-scene audio slices baked in, block-based visuals, and
frame-exact step durations from the beat-anchored windows. Sections concat
(hard cuts) into final.mp4; video ≡ narration by construction.

Eligibility: every scene must map to a Chapter block —
  - layout_spec scenes -> the Phase 3a template adapters (layout_blocks)
  - image-backed scenes (matched_asset / generated_asset) -> ArtworkStage
    (the ART-flow camera tour: establish, glide, pull back)
Video-backed scenes (matched_clip) have no Chapter block yet; a plan that
contains one raises PremiumIneligible with the offending scene ids — the
standard per-scene path remains the fallback for such projects.

Requires beat-anchored narration: per-section wavs in
assets/voiceover/_work/sec_NNNN.wav matching the plan's section count.
"""

from __future__ import annotations

import json
import logging
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class PremiumIneligible(RuntimeError):
    """The plan contains scenes with no Chapter-block mapping."""


def _wav_duration(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _slice_wav(src: Path, offset: float, duration: float, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(src), "-ss", f"{max(0.0, offset):.3f}",
         "-t", f"{max(0.05, duration):.3f}", "-ar", "44100", str(dest)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"audio slice failed: {r.stderr[-300:]}")
    return dest


def _section_words(wav: Path) -> List[Dict[str, Any]]:
    """Word-level timestamps for one section wav (CPU whisper), or [].

    Feeds the blocks' word-sync (`words`) and reveal cues (`revealFrames`) —
    the same contract FLOW computes upstream. Degrades gracefully: no
    whisper → empty words → blocks reveal at frame 0 (pre-word-sync look).
    """
    try:
        from nolan.whisper import WHISPER_AVAILABLE, WhisperConfig, WhisperTranscriber
        if not WHISPER_AVAILABLE:
            return []
        tr = WhisperTranscriber(WhisperConfig(
            model_size="base", device="cpu", compute_type="int8"))
        return [{"t0": float(w.start), "t1": float(w.end),
                 "text": (w.word or "").strip()}
                for w in tr.transcribe_words(wav) if (w.word or "").strip()]
    except Exception as exc:
        logger.warning("word timings unavailable for %s: %s", wav.name, exc)
        return []


def _step_words(section_words: List[Dict[str, Any]], start_s: float,
                end_s: float, fps: int, frames: int) -> Tuple[list, list]:
    """(words, revealFrames) for one step spanning [start_s, end_s) of its section.

    Words become step-relative frames. Reveal cues: primary content lands on
    the FIRST spoken word — but capped at ~0.4s, because scene boundaries sit
    on speech pauses and a step whose narration starts with a breath would
    otherwise hold an empty card. The secondary line (attribution/definition/
    closer per block) stays truly word-synced at ~60% through the step's words.
    """
    words = []
    for w in section_words:
        if w["t1"] <= start_s or w["t0"] >= end_s:
            continue
        f0 = max(0, int(round((w["t0"] - start_s) * fps)))
        f1 = min(frames, max(f0 + 1, int(round((w["t1"] - start_s) * fps))))
        words.append({"text": w["text"], "startFrame": f0, "endFrame": f1})
    if not words:
        return [], []
    primary = min(words[0]["startFrame"], int(round(fps * 0.4)))
    second = words[min(len(words) - 1, int(len(words) * 0.6))]["startFrame"]
    return words, [primary, max(second, primary)]


def _scene_step(scene: Dict[str, Any], project_path: Path, fps: int,
                duration_s: float, ordinal: int = 0) -> Tuple[str, Dict[str, Any]]:
    """(block, props) for a scene, or raise PremiumIneligible."""
    from nolan.layout_blocks import adapt

    spec = scene.get("layout_spec") or {}
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except Exception:
            spec = {}
    template = spec.get("template")
    if template and template != "custom":
        adapted = adapt(template, spec.get("params") or {})
        if adapted:
            return adapted

    asset = scene.get("matched_asset") or (
        f"assets/generated/{scene['generated_asset']}"
        if scene.get("generated_asset") else None)
    if asset:
        p = Path(asset)
        if not p.is_absolute():
            p = project_path / asset
        if p.exists():
            props = {"src": str(p)}
            props.update(_still_motion_props(scene, ordinal))
            return "ArtworkStage", props

    raise PremiumIneligible(
        f"scene {scene.get('id')} ({scene.get('visual_type')}) has no "
        "Chapter-block mapping (needs layout_spec or a still asset)")


def _still_motion_props(scene: Dict[str, Any], ordinal: int = 0) -> Dict[str, Any]:
    """Camera-tour props for a still, from the scene's authored tempo.

    ArtworkStage keyframes its camera ONLY from focus regions — this is where
    the treatment vocabulary lands: energy sets zoom tightness, motion_speed
    sets glide/hold pacing, and placement honors a stamped still-motion
    direction (else alternates center/left/right by ordinal so consecutive
    stills don't all push the same way).
    """
    energy = 0.5
    try:
        energy = float(scene.get("energy") or 0.5)
    except (TypeError, ValueError):
        pass
    speed = str(scene.get("motion_speed") or "medium").lower()

    side = max(0.45, min(0.8, 0.78 - 0.35 * energy))
    ms = scene.get("motion_spec") or {}
    direction = ((ms.get("content") or {}).get("direction")
                 or ms.get("direction") or "")
    if direction == "left":
        x = 0.06
    elif direction == "right":
        x = 1 - side - 0.06
    else:
        lane = ordinal % 3
        x = {0: (1 - side) / 2, 1: 0.08, 2: 1 - side - 0.08}[lane]
    y = (1 - side) / 2

    glide = {"slow": 34, "medium": 26, "fast": 18}.get(speed, 26)
    intro = {"slow": 48, "medium": 40, "fast": 26}.get(speed, 40)
    return {"focuses": [{"word": "", "x": round(x, 3), "y": round(y, 3),
                         "w": side, "h": side}],
            "glide": glide, "introHold": intro}


def build_section_job(name: str, scenes: List[Dict[str, Any]], *,
                      project_path: Path, section_wav: Path,
                      section_start: float, out_name: str,
                      work_dir: Path, theme: str = "bold-signal",
                      fps: int = 30,
                      section_words: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """A FLOW-shaped Chapter job for one beat-anchored section.

    The section WAV is the timing authority: scene windows are normalized
    onto its exact duration (proportionally, frame-exact cumulative
    boundaries), so the Chapter ≡ its narration even if an upstream pass
    mutated the plan's absolute windows. `section_start` is kept for the
    signature but the wav-relative normalization supersedes it.
    """
    wav_dur = _wav_duration(section_wav)
    lo = min(float(s.get("start_seconds") or 0.0) for s in scenes)
    hi = max(float(s.get("end_seconds") or 0.0) for s in scenes)
    span = max(hi - lo, 1e-6)
    scale = wav_dur / span

    # Frame-exact tiling: boundaries in frames, each step owns [f0, f1).
    bounds = []
    for scene in scenes:
        b = (float(scene.get("end_seconds") or 0.0) - lo) * scale
        bounds.append(int(round(b * fps)))
    bounds[-1] = int(round(wav_dur * fps))          # last step ends exactly at the wav end

    steps = []
    f_prev = 0
    for scene, f1 in zip(scenes, bounds):
        frames = max(f1 - f_prev, 2)
        dur = frames / fps
        block, props = _scene_step(scene, project_path, fps, dur,
                                   ordinal=len(steps))
        clip_wav = _slice_wav(section_wav, f_prev / fps, dur,
                              work_dir / f"{scene.get('id', 'scene')}.wav")
        words, reveals = _step_words(section_words or [], f_prev / fps,
                                     f_prev / fps + dur, fps, frames)
        steps.append({
            "block": block, "props": props,
            "revealFrames": reveals, "words": words,
            "audioSrc": str(clip_wav),
            "durationInFrames": frames,
        })
        f_prev = f_prev + frames
    return {"out": out_name, "theme": theme, "fps": fps,
            "captions": False, "props": {"steps": steps}}


def render_premium(project_path: Path, *, theme: str = None,
                   fps: int = 30, output: Path = None,
                   gate: bool = None) -> Path:
    """Render the whole plan as per-section Chapters + concat. Returns final.

    ``gate`` (default on; project.yaml `premium_gate: false` opts out) runs
    FLOW's contact-sheet pre-flight over every section job before rendering.
    """
    from nolan.flows.base import render_chapter
    from nolan.flows.render import concat_beats

    # Absolute paths are load-bearing: staged media (stage.mjs) existence-checks
    # every path string, and node's CWD is render-service/, not the repo root.
    project_path = Path(project_path).resolve()
    plan = json.loads((project_path / "scene_plan.json").read_text(encoding="utf-8"))
    sections = [(k, v) for k, v in (plan.get("sections") or {}).items()
                if isinstance(v, list) and v]
    wavs = sorted((project_path / "assets" / "voiceover" / "_work").glob("sec_*.wav"))
    if len(wavs) != len(sections):
        raise PremiumIneligible(
            f"premium mode needs beat anchors: {len(wavs)} section wavs vs "
            f"{len(sections)} plan sections (run voiceover + align first)")

    meta = {}
    try:
        import yaml
        meta = yaml.safe_load(
            (project_path / "project.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    if theme is None:
        theme = meta.get("theme") or "bold-signal"
    if gate is None:
        gate = meta.get("premium_gate", True) is not False

    work = project_path / "assets" / "premium" / "_work"
    jobs_dir = project_path / "assets" / "premium" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    # Eligibility check FIRST — fail before rendering anything, listing every
    # blocker (no silent partial output).
    blockers = []
    t = 0.0
    spans = []
    for (name, scenes), wav in zip(sections, wavs):
        d = _wav_duration(wav)
        spans.append((t, d))
        for s in scenes:
            try:
                _scene_step(s, project_path, fps, 1.0)
            except PremiumIneligible as exc:
                blockers.append(str(exc))
        t += d
    if blockers:
        raise PremiumIneligible(
            f"{len(blockers)} scenes are not premium-renderable: "
            + "; ".join(blockers[:6]))

    clips = []
    job_paths = []
    for i, ((name, scenes), wav, (sec_start, _d)) in enumerate(
            zip(sections, wavs, spans)):
        logger.info("premium: word timings for section %d/%d", i + 1, len(sections))
        section_words = _section_words(wav)
        job = build_section_job(
            name, scenes, project_path=project_path, section_wav=wav,
            section_start=sec_start, out_name=f"premium_{i:04d}.mp4",
            work_dir=work, theme=theme, fps=fps, section_words=section_words)
        job_path = jobs_dir / f"premium_{i:04d}.json"
        job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        job_paths.append((i, name, job_path))

    # Contact-sheet pre-flight (FLOW's Tier-1 gate, reused verbatim + the
    # edge-overflow check): one cheap still per step fraction catches
    # empty/near-black beats and text escaping the frame BEFORE the expensive
    # render. Explicit opt-out: project.yaml `premium_gate: false`.
    if gate:
        from nolan.flows.gate.contact import contact
        problems = []
        for i, name, job_path in job_paths:
            flags, sheet = contact(job_path, overflow=True,
                                   sheet_name=f"premium_{i:04d}.contact.png")
            for beat, block, frame, what in flags:
                problems.append(
                    f"section {i} ({name[:30]}) step {beat} [{block}] "
                    f"frame {frame}: {what}")
            logger.info("premium gate: section %d contact sheet -> %s", i, sheet)
        if problems:
            raise PremiumIneligible(
                f"pre-flight gate flagged {len(problems)} problem(s) — review "
                "the contact sheets under render-service/remotion-lib/output/: "
                + "; ".join(problems[:8]))

    for i, name, job_path in job_paths:
        logger.info("premium: rendering section %d/%d (%s)",
                    i + 1, len(sections), name[:40])
        clips.append(render_chapter(job_path))

    final = Path(output) if output else project_path / "output" / "final.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    concat_beats(clips, final)
    return final
