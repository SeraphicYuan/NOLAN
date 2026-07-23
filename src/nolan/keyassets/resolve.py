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


# Kinds whose NAME is generic/ambiguous without the essay's subject ("The Four Cs" → four-stroke engine;
# "Star of South Africa" → a Call-of-Duty cover). These get the domain woven into their queries + verify;
# specific named people/orgs/places don't (their names already disambiguate).
_DOMAIN_KINDS = {"concept", "work", "event"}


def _dedup(cands: List[str], cap: int) -> List[str]:
    seen, out = set(), []
    for q in cands:
        q = (q or "").strip()
        k = q.lower()
        if q and k not in seen:
            seen.add(k)
            out.append(q)
    return out[:cap]


def queries_for(entity: KeyEntity, desired: DesiredAsset, domain: str = "") -> List[str]:
    """Image-search phrasings for one desired asset. PREFER the LLM-generated `desired.queries`
    (querygen — context-rich, ordered canonical→descriptive) + a bare-name safety net. Falls back to
    mechanical templating (name+note / domain-anchored / name+qualifier / bare) when querygen didn't run."""
    llm_qs = getattr(desired, "queries", None) or []
    if llm_qs:
        return _dedup(list(llm_qs) + [(entity.name or "").strip()], cap=5)
    name = (entity.name or "").strip()
    qual = _QUALIFIER.get(desired.type, "")
    note = (desired.note or "").strip()
    dom = domain.strip()
    use_dom = bool(dom) and entity.kind in _DOMAIN_KINDS and dom.lower() not in name.lower()
    cands = []
    if note:
        cands.append(f"{name} {note}"[:90].strip())          # most specific — the note has real context
    if use_dom:
        cands.append(f"{name} {dom} {qual}".strip())          # disambiguate a generic name by domain
    cands.append(f"{name} {qual}".strip())
    cands.append(name)
    return _dedup(cands, cap=4)


def _verify_subject(entity: KeyEntity, desired: DesiredAsset, domain: str = "") -> str:
    """The subject string the VLM judges against — name + the entity's IDENTIFIERS (querygen: role/
    affiliation/era) + note, so a correct 'four Cs diamond grading chart' isn't rejected because
    'The Four Cs' alone is too vague, AND so the verify aligns with the enriched queries (no drift).
    Falls back to the domain hint for ambiguous kinds when identifiers are absent."""
    name = (entity.name or "").strip()
    parts = [name]
    ids = getattr(entity, "identifiers", None) or []
    if ids:
        parts.append(", ".join(str(x) for x in ids[:3]))
    elif domain.strip() and entity.kind in _DOMAIN_KINDS and domain.strip().lower() not in name.lower():
        parts.append(domain.strip())
    if desired.note:
        parts.append(desired.note.strip())
    return " — ".join(dict.fromkeys(p for p in parts if p))[:180]


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


def _reformulate_queries(cfg, entity: KeyEntity, desired: DesiredAsset, failed: List[str],
                         reason: str) -> List[str]:
    """Tier C: ONE extra try. Given the failed queries + WHY (`nothing` found vs `wrong` subject), ask
    the LLM for 3 new queries from a different angle. Empty on any failure (contained)."""
    try:
        import asyncio
        import json as _json
        import re as _re
        from nolan.llm import create_text_llm
        sys = "You are a photo researcher. Your earlier image-search queries failed. Reply with STRICT JSON only."
        fail = "returned images of the WRONG subject" if reason == "wrong" else "returned nothing"
        ids = "; ".join(str(x) for x in (getattr(entity, "identifiers", None) or []))
        user = (f'SUBJECT: "{entity.name}" ({entity.kind}) — {entity.narrative_role}\n'
                f'IDENTIFIERS: {ids}\nASSET NEED: type={desired.type}, note="{(desired.note or "").strip()}"\n'
                f'These queries FAILED: {failed}\nFAILURE: {fail}\n\n'
                "Write 3 NEW queries from a DIFFERENT angle, each 3-7 words:\n"
                "- if nothing was found: BROADEN, or use alternative names / simpler terms.\n"
                "- if the wrong subject returned: ADD stronger disambiguators (exact proper name, role, "
                "affiliation, era, place).\n"
                'Return ONLY JSON: {"queries": ["...","...","..."]}')
        raw = asyncio.run(create_text_llm(cfg).generate(user, system_prompt=sys))
        m = _re.search(r"\{.*\}", raw or "", _re.DOTALL)
        d = _json.loads(m.group(0)) if m else {}
        return _dedup([str(q) for q in (d.get("queries") or [])], cap=3)
    except Exception:
        return []


def resolve_image(cfg, client, entity: KeyEntity, desired: DesiredAsset, out: Path,
                  *, verify: bool = True, domain: str = "", reformulate: bool = True) -> Optional[dict]:
    """Search → download → validate → VLM relevance-verify the first usable image into `out`. On total
    failure, Tier-C reformulates the queries once and retries. Returns a provenance dict (with `verified`)
    or None — an EXACT asset that never confirms is dropped (missing beats wrong); `related` kept unverified."""
    need_verify = verify and desired.type in _VERIFY_IMAGE_TYPES
    evocative = desired.relevance == "related"
    subject = _verify_subject(entity, desired, domain)

    def _run(queries):
        downloaded = False
        tries = 0
        for q in queries:
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
                downloaded = True
                confirmed = None
                if need_verify:
                    confirmed = _verify_match(cfg, out, subject, evocative=evocative)
                    if not evocative and confirmed is not True:   # EXACT: require a POSITIVE match
                        tries += 1
                        out.unlink(missing_ok=True)
                        if tries >= _MAX_VERIFY_ATTEMPTS:
                            return None, downloaded
                        continue
                prov = _provenance(res, q)
                prov["file"] = out
                prov["verified"] = confirmed is True
                return prov, downloaded
        return None, downloaded

    queries = queries_for(entity, desired, domain)
    prov, downloaded = _run(queries)
    if prov:
        return prov
    if reformulate and not evocative:                        # Tier C — one fresh-angle retry
        seen = {q.lower() for q in queries}
        new = [q for q in _reformulate_queries(cfg, entity, desired, queries,
                                               "wrong" if downloaded else "nothing") if q.lower() not in seen]
        if new:
            prov, _ = _run(new)
            if prov:
                return prov
    return None


def _verify_video(cfg, video_path: Path, subject: str) -> Optional[bool]:
    """Multi-frame footage verify: sample up to 3 frames (a subject can be absent from any single one).
    True if ANY frame confirms, False only if ALL explicitly reject, else None (kept-but-unverified) —
    a single mid-frame was too strict and dropped recoverable clips."""
    import os
    import subprocess
    import tempfile
    from nolan.acquire.context import _ffmpeg
    ff = _ffmpeg()
    verdicts = []
    for ss in (1.0, 2.5, 4.0):
        fd, tmp = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        tmp = Path(tmp)
        try:
            subprocess.run([ff, "-y", "-ss", str(ss), "-i", str(video_path), "-frames:v", "1",
                            "-vf", "scale=768:-1", "-q:v", "4", str(tmp)], capture_output=True, timeout=30)
            if tmp.exists() and tmp.stat().st_size > 800:
                v = _verify_match(cfg, tmp, subject, evocative=False, retries=1)
                verdicts.append(v)
                if v is True:
                    return True                              # early accept on the first confirming frame
        except Exception:
            pass
        finally:
            tmp.unlink(missing_ok=True)
    if verdicts and all(v is False for v in verdicts):
        return False                                         # every frame rejected → genuinely wrong
    return None


def resolve_video(cfg, client, entity: KeyEntity, desired: DesiredAsset, out: Path,
                  clip_seconds: int = 20, *, verify: bool = True, domain: str = "",
                  reformulate: bool = True) -> Optional[dict]:
    """Search video providers → fetch a short on-disk segment into `out` → (for EXACT footage) VLM
    relevance-verify by MULTIPLE sampled frames; Tier-C reformulates once on total failure. Best-effort
    (archival video is fragile); returns provenance or None."""
    from nolan.acquire.context import _fetch_video_segment
    evocative = desired.relevance == "related"
    subject = _verify_subject(entity, desired, domain)

    def _run(queries):
        downloaded = False
        tries = 0
        for q in queries:
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
                downloaded = True
                confirmed = None
                if verify and not evocative:                 # verify EXACT footage; related stays loose
                    confirmed = _verify_video(cfg, out, subject)
                    if confirmed is False:                   # every sampled frame rejected → wrong clip
                        tries += 1
                        out.unlink(missing_ok=True)
                        if tries >= _MAX_VERIFY_ATTEMPTS:
                            return None, downloaded
                        continue
                prov = _provenance(res, q)
                prov["file"] = out
                prov["verified"] = confirmed is True
                return prov, downloaded
        return None, downloaded

    queries = queries_for(entity, desired, domain)
    prov, downloaded = _run(queries)
    if prov:
        return prov
    if reformulate and not evocative:
        seen = {q.lower() for q in queries}
        new = [q for q in _reformulate_queries(cfg, entity, desired, queries,
                                               "wrong" if downloaded else "nothing") if q.lower() not in seen]
        if new:
            prov, _ = _run(new)
            if prov:
                return prov
    return None
