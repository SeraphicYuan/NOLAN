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
import wave
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class PremiumIneligible(RuntimeError):
    """The plan contains scenes with no Chapter-block mapping."""


def _wav_duration(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _slice_wav(src: Path, offset: float, duration: float, dest: Path) -> Path:
    """Sample-exact PCM slice — both edges round to source samples from the
    same absolute offsets, so consecutive slices tile the wav with ZERO
    gap/overlap. This matters since J-cuts: step boundaries now land
    mid-speech, where even a millisecond seam (ffmpeg -ss/-t rounding)
    would click; on the old sentence-pause boundaries it was inaudible."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(src), "rb") as w:
        rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        n = w.getnframes()
        a = max(0, min(n, int(round(max(0.0, offset) * rate))))
        b = max(a, min(n, int(round((max(0.0, offset) + duration) * rate))))
        b = min(n, max(b, a + int(0.05 * rate)))    # never an empty clip
        w.setpos(a)
        data = w.readframes(b - a)
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(ch)
        out.setsampwidth(sw)
        out.setframerate(rate)
        out.writeframes(data)
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


def _tray_placements(scene: Dict[str, Any],
                     project_path: Path) -> List[Tuple[Path, Tuple[float, float], str]]:
    """Human-PLACED tray images: [(abs_path, (x, y), caption)].

    The Scenes page's nine-dot grid stores `place: [x, y]` on curated tray
    assets — only placed images drive rendering (unplaced tray entries remain
    comment references, per the tray contract).
    """
    out = []
    for a in scene.get("assets") or []:
        if a.get("kind") != "image" or not a.get("src") or not a.get("place"):
            continue
        p = Path(a["src"])
        if not p.is_absolute():
            p = Path(project_path) / a["src"]
        if p.exists():
            try:
                x, y = float(a["place"][0]), float(a["place"][1])
            except (TypeError, ValueError, IndexError):
                continue
            out.append((p, (x, y), str(a.get("label") or "")))
    return out


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

    # Human-placed tray assets outrank the automatic still: the nine-dot
    # placements ARE the composition. 2+ placed images -> a montage with the
    # cards at their chosen spots; exactly one -> the camera pushes to it.
    placed = _tray_placements(scene, project_path)
    if len(placed) >= 2:
        cards = [{"src": str(p), "x": round(x, 3), "y": round(y, 3),
                  **({"caption": cap} if cap else {})}
                 for p, (x, y), cap in placed]
        return "PhotoMontage", {"cards": cards}
    if len(placed) == 1:
        p, (x, y), _cap = placed[0]
        return "ArtworkStage", {"src": str(p),
                                **_still_motion_props(scene, ordinal, center=(x, y))}

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


def _still_motion_props(scene: Dict[str, Any], ordinal: int = 0,
                        center: Tuple[float, float] = None) -> Dict[str, Any]:
    """Camera-tour props for a still, from the scene's authored tempo.

    ArtworkStage keyframes its camera ONLY from focus regions — this is where
    the treatment vocabulary lands: energy sets zoom tightness, motion_speed
    sets glide/hold pacing. Placement precedence: an explicit ``center``
    (a human's nine-dot tray placement — the camera pushes exactly there) →
    a stamped still-motion direction → center/left/right lane alternation by
    ordinal so consecutive stills don't all push the same way.
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
    if center is not None:
        x = max(0.0, min(1.0 - side, float(center[0]) - side / 2))
        y = max(0.0, min(1.0 - side, float(center[1]) - side / 2))
    elif direction == "left":
        x, y = 0.06, (1 - side) / 2
    elif direction == "right":
        x, y = 1 - side - 0.06, (1 - side) / 2
    else:
        lane = ordinal % 3
        x = {0: (1 - side) / 2, 1: 0.08, 2: 1 - side - 0.08}[lane]
        y = (1 - side) / 2

    glide = {"slow": 34, "medium": 26, "fast": 18}.get(speed, 26)
    intro = {"slow": 48, "medium": 40, "fast": 26}.get(speed, 40)
    return {"focuses": [{"word": "", "x": round(x, 3), "y": round(y, 3),
                         "w": side, "h": side}],
            "glide": glide, "introHold": intro}


MIN_STEP_FRAMES = 24        # no visual unit shorter than ~0.8s


def _resolve_shots(scene: Dict[str, Any], project_path: Path):
    """A scene's explicit shot list: [(abs_path, shot_dict)], or None.

    ``scene.shots``: [{src, place?, weight?, caption?}] — the temporal analog
    of the nine-dot tray (place targets the camera per shot). Two resolvable
    shots minimum; otherwise the scene renders as one unit.
    """
    shots = scene.get("shots")
    if not isinstance(shots, list) or len(shots) < 2:
        return None
    resolved = []
    for sh in shots:
        if not isinstance(sh, dict) or not sh.get("src"):
            continue
        p = Path(sh["src"])
        if not p.is_absolute():
            p = Path(project_path) / sh["src"]
        if p.exists():
            resolved.append((p, sh))
    return resolved if len(resolved) >= 2 else None


def _expand_shots(scene: Dict[str, Any], project_path: Path, fps: int,
                  frames: int, ordinal: int):
    """[(block, props, sub_frames)] — cut a scene's window into its shots.

    Editors cut in shots, not sentences (the deconstruction corpus shows 2-4s
    shots under longer narration spans). Each shot is a still with the full
    camera-tour treatment; ordinal advances per shot so consecutive shots
    alternate lanes. Without a shot list the scene is one unit.
    """
    resolved = _resolve_shots(scene, project_path)
    if not resolved:
        block, props = _scene_step(scene, project_path, fps, frames / fps,
                                   ordinal=ordinal)
        return [(block, props, frames)]

    # A window too small for every shot keeps the FIRST ones (never falls back
    # to _scene_step — a shots scene stays a shots scene).
    n = max(1, min(len(resolved), frames // MIN_STEP_FRAMES))
    resolved = resolved[:n]
    weights = [max(0.1, float(sh.get("weight", 1) or 1)) for _, sh in resolved]
    total_w = sum(weights)
    edges = [int(round(frames * sum(weights[:k + 1]) / total_w))
             for k in range(n)]
    edges[-1] = frames                              # frame-exact by construction
    subs = [e - (edges[k - 1] if k else 0) for k, e in enumerate(edges)]
    for k in range(n):                              # enforce the floor: steal
        while subs[k] < MIN_STEP_FRAMES:            # from the fattest shot
            j = max(range(n), key=lambda m: subs[m])
            take = min(subs[j] - MIN_STEP_FRAMES, MIN_STEP_FRAMES - subs[k])
            if take <= 0:
                break
            subs[j] -= take
            subs[k] += take

    units = []
    for k, ((p, sh), sub) in enumerate(zip(resolved, subs)):
        center = None
        place = sh.get("place")
        if isinstance(place, (list, tuple)) and len(place) == 2:
            center = (float(place[0]), float(place[1]))
        props = {"src": str(p)}
        props.update(_still_motion_props(scene, ordinal + k, center=center))
        units.append(("ArtworkStage", props, sub))
    return units


def _is_still_led(scene: Dict[str, Any], project_path: Path) -> bool:
    """Whether the scene OPENS on imagery (vs a text card that word-syncs).

    Editors J-cut onto imagery — the picture arrives while the last sentence
    finishes. A quote/title card gains nothing from arriving early: its
    reveal waits for the word cue, so an early cut only extends the empty
    background. Mirrors _scene_step precedence (layout template outranks
    stills)."""
    spec = scene.get("layout_spec") or {}
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except Exception:
            spec = {}
    if spec.get("template") and spec.get("template") != "custom":
        return False
    return bool(_resolve_shots(scene, project_path)
                or _tray_placements(scene, project_path)
                or scene.get("matched_asset") or scene.get("generated_asset"))


def build_section_job(name: str, scenes: List[Dict[str, Any]], *,
                      project_path: Path, section_wav: Path,
                      section_start: float, out_name: str,
                      work_dir: Path, theme: str = "bold-signal",
                      fps: int = 30,
                      section_words: List[Dict[str, Any]] = None,
                      j_cut_frames: int = 12) -> Dict[str, Any]:
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

    # J-cut offsets (SOTA #2): narration is CONTINUOUS within a section, so an
    # internal cut point can shift (audio slice + visual together) without
    # touching sync — total narration is byte-identical; the cut simply stops
    # landing exactly on the sentence pause. Pulling a boundary EARLIER means
    # the next scene's image arrives while the previous sentence finishes —
    # the editor's J-cut, and the death of the cut-on-sentence tell. Only
    # boundaries INTO still-led scenes shift (text cards keep straight cuts);
    # section edges stay untouched (beat anchors are sacred).
    if j_cut_frames:
        for i in range(len(bounds) - 1):        # never the section's last edge
            if not _is_still_led(scenes[i + 1], project_path):
                continue
            floor_f = (bounds[i - 1] if i else 0) + MIN_STEP_FRAMES
            bounds[i] = max(floor_f, bounds[i] - int(j_cut_frames))

    steps = []
    f_prev = 0
    for scene, f1 in zip(scenes, bounds):
        frames = max(f1 - f_prev, 2)
        # a scene may carry a SHOT LIST — cut within its window
        for shot_idx, (block, props, sub_frames) in enumerate(
                _expand_shots(scene, project_path, fps, frames,
                              ordinal=len(steps))):
            dur = sub_frames / fps
            clip_wav = _slice_wav(
                section_wav, f_prev / fps, dur,
                work_dir / f"{scene.get('id', 'scene')}_{shot_idx}.wav")
            words, reveals = _step_words(section_words or [], f_prev / fps,
                                         f_prev / fps + dur, fps, sub_frames)
            step = {
                "block": block, "props": props,
                "revealFrames": reveals, "words": words,
                "audioSrc": str(clip_wav),
                "durationInFrames": sub_frames,
            }
            # transition-in (editing registry): tempo_plan's authored per-scene
            # entrance, executed as a short opacity ramp in Chapter. Only the
            # scene's FIRST sub-step; a section's first scene stays a hard cut
            # (it lands on the beat anchor).
            if (shot_idx == 0 and steps
                    and scene.get("transition") in ("dissolve", "fade")):
                step["transitionIn"] = scene["transition"]
            steps.append(step)
            f_prev = f_prev + sub_frames
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
    from nolan.project_brief import load_brief, resolve_render_look
    brief = load_brief(project_path)
    accent = None
    if theme is None:
        theme, accent = resolve_render_look(meta, brief)
    if gate is None:
        gate = meta.get("premium_gate", True) is not False
    try:                                   # project.yaml `j_cut_frames: 0` disables
        j_cut = int(meta.get("j_cut_frames", 12))
    except (TypeError, ValueError):
        j_cut = 12

    work = project_path / "assets" / "premium" / "_work"
    jobs_dir = project_path / "assets" / "premium" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    # Eligibility check FIRST — fail before rendering anything, listing every
    # blocker (no silent partial output). Authored editing decisions go
    # through their registry gate here too (the executors are lenient by
    # design; this is where malformed authoring gets NAMED).
    from nolan.editing import validate_plan_editing
    blockers = list(validate_plan_editing(plan))
    t = 0.0
    spans = []
    for (name, scenes), wav in zip(sections, wavs):
        d = _wav_duration(wav)
        spans.append((t, d))
        for s in scenes:
            if _resolve_shots(s, project_path):     # a shot list IS a mapping
                continue
            try:
                _scene_step(s, project_path, fps, 1.0)
            except PremiumIneligible as exc:
                blockers.append(str(exc))
        t += d
    if blockers:
        raise PremiumIneligible(
            f"{len(blockers)} premium blocker(s): " + "; ".join(blockers[:6]))

    clips = []
    job_paths = []
    for i, ((name, scenes), wav, (sec_start, _d)) in enumerate(
            zip(sections, wavs, spans)):
        logger.info("premium: word timings for section %d/%d", i + 1, len(sections))
        section_words = _section_words(wav)
        job = build_section_job(
            name, scenes, project_path=project_path, section_wav=wav,
            section_start=sec_start, out_name=f"premium_{i:04d}.mp4",
            work_dir=work, theme=theme, fps=fps, section_words=section_words,
            j_cut_frames=j_cut)
        if accent:                       # brief accent override (staged by stage.mjs)
            job["accent"] = accent
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
