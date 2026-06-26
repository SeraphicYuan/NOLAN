"""Deterministic visual-style statistics for a video.

Cheap, objective signals computed with OpenCV/NumPy (both already deps via the
sampler) — no LLM. These form the trustworthy backbone of a video-style analysis;
the vision pass layers interpretation on top.

Computed:
- **format**: width, height, fps, aspect ratio, duration, orientation
- **color**: dominant palette (k-means → hex + weight), mean saturation/brightness/
  contrast, warm↔cool ratio
- **motion**: mean frame-to-frame difference across sampled frames (0–1)
- **graphics**: edge density + a lower-third activity proxy (overlay-heaviness)
- **pacing** (from indexed segments): cuts/min, shot-length mean/median/stdev
"""

from __future__ import annotations

import math
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


# --- helpers ---------------------------------------------------------------

def _aspect_ratio(w: int, h: int) -> str:
    if not w or not h:
        return "?"
    g = math.gcd(w, h)
    return f"{w // g}:{h // g}"


def _orientation(w: int, h: int) -> str:
    if not w or not h:
        return "?"
    if abs(w - h) / max(w, h) < 0.05:
        return "square"
    return "landscape" if w > h else "portrait"


def _to_hex(bgr) -> str:
    b, g, r = (int(max(0, min(255, c))) for c in bgr)
    return f"#{r:02x}{g:02x}{b:02x}"


def _resize(frame: np.ndarray, width: int = 160) -> np.ndarray:
    h, w = frame.shape[:2]
    if w <= width:
        return frame
    return cv2.resize(frame, (width, max(1, int(h * width / w))), interpolation=cv2.INTER_AREA)


# --- color / palette -------------------------------------------------------

def color_stats(frames: List[np.ndarray], n_colors: int = 5) -> Dict[str, Any]:
    """Palette (hex+weight), saturation/brightness/contrast, warm/cool ratio."""
    if not frames:
        return {}
    small = [_resize(f) for f in frames]
    pixels = np.concatenate([f.reshape(-1, 3) for f in small], axis=0).astype(np.float32)

    # Dominant palette via k-means (BGR).
    k = min(n_colors, max(1, len(np.unique(pixels.astype(np.uint8).reshape(-1, 3), axis=0))))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _compactness, labels, centers = cv2.kmeans(
        pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    labels = labels.flatten()
    counts = np.bincount(labels, minlength=k).astype(float)
    weights = counts / counts.sum()
    order = np.argsort(-weights)
    palette = [{"hex": _to_hex(centers[i]), "weight": round(float(weights[i]), 3)}
               for i in order]

    # HSV-based descriptors.
    hsv = cv2.cvtColor(np.concatenate(small, axis=0), cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0].astype(float), hsv[..., 1].astype(float), hsv[..., 2].astype(float)
    gray = cv2.cvtColor(np.concatenate(small, axis=0), cv2.COLOR_BGR2GRAY).astype(float)

    # Warm/cool only over reasonably saturated, lit pixels.
    colored = (S > 40) & (V > 30)
    hh = H[colored]
    warm = int(np.count_nonzero((hh <= 40) | (hh >= 150)))   # red/orange/yellow + wrap-red
    cool = int(np.count_nonzero((hh >= 80) & (hh <= 140)))   # green/cyan/blue
    denom = warm + cool
    warm_ratio = round(warm / denom, 3) if denom else 0.5

    return {
        "palette": palette,
        "saturation": round(float(S.mean()) / 255, 3),
        "brightness": round(float(V.mean()) / 255, 3),
        "contrast": round(float(gray.std()) / 255, 3),
        "warm_ratio": warm_ratio,            # 1.0 = all warm, 0.0 = all cool
        "temperature": "warm" if warm_ratio > 0.6 else "cool" if warm_ratio < 0.4 else "neutral",
    }


# --- motion / graphics -----------------------------------------------------

def motion_score(frames: List[np.ndarray]) -> float:
    """Mean abs luminance difference between consecutive sampled frames (0–1)."""
    if len(frames) < 2:
        return 0.0
    grays = [cv2.cvtColor(_resize(f), cv2.COLOR_BGR2GRAY).astype(float) for f in frames]
    diffs = [np.abs(grays[i] - grays[i - 1]).mean() / 255 for i in range(1, len(grays))]
    return round(float(mean(diffs)), 3)


def graphics_stats(frames: List[np.ndarray]) -> Dict[str, Any]:
    """Edge density (graphics/overlay proxy) + lower-third activity ratio."""
    if not frames:
        return {}
    edge_fracs, lower_ratios = [], []
    for f in frames:
        s = _resize(f)
        edges = cv2.Canny(cv2.cvtColor(s, cv2.COLOR_BGR2GRAY), 100, 200)
        frac = float(np.count_nonzero(edges)) / edges.size
        edge_fracs.append(frac)
        h = edges.shape[0]
        lower = float(np.count_nonzero(edges[int(h * 0.72):])) / max(1, edges[int(h * 0.72):].size)
        lower_ratios.append((lower / frac) if frac else 0.0)
    return {
        "edge_density": round(float(mean(edge_fracs)), 4),       # higher = more graphic/busy
        "lower_third_activity": round(float(mean(lower_ratios)), 3),  # >1 = bottom busier than avg
    }


# --- pacing (from indexed segments) ----------------------------------------

def pacing_from_segments(segments: List[Dict[str, Any]], duration: float) -> Dict[str, Any]:
    """Cut rhythm from the index's segment boundaries."""
    lengths = []
    for s in segments or []:
        a = s.get("timestamp_start"); b = s.get("timestamp_end")
        if a is not None and b is not None and b > a:
            lengths.append(float(b) - float(a))
    if not lengths:
        return {"available": False}
    cpm = round(len(lengths) / (duration / 60), 2) if duration else None
    tempo = ("fast" if (cpm or 0) >= 20 else "moderate" if (cpm or 0) >= 8 else "slow")
    return {
        "available": True,
        "segment_count": len(lengths),
        "cuts_per_min": cpm,
        "shot_len_mean": round(mean(lengths), 2),
        "shot_len_median": round(median(lengths), 2),
        "shot_len_stdev": round(pstdev(lengths), 2) if len(lengths) > 1 else 0.0,
        "tempo": tempo,
    }


# --- top-level -------------------------------------------------------------

def sample_frames(video_path: Path, max_frames: int = 24) -> Dict[str, Any]:
    """Evenly sample up to ``max_frames`` BGR frames; return frames + format info."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = (total / fps) if fps else 0.0
        frames, timestamps = [], []
        if total > 0:
            idxs = np.linspace(0, total - 1, min(max_frames, total)).astype(int)
            for i in idxs:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
                ok, fr = cap.read()
                if ok and fr is not None:
                    frames.append(fr)
                    timestamps.append(round(i / fps, 2) if fps else 0.0)
    finally:
        cap.release()
    return {
        "frames": frames,
        "timestamps": timestamps,
        "format": {
            "width": w, "height": h, "fps": round(fps, 2),
            "aspect_ratio": _aspect_ratio(w, h), "orientation": _orientation(w, h),
            "duration": round(duration, 2),
        },
    }


def analyze_video(video_path: Path, segments: Optional[List[Dict[str, Any]]] = None,
                  max_frames: int = 24) -> Dict[str, Any]:
    """Compute the full deterministic visual-stats bundle for a video."""
    sampled = sample_frames(video_path, max_frames=max_frames)
    frames = sampled["frames"]
    fmt = sampled["format"]
    return {
        "format": fmt,
        "color": color_stats(frames),
        "motion": motion_score(frames),
        "graphics": graphics_stats(frames),
        "pacing": pacing_from_segments(segments or [], fmt.get("duration", 0.0)),
        "frames_analyzed": len(frames),
    }
