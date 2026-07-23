"""Per-shot visual facts — Tier 1 of video deconstruction.

Extracts lens-independent FACTS about what a video does, per shot
(cut-to-cut interval):

- **Shot boundaries** — from the sampler's cached FFmpeg scene scores
  (``<video>.scores.json``) when present, else HSV-histogram cut detection
  (same method as ``video_style.tempo``).
- **Motion classification** — deterministic optical flow (OpenCV Farneback),
  no LLM: global translation → pan/tilt, radial divergence → push-in/pull-out,
  residual flow → subject motion. Emits a ``treatment_hint`` in the motion
  library's still-motion vocabulary so downstream analysis speaks the same
  language the forward pipeline renders.
- **Vision facts** (optional) — one structured vision call per shot on a
  representative frame: ``asset_type`` / ``framing`` / ``on_screen_text`` /
  ``identity_hint``. Same providers as ingestion (Gemini/OpenRouter).

Facts persist to the library's ``shots`` table (``VideoIndex``, schema v8),
stamped with ``FACTS_VERSION`` so re-runs are incremental: a video whose rows
match the current version is skipped unless forced.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

FACTS_VERSION = 1

# --- vocabularies (aligned with the forward pipeline) -----------------------

CAMERA_MOTIONS = ("static", "pan-left", "pan-right", "tilt-up", "tilt-down",
                  "push-in", "pull-out", "complex")
SUBJECT_MOTIONS = ("none", "low", "medium", "high")

# Finer than scene_plan visual_type; ASSET_TYPE_TO_VISUAL maps down to it.
ASSET_TYPES = ("painting", "illustration", "photo", "archival-footage",
               "live-footage", "map", "chart-graphic", "text-card",
               "talking-head", "animation", "other")
ASSET_TYPE_TO_VISUAL = {
    "painting": "generated-image", "illustration": "generated-image",
    "photo": "b-roll", "archival-footage": "b-roll", "live-footage": "b-roll",
    "talking-head": "b-roll", "animation": "generated-image",
    "map": "graphic", "chart-graphic": "graphic", "text-card": "text-overlay",
    "other": "b-roll",
}

# The COARSE, cross-library EDITORIAL roll-up — the one label a video-essay editor filters on ("give me
# b-roll"). The transcript tier's gemma emits `content_kind` directly (it has no shots); the video library
# derives it from a shot's richer `asset_type` via this map, so a "b-roll only" filter means the same thing
# in both. talking_head is split OUT of b-roll here (unlike ASSET_TYPE_TO_VISUAL, which is a RENDER-treatment
# map) because for asset finding a talking head is the thing you usually DON'T want.
CONTENT_KINDS = ("broll", "stills", "talking_head", "graphics")
ASSET_TYPE_TO_CONTENT_KIND = {
    "live-footage": "broll", "archival-footage": "broll",   # MOVING footage — the b-roll workhorse
    "photo": "stills", "painting": "stills", "illustration": "stills",   # still imagery, its own category
    "talking-head": "talking_head",
    "map": "graphics", "chart-graphic": "graphics", "text-card": "graphics", "animation": "graphics",
    "other": "",
}


def content_kind_of(asset_type: str) -> str:
    """Coarse editorial content_kind for a shot's asset_type (see ASSET_TYPE_TO_CONTENT_KIND)."""
    return ASSET_TYPE_TO_CONTENT_KIND.get((asset_type or "").strip().lower(), "")

# Cut detection (mirrors video_style.tempo / sampler adaptive settings)
CUT_FLOOR = 0.45
CUT_SIGMA = 3.0
SCORES_SIGMA = 5.0          # adaptive sigma used by the sampler's scene scores
MIN_SHOT = 0.4              # seconds

# Motion thresholds (flow normalized by frame diagonal, per second)
STATIC_EPS = 0.010
DIV_DOMINANCE = 1.2
# subject metric = fraction of pixels moving faster than SUBJECT_SPEED_FLOOR
# after removing camera translation (calibrated on synthetic pans/subjects)
SUBJECT_SPEED_FLOOR = 0.02
SUBJECT_BUCKETS = ((0.02, "none"), (0.10, "low"), (0.35, "medium"))  # else high
FLOW_DT = 0.4               # seconds between flow sample frames
FLOW_SIZE = (320, 180)      # downscale for Farneback


# ============================ shot detection ================================

def _video_duration(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        return (total / fps) if fps else 0.0
    finally:
        cap.release()


def _cuts_from_scores_json(video_path: Path) -> Optional[List[tuple]]:
    """Cut list from the sampler's cached FFmpeg scene scores, if usable.

    Returns [(timestamp, score), ...] or None when no valid cache exists.
    """
    p = Path(str(video_path) + ".scores.json")
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        frames = data.get("frames") or []
        if len(frames) < 10:
            return None
        scores = [float(s) for _, s in frames]
        thr = mean(scores) + SCORES_SIGMA * (pstdev(scores) if len(scores) > 1 else 0)
        cuts, last = [], -1e9
        for t, s in frames:
            if s >= thr and t - last >= MIN_SHOT:
                cuts.append((float(t), float(s)))
                last = t
        return cuts
    except Exception:
        return None


def detect_shots(video_path: Path) -> List[Dict[str, Any]]:
    """Split a video into shots (cut-to-cut intervals).

    Prefers the sampler's ``.scores.json`` cache (free); falls back to
    ``video_style.tempo.detect_cuts`` (one streaming pass). Returns dicts with
    ``shot_index / timestamp_start / timestamp_end / cut_score``.
    """
    video_path = Path(video_path)
    duration = _video_duration(video_path)
    cuts = _cuts_from_scores_json(video_path)
    if cuts is None:
        from nolan.video_style.tempo import detect_cuts
        cut_ts, scan = detect_cuts(video_path, sample_fps=4.0)
        duration = duration or scan.get("duration", 0.0)
        score_at = dict(zip(scan.get("ts", []), scan.get("scores", [])))
        cuts = [(t, score_at.get(t)) for t in cut_ts]

    bounds = [0.0] + [t for t, _ in cuts if 0.0 < t < duration]
    shots = []
    for i, start in enumerate(bounds):
        end = bounds[i + 1] if i + 1 < len(bounds) else duration
        if end - start < 0.05:      # degenerate sliver
            continue
        score = next((s for t, s in cuts if t == start), None)
        shots.append({"shot_index": len(shots), "timestamp_start": round(start, 3),
                      "timestamp_end": round(end, 3), "cut_score": score,
                      "rep_timestamp": round((start + end) / 2, 3)})
    return shots


# =========================== motion classification ==========================

def _gray(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(cv2.resize(frame, FLOW_SIZE), cv2.COLOR_BGR2GRAY)


def _flow_pair(cap: cv2.VideoCapture, t: float, dt: float,
               fps: float) -> Optional[tuple]:
    """Read two frames `dt` seconds apart starting at `t`.

    Seeks ONCE then reads forward — a second POS_MSEC seek can snap to the
    same keyframe on some codecs (mp4v), which reads as zero motion.
    """
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
    ok, a = cap.read()
    if not ok or a is None:
        return None
    skip = max(0, int(round(dt * (fps or 24.0))) - 1)
    for _ in range(skip):
        if not cap.grab():
            return None
    ok, b = cap.read()
    if not ok or b is None:
        return None
    return _gray(a), _gray(b)


def classify_flow(prev: np.ndarray, curr: np.ndarray, dt: float) -> Dict[str, Any]:
    """Classify camera + subject motion from one dense-flow field.

    All magnitudes are normalized by the frame diagonal and expressed
    per second, so shot length and resolution don't skew the buckets.
    """
    flow = cv2.calcOpticalFlowFarneback(prev, curr, None,
                                        0.5, 4, 25, 3, 5, 1.2, 0)
    h, w = prev.shape
    diag = float(np.hypot(w, h))
    per_sec = 1.0 / (diag * max(dt, 1e-6))

    # Global (camera) translation: median is robust to moving subjects.
    med = np.median(flow.reshape(-1, 2), axis=0)          # content drift px
    trans = float(np.hypot(*med)) * per_sec

    # Radial divergence: positive = content expanding = push-in / zoom-in.
    ys, xs = np.mgrid[0:h, 0:w]
    rx, ry = (xs - w / 2.0), (ys - h / 2.0)
    rn = np.sqrt(rx * rx + ry * ry) + 1e-6
    radial = (flow[..., 0] * rx + flow[..., 1] * ry) / rn  # px along radial
    div = float(np.mean(radial)) * per_sec

    # Subject motion: what's left after removing the global translation —
    # measured as the FRACTION of pixels moving faster than a speed floor,
    # so a small-but-real subject isn't diluted by a mostly-static frame.
    # The floor scales with camera speed: optical-flow noise grows when the
    # camera moves, and a subject slower than ~half the camera drift reads
    # as part of the scene drift anyway.
    residual = flow - med.reshape(1, 1, 2)
    r_speed = np.hypot(residual[..., 0], residual[..., 1]) * per_sec
    floor = max(SUBJECT_SPEED_FLOOR, 0.5 * max(trans, abs(div)))
    subject = float(np.mean(r_speed > floor))

    return {"translation": trans, "dx": float(med[0]) * per_sec,
            "dy": float(med[1]) * per_sec, "divergence": div, "subject": subject}


def _camera_label(m: Dict[str, float]) -> str:
    trans, div = m["translation"], m["divergence"]
    if max(trans, abs(div)) < STATIC_EPS:
        return "static"
    if abs(div) > trans * DIV_DOMINANCE:
        return "push-in" if div > 0 else "pull-out"
    dx, dy = m["dx"], m["dy"]
    if abs(dx) >= abs(dy):
        # content drifting left (dx<0) means the camera pans right
        return "pan-right" if dx < 0 else "pan-left"
    return "tilt-down" if dy < 0 else "tilt-up"


def _subject_label(subject: float) -> str:
    for thr, label in SUBJECT_BUCKETS:
        if subject < thr:
            return label
    return "high"


def treatment_hint(camera_motion: str, subject_motion: str) -> str:
    """Map measured motion to the motion library's treatment vocabulary."""
    if subject_motion in ("medium", "high"):
        return "as-is"                       # real moving footage: use as clip
    return {
        "static": "hold",
        "push-in": "ken-burns-in",
        "pull-out": "ken-burns-out",
        "pan-left": "ken-burns-pan", "pan-right": "ken-burns-pan",
        "tilt-up": "ken-burns-pan", "tilt-down": "ken-burns-pan",
        "complex": "subtle-push",
    }.get(camera_motion, "hold")


def classify_shot_motion(video_path: Path, shots: List[Dict[str, Any]]) -> None:
    """Annotate shots in place with camera/subject motion + treatment hint.

    Samples up to two flow pairs per shot, FLOW_DT seconds apart around the
    shot's middle (consistent dt keeps Farneback correspondences reliable).
    Shots too short for a pair are labeled static/none with magnitude 0.
    """
    cap = cv2.VideoCapture(str(Path(video_path)))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        for shot in shots:
            s, e = shot["timestamp_start"], shot["timestamp_end"]
            mid, length = (s + e) / 2.0, e - s
            metrics: List[Dict[str, Any]] = []
            if length >= FLOW_DT * 1.5:
                anchors = [mid - FLOW_DT / 2] if length < FLOW_DT * 4 else \
                          [s + length * 0.25, mid, min(e - FLOW_DT, s + length * 0.75)]
                for t in anchors:
                    pair = _flow_pair(cap, t, FLOW_DT, fps)
                    if pair is not None:
                        metrics.append(classify_flow(pair[0], pair[1], FLOW_DT))
            if metrics:
                agg = {k: float(np.median([m[k] for m in metrics]))
                       for k in ("translation", "dx", "dy", "divergence", "subject")}
                cam = _camera_label(agg)
                sub = _subject_label(agg["subject"])
                mag = round(max(agg["translation"], abs(agg["divergence"])), 5)
            else:
                cam, sub, mag = "static", "none", 0.0
            shot["camera_motion"] = cam
            shot["subject_motion"] = sub
            shot["motion_magnitude"] = mag
            shot["treatment_hint"] = treatment_hint(cam, sub)
    finally:
        cap.release()


# ============================== vision facts ================================

FACTS_PROMPT = """Look at this single video frame and classify it. Reply with STRICT JSON only, no prose:
{"asset_type": "<one of: painting, illustration, photo, archival-footage, live-footage, map, chart-graphic, text-card, talking-head, animation, other>",
 "framing": "<wide | medium | close-up>",
 "on_screen_text": "<any text burned into the frame, verbatim, else empty string>",
 "identity_hint": "<ONLY if this shows a famous identifiable artwork/place/person: its name; else empty string>",
 "confidence": "<high | medium | low>"}"""


def _parse_json_object(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def extract_rep_frame(video_path: Path, timestamp: float, out_path: Path) -> bool:
    """Save the frame at `timestamp` as JPEG (Unicode/Windows-safe write)."""
    cap = cv2.VideoCapture(str(Path(video_path)))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, timestamp) * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            return False
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            return False
        buf.tofile(str(out_path))
        return True
    finally:
        cap.release()


VISION_CONCURRENCY = 5


def _apply_vision_data(shot: Dict[str, Any], data: Dict[str, Any]) -> None:
    at = str(data.get("asset_type") or "").strip().lower()
    shot["asset_type"] = at if at in ASSET_TYPES else ("other" if at else None)
    fr = str(data.get("framing") or "").strip().lower()
    shot["framing"] = fr if fr in ("wide", "medium", "close-up") else None
    shot["on_screen_text"] = (str(data.get("on_screen_text") or "").strip() or None)
    shot["identity_hint"] = (str(data.get("identity_hint") or "").strip() or None)


def _extract_rep_frames(video_path: Path, shots: List[Dict[str, Any]],
                        out_dir: Path) -> Dict[int, Path]:
    """Save every shot's representative frame with ONE capture handle."""
    frames: Dict[int, Path] = {}
    cap = cv2.VideoCapture(str(Path(video_path)))
    try:
        for shot in shots:
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, shot["rep_timestamp"]) * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok:
                continue
            p = out_dir / f"shot_{shot['shot_index']:04d}.jpg"
            buf.tofile(str(p))
            frames[shot["shot_index"]] = p
    finally:
        cap.release()
    return frames


async def vision_shot_facts(video_path: Path, shots: List[Dict[str, Any]],
                            vision_provider, index=None,
                            concurrency: int = VISION_CONCURRENCY) -> int:
    """Annotate shots in place with vision facts; returns shots annotated.

    Frames are extracted serially (one capture handle — seeks are fast), then
    the vision calls run CONCURRENTLY under a semaphore, mirroring ingestion's
    pattern. When ``index`` is given and a shot carries a DB ``id``, each
    result is written through immediately (`update_shot_vision_facts`) so
    progress is observable and a crash loses nothing already fetched.
    Per-shot failures are skipped, not fatal.
    """
    import asyncio

    done = 0
    sem = asyncio.Semaphore(max(1, concurrency))
    with tempfile.TemporaryDirectory() as td:
        frames = _extract_rep_frames(Path(video_path), shots, Path(td))

        async def one(shot):
            nonlocal done
            frame_path = frames.get(shot["shot_index"])
            if frame_path is None:
                return
            async with sem:
                try:
                    raw = await vision_provider.describe_image(frame_path, FACTS_PROMPT)
                except Exception:
                    return
            data = _parse_json_object(raw)
            if not data:
                return
            _apply_vision_data(shot, data)
            if index is not None and shot.get("id") is not None:
                try:
                    index.update_shot_vision_facts(
                        shot["id"], asset_type=shot.get("asset_type"),
                        framing=shot.get("framing"),
                        on_screen_text=shot.get("on_screen_text"),
                        identity_hint=shot.get("identity_hint"))
                except Exception:
                    pass
            done += 1

        await asyncio.gather(*(one(s) for s in shots))
    return done


# ============================== orchestration ===============================

def facts_current(index, video_path: str) -> bool:
    """True when the library already has current-version facts for the video."""
    rows = index.get_shots(video_path)
    return bool(rows) and all(r.get("facts_version") == FACTS_VERSION for r in rows)


async def ensure_visual_facts(video_path: str, index, *, vision_provider=None,
                              force: bool = False) -> List[Dict[str, Any]]:
    """Compute-and-persist (or fetch) per-shot visual facts for one video.

    Idempotent and incremental:
    - rows current + vision present (or no provider) → returned as-is;
    - rows current but vision missing + provider given → **vision backfill
      only** (no recompute of shots/motion);
    - otherwise full recompute: deterministic facts (shots + motion) are
      persisted FIRST, then vision facts are written through row by row —
      so progress is observable mid-run and a vision crash still leaves
      complete motion facts in the library.
    """
    vid = index.get_video_id_by_path(video_path)
    if vid is None:
        raise ValueError(f"video not in library index: {video_path}")

    if not force and facts_current(index, video_path):
        rows = index.get_shots_by_video_id(vid)
        if vision_provider is None or any(r.get("asset_type") for r in rows):
            return rows
        # vision backfill on existing deterministic rows
        await vision_shot_facts(Path(video_path), rows, vision_provider, index=index)
        return index.get_shots_by_video_id(vid)

    shots = detect_shots(Path(video_path))
    classify_shot_motion(Path(video_path), shots)
    for s in shots:
        s["facts_version"] = FACTS_VERSION
    index.clear_shots(vid)
    index.add_shots_bulk(vid, shots)

    rows = index.get_shots_by_video_id(vid)     # now carrying DB ids
    if vision_provider is not None and rows:
        await vision_shot_facts(Path(video_path), rows, vision_provider, index=index)
        rows = index.get_shots_by_video_id(vid)
    return rows
