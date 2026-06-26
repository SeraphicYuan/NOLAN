"""Video-measured tempo — true cut rhythm, not an index-segment proxy.

The index's segment boundaries are shaped by the sampler config (min/max
interval), so cuts/min derived from them undercounts real editing. Here we
measure tempo directly from the video:

- **A. True cut detection** — stream the video at a low fps and flag shot cuts by
  HSV-histogram difference between consecutive frames (motion-robust: a moving
  subject barely changes the global histogram; a hard cut changes it a lot).
- **B. Tempo curve** — cuts/min in sliding windows + a trend descriptor
  (accelerates / steady / decelerates / varied).
- **C. Motion-weighted energy** — per-window intra-shot motion (mean pixel diff of
  *non-cut* transitions) blended with cut-rate into an overall energy index.

All local (OpenCV/NumPy); one decode pass per video.
"""

from __future__ import annotations

from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Dict, List

import cv2
import numpy as np

# Cut threshold on histogram distance (1 - HSV correlation), in [0,2]. Floored so
# static videos don't produce phantom cuts; adaptive component handles busy ones.
CUT_FLOOR = 0.45
CUT_SIGMA = 3.0
MIN_SHOT = 0.4  # seconds; merge cuts closer than this


def _hsv_hist(frame: np.ndarray) -> np.ndarray:
    small = cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(h, h)
    return h.astype(np.float32)


def _scan(video_path: Path, sample_fps: float):
    """Stream the video; return (timestamps, cut_scores, pixel_diffs, fps, duration)."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = (total / fps) if fps else 0.0
        stride = max(1, int(round(fps / sample_fps))) if fps else 1
        ts, cut_scores, pix = [], [], []
        prev_hist = prev_gray = None
        i = 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            if i % stride == 0:
                ok, frame = cap.retrieve()
                if not ok or frame is None:
                    break
                hist = _hsv_hist(frame)
                gray = cv2.cvtColor(cv2.resize(frame, (64, 36)), cv2.COLOR_BGR2GRAY).astype(float)
                if prev_hist is not None:
                    corr = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                    cut_scores.append(1.0 - float(corr))
                    pix.append(float(np.abs(gray - prev_gray).mean()) / 255)
                    ts.append(round(i / fps, 3) if fps else float(i))
                prev_hist, prev_gray = hist, gray
            i += 1
        return ts, cut_scores, pix, fps, duration
    finally:
        cap.release()


def detect_cuts(video_path: Path, sample_fps: float = 4.0):
    """Return (cut_timestamps, scan) — shot-boundary times in seconds."""
    ts, scores, pix, fps, duration = _scan(Path(video_path), sample_fps)
    scan = {"ts": ts, "scores": scores, "pix": pix, "fps": fps, "duration": duration}
    if not scores:
        return [], scan
    thr = max(CUT_FLOOR, mean(scores) + CUT_SIGMA * (pstdev(scores) if len(scores) > 1 else 0))
    cuts = []
    last = -1e9
    for i, sc in enumerate(scores):
        if sc >= thr and ts[i] - last >= MIN_SHOT:
            # local maximum vs neighbours to avoid double counting a transition
            if (i == 0 or sc >= scores[i - 1]) and (i == len(scores) - 1 or sc >= scores[i + 1]):
                cuts.append(ts[i])
                last = ts[i]
    return cuts, scan


def _trend(curve: List[Dict[str, Any]]) -> str:
    rates = [w["cuts_per_min"] for w in curve]
    if len(rates) < 2:
        return "steady"
    m = mean(rates) or 1e-6
    if pstdev(rates) / m > 0.6:
        return "varied"
    k = max(1, len(rates) // 3)
    first, last = mean(rates[:k]), mean(rates[-k:])
    if last > first * 1.4:
        return "accelerates"
    if first > last * 1.4:
        return "decelerates"
    return "steady"


def analyze_tempo(video_path: Path, sample_fps: float = 4.0,
                  window: float = 30.0) -> Dict[str, Any]:
    """Full video-measured tempo: cut rate, shot-length stats, curve, energy."""
    try:
        cuts, scan = detect_cuts(video_path, sample_fps=sample_fps)
    except ValueError as e:
        return {"available": False, "reason": str(e)}
    duration = scan["duration"]
    if not scan["scores"] or not duration:
        return {"available": False, "reason": "could not scan video"}

    n_shots = len(cuts) + 1
    cpm = round(n_shots / (duration / 60), 2) if duration else 0.0
    # shot lengths from cut boundaries
    bounds = [0.0] + cuts + [duration]
    shot_lens = [b - a for a, b in zip(bounds, bounds[1:]) if b > a]

    # B: windowed curve (cuts/min per window) + C: per-window intra-shot motion
    ts, scores, pix = scan["ts"], scan["scores"], scan["pix"]
    thr = max(CUT_FLOOR, mean(scores) + CUT_SIGMA * (pstdev(scores) if len(scores) > 1 else 0))
    curve = []
    t = 0.0
    while t < duration:
        t1 = min(duration, t + window)
        cuts_in = sum(1 for c in cuts if t <= c < t1)
        # intra-shot motion = mean pixel diff of NON-cut transitions in the window
        motions = [pix[i] for i in range(len(ts)) if t <= ts[i] < t1 and scores[i] < thr]
        curve.append({
            "t": round(t, 1),
            "cuts_per_min": round(cuts_in / ((t1 - t) / 60), 2) if t1 > t else 0.0,
            "motion": round(mean(motions), 3) if motions else 0.0,
        })
        t += window

    intra_motion = round(mean([w["motion"] for w in curve]), 3) if curve else 0.0
    # C: blended energy (heuristic): cut-rate (norm to ~24 cpm) + intra-shot motion
    energy = round(0.6 * min(1.0, cpm / 24) + 0.4 * min(1.0, intra_motion * 6), 3)
    tempo = "fast" if cpm >= 20 else "moderate" if cpm >= 8 else "slow"

    return {
        "available": True,
        "method": "video-cut-detection",
        "sample_fps": sample_fps,
        "cut_count": len(cuts),
        "cuts_per_min": cpm,
        "shot_len_mean": round(mean(shot_lens), 2) if shot_lens else 0.0,
        "shot_len_median": round(median(shot_lens), 2) if shot_lens else 0.0,
        "shot_len_stdev": round(pstdev(shot_lens), 2) if len(shot_lens) > 1 else 0.0,
        "intra_shot_motion": intra_motion,
        "energy": energy,
        "tempo": tempo,
        "trend": _trend(curve),
        "window": window,
        "curve": curve,
    }
