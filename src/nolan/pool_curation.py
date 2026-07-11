"""P2.1 — pool curation scoring.

The v2 pool had unusable assets (burned-in text, too-busy-for-overlay, wrong aspect) and nothing
modeled fitness — the author caught them by hand with a contact sheet. This scores each pool image
so the author + the density gate stop forcing bad grounds:

  - orientation / aspect        (PIL) — a portrait clip as a full-bleed ground letterboxes
  - overlay_safe + safe_rect    (numpy gradient) — is there a large low-detail region to place text
  - has_burned_text             (Tesseract, OPTIONAL — None if unavailable) — route to document/newshead only

Plus a THINNESS signal (overlay-safe landscape supply vs grounded-beat demand — v2 had ~13 clean
images for 26 grounded beats, silently forcing a2_00×5) and a best_asset router.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


def _load_gray(path: Path, width: int = 200):
    from PIL import Image
    import numpy as np
    im = Image.open(path).convert("L")
    ow, oh = im.size
    h = max(1, round(width * oh / ow))
    arr = np.asarray(im.resize((width, h)), dtype="float32") / 255.0
    return arr, (ow, oh)


def orientation(size) -> tuple:
    w, h = size
    a = (w / h) if h else 1.0
    o = "landscape" if a >= 1.2 else ("portrait" if a <= 0.83 else "square")
    return o, round(a, 2)


def _gradmag(gray):
    import numpy as np
    gy, gx = np.gradient(gray)
    return np.sqrt(gx * gx + gy * gy)


def overlay_safety(gray) -> Dict:
    """A large low-detail region to drop text on? Scans a 3×3 grid for the calmest cell."""
    mag = _gradmag(gray)
    h, w = gray.shape
    rh, rw = h // 3, w // 3
    best_score, best_rect = 1e9, (0.0, 0.0, 1 / 3, 1 / 3)
    for ry in (0, rh, 2 * rh):
        for rx in (0, rw, 2 * rw):
            score = float(mag[ry:ry + rh, rx:rx + rw].mean())
            if score < best_score:
                best_score, best_rect = score, (rx / w, ry / h, rw / w, rh / h)
    overall = float(mag.mean())
    safe = best_score < 0.06 and overall < 0.13
    return {"overlay_safe": safe, "safe_rect": [round(x, 3) for x in best_rect],
            "calmest_region_detail": round(best_score, 4), "overall_detail": round(overall, 4)}


def has_burned_text(path: Path) -> Optional[bool]:
    """True/False if Tesseract is available (≥4 confident words = burned-in text); None if not."""
    try:
        import pytesseract
        from PIL import Image
        d = pytesseract.image_to_data(Image.open(path), output_type=pytesseract.Output.DICT)
        words = [t for t, c in zip(d.get("text", []), d.get("conf", []))
                 if str(t).strip() and float(c) > 60]
        return len(words) >= 4
    except Exception:
        return None


def score_asset(path) -> Dict:
    path = Path(path)
    gray, size = _load_gray(path)
    o, a = orientation(size)
    sc = {"orientation": o, "aspect": a, "has_burned_text": has_burned_text(path)}
    sc.update(overlay_safety(gray))
    return sc


def _asset_path(comp_dir: Path, entry: dict) -> Optional[Path]:
    for cand in (comp_dir / "capture" / "assets" / entry.get("file", ""),
                 comp_dir / "assets" / Path(entry.get("file", "")).name):
        if cand.is_file():
            return cand
    return None


def curate_pool(comp_dir) -> Dict:
    """Score every pool image, write the tags back into pool.json, return a thinness summary."""
    comp_dir = Path(comp_dir)
    pool = json.loads((comp_dir / "pool.json").read_text(encoding="utf-8"))
    scored = 0
    for a in pool:
        if a.get("media_type") == "video":
            continue
        p = _asset_path(comp_dir, a)
        if not p:
            continue
        try:
            a.update(score_asset(p))
            scored += 1
        except Exception as e:
            a["curation_error"] = f"{type(e).__name__}: {e}"
    (comp_dir / "pool.json").write_text(json.dumps(pool, indent=2), encoding="utf-8")
    summary = thinness(pool)
    summary["scored"] = scored
    return summary


def thinness(pool: List[dict], grounded_beats: Optional[int] = None) -> Dict:
    """Supply of clean full-bleed grounds vs demand — the silent thinness that forces asset reuse."""
    imgs = [a for a in pool if a.get("media_type") != "video"]
    safe_landscapes = [a for a in imgs if a.get("overlay_safe") and a.get("orientation") == "landscape"]
    burned = [a for a in imgs if a.get("has_burned_text") is True]
    out = {"n_images": len(imgs), "overlay_safe_landscapes": len(safe_landscapes),
           "burned_text": len(burned)}
    if grounded_beats:
        out["grounded_beats"] = grounded_beats
        out["thin"] = len(safe_landscapes) < grounded_beats
    return out


def best_asset(candidates: List[dict], role: str = "ground") -> Optional[dict]:
    """Rank candidates for a use. Full-bleed grounds want overlay-safe landscapes with no burned text;
    framed uses (gallery/newshead/comparison) only need to not have burned text."""
    def key(a):
        clean = 0 if a.get("has_burned_text") else 1
        if role == "ground":
            land = 1 if a.get("orientation") == "landscape" else 0
            safe = 1 if a.get("overlay_safe") else 0
            calm = -a.get("overall_detail", 1.0)
            return (clean, safe, land, calm)
        return (clean, -a.get("overall_detail", 1.0))
    ranked = sorted(candidates, key=key, reverse=True)
    return ranked[0] if ranked else None
