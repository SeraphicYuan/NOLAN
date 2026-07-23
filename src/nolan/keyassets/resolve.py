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

# EVERY downloaded image/clip is relevance-checked by a VLM — not just faces. A wrong photo/document/clip
# is the same failure as a wrong portrait ("Star of South Africa" that's a Call of Duty screenshot, a
# "four Cs" chart that's unrelated). EXACT assets that never confirm are dropped LOUDLY (a wrong hero is
# worse than a missing one — the human hand-adds it); `related` (evocative) assets are kept but flagged
# (their match is loose by design). Capped so a stubborn beat doesn't burn many vision calls.
_VERIFY_IMAGE_TYPES = {"logo", "portrait", "product", "artwork", "document", "photo", "map"}
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


def _verify_match(cfg, path: Path, subject: str, *, evocative: bool = False,
                  retries: int = 2) -> Optional[bool]:
    """Ask the VLM 'does this image match <subject>?'. Returns True (confirmed), False (clearly wrong),
    or None (couldn't reach a verdict after retries). CRITICAL: an error/timeout NEVER returns True — a
    rate-limited call must not become a false confirmation (that shipped a Call-of-Duty cover as the
    'Star of South Africa'). Calls the vision provider directly (not verify_generation, which defaults
    to matches=True on error). Retries transient failures so a momentary rate-limit isn't a hard miss."""
    import asyncio
    import json
    import os
    import re
    import tempfile
    import time
    try:
        from nolan.evoke_broll import _vision_config
        from nolan.vision import create_vision_provider
        prov = create_vision_provider(_vision_config(cfg))
    except Exception:
        return None
    # Downscale first: a multi-MB / >4k-px image errors the vision API (that's why a Call-of-Duty cover
    # returned None instead of a clean False) — and under strict-keep an errored verdict would drop even
    # a CORRECT large image. A 1024px copy verifies reliably.
    small, tmp = str(path), None
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.thumbnail((1024, 1024))
        fd, tmp = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        im.save(tmp, "JPEG", quality=85)
        small = tmp
    except Exception:
        tmp = None
    metaphor = (" (this is an EVOCATIVE metaphor — judge whether it plausibly evokes the idea, not "
                "whether it literally depicts it)") if evocative else ""
    prompt = (f'Does this image clearly match / depict: "{subject}"?{metaphor} Judge the SUBJECT/entity, '
              "ignore art style. If it is obviously something else — a different product, a video-game or "
              'movie cover, a screenshot, an unrelated photo — answer false. Reply ONLY JSON: '
              '{"matches": true or false, "reason": "<short>"}.')
    try:
        for attempt in range(retries + 1):
            try:
                raw = asyncio.run(prov.describe_image(small, prompt))
                m = re.search(r"\{.*\}", raw or "", re.DOTALL)
                if m:
                    d = json.loads(m.group(0))
                    if "matches" in d:
                        return bool(d["matches"])            # the only path that can return True
            except Exception:
                pass
            if attempt < retries:
                time.sleep(1.2)
        return None                                          # never a false confirm
    finally:
        if tmp:
            Path(tmp).unlink(missing_ok=True)


def resolve_image(cfg, client, entity: KeyEntity, desired: DesiredAsset, out: Path,
                  *, verify: bool = True) -> Optional[dict]:
    """Search → download → validate → VLM relevance-verify the first usable image into `out`. Returns a
    provenance dict (with `verified`) or None. An EXACT asset that never confirms within the cap is
    dropped (None) — a wrong hero is worse than a missing one; a `related` asset is kept but unverified."""
    need_verify = verify and desired.type in _VERIFY_IMAGE_TYPES
    evocative = desired.relevance == "related"
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
                confirmed = _verify_match(cfg, out, entity.name, evocative=evocative)
                if not evocative and confirmed is not True:  # EXACT: require a POSITIVE match to keep
                    tries += 1                               # (False OR unconfirmed → try the next candidate)
                    out.unlink(missing_ok=True)
                    if tries >= _MAX_VERIFY_ATTEMPTS:
                        return None                          # missing beats wrong for a hero
                    continue
            prov = _provenance(res, q)
            prov["file"] = out
            prov["verified"] = confirmed is True
            return prov
    return None


def resolve_video(cfg, client, entity: KeyEntity, desired: DesiredAsset, out: Path,
                  clip_seconds: int = 20, *, verify: bool = True) -> Optional[dict]:
    """Search video providers → fetch a short on-disk segment into `out` → (for EXACT footage) VLM
    relevance-verify a mid-frame. Best-effort (archival video is fragile); returns provenance or None.
    Reuses the acquisition engine's range-seek segment fetch + mid-frame extract."""
    from nolan.acquire.context import _extract_midframe, _fetch_video_segment
    evocative = desired.relevance == "related"
    tries = 0
    for q in queries_for(entity, desired):
        try:
            results = client.search_assets(q, media_type="video", max_results=6) or []
        except Exception:
            continue
        for res in _boost(results, "footage"):
            try:
                res2 = client.resolve_video(res) or res
                url = getattr(res2, "url", None)
                if not url or not _fetch_video_segment(url, out, clip_seconds, getattr(res2, "duration", None)):
                    continue
            except Exception:
                continue
            confirmed = None
            if verify and not evocative:                     # verify EXACT footage by a mid-frame; related stays loose
                fr = _extract_midframe(out)
                if fr:
                    confirmed = _verify_match(cfg, fr, entity.name, evocative=False)
                    fr.unlink(missing_ok=True)
                    if confirmed is False:
                        tries += 1
                        out.unlink(missing_ok=True)
                        if tries >= _MAX_VERIFY_ATTEMPTS:
                            return None
                        continue
            prov = _provenance(res, q)
            prov["file"] = out
            prov["verified"] = confirmed is True
            return prov
    return None
