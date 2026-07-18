"""Composite asset-cleanup for the pool: DETECT (logo / burned-in captions / stray head+tail frames) →
PLAN one same-aspect crop + trim → EXECUTE in ONE ffmpeg pass → a new pool asset.

The detectors are deterministic CV (opencv + numpy) — three different signatures feeding ONE crop planner:
  • logo      — a STATIONARY structured blob in a CORNER (low temporal variance + real edges).
  • captions  — an INTERMITTENT, CHANGING TEXT band at the BOTTOM (bright centered strokes that vary).
  • trim      — a hard CUT within the first/last ~0.4s (the "belongs to the previous clip" frames).
An optional vision hook (`confirm=`) can sanity-check logo/caption against real content (a chyron, a
lower-third that's meant to be there) — the one place a model earns its keep; everything else is free.

`analyze(path)` returns a reviewable PLAN; `build_cmd(...)` turns it into the ffmpeg argv (crop keeps the
original W×H + aspect by scaling the cleared window back to fill — a small zoom, like a watermark crop).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_IMG_EXT = ("png", "jpg", "jpeg", "webp", "bmp", "gif", "avif")
_VID_EXT = ("mp4", "mov", "webm", "m4v", "avi", "mkv")


def _is_image(path) -> bool:
    return str(path).lower().rsplit(".", 1)[-1] in _IMG_EXT


# ------------------------------------------------------------------ frame loading (cv2)

def _load(path, max_frames: int = 240, width: int = 480):
    """Read frames (grayscale, downscaled to `width`) as an (N,H,W) uint8 stack + metadata. Short clips are
    read whole; long clips read the first/last ~1s FULLY (for edge-cut trim) and sample the middle. A still
    IMAGE loads as a 1-frame stack (fps=0, total=1) — caption + logo still apply; trim does not."""
    import cv2
    import numpy as np
    if _is_image(path):
        img = cv2.imread(str(path))
        if img is None:
            raise RuntimeError(f"could not read image {path}")
        oh, ow = img.shape[:2]
        h = max(1, round(width * oh / ow))
        g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (width, h), interpolation=cv2.INTER_AREA)
        return (np.stack([g]), ow, oh, 0.0, 1, [0])        # fps=0, total=1 → a single frame
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"could not open {path}")
    ow = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 0
    oh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if not (ow and oh):
        cap.release(); raise RuntimeError("no video dimensions")
    h = max(1, round(width * oh / ow))
    edge = max(2, round(fps * 1.0))                         # keep the first/last ~1s at full frame rate
    take = None
    if total and total > max_frames:                       # sample: all edges + strided middle
        mid = set(range(edge, max(edge, total - edge), max(1, (total - 2 * edge) // (max_frames - 2 * edge))))
        take = set(range(0, edge)) | mid | set(range(max(0, total - edge), total))
    grays, idxs = [], []
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if take is None or i in take:
            g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            grays.append(cv2.resize(g, (width, h), interpolation=cv2.INTER_AREA))
            idxs.append(i)
        i += 1
        if len(grays) >= max_frames and take is None:
            break
    cap.release()
    if len(grays) < 2:
        raise RuntimeError("too few frames to analyze")
    return (np.stack(grays), ow, oh, float(fps), (total or i), idxs)


# ------------------------------------------------------------------ detectors

def detect_logo(gray, persist: float = 0.6, min_px: int = 40) -> List[Dict[str, float]]:
    """STATIONARY corner graphics via EDGE PERSISTENCE — the fraction of frames a pixel is a Canny edge. A
    composited logo's OUTLINE sits at the same pixels every frame (even a SEMI-TRANSPARENT one, whose fill
    varies as the scene pans behind it — so temporal 'stillness' misses it, but its edge does not); moving
    scenery's edges wander, so their persistence is low. A logo = a COMPACT cluster of high-persistence edge
    pixels in a corner. Deliberately SENSITIVE (a static clip's corner scenery can persist too) — the vision
    `confirm` hook is the filter. Returns normalized [{x,y,w,h}]."""
    import cv2
    import numpy as np
    N, H, W = gray.shape
    if N == 1:                                              # a still IMAGE has no temporal cue → spatial proposer
        return _detect_logo_static(gray[0])
    acc = np.zeros((H, W), dtype=np.float32)
    for i in range(N):
        acc += (cv2.Canny(gray[i], 80, 180) > 0)
    hot = (acc / N > persist).astype("uint8")
    ch, cw = int(H * 0.30), int(W * 0.33)                   # true corners — keep the centre-bottom (captions!) out
    out = []
    for (y0, x0) in [(0, 0), (0, W - cw), (H - ch, 0), (H - ch, W - cw)]:
        m = hot[y0:y0 + ch, x0:x0 + cw]
        if int(m.sum()) < min_px:
            continue
        ys, xs = np.where(m)
        bw, bh = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
        density = m.sum() / float(bw * bh)                 # compact logo → dense; scattered scenery → sparse
        if density < 0.06 or bh > 0.32 * H or bw > 0.62 * W:
            continue
        bx0, by0 = (x0 + xs.min()) / W, (y0 + ys.min()) / H
        out.append({"x": round(bx0, 4), "y": round(by0, 4), "w": round(bw / W, 4), "h": round(bh / H, 4)})
    return out


def _detect_logo_static(frame) -> List[Dict[str, float]]:
    """A single IMAGE has no temporal cue, so PROPOSE a compact edge-dense graphic in each corner (a logo is
    a small dense cluster). Over-proposes (a busy corner qualifies) — the vision `confirm` hook is the filter
    that keeps only real logos. Returns normalized [{x,y,w,h}]."""
    import cv2
    import numpy as np
    H, W = frame.shape
    edges = cv2.dilate((cv2.Canny(frame, 80, 180) > 0).astype("uint8"), np.ones((3, 3), np.uint8))
    ch, cw = int(H * 0.30), int(W * 0.33)
    out = []
    for (y0, x0) in [(0, 0), (0, W - cw), (H - ch, 0), (H - ch, W - cw)]:
        m = edges[y0:y0 + ch, x0:x0 + cw]
        n, _lbl, stats, _c = cv2.connectedComponentsWithStats(m, 8)
        best = None
        for j in range(1, n):
            x, y, w, h, area = stats[j]
            if area < 0.02 * ch * cw or w > 0.9 * cw or h > 0.9 * ch:   # skip tiny specks + corner-filling scenery
                continue
            if best is None or area > best[4]:
                best = (x, y, w, h, area)
        if best is None:
            continue
        x, y, w, h, _a = best
        out.append({"x": round((x0 + x) / W, 4), "y": round((y0 + y) / H, 4),
                    "w": round(w / W, 4), "h": round(h / H, 4)})
    return out


def detect_captions(gray, min_cov: float = 0.35, cap_margin: float = 0.02) -> Optional[Dict[str, float]]:
    """Burned-in subtitles, detected as TEXT (not just bright edges): several GLYPH-SIZED bright connected
    components sharing a baseline in the central bottom band, in a good fraction of frames. Glyph-shaped +
    on-a-line is what tells a caption apart from busy scene content (suits, desks, a mic) that also has
    bright vertical edges. It does NOT require change (a single short subtitle is static). The
    caption-vs-legit-content call is left to the optional vision `confirm` hook + review. Returns
    {top, coverage} or None."""
    import cv2
    import numpy as np
    N, H, W = gray.shape
    band0 = int(H * 0.58)
    cx0, cx1 = int(W * 0.10), int(W * 0.90)
    line_tops: List[float] = []
    frame_has = 0
    for i in range(N):
        band = gray[i][band0:, :]
        _, th = cv2.threshold(band, 195, 255, cv2.THRESH_BINARY)       # white subtitle fill only
        n, _lbl, stats, _c = cv2.connectedComponentsWithStats(th, 8)
        gy0, cxs = [], []
        for j in range(1, n):
            x, y, w, h, area = stats[j]
            gx = x + w / 2
            if (0.012 * H <= h <= 0.09 * H) and (2 <= w <= 0.06 * W) and area >= 3 and cx0 <= gx <= cx1:
                gy0.append(band0 + y); cxs.append(gx)
        if len(gy0) >= 6:                                   # find the densest BASELINE (ignore stray specks)
            gy0, cxs = np.array(gy0, float), np.array(cxs, float)
            best_n, best_top = 0, None
            for t in np.unique(gy0):
                sel = (gy0 >= t) & (gy0 <= t + 0.055 * H)
                if sel.sum() >= 6 and (cxs[sel].max() - cxs[sel].min()) >= 0.20 * W and sel.sum() > best_n:
                    best_n, best_top = int(sel.sum()), t
            if best_top is not None:                        # ≥6 glyphs on a line, spread across the centre
                frame_has += 1
                line_tops.append(best_top)
    coverage = frame_has / N
    if coverage < min_cov:
        return None
    top = float(np.percentile(line_tops, 10)) / H - cap_margin          # the highest lines (2-line subs)
    top = min(max(top, 0.62), 0.98)                                     # never claim more than bottom ~38%
    return {"top": round(top, 4), "coverage": round(coverage, 3)}


def detect_trim(gray, fps: float, total: int, idxs: List[int], auto_max: float = 0.4,
                cand_max: float = 1.4, min_keep: float = 0.45) -> Tuple[float, float, List[Dict]]:
    """A stray from a neighbouring clip = a HARD CUT leaving a SHORT segment at the head/tail. Returns
    (trim_in, trim_out, candidates). A crumb (< auto_max s) is AUTO-trimmed (unambiguous); a bigger segment
    (auto_max‥cand_max, and < min_keep of the clip) is a CANDIDATE — because a hard cut leaving ~40% is
    indistinguishable by pixels from an intentional in-clip edit, so the vision `confirm` hook (or the human
    at review) decides. Conservative by default: candidates are NOT applied unless confirmed."""
    import numpy as np
    dur = total / fps if fps else 0.0
    if len(gray) < 3 or not dur:
        return 0.0, round(dur, 3), []
    d = np.array([np.abs(gray[i].astype(int) - gray[i - 1].astype(int)).mean() for i in range(1, len(gray))])
    thr = max(float(np.median(d)) * 6.0, 20.0)             # a real cut dwarfs normal motion
    cuts = [(idxs[k] / fps, float(d[k - 1])) for k in range(1, len(gray)) if d[k - 1] > thr]
    t_in, t_out, cands = 0.0, dur, []
    for t, mag in cuts:
        head, tail = t, dur - t
        if t <= cand_max and t < dur * min_keep:           # short HEAD segment
            if t <= auto_max:
                t_in = max(t_in, t)
            else:
                cands.append({"side": "head", "t": round(t, 3), "len": round(head, 3),
                              "frac": round(head / dur, 3), "mag": round(mag, 1)})
        if tail <= cand_max and tail < dur * min_keep:     # short TAIL segment
            if tail <= auto_max:
                t_out = min(t_out, t)
            else:
                cands.append({"side": "tail", "t": round(t, 3), "len": round(tail, 3),
                              "frac": round(tail / dur, 3), "mag": round(mag, 1)})
    return round(t_in, 3), round(t_out, 3), cands


# ------------------------------------------------------------------ crop planner (keep W×H + aspect)

def plan_crop(ow: int, oh: int, logos: List[Dict], caption: Optional[Dict],
              margin: float = 0.012) -> Optional[Dict[str, int]]:
    """One same-aspect crop rect (pixels) that CLEARS every exclusion, centred in the cleared area and
    scaled back to ow×oh by the executor. None when nothing to clear."""
    top = bottom = left = right = 0.0
    for b in logos:                                        # clear each corner logo via its cheaper edge
        cx, cy = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
        v_cost = (b["y"] + b["h"]) if cy < 0.5 else (1 - b["y"])
        h_cost = (b["x"] + b["w"]) if cx < 0.5 else (1 - b["x"])
        if v_cost <= h_cost:
            top = max(top, b["y"] + b["h"]) if cy < 0.5 else top
            bottom = max(bottom, 1 - b["y"]) if cy >= 0.5 else bottom
        else:
            left = max(left, b["x"] + b["w"]) if cx < 0.5 else left
            right = max(right, 1 - b["x"]) if cx >= 0.5 else right
    if caption:
        bottom = max(bottom, 1 - caption["top"])
    if top + bottom + left + right < 1e-6:
        return None
    left, top = left + margin, top + margin
    right, bottom = right + margin, bottom + margin
    ax0, ay0, ax1, ay1 = left * ow, top * oh, (1 - right) * ow, (1 - bottom) * oh  # allowed box (px)
    bw, bh = ax1 - ax0, ay1 - ay0
    if bw < ow * 0.4 or bh < oh * 0.4:                      # would zoom too hard → over-detection; bail
        return None
    A = ow / oh
    if bw / bh > A:
        h = bh; w = h * A
    else:
        w = bw; h = w / A
    ccx, ccy = (ax0 + ax1) / 2, (ay0 + ay1) / 2
    x = min(max(ccx - w / 2, 0), ow - w)
    y = min(max(ccy - h / 2, 0), oh - h)
    # even dims (encoders want them)
    W2, H2 = int(w) & ~1, int(h) & ~1
    return {"x": int(x) & ~1, "y": int(y) & ~1, "w": W2, "h": H2}


# ------------------------------------------------------------------ analyze + execute

def analyze(path, confirm: Optional[Callable[[str, Dict], bool]] = None) -> Dict[str, Any]:
    """Full cleanup PLAN for one asset — VIDEO or still IMAGE. `confirm(kind, info)->bool` is an optional
    vision hook to reject a false logo/caption / disambiguate a stray trim; when absent, CV decides alone.
    For an image: logo + caption crop apply (it's mostly for transcript + logo); trim does not."""
    is_img = _is_image(path)
    gray, ow, oh, fps, total, idxs = _load(path)
    logos = detect_logo(gray)
    caption = detect_captions(gray)
    if confirm:                                            # vision sanity-check logo/caption vs real content
        logos = [b for b in logos if confirm("logo", b)]
        if caption and not confirm("caption", caption):
            caption = None
    dur = total / fps if fps else 0.0
    t_in, t_out, open_cands = 0.0, dur, []
    if not is_img:                                         # trim is a VIDEO-only concept
        t_in, t_out, cands = detect_trim(gray, fps, total, idxs)
        for c in cands:                                    # confirm the ambiguous trims; unconfirmed → surfaced
            if confirm and confirm("trim", c):
                if c["side"] == "head":
                    t_in = max(t_in, c["t"])
                else:
                    t_out = min(t_out, c["t"])
            else:
                open_cands.append(c)
    crop = plan_crop(ow, oh, logos, caption)
    zoom = round(ow / crop["w"], 3) if crop else 1.0
    return {"kind": "image" if is_img else "video", "ow": ow, "oh": oh, "fps": round(fps, 3),
            "dur": round(dur, 3), "logos": logos, "caption": caption,
            "trim_in": round(t_in, 3), "trim_out": round(t_out, 3), "trim_candidates": open_cands,
            "crop": crop, "zoom": zoom,
            "changed": bool(crop) or t_in > 0 or (not is_img and t_out < dur - 1e-3)}


def make_vision_confirm(video_path, config=None, provider=None) -> Callable[[str, Dict], bool]:
    """A `confirm(kind, info) -> bool` backed by the OpenRouter VISION model — the semantic filter over the
    CV proposals. It extracts the relevant frame(s) and asks a strict yes/no: is the corner blob really a
    broadcaster LOGO (not filmed scenery)? is the bottom band a burned-in SUBTITLE (not a content chyron)?
    does the head/tail belong to a DIFFERENT shot (a stray to trim)? Lazy imports; the async vision call
    runs via asyncio.run — so run analyze() in a thread if you're already inside an event loop."""
    import asyncio
    import os
    import tempfile
    import cv2
    import numpy as np
    from pathlib import Path as _P
    if provider is None:
        from nolan.config import load_config
        from nolan.vision import VisionConfig, create_vision_provider
        v = (config or load_config()).vision                # map openrouter_api_key -> the provider's api_key
        model = v.model if "/" in (v.model or "") else "qwen/qwen3.7-plus"
        provider = create_vision_provider(VisionConfig(
            provider="openrouter", model=model, host=v.host, port=v.port, timeout=v.timeout,
            api_key=v.openrouter_api_key, base_url=v.base_url,
            reasoning_enabled=v.reasoning_enabled, reasoning_max_tokens=v.reasoning_max_tokens))
    is_img = _is_image(video_path)
    if is_img:
        dur = 0.0
    else:
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        dur = (int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0) / fps
        cap.release()

    def _grab(t: float):
        if is_img:
            return cv2.imread(str(video_path))             # a still — the frame is the image, ignore t
        c = cv2.VideoCapture(str(video_path))
        c.set(cv2.CAP_PROP_POS_MSEC, max(0.0, min(t, max(0.0, dur - 0.05))) * 1000)
        ok, fr = c.read()
        if not ok:
            c.release(); c = cv2.VideoCapture(str(video_path)); ok, fr = c.read()
        c.release()
        return fr if ok else None

    def _ask(img, prompt: str):
        fd, path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)                                       # close the mkstemp handle (Windows would lock it)
        p = _P(path)
        cv2.imwrite(str(p), img)
        try:
            ans = (asyncio.run(provider.describe_image(p, prompt)) or "").strip().lower()
        except Exception:
            return None                                    # vision unavailable → caller keeps CV verdict
        finally:
            try:
                p.unlink(missing_ok=True)
            except PermissionError:
                pass                                       # Windows lag — the temp dir cleans up
        return ans.startswith("yes") or "yes" in ans[:16]

    def confirm(kind: str, info: Dict) -> bool:
        if kind == "logo":
            corner = ("top-" if info["y"] < 0.5 else "bottom-") + ("left" if info["x"] < 0.5 else "right")
            img = _grab(dur * 0.5)
            r = img is not None and _ask(img, f"Look ONLY at the {corner} corner. Is there a broadcaster/"
                f"channel LOGO or watermark (a graphic overlaid on top of the footage) there — NOT part of "
                f"the filmed scene? Answer strictly 'yes' or 'no'.")
            return True if r is None else r                # None (no vision) → trust CV
        if kind == "caption":
            img = _grab(dur * 0.5)
            r = img is not None and _ask(img, "Across the BOTTOM of this frame, is there a burned-in "
                "SUBTITLE / closed-caption (a line of transcribed speech)? Answer 'no' if the bottom text is "
                "a news chyron, a lower-third name/title, a logo, or scene signage. Answer strictly 'yes' or "
                "'no'.")
            return True if r is None else r
        if kind == "trim":
            t, side = info["t"], info["side"]
            a, b = _grab(t - 0.2), _grab(t + 0.2)          # a shot each side of the cut
            if a is None or b is None:
                return False
            h = min(a.shape[0], b.shape[0])
            mont = np.hstack([cv2.resize(a, (int(a.shape[1] * h / a.shape[0]), h)),
                              cv2.resize(b, (int(b.shape[1] * h / b.shape[0]), h))])
            pos = "RIGHT" if side == "tail" else "LEFT"
            r = _ask(mont, f"Two frames from one video, on either side of a cut (left = earlier, right = "
                f"later). Is the {pos} frame a COMPLETELY DIFFERENT setting/location/subject — a stray shard "
                f"accidentally left from a NEIGHBOURING clip — rather than the SAME scene from another angle "
                f"or a natural continuation? Answer 'yes' ONLY if it is an unrelated shot that should be "
                f"removed; answer 'no' if it is the same scene/subject continuing. Strictly 'yes' or 'no'.")
            return bool(r)                                 # None (no vision) → don't trim (conservative)
        return True

    return confirm


def build_cmd(ff: str, src: Path, out: Path, plan: Dict[str, Any]) -> List[str]:
    """ONE ffmpeg pass from a plan(). VIDEO: trim (‑ss/‑t) + crop→scale-back (‑vf), re-encoded once. IMAGE:
    just crop→scale-back to a single still (no trim, keeps the same W×H)."""
    ow, oh = plan["ow"], plan["oh"]
    c = plan.get("crop")
    vf = f"crop={c['w']}:{c['h']}:{c['x']}:{c['y']},scale={ow}:{oh}:flags=lanczos" if c else None
    if plan.get("kind") == "image":
        args = [ff, "-y", "-i", str(src)]
        if vf:
            args += ["-vf", vf]
        return args + ["-frames:v", "1", "-update", "1", str(out)]
    dur = plan.get("dur") or 0.0
    t_in, t_out = float(plan.get("trim_in") or 0.0), float(plan.get("trim_out") or dur or 0.0)
    args = [ff, "-y"]
    if t_in > 0:
        args += ["-ss", f"{t_in:.3f}"]
    args += ["-i", str(src)]
    length = (t_out - t_in) if (t_out and t_out > t_in) else None
    if length and dur and (t_out < dur - 1e-3 or t_in > 0):
        args += ["-t", f"{length:.3f}"]
    if vf:
        args += ["-vf", vf]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-movflags", "+faststart", str(out)]
    return args
