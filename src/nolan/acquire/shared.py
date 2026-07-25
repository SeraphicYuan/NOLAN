"""Shared acquisition plumbing — ONE home for the small organs the recall pool (acquire engine + the HF
bridge) and the precision pool (keyassets) both need, so a fix lands once instead of drifting across 3
copies. Deliberately narrow: the genuinely-identical, correctness-critical helpers. The provider-tier
tables stay per-path (they differ on purpose — the engine ranks local+providers, the bridge providers
only) and the VLM *decision* stays per-path (a recall FLOOR vs a precision GATE); only the plumbing is
shared here.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional, Tuple


def valid_image(path) -> bool:
    """Reject non-decodable downloads (HTML error pages saved as .jpg, truncated files). Was copied
    verbatim into acquire/context.py, the bridge, and keyassets/resolve.py."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.load()
        return True
    except Exception:
        return False


def build_search_client(cfg):
    """The canonical ImageSearchClient construction — was copied 3× (context._stock_client, bridge
    _client, resolve.build_client). Keyed providers come from provider_keys() (single source of truth)."""
    from nolan.image_search import ImageSearchClient
    s = cfg.image_sources
    return ImageSearchClient(pexels_api_key=s.pexels_api_key or None,
                             pixabay_api_key=s.pixabay_api_key or None,
                             smithsonian_api_key=getattr(s, "smithsonian_api_key", "") or None,
                             keys=s.provider_keys())


def downscale_for_vision(path, max_dim: int = 1024) -> Tuple[Path, Optional[Path]]:
    """Downscale a still to <=max_dim BEFORE any vision call. A multi-MB / >4k-px image ERRORS the vision
    API, and depending on the caller's error-policy that either survives a floor as junk or drops from a
    gate — either way it must be avoided. Returns (path_to_send, temp_to_clean_or_None); a small image is
    sent as-is; on any failure the original is returned unchanged."""
    path = Path(path)
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        if max(im.size) <= max_dim:
            return path, None
        im.thumbnail((max_dim, max_dim))
        fd, tmp = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        im.save(tmp, "JPEG", quality=85)
        return Path(tmp), Path(tmp)
    except Exception:
        return path, None


# ---- clip CLAIM ledger: the one dedup channel between the precision pool and the recall pool ----
# keyassets (heroes) and the acquire fan-out (b-roll) both materialise clips by downloading a RANGE of a
# source URL, and they run as separate passes over the same project — so the same Bloomberg vault shot
# could land twice, once as `ka_de_beers_footage.mp4` and once as `a7_02.mp4`. Perceptual hashing is the
# wrong tool for video (two crops of one shot hash differently, and it costs decode); the RANGE is exact
# and already known at search time. So: whoever materialises a range CLAIMS it, and later passes skip an
# overlapping claim. Stills need none of this — seeding the pool's existing `taken_hashes` covers them.

def claims_path(project_dir) -> Path:
    return Path(project_dir) / "capture" / "_claims.json"


def load_claims(project_dir) -> list:
    p = claims_path(project_dir)
    if not p.exists():
        return []
    try:
        c = json.loads(p.read_text(encoding="utf-8"))
        return c if isinstance(c, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def record_claim(project_dir, *, url: str, start: float, dur: float, owner: str, file: str = "") -> None:
    """Claim [start, start+dur] of `url` for `owner` ('hero' | 'pool'). Best-effort — never raises."""
    if not url:
        return
    try:
        p = claims_path(project_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        claims = load_claims(project_dir)
        claims.append({"url": str(url), "start": round(float(start), 2), "dur": round(float(dur), 2),
                       "owner": owner, "file": str(file)})
        p.write_text(json.dumps(claims, indent=2, ensure_ascii=False), encoding="utf-8")
    except (OSError, TypeError, ValueError):
        pass


def clear_claims(project_dir, owner: str) -> int:
    """Drop every claim held by `owner`, keeping the others. Returns how many were dropped.

    A pool REBUILD must release its own claims first: the ledger is append-only, so re-acquiring into the
    same project would otherwise see the previous run's ranges as taken and skip them — the second run
    would come back with almost no transcript_lib clips and look like the source had gone dry. Hero claims
    survive, which is the point: heroes are collected once and the b-roll pool defers to them every time.
    """
    claims = load_claims(project_dir)
    kept = [c for c in claims if c.get("owner") != owner]
    dropped = len(claims) - len(kept)
    if dropped:
        try:
            claims_path(project_dir).write_text(json.dumps(kept, indent=2, ensure_ascii=False),
                                                encoding="utf-8")
        except OSError:
            return 0
    return dropped


def range_is_claimed(claims, url: str, start: float, dur: float, *, overlap: float = 0.5) -> Optional[dict]:
    """The existing claim this (url, range) duplicates, or None. `overlap` is the share of the SHORTER
    window that must intersect — two clips of the same shot rarely share exact in/out points."""
    if not url:
        return None
    try:
        a0, a1 = float(start), float(start) + float(dur)
    except (TypeError, ValueError):
        return None
    for c in claims or []:
        if c.get("url") != url:
            continue
        b0 = float(c.get("start", 0) or 0)
        b1 = b0 + float(c.get("dur", 0) or 0)
        inter = max(0.0, min(a1, b1) - max(a0, b0))
        shorter = min(a1 - a0, b1 - b0)
        if shorter > 0 and inter / shorter >= overlap:
            return c
    return None


def clean_media_inplace(path, cfg=None, *, vision: bool = True) -> Optional[dict]:
    """Crop a burned-in watermark/logo + caption band out of a freshly-pulled clip (and trim stray head/
    tail frames), REPLACING the file in place so the pooled asset is clean and the same aspect.

    Wraps `hyperframes.cleanup` (deterministic CV detect → one same-aspect crop + trim → one ffmpeg pass,
    with an optional vision confirm). Shared because the download-then-pool path exists TWICE: the human
    clip-review route (`POST /api/clipper/clip`) and the HEADLESS transcript_lib acquisition — the latter
    shipped without it, so acquisition pooled Bloomberg chyrons and 'PBS | AMERICAN EXPERIENCE' watermarks
    burned into the b-roll.

    NEVER raises and never loses the original: returns a summary dict ({changed:False} when there was
    nothing to remove, {error:…} when the attempt failed) — the caller keeps the clip either way.
    """
    import subprocess

    path = Path(path)
    try:
        from nolan.hyperframes import cleanup as cu
        confirm = None
        if vision:
            try:
                if cfg is None:
                    from nolan.config import load_config
                    cfg = load_config()
                confirm = cu.make_vision_confirm(path, cfg, cu.default_vision_provider(cfg))
            except Exception:
                confirm = None                      # vision down → deterministic CV alone (still useful)
        plan = cu.analyze(path, confirm)
        if not plan.get("changed"):
            return {"changed": False}
        out = path.with_name(path.stem + "__clean" + path.suffix)
        from nolan import clipper
        subprocess.run(cu.build_cmd(clipper._ffmpeg(), path, out, plan), capture_output=True)
        if not (out.exists() and out.stat().st_size > 1000):
            out.unlink(missing_ok=True)
            return {"error": "cleanup produced no file"}
        path.unlink(missing_ok=True)
        out.rename(path)                            # same name/path — the pool entry still points here
        return {"changed": True, "logo": bool(plan.get("logos")), "caption": bool(plan.get("caption")),
                "trimmed": plan.get("trim_in", 0) > 0
                or plan.get("trim_out", 0) < plan.get("dur", 0) - 1e-3,
                "zoom": plan.get("zoom")}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def parse_vision_json(raw: str) -> Optional[dict]:
    """Best-effort JSON object out of a VLM reply (handles ```json fences / prose around the object).
    Returns None when nothing parses — the caller decides what None means (a FLOOR keeps, a GATE drops)."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    return d if isinstance(d, dict) else None
