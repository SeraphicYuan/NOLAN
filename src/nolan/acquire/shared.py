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
