"""RESOLVE — turn a KeyEntity's desired assets into real downloaded (+ conditioned) files.

Reuses NOLAN's existing organs rather than reinventing them: `ImageSearchClient` for the multi-
provider search + download (the same client the acquisition engine uses — so all 25 providers,
Wikimedia/museums/archive.org included), `cutout.py` for collage cutouts, and the acquisition
engine's video-segment fetch for footage. Precision-first (this is the HERO pool, not b-roll):
named-entity queries, institutional sources boosted, and the entity id prefixes every filename so
`view._collected` attaches it to the right entity and the /keyassets gallery lights up.

Pure query/naming helpers are testable without a network; `resolve_image`/`resolve_video` do the I/O.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .schema import DesiredAsset, KeyEntity

# A short qualifier appended to the entity name per asset type (recall aid for provider search).
_QUALIFIER = {"logo": "logo", "portrait": "portrait", "product": "product photo",
              "artwork": "", "document": "", "photo": "", "map": "map", "footage": ""}

# Asset types where a wrong subject is a credibility hit → confirm the identity with a VLM before keeping
# (the wrong-entity risk: ddgs returns a plausible face that may not be the right person). Capped so a
# stubborn beat doesn't burn many vision calls; a portrait that never confirms is dropped LOUDLY (a
# wrong hero portrait is worse than a missing one — the human hand-adds it).
_VERIFY_TYPES = {"portrait", "artwork"}
_MAX_VERIFY_ATTEMPTS = 5

# Sources to BOOST for a named-entity asset (precision) — institutional/encyclopedic first. Names must
# match ImageSearchClient provider names. Unlisted → the client's own ranking.
_SOURCE_PREF = {
    "logo": ["wikimedia", "openverse"],
    "portrait": ["wikimedia", "loc", "smithsonian"],
    "artwork": ["wikimedia", "met", "artvee", "artic", "rijksmuseum"],
    "document": ["wikimedia", "archive_image", "loc"],
    "photo": ["wikimedia", "archive_image", "loc", "smithsonian"],
    "map": ["wikimedia", "loc"],
    "footage": ["archive", "nasa_video"],
}


def _valid_image(path: Path) -> bool:
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.load()
        return True
    except Exception:
        return False


def build_client(cfg):
    """The canonical ImageSearchClient (same construction as the acquisition bridge)."""
    from nolan.image_search import ImageSearchClient
    s = cfg.image_sources
    return ImageSearchClient(pexels_api_key=s.pexels_api_key or None,
                             pixabay_api_key=s.pixabay_api_key or None,
                             smithsonian_api_key=getattr(s, "smithsonian_api_key", "") or None,
                             keys=s.provider_keys())


def queries_for(entity: KeyEntity, desired: DesiredAsset) -> List[str]:
    """Search phrasings for one desired asset: name+qualifier, name+note, bare name — deduped, capped.
    For a `related` clip the entity name IS the evocative concept, so the bare name leads."""
    name = (entity.name or "").strip()
    qual = _QUALIFIER.get(desired.type, "")
    cands = [f"{name} {qual}".strip()]
    if desired.note:
        cands.append(f"{name} {desired.note}".strip()[:90])
    cands.append(name)
    seen, out = set(), []
    for q in cands:
        k = q.lower()
        if q and k not in seen:
            seen.add(k)
            out.append(q)
    return out[:3]


def _boost(results, asset_type: str):
    """Stable-sort so preferred (institutional) sources for this asset type come first."""
    pref = _SOURCE_PREF.get(asset_type, [])
    rank = {s: i for i, s in enumerate(pref)}
    return sorted(results, key=lambda r: rank.get(getattr(r, "source", ""), len(pref) + 5))


def _provenance(res, query: str) -> dict:
    return {"source": getattr(res, "source", "") or "", "source_url": getattr(res, "source_url", "") or "",
            "license": getattr(res, "license", "") or "", "photographer": getattr(res, "photographer", "") or "",
            "query": query}


def _verify_identity(cfg, path: Path, subject: str) -> Optional[bool]:
    """Ask the VLM 'does this depict <subject>?'. True/False when it can judge, None when vision is
    unavailable (→ caller accepts, unconfirmed). Reuses acquire.art_direction.verify_generation."""
    try:
        import asyncio
        from nolan.acquire.art_direction import verify_generation
        v = asyncio.run(verify_generation(cfg, path, {"query": subject, "evocative": False}))
        m = v.get("matches", True)
        return None if v.get("reason", "").lower().find("unavailable") >= 0 else bool(m)
    except Exception:
        return None


def resolve_image(cfg, client, entity: KeyEntity, desired: DesiredAsset, out: Path,
                  *, verify: bool = True) -> Optional[dict]:
    """Search → download → validate → (for portraits/artwork) VLM identity-verify the first usable image
    into `out`. Returns a provenance dict (with `verified`) or None. A verify-required asset that never
    confirms within the cap is dropped (None) — a wrong hero is worse than a missing one."""
    need_verify = verify and desired.type in _VERIFY_TYPES
    tries = 0
    for q in queries_for(entity, desired):
        try:
            results = client.search_assets(q, media_type="image", max_results=8) or []
        except Exception:
            continue
        for res in _boost(results, desired.type):
            try:
                res2 = client.resolve_asset(res)
                if client.download_image(res2, out) is None or not _valid_image(out):
                    out.unlink(missing_ok=True)
                    continue
            except Exception:
                out.unlink(missing_ok=True)
                continue
            confirmed = None
            if need_verify:
                confirmed = _verify_identity(cfg, out, entity.name)
                if confirmed is False:                       # wrong subject → try the next candidate
                    tries += 1
                    out.unlink(missing_ok=True)
                    if tries >= _MAX_VERIFY_ATTEMPTS:
                        return None                          # give up loudly rather than keep a wrong face
                    continue
            prov = _provenance(res, q)
            prov["file"] = out
            prov["verified"] = confirmed is True
            return prov
    return None


def resolve_video(cfg, client, entity: KeyEntity, desired: DesiredAsset, out: Path,
                  clip_seconds: int = 20) -> Optional[dict]:
    """Search video providers → fetch a short on-disk segment into `out`. Best-effort (archival video
    is fragile); returns provenance or None. Reuses the acquisition engine's range-seek segment fetch."""
    from nolan.acquire.context import _fetch_video_segment
    for q in queries_for(entity, desired):
        try:
            results = client.search_assets(q, media_type="video", max_results=6) or []
        except Exception:
            continue
        for res in _boost(results, "footage"):
            try:
                res2 = client.resolve_video(res) or res
                url = getattr(res2, "url", None)
                if not url:
                    continue
                if _fetch_video_segment(url, out, clip_seconds, getattr(res2, "duration", None)):
                    prov = _provenance(res, q)
                    prov["file"] = out
                    return prov
            except Exception:
                continue
    return None
