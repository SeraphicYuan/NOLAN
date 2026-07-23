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

from ..acquire.shared import build_search_client, downscale_for_vision, parse_vision_json
from ..acquire.shared import valid_image as _valid_image
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
_MAX_VERIFY_ATTEMPTS = 3          # candidates tried per need before giving up (was 5 — trimmed for speed)

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


def build_client(cfg):
    """The canonical ImageSearchClient — delegates to the shared organ (was a 3rd copy)."""
    return build_search_client(cfg)


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
                  retries: int = 1) -> Optional[bool]:
    """Ask the VLM 'does this image match <subject>?'. Returns True (confirmed), False (clearly wrong),
    or None (couldn't reach a verdict after retries). CRITICAL: an error/timeout NEVER returns True — a
    rate-limited call must not become a false confirmation (that shipped a Call-of-Duty cover as the
    'Star of South Africa'). Calls the vision provider directly (not verify_generation, which defaults
    to matches=True on error). Retries transient failures so a momentary rate-limit isn't a hard miss."""
    import asyncio
    import time
    try:
        from nolan.evoke_broll import _vision_config
        from nolan.vision import create_vision_provider
        prov = create_vision_provider(_vision_config(cfg))
    except Exception:
        return None
    send, tmp = downscale_for_vision(path)                    # shared: big images error the API → 1024px copy
    metaphor = (" (this is an EVOCATIVE metaphor — judge whether it plausibly evokes the idea, not "
                "whether it literally depicts it)") if evocative else ""
    prompt = (f'Does this image clearly match / depict: "{subject}"?{metaphor} Judge the SUBJECT/entity, '
              "ignore art style. If it is obviously something else — a different product, a video-game or "
              'movie cover, a screenshot, an unrelated photo — answer false. Reply ONLY JSON: '
              '{"matches": true or false, "reason": "<short>"}.')
    try:
        for attempt in range(retries + 1):
            try:
                d = parse_vision_json(asyncio.run(prov.describe_image(str(send), prompt)))
                if d and "matches" in d:
                    return bool(d["matches"])                 # the only path that can return True
            except Exception:
                pass
            if attempt < retries:
                time.sleep(1.2)
        return None                                          # never a false confirm
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)


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
                  *, verify: bool = True, domain: str = "", reformulate: bool = True,
                  keep: int = 4) -> List[dict]:
    """Search → download → validate → VLM relevance-verify, keeping up to `keep` VERIFIED, distinct-source
    images (named out, out_2, out_3…) so the author has options. Returns a LIST of provenance dicts (empty
    if none). EXACT needs keep only positively-verified (missing beats wrong); `related` keep downloaded.
    On TOTAL failure (0 kept), Tier-C reformulates once. Total downloads/need are bounded."""
    need_verify = verify and desired.type in _VERIFY_IMAGE_TYPES
    evocative = desired.relevance == "related"
    subject = _verify_subject(entity, desired, domain)
    kept: List[dict] = []
    seen_urls: set = set()
    state = {"downloaded": False}
    max_dl = keep + _MAX_VERIFY_ATTEMPTS                      # cap total downloads (verified + rejected)/need

    def _dest() -> Path:
        return out if not kept else out.with_name(f"{out.stem}_{len(kept) + 1}{out.suffix}")

    def _run(queries):
        dls = 0
        for q in queries:
            if len(kept) >= keep:
                return
            try:
                results = client.search_assets(q, media_type="image", max_results=8) or []
            except Exception:
                continue
            for res in _boost(results, desired.type):
                if len(kept) >= keep or dls >= max_dl:
                    return
                url = getattr(res, "source_url", "") or getattr(res, "url", "") or ""
                if url and url in seen_urls:                  # don't keep the same image twice
                    continue
                dest = _dest()
                try:
                    res2 = client.resolve_asset(res)
                    if client.download_image(res2, dest) is None or not _valid_image(dest):
                        dest.unlink(missing_ok=True)
                        continue
                except Exception:
                    dest.unlink(missing_ok=True)
                    continue
                dls += 1
                state["downloaded"] = True
                confirmed = None
                if need_verify:
                    confirmed = _verify_match(cfg, dest, subject, evocative=evocative)
                    if not evocative and confirmed is not True:   # EXACT: require a POSITIVE match
                        dest.unlink(missing_ok=True)
                        continue
                if url:
                    seen_urls.add(url)
                prov = _provenance(res, q)
                prov["file"] = dest
                prov["verified"] = confirmed is True
                kept.append(prov)

    queries = queries_for(entity, desired, domain)
    _run(queries)
    if not kept and reformulate and not evocative:           # Tier C — one fresh-angle retry only on TOTAL miss
        seen = {q.lower() for q in queries}
        new = [q for q in _reformulate_queries(cfg, entity, desired, queries,
                                               "wrong" if state["downloaded"] else "nothing")
               if q.lower() not in seen]
        if new:
            _run(new)
    return kept


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
    for ss in (1.0, 3.0):                                    # 2 frames (was 3) — early-exits on first confirm
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
                  reformulate: bool = True, keep: int = 2) -> List[dict]:
    """Search video providers → fetch short on-disk segments → (for EXACT footage) multi-frame VLM verify,
    keeping up to `keep` distinct clips (out, out_2…). `keep` defaults LOWER than images — video is ~4x the
    cost (download + trim + multi-frame verify). Returns a LIST of provenance dicts (empty if none); Tier-C
    reformulates once on total failure."""
    from nolan.acquire.context import _fetch_video_segment
    evocative = desired.relevance == "related"
    subject = _verify_subject(entity, desired, domain)
    kept: List[dict] = []
    seen_urls: set = set()
    state = {"downloaded": False}
    max_dl = keep + _MAX_VERIFY_ATTEMPTS

    def _dest() -> Path:
        return out if not kept else out.with_name(f"{out.stem}_{len(kept) + 1}{out.suffix}")

    def _run(queries):
        dls = 0
        for q in queries:
            if len(kept) >= keep:
                return
            try:
                results = client.search_assets(q, media_type="video", max_results=6) or []
            except Exception:
                continue
            for res in _boost(results, "footage"):
                if len(kept) >= keep or dls >= max_dl:
                    return
                skey = getattr(res, "source_url", "") or getattr(res, "url", "") or ""
                if skey and skey in seen_urls:
                    continue
                dest = _dest()
                try:
                    res2 = client.resolve_video(res) or res
                    vurl = getattr(res2, "url", None)
                    if not vurl or not _fetch_video_segment(vurl, dest, clip_seconds, getattr(res2, "duration", None)):
                        continue
                except Exception:
                    continue
                dls += 1
                state["downloaded"] = True
                confirmed = None
                if verify and not evocative:                 # verify EXACT footage; related stays loose
                    confirmed = _verify_video(cfg, dest, subject)
                    if confirmed is False:                   # every sampled frame rejected → wrong clip
                        dest.unlink(missing_ok=True)
                        continue
                if skey:
                    seen_urls.add(skey)
                prov = _provenance(res, q)
                prov["file"] = dest
                prov["verified"] = confirmed is True
                kept.append(prov)

    queries = queries_for(entity, desired, domain)
    _run(queries)
    if not kept and reformulate and not evocative:
        seen = {q.lower() for q in queries}
        new = [q for q in _reformulate_queries(cfg, entity, desired, queries,
                                               "wrong" if state["downloaded"] else "nothing")
               if q.lower() not in seen]
        if new:
            _run(new)
    return kept
