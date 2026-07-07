"""Shared external-provider asset matching (pipeline consolidation P2).

One implementation of "find the best external stock/archival asset for a scene"
(query-variant fallback → provider search → quality pre-filter → vision score →
attach video by reference / download image). Used by both the Studio b-roll job
(`match_broll_v2`) and the segment/orchestrator `AssetResolver` (as its
`external_fn`), so the resolver chain is the single asset picker.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


def scene_query_text(scene) -> str:
    """Rich description query for a scene (narration + visual intent + keywords).

    Mirrors ClipMatcher.build_search_query — used for description<->description
    semantic matching against the picture library (the same way the video library
    matches scenes to segment descriptions).
    """
    parts = []
    for attr in ("narration_excerpt", "visual_description", "search_query"):
        v = (getattr(scene, attr, "") or "").strip()
        if v:
            parts.append(v)
    return " ".join(parts).strip()


def semantic_match_for_scene(scene, *, libs, client, scorer, vid_sources, out_dir: Path,
                             project_root: Path, describer=None, ingest_lib=None,
                             max_results: int = 4, score_cap: int = 4,
                             sim_gate: float = 0.30, library_first_gate: float = 0.45,
                             lead_queries=None, img_sources=None, tier: str = "stock",
                             log=None) -> Optional[str]:
    """Unified description-based b-roll match (Phases 2-3).

    1. **Library-first**: hybrid (BGE description + CLIP) search over ``libs`` using
       the scene's rich description query. A hit >= ``sim_gate`` is reused directly.
    2. **External as ingest**: on a miss, search providers, quality-prefilter the
       top ``score_cap`` candidates, **describe + ingest** them into ``ingest_lib``
       (so they grow the reusable library), then re-search by description and pick
       the best. Sets ``scene.matched_asset`` (copied into ``out_dir``).

    Reusing an existing library asset uses a stricter ``library_first_gate`` than
    the post-ingest ``sim_gate`` — so a loosely-related asset in a sparse library
    doesn't pre-empt fetching a fresh, more relevant one.

    Returns a short kind string ("library:<source>" / "ingest:<source>") or None.
    """
    import shutil

    query = scene_query_text(scene) or (getattr(scene, "visual_description", "") or "")
    sid = getattr(scene, "id", "scene")

    def _attach_from_lib(best, kind_prefix: str) -> Optional[str]:
        lib, asset, h = best
        src = lib.abs_path(asset)
        if not src.exists():
            return None
        dest = Path(out_dir) / f"{sid}{src.suffix or '.jpg'}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy(src, dest)
        except Exception:
            return None
        scene.matched_asset = str(dest.relative_to(project_root)).replace("\\", "/")
        # library records carry provenance — pass it to the scene so the
        # attribution manifest and the on-screen citation see it
        try:
            from nolan.asset_gate import clean_title
            scene.extra["asset_license"] = {
                "source": asset.source, "license": asset.license,
                "source_url": asset.source_url or asset.url,
                "title": clean_title(asset.title)}
        except Exception:
            pass
        if log:
            log(f"{sid}: {asset.source} ({kind_prefix}, sim {h.score:.2f})")
        return f"{kind_prefix}:{asset.source or '?'}"

    def _best_over_libs(q):
        """Best (lib, asset, hit) across all libs via hybrid search."""
        best = None
        for lib in libs or []:
            try:
                hits = lib.search_hybrid(q, k=score_cap)
            except Exception:
                hits = []
            for h in hits:
                if best is None or h.score > best[2].score:
                    best = (lib, h.asset, h)
        return best

    # (1) library-first (stricter bar — only reuse a clearly relevant asset)
    if libs and query:
        best = _best_over_libs(query)
        if best and best[2].score >= library_first_gate:
            return _attach_from_lib(best, "library")

    # (2) external -> describe + ingest -> re-match
    if ingest_lib is None:
        # No ingest target: accept a softer library hit rather than nothing.
        if libs and query:
            best = _best_over_libs(query)
            if best and best[2].score >= sim_gate:
                return _attach_from_lib(best, "library")
        return None
    variants = build_query_variants(scene, lead_queries=lead_queries)
    cands = _search(client, variants, "image", vid_sources, max_results, img_sources)
    # Provenance gate before ingest: preview-domain / unlicensed-for-tier /
    # sub-floor candidates never enter the library.
    from nolan.asset_gate import check_candidate
    kept = []
    for c in cands:
        verdict = check_candidate(c, tier=tier)
        if verdict.ok:
            kept.append(c)
        elif log:
            log(f"{sid}: gate rejected {(c.url or '')[:60]} "
                f"({'; '.join(verdict.reasons)})")
    cands = kept
    if not cands:
        return None
    for c in cands:
        try:
            qs, _ = scorer.calculate_quality_score(c)
            c.quality_score = qs
        except Exception:
            c.quality_score = 0
    cands = sorted(cands, key=lambda c: c.quality_score or 0, reverse=True)[:score_cap]
    ingested = 0
    for c in cands:
        try:
            ingest_lib.add_result(c, query=query)  # describer (if set) generates description
            ingested += 1
        except Exception:
            continue
    if not ingested:
        return None
    # re-search now that fresh, described candidates are in the library
    best = _best_over_libs(query) if query else None
    if best and best[2].score >= sim_gate:
        return _attach_from_lib(best, "ingest")
    return None


def build_query_variants(scene, lead_queries=None) -> list:
    """Generate search queries broad→specific for a scene.

    The scene designer's queries are often too literal (proper nouns, years) for
    stock/archival libraries. We try the original, then progressively broader
    variants (drop years/proper-nouns), then a generic phrase from the description.

    ``lead_queries`` (optional) are knowledge-driven, whole-script-aware search phrases —
    e.g. specific era-correct artworks named by the model ("Waterhouse Ulysses and the
    Sirens 1891"). When given, they are tried FIRST (most specific), ahead of the
    proper-noun-stripping fallback below. See ``nolan.knowledge_query``.
    """
    out = []
    for lq in (lead_queries or []):
        lq = (lq or "").strip()
        if lq:
            out.append(lq)
    q = (getattr(scene, "search_query", "") or "").strip()
    if q:
        out.append(q)
        broad = re.sub(r"\b\d{4}\b", "", q)                       # drop years
        broad = re.sub(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", "", broad)  # drop Proper Nouns
        broad = re.sub(r"\s+", " ", broad).strip()
        if broad and broad.lower() != q.lower():
            out.append(broad)
    vd = (getattr(scene, "visual_description", "") or "").strip()
    if vd:
        out.append(" ".join(vd.split()[:6]))
    seen, res = set(), []
    for x in out:
        if x and x.lower() not in seen:
            seen.add(x.lower())
            res.append(x)
    return res or ["archival documentary footage"]


def _search(client, variants, media_type, vid_sources, max_results, img_sources=None):
    for variant in variants:
        kw = {"media_type": media_type, "max_results": max_results}
        if media_type == "video" and vid_sources:
            kw["sources"] = vid_sources
        if media_type == "image" and img_sources:
            kw["sources"] = img_sources        # e.g. museum/PD-art providers
        cands = client.search_assets(variant, **kw)
        if cands:
            return cands
    return []


def external_match_for_scene(scene, *, client, scorer, vid_sources, out_dir: Path,
                             project_root: Path, prefer_video: bool = True,
                             max_results: int = 4, score_cap: int = 4, gate: int = 4,
                             use_vision: bool = False, lead_queries=None,
                             img_sources=None, log=None) -> Optional[str]:
    """Find + attach the best external asset for one scene.

    Sets ``scene.matched_clip`` (video, by reference) or ``scene.matched_asset``
    (image, downloaded into ``out_dir``). Returns a short kind string
    ("video:<source>" / "image:<source>") or None if nothing cleared the gate.

    By default (``use_vision=False``) the best candidate is picked by the free
    local quality pre-filter — fast, no network. Set ``use_vision=True`` to also
    run the (slow, remote) vision relevance scorer and apply ``gate``.
    """
    import httpx

    from nolan.asset_gate import check_candidate, check_file

    variants = build_query_variants(scene, lead_queries=lead_queries)
    cands = []
    if prefer_video and vid_sources:
        cands = _search(client, variants, "video", vid_sources, max_results)
    if not cands:
        cands = _search(client, variants, "image", vid_sources, max_results, img_sources)
    # Provenance gate BEFORE spending scoring/download budget: stock-preview
    # domains and sub-floor candidates are dropped loudly here.
    kept = []
    for c in cands:
        verdict = check_candidate(c, tier="stock")
        if verdict.ok:
            kept.append(c)
        elif log:
            log(f"{getattr(scene, 'id', '?')}: gate rejected "
                f"{(c.url or '')[:60]} ({'; '.join(verdict.reasons)})")
    cands = kept
    if not cands:
        return None

    # Cheap quality pre-filter (free, local). Keep the top score_cap.
    for c in cands:
        qs, _ = scorer.calculate_quality_score(c)
        c.quality_score = qs
    cands = sorted(cands, key=lambda c: c.quality_score or 0, reverse=True)[:score_cap]

    if use_vision:
        # Slow path: remote vision relevance scoring + gate.
        ctx = f"for a documentary scene: {getattr(scene, 'visual_description', '') or ''}"
        query = getattr(scene, "search_query", "") or getattr(scene, "visual_description", "") or ""
        scored = scorer.score_results(cands, query, context=ctx)
        best = scored[0] if scored else None
        if not best or (best.score or 0) < gate:
            return None
    else:
        # Fast default: trust the local quality ranking, no network round-trip.
        best = cands[0] if cands else None
        if not best:
            return None
        if getattr(best, "score", None) is None:
            best.score = round(best.quality_score or 0, 2)

    sid = getattr(scene, "id", "scene")
    if best.media_type == "video":
        resolved = client.resolve_video(best)
        if resolved and resolved.url:
            scene.matched_clip = {
                "external_url": resolved.url, "source": resolved.source,
                "source_url": resolved.source_url, "title": resolved.title,
                "license": resolved.license, "duration": resolved.duration,
                "media_type": "video",
                "preview_image_url": resolved.preview_image_url or resolved.thumbnail_url,
                "score": best.score, "external": True,
            }
            if log:
                log(f"{sid}: video from {resolved.source} (score {best.score})")
            return f"video:{resolved.source}"
        return None

    dest = Path(out_dir) / f"{sid}.jpg"
    try:
        data = httpx.get(best.url, follow_redirects=True, timeout=30.0,
                         headers={"User-Agent": "Mozilla/5.0"}).content
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except Exception:
        return None
    verdict = check_file(dest, tier="stock")
    if not verdict.ok:
        dest.unlink(missing_ok=True)
        if log:
            log(f"{sid}: gate rejected downloaded file ({'; '.join(verdict.reasons)})")
        return None
    scene.matched_asset = str(dest.relative_to(project_root)).replace("\\", "/")
    # license sidecar (SOTA #5): downloaded stills used to shed their license
    # metadata at this exact line — the attribution manifest reads this field
    # (it survives via the lossless Scene.extra contract).
    try:
        scene.extra["asset_license"] = {
            "source": getattr(best, "source", None),
            "license": getattr(best, "license", None),
            "source_url": getattr(best, "source_url", None) or getattr(best, "url", None),
            "title": getattr(best, "title", None),
        }
    except Exception:
        pass
    if log:
        log(f"{sid}: image from {best.source} (score {best.score})")
    return f"image:{best.source}"
