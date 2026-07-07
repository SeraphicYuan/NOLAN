"""Premium render mode — each beat is ONE Remotion Chapter with baked VO.

Phase 3 FLOW convergence (decision D2): instead of rendering scenes to
independent MP4s and assembling them over the narration, a premium render
treats every scene-plan SECTION as a Chapter composition — the same driver
FLOW uses — with per-scene audio slices baked in, block-based visuals, and
frame-exact step durations from the beat-anchored windows. Sections concat
(hard cuts) into final.mp4; video ≡ narration by construction.

Eligibility: every scene must map to a Chapter step —
  - layout_spec scenes -> the template adapters (layout_blocks)
  - motion_spec scenes -> hosted motion comps (render story v2: the same
    components the standalone compositions use, keyed via comps.ts)
  - rendered_clip / matched_clip -> a muted Video step (narration stays the
    step audio; the clip loops if shorter than its window)
  - image-backed scenes (matched_asset / generated_asset) -> ArtworkStage
    (the ART-flow camera tour: establish, glide, pull back)

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
    """(block, props) for a scene, or raise PremiumIneligible.

    Precedence: HUMAN PIN first (a pin means the editor chose THAT frame —
    it beats agent authoring, and a pin placed AFTER matching wins without
    re-running select_clips), then explicit authoring: layout_spec template →
    motion_spec (hosted comp, render story v2) → nine-dot tray →
    rendered_clip / video match (Video step) → matched/generated still
    (ArtworkStage)."""
    from nolan.layout_blocks import adapt

    pinned = scene.get("pinned_asset") or {}
    if isinstance(pinned, dict) and pinned.get("src"):
        p = Path(pinned["src"])
        if not p.is_absolute():
            p = project_path / pinned["src"]
        if p.exists():
            if pinned.get("kind") == "clip" or p.suffix.lower() in (".mp4", ".mov", ".webm", ".m4v"):
                start = float(pinned.get("clip_start") or 0.0)
                return "Video", {"src": str(p),
                                 "startFromFrames": int(round(start * fps))}
            props = {"src": str(p)}
            props.update(_still_motion_props(scene, ordinal,
                                             center=_subject_center(p)))
            return "ArtworkStage", props

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
            # media-bearing templates (image_compare, detail_loupe): make
            # paths absolute for stage.mjs (node CWD is render-service/)
            from nolan.motion.executor import _abs_media
            block, props = adapted
            return block, _abs_media(props, project_path)

    # Authored motion (render story v2): the spec's comp is hosted as a
    # Chapter step. Unhostable backends (python, preprocessing comps) fall
    # through to the still treatment; an INVALID spec fails loudly.
    ms = scene.get("motion_spec")
    if isinstance(ms, dict) and ms.get("effect"):
        from nolan.motion import chapter_step_for_spec
        try:
            hosted = chapter_step_for_spec(ms, project_path)
        except ValueError as exc:
            raise PremiumIneligible(f"scene {scene.get('id')}: {exc}")
        if hosted:
            return hosted

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

    # Video (render story v2): a clip PRODUCED for this scene plays as a
    # muted Video step under the narration slice (assemble's top priority).
    rendered = scene.get("rendered_clip")
    if rendered:
        p = Path(rendered)
        if not p.is_absolute():
            p = project_path / rendered
        if p.exists():
            return "Video", {"src": str(p)}

    asset = scene.get("matched_asset") or (
        f"assets/generated/{scene['generated_asset']}"
        if scene.get("generated_asset") else None)
    if asset:
        p = Path(asset)
        if not p.is_absolute():
            p = project_path / asset
        if p.exists():
            props = {"src": str(p)}
            # aim the synthesized push at the SUBJECT (rembg saliency,
            # sidecar-cached); None falls back to lane alternation
            props.update(_still_motion_props(scene, ordinal,
                                             center=_subject_center(p)))
            # on-screen citation (museum-label convention): named artworks
            # carry their attribution INTO the frame — the credibility habit
            # every reference channel has and we never rendered
            lic = scene.get("asset_license") or {}
            if (scene.get("visual_type") == "archival-art"
                    and lic.get("title") and "label" not in props):
                props["label"] = {"title": str(lic["title"])[:80],
                                  "collection": lic.get("source") or None}
            return "ArtworkStage", props

    # Library/stock video match — LAST resort: vector matches carry no vision
    # gate (the 2-beat test matched a lecture clip to an aerial query), so a
    # scored still outranks one.
    mc = scene.get("matched_clip")
    if isinstance(mc, dict) and mc.get("video_path"):
        p = Path(mc["video_path"])
        if not p.is_absolute():
            p = project_path / mc["video_path"]
        if p.exists():
            start = float(mc.get("clip_start") or 0.0)
            return "Video", {"src": str(p),
                             "startFromFrames": int(round(start * fps))}

    raise PremiumIneligible(
        f"scene {scene.get('id')} ({scene.get('visual_type')}) has no "
        "Chapter-block mapping (needs layout_spec, motion_spec, a video, "
        "or a still asset)")


# The energy→camera vocabulary lives in ONE place (nolan.still_motion) since
# the plumbing consolidation — three modules used to encode it independently.
from nolan.still_motion import camera_tour_props as _still_motion_props  # noqa: E402
from nolan.still_motion import subject_center as _subject_center  # noqa: E402
from nolan.still_motion import STILL_TREATMENTS  # noqa: E402  (resolve_scene_intent)


MIN_STEP_FRAMES = 24        # no visual unit shorter than ~0.8s


def _job_stamp(job: Dict[str, Any], extra_files=()) -> str:
    """Content stamp for the beat cache: the job JSON + (size, mtime) of every
    file it references — EXCEPT the _work audio slices, which are rewritten at
    the same paths on every run (their content derives from the section wav,
    so the caller passes the wav via `extra_files` instead; without this the
    cache could never hit)."""
    import hashlib
    h = hashlib.sha256(json.dumps(job, sort_keys=True).encode("utf-8"))

    def stat_in(path_str: str):
        p = Path(path_str)
        try:
            if p.is_file():
                st = p.stat()
                h.update(f"{path_str}:{st.st_size}:{st.st_mtime_ns}".encode("utf-8"))
        except OSError:
            pass

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and ("/" in o or "\\" in o):
            if "_work" in o.replace("\\", "/").split("/"):
                return                       # regenerated every run — excluded
            stat_in(o)
    walk(job.get("props", {}).get("steps", []))
    for f in extra_files:
        stat_in(str(f))
    return h.hexdigest()


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
    # AUTO-fulfilled shot lists yield to an explicit motion_spec — the agent
    # designed a treatment for this exact window (and may have dodged
    # defects the auto list can't see, e.g. duplicate stills). HUMAN shots
    # (shots_auto false/absent after a drawer edit) still outrank motion.
    if (resolved and scene.get("shots_auto")
            and isinstance(scene.get("motion_spec"), dict)
            and scene["motion_spec"].get("effect")):
        resolved = None
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
            center = (float(place[0]), float(place[1]))   # human placement wins
        if center is None:
            center = _subject_center(p)                   # saliency, else lanes
        props = {"src": str(p)}
        props.update(_still_motion_props(scene, ordinal + k, center=center))
        units.append(("ArtworkStage", props, sub))
    return units


def resolve_scene_intent(scene: Dict[str, Any], project_path) -> Dict[str, Any]:
    """What will this scene ACTUALLY render, and which authored edits lose?

    The Inspector strip, the timeline conflict markers and the pre-render
    plan all read this one function. It walks the SAME ladder with the SAME
    helpers `_expand_shots`/`_scene_step` use — human shots → pin →
    layout_spec → motion_spec → placed tray → rendered clip → still → video
    match — without rendering anything. Agreement with the real render path
    is enforced by tests/test_scene_intent.py (pitfall #4: one decision, one
    function; this is a dry-run of it, not a second copy).

    Returns {"winner": {rung, media, detail}, "overridden": [...],
             "conflicts": [{id, severity: error|warn|info, message}]}.
    """
    from nolan.layout_blocks import adapt
    from nolan.motion import chapter_step_for_spec

    project_path = Path(project_path)
    conflicts: List[Dict[str, Any]] = []

    def _abs(rel):
        p = Path(rel)
        return p if p.is_absolute() else project_path / rel

    # -- contenders, evaluated with the render path's own helpers ------------
    shots_resolved = _resolve_shots(scene, project_path)
    ms = scene.get("motion_spec")
    has_motion = isinstance(ms, dict) and bool(ms.get("effect"))
    human_shots = bool(shots_resolved) and not scene.get("shots_auto")
    auto_shots = bool(shots_resolved) and bool(scene.get("shots_auto"))

    pinned = scene.get("pinned_asset") or {}
    pin_declared = isinstance(pinned, dict) and bool(pinned.get("src"))
    pin_ok = pin_declared and _abs(pinned["src"]).exists()
    pin_is_clip = pin_ok and (
        pinned.get("kind") == "clip"
        or _abs(pinned["src"]).suffix.lower() in (".mp4", ".mov", ".webm", ".m4v"))

    spec = scene.get("layout_spec") or {}
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except Exception:
            spec = {}
    template = spec.get("template")
    layout_declared = bool(template) and template != "custom"
    layout_ok = layout_declared and adapt(template, spec.get("params") or {}) is not None

    motion_ok = motion_invalid = False
    if has_motion:
        try:
            motion_ok = chapter_step_for_spec(ms, project_path) is not None
        except ValueError as exc:
            motion_invalid = True
            conflicts.append({"id": "motion-spec-invalid", "severity": "error",
                              "message": f"motion_spec is invalid — the premium render "
                                         f"will REFUSE this scene: {exc}"})

    placed = _tray_placements(scene, project_path)
    rendered = scene.get("rendered_clip")
    rendered_ok = bool(rendered) and _abs(rendered).exists()
    asset = scene.get("matched_asset") or (
        f"assets/generated/{scene['generated_asset']}"
        if scene.get("generated_asset") else None)
    still_ok = bool(asset) and _abs(asset).exists()
    mc = scene.get("matched_clip")
    vid_ok = isinstance(mc, dict) and mc.get("video_path") and _abs(mc["video_path"]).exists()

    # -- winner: the ladder, verbatim ----------------------------------------
    # (_expand_shots: a resolvable shot list wraps the whole scene UNLESS it
    # was auto-generated and an explicit motion_spec exists.)
    if shots_resolved and not (auto_shots and has_motion):
        winner = ("shots", f"{len(shots_resolved)} shots",
                  "human shot list" if human_shots else "auto shot list")
    elif pin_ok:
        winner = ("pin", Path(pinned["src"]).name,
                  "human pin" + (" (clip)" if pin_is_clip else " (still)"))
    elif layout_ok:
        winner = ("layout", template, "layout_spec template")
    elif has_motion and motion_ok and not motion_invalid:
        winner = ("motion", ms["effect"], "motion_spec hosted comp")
    elif len(placed) >= 2:
        winner = ("placements", f"{len(placed)}-card montage", "nine-dot tray placements")
    elif len(placed) == 1:
        winner = ("placements", placed[0][0].name, "nine-dot placed image (camera push)")
    elif rendered_ok:
        winner = ("rendered-clip", Path(rendered).name, "clip rendered for this scene")
    elif still_ok:
        winner = ("still", Path(asset).name, "matched/generated still + camera treatment")
    elif vid_ok:
        winner = ("video-match", Path(mc["video_path"]).name, "library/stock video match")
    else:
        winner = ("ineligible", None, "nothing renderable — premium will refuse this scene")
    rung = winner[0]

    # -- conflicts: silent losers made loud ----------------------------------
    if pin_declared and not pin_ok:
        conflicts.append({"id": "pin-missing-file", "severity": "error",
                          "message": f"pinned asset file is MISSING ({pinned['src']}) — "
                                     "the pin is silently skipped and auto-matching takes over"})
    if rung == "shots" and human_shots and has_motion:
        conflicts.append({"id": "shots-override-motion", "severity": "warn",
                          "message": f"your shot list wins — motion_spec "
                                     f"'{ms['effect']}' will NOT render"})
    if auto_shots and has_motion and not motion_invalid:
        conflicts.append({"id": "auto-shots-yield-to-motion", "severity": "info",
                          "message": "the auto shot list yields to the authored motion_spec"})
    if rung == "pin":
        if layout_declared:
            conflicts.append({"id": "pin-overrides-layout", "severity": "warn",
                              "message": f"the pin wins — layout_spec '{template}' will NOT render"})
        if has_motion and not motion_invalid:
            conflicts.append({"id": "pin-overrides-motion", "severity": "warn",
                              "message": f"the pin wins — motion_spec '{ms['effect']}' will NOT render"})
        if placed:
            conflicts.append({"id": "pin-overrides-placements", "severity": "info",
                              "message": f"{len(placed)} placed tray image(s) lose to the pin"})
    if rung == "layout" and has_motion and not motion_invalid:
        conflicts.append({"id": "layout-overrides-motion", "severity": "info",
                          "message": f"layout_spec wins — motion_spec '{ms['effect']}' will NOT render"})
    if has_motion and not motion_ok and not motion_invalid:
        conflicts.append({"id": "motion-unhostable", "severity": "info",
                          "message": f"motion_spec '{ms['effect']}' isn't chapter-hostable — "
                                     "the scene falls back to its still treatment"})
    lock = scene.get("still_treatment")
    if lock in STILL_TREATMENTS:
        # the camera treatment reaches stills: shot sequences, pinned stills,
        # single placements and the matched still — nothing else
        camera_applies = (rung in ("shots", "still")
                          or (rung == "pin" and not pin_is_clip)
                          or (rung == "placements" and len(placed) == 1))
        if not camera_applies:
            conflicts.append({"id": "camera-lock-inert", "severity": "warn",
                              "message": f"camera lock '{lock}' has no effect — "
                                         f"this scene renders via {rung}"})

    # -- authored contenders that lost ---------------------------------------
    overridden = []
    for r, declared, detail in (
            ("pin", pin_ok, "pinned asset"),
            ("layout", layout_ok, f"layout_spec '{template}'" if template else ""),
            ("motion", has_motion and motion_ok and not motion_invalid,
             f"motion_spec '{ms['effect']}'" if has_motion else ""),
            ("placements", bool(placed), f"{len(placed)} placed tray image(s)"),
            ("shots", bool(shots_resolved), "shot list")):
        if declared and r != rung:
            overridden.append({"rung": r, "detail": detail})

    return {"winner": {"rung": rung, "media": winner[1], "detail": winner[2]},
            "overridden": overridden, "conflicts": conflicts}


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
                      j_cut_frames: int = 12,
                      captions: bool = False) -> Dict[str, Any]:
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
                "sceneId": scene.get("id"),
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
            "captions": bool(captions), "props": {"steps": steps}}


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
    # Motif layer: materialize scene.motif references (accumulated state +
    # this scene's delta stamped isNew) into in-memory motion_specs. The plan
    # on disk keeps the motif AUTHORING; only the render sees the expansion.
    from nolan.motion.motifs import resolve_plan_motifs
    _motif_scenes = resolve_plan_motifs(plan)
    if _motif_scenes:
        print(f"motifs: materialized {_motif_scenes} scene(s)")
    # Recipe layer (same contract): scene.recipe roles with baked motion
    # templates become in-memory motion_specs.
    from nolan.recipes import resolve_plan_recipes
    _recipe_scenes = resolve_plan_recipes(plan)
    if _recipe_scenes:
        print(f"recipes: materialized {_recipe_scenes} scene(s)")
    # Still-treatment variety (aeneid feedback: every image got the same
    # push): narrative-semantic in/out/pan + no-two-consecutive, in memory.
    from nolan.still_motion import assign_still_treatments
    _treated = assign_still_treatments(plan)
    if _treated:
        print(f"still treatments assigned: {_treated} scene(s)")
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
    captions = meta.get("captions", False) is True   # project.yaml `captions: true`
    # Draft mode (SOTA #7): half-res proof render — no whisper, no gate, no
    # cache writes. Loud everywhere: the checkpoint and logs say DRAFT.
    draft = meta.get("draft", False) is True
    use_cache = (meta.get("beat_cache", True) is not False) and not draft

    work = project_path / "assets" / "premium" / "_work"
    jobs_dir = project_path / "assets" / "premium" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    beats_dir = project_path / "assets" / "premium" / "beats"
    beats_dir.mkdir(parents=True, exist_ok=True)
    if draft:
        gate = False
        logger.warning("premium: DRAFT mode — half-res, no word-sync, no gate")

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

    # Language of the piece → which display face the theme alias resolves to.
    # Blocks read --font-display; an English essay should get the theme's EN
    # face (Syne, Archivo…), not the CJK face's latin glyphs (the font drift
    # the 2-beat tests exposed). CJK-share > 15% of narration → cn.
    _narr = " ".join((s.get("narration_excerpt") or "")
                     for sc in (plan.get("sections") or {}).values()
                     if isinstance(sc, list) for s in sc if isinstance(s, dict))
    _cjk = sum(1 for ch in _narr if "一" <= ch <= "鿿")
    lang = "cn" if _narr and _cjk / max(1, len(_narr)) > 0.15 else "en"

    # Word-timing cache: whisper costs ~40-60s/section and the wavs rarely
    # change between renders — key on (size, mtime) like the beat cache.
    words_cache_path = project_path / "assets" / "premium" / "words_cache.json"
    words_cache: Dict[str, Any] = {}
    if words_cache_path.exists():
        try:
            words_cache = json.loads(words_cache_path.read_text(encoding="utf-8"))
        except Exception:
            words_cache = {}

    def _words_for(wav: Path):
        st = wav.stat()
        stamp = f"{st.st_size}:{st.st_mtime_ns}"
        hit = words_cache.get(wav.name)
        if hit and hit.get("stamp") == stamp:
            return hit["words"]
        words = _section_words(wav)
        words_cache[wav.name] = {"stamp": stamp, "words": words}
        return words

    clips = []
    job_paths = []
    for i, ((name, scenes), wav, (sec_start, _d)) in enumerate(
            zip(sections, wavs, spans)):
        if not draft:
            logger.info("premium: word timings for section %d/%d",
                        i + 1, len(sections))
        section_words = [] if draft else _words_for(wav)
        job = build_section_job(
            name, scenes, project_path=project_path, section_wav=wav,
            section_start=sec_start, out_name=f"premium_{i:04d}.mp4",
            work_dir=work, theme=theme, fps=fps, section_words=section_words,
            j_cut_frames=j_cut, captions=captions)
        if accent:                       # brief accent override (staged by stage.mjs)
            job["accent"] = accent
        job["lang"] = lang               # font-display face: en vs cn (stage.mjs)
        if draft:
            job["scale"] = 0.5
        if brief and isinstance(brief.get("grade"), dict):
            job["fx"] = dict(brief["grade"])   # PostFX over the whole Chapter
        job_path = jobs_dir / f"premium_{i:04d}.json"
        job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        job_paths.append((i, name, job_path))
    if not draft:
        words_cache_path.parent.mkdir(parents=True, exist_ok=True)
        words_cache_path.write_text(json.dumps(words_cache), encoding="utf-8")

    # Beat cache (SOTA #7): a section whose job (content + every referenced
    # media/audio file) is unchanged reuses its last render. Reuse is REPORTED
    # (last_run.json + logs) — never silent. project.yaml `beat_cache: false`
    # opts out; draft renders never populate the cache.
    import shutil
    manifest_path = beats_dir / "cache.json"
    manifest: Dict[str, Any] = {}
    if use_cache and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    reused = 0
    ordered: Dict[int, Path] = {}
    to_render = []
    for i, name, job_path in job_paths:
        job = json.loads(job_path.read_text(encoding="utf-8"))
        stamp = _job_stamp(job, extra_files=[wavs[i]])
        beat_file = beats_dir / f"premium_{i:04d}.mp4"
        if (use_cache and manifest.get(beat_file.name) == stamp
                and beat_file.exists()):
            logger.info("premium: section %d/%d unchanged — reusing %s",
                        i + 1, len(sections), beat_file.name)
            ordered[i] = beat_file
            reused += 1
            continue
        to_render.append((i, name, job_path, beat_file, stamp))

    # Contact-sheet pre-flight (FLOW's Tier-1 gate + edge-overflow), scoped
    # to the sections that will actually render — a cache-reused beat already
    # passed its gate on first render, so re-checking it wastes ~1 min/beat.
    # Explicit opt-out: project.yaml `premium_gate: false`.
    if gate and to_render:
        from nolan.flows.gate.contact import contact
        problems = []
        for i, name, job_path, _bf, _st in to_render:
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

    # Chapter renders are CPU work (node bundling + Chromium frames) with NO
    # GPU involvement, so they parallelize safely — the GPU stages (ComfyUI
    # generation, OmniVoice TTS) stay serialized behind get_gpu_lock() in
    # their own steps and are never in flight here. project.yaml
    # `render_workers` tunes concurrency (default 2; 1 = serial).
    try:
        workers = max(1, int(meta.get("render_workers", 2)))
    except (TypeError, ValueError):
        workers = 2
    rendered = len(to_render)
    if to_render:
        logger.info("premium: rendering %d section(s) with %d worker(s)%s",
                    len(to_render), min(workers, len(to_render)),
                    " [DRAFT]" if draft else "")
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(workers, len(to_render))) as ex:
            futures = {ex.submit(render_chapter, jp): (i, bf, st)
                       for i, _n, jp, bf, st in to_render}
            errors = []
            for fut in futures:
                i, beat_file, stamp = futures[fut]
                try:
                    clip = fut.result()
                except Exception as exc:            # loud, per section
                    errors.append(f"section {i}: {exc}")
                    continue
                if use_cache:
                    shutil.copy(str(clip), str(beat_file))
                    manifest[beat_file.name] = stamp
                    ordered[i] = beat_file
                else:
                    ordered[i] = Path(clip)
        if errors:
            raise RuntimeError(
                f"{len(errors)} section render(s) failed: " + "; ".join(errors))
    clips = [ordered[i] for i, _n, _jp in job_paths]
    if use_cache:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (beats_dir / "last_run.json").write_text(
        json.dumps({"reused": reused, "rendered": rendered,
                    "draft": draft}), encoding="utf-8")

    final = Path(output) if output else project_path / "output" / "final.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    concat_beats(clips, final)
    # RENDER MANIFEST — the pool's "in-video" truth. Written ONLY by this
    # step after a successful concat (nothing else may flip usage tags):
    # scene id -> the media files its rendered steps actually referenced.
    _write_render_manifest(project_path, job_paths, final)
    return final


def scene_stamp(scene: Dict[str, Any]) -> str:
    """Content stamp of one scene's AUTHORED state (underscore keys are
    render-time expansion and excluded). Written into the render manifest at
    concat time; the timeline compares against it to show edited-since-render
    honestly (the per-scene analog of the beat cache's job stamp)."""
    import hashlib
    canon = json.dumps({k: v for k, v in scene.items()
                        if not str(k).startswith("_")},
                       sort_keys=True, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _write_render_manifest(project_path: Path, job_paths, final: Path) -> Path:
    """output/render_manifest.json: per-scene media that made it into the cut."""
    scenes: Dict[str, list] = {}
    beats = []
    for _i, name, job_path in job_paths:
        try:
            job = json.loads(Path(job_path).read_text(encoding="utf-8"))
        except Exception:
            continue
        beats.append({"name": name, "job": Path(job_path).name})
        for step in job.get("props", {}).get("steps", []):
            sid = step.get("sceneId")
            if not sid:
                continue
            bucket = scenes.setdefault(sid, [])

            def _walk(o):
                if isinstance(o, dict):
                    for v in o.values():
                        _walk(v)
                elif isinstance(o, list):
                    for v in o:
                        _walk(v)
                elif isinstance(o, str) and ("/" in o or "\\" in o):
                    try:
                        pp = Path(o)
                        if (pp.suffix.lower() in (".jpg", ".jpeg", ".png",
                                                  ".webp", ".gif", ".mp4",
                                                  ".mov", ".webm", ".m4v")
                                and pp.is_file() and str(pp) not in bucket):
                            bucket.append(str(pp))
                    except OSError:
                        pass

            _walk(step.get("props", {}))
    # per-scene authored-state stamps, from the plan ON DISK (the in-memory
    # render plan carries motif/recipe/treatment expansion that must not leak
    # into the stamp — the timeline stamps the same on-disk view)
    stamps: Dict[str, str] = {}
    try:
        disk_plan = json.loads((project_path / "scene_plan.json")
                               .read_text(encoding="utf-8"))
        for grp in (disk_plan.get("sections") or {}).values():
            for s in (grp if isinstance(grp, list) else []):
                if isinstance(s, dict) and s.get("id"):
                    stamps[s["id"]] = scene_stamp(s)
    except Exception:
        stamps = {}
    manifest = {"version": 2, "written_by": "render",
                "final": str(final), "beats": beats, "scenes": scenes,
                "scene_stamps": stamps}
    out = project_path / "output" / "render_manifest.json"
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    return out
