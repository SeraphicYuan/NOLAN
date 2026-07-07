"""Archival-art sourcing — route named-artwork scenes through existing machinery.

The masterwork-raid sourcing step: scene_plan scenes typed ``archival-art``
(classical paintings, manuscripts, statues — usually carrying a precise
``search_query`` like "Vergilius Vaticanus manuscript page") get REAL
public-domain images matched onto them.

This module deliberately builds almost nothing — it is a *router* over
subsystems that already exist:

- query→candidates: ``ImageSearchClient.search_assets`` with a **museum/PD-art
  provider preset** (Wikimedia Commons, Met, Art Institute, Cleveland,
  Rijksmuseum, Wellcome, LoC, + keyed ones when configured);
- library-first + describe-and-ingest + stamping: ``external_assets.
  semantic_match_for_scene`` (sets ``scene.matched_asset``, project-relative —
  the field ``nolan assemble`` renders as a Ken-Burns still);
- persistence/license/dedup: ``imagelib.ImageLibrary`` (every sourced work is
  ingested into the project library, so the next project gets it free).

Wired into Director step 4 (select_clips) for scenes the video matcher can't
serve, and exposed standalone via the hub (POST /api/source-art).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

# Art providers, tiered by priority. Artvee is the PRIMARY (high) tier — a
# large, curated, well-titled public-domain art catalog — queried FIRST for
# named works. The museum/aggregator providers are the FALLBACK tier, reached
# only when the primary yields no accepted title match (see exact_title_pass).
# ART_SOURCES stays a single flat list (primary first) for the merged-pool
# callers (semantic fallback, shots-wanted); exact_title_pass splits it on
# ART_SOURCES_PRIMARY membership. Keyed providers are skipped automatically by
# the client when unconfigured.
ART_SOURCES_PRIMARY = ["artvee"]
ART_SOURCES_FALLBACK = ["wikimedia", "met", "artic", "cleveland", "rijksmuseum",
                        "wellcome", "loc", "harvard", "europeana", "dpla"]
ART_SOURCES = ART_SOURCES_PRIMARY + ART_SOURCES_FALLBACK

# visual_type values this step owns. "archival-art" is the vocabulary the
# style-adaptation agent declares for masterwork-sourcing projects.
DEFAULT_SCENE_TYPES = ("archival-art",)


def _needs_art(scene, scene_types) -> bool:
    if getattr(scene, "visual_type", None) not in scene_types:
        return False
    if getattr(scene, "matched_asset", None) or getattr(scene, "generated_asset", None):
        return False
    if getattr(scene, "matched_clip", None):
        return False
    return True


def _build_client(config):
    from nolan.image_search import ImageScorer, ImageSearchClient
    img = getattr(config, "image_sources", None)
    client = ImageSearchClient(
        pexels_api_key=getattr(img, "pexels_api_key", None),
        pixabay_api_key=getattr(img, "pixabay_api_key", None),
        smithsonian_api_key=getattr(img, "smithsonian_api_key", None),
        keys=img.provider_keys() if img and hasattr(img, "provider_keys") else None,
    )
    scorer = ImageScorer()          # local quality pre-filter only (no vision)
    return client, scorer


def _build_libs(config, project_name: str):
    """(search libs [global+project], ingest lib [project, describing])."""
    from nolan.imagelib import ImageLibrary
    from nolan.imagelib.describe import make_describer
    try:
        describer = make_describer(config)
    except Exception:
        describer = None
    glob = ImageLibrary("global")
    proj = ImageLibrary("project", project=project_name, describer=describer)
    return [glob, proj], proj


# Generic art-medium words: useless for identifying WHICH work, and they
# wreck recall on Commons' search (long compound queries return nothing).
_GENERIC = {"painting", "sculpture", "manuscript", "page", "illustration",
            "detail", "relief", "fresco", "statue", "portrait", "engraving",
            "print", "drawing", "photo", "photograph", "plate", "panel",
            "the", "a", "an", "of", "and", "by", "with", "from", "in"}


def _distinctive(query: str) -> List[str]:
    import re
    return [t for t in re.findall(r"[a-z0-9']+", (query or "").lower())
            if t not in _GENERIC and len(t) > 2]


def _title_match(query: str, title: str) -> float:
    """Fraction of the query's distinctive tokens present in the title."""
    q = _distinctive(query)
    if not q:
        return 0.0
    t = set(_distinctive(title))
    return sum(1 for tok in q if tok in t) / len(q)


def _query_variants_for_title(query: str) -> List[str]:
    """The query, a medium-stripped variant, and a short head — recall laddered."""
    toks = _distinctive(query)
    out = [query]
    stripped = " ".join(toks)
    if stripped and stripped != query.lower():
        out.append(stripped)
    if len(toks) > 3:
        out.append(" ".join(toks[:3]))
    return out


def _curl_download(url: str, dest: Path, timeout: int = 90) -> bool:
    """Download via curl — a fallback for hosts (Wikimedia's upload edge) that
    fingerprint-block python-httpx TLS regardless of User-Agent. curl ships
    with both Windows 10+ and Linux and passes their heuristic."""
    import subprocess
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    try:
        r = subprocess.run(
            ["curl", "-sS", "-L", "-o", str(dest), "-A", ua,
             "--max-time", str(timeout), url],
            capture_output=True, timeout=timeout + 15)
        return (r.returncode == 0 and dest.exists()
                and dest.stat().st_size >= 1024)
    except Exception:
        return False


def exact_title_pass(scene, *, client, ingest_lib, out_dir: Path,
                     project_root: Path, img_sources: List[str],
                     match_gate: float = 0.6, max_results: int = 8,
                     vision=None, rejected: Optional[List[dict]] = None,
                     log=None) -> Optional[str]:
    """Find THE named work by title text, not pixel similarity.

    CLIP cannot tell Bernini's Aeneas group from any other white marble — but
    Commons/museum results carry titles that name the work. When a candidate's
    title covers >= ``match_gate`` of the query's distinctive tokens, take it
    (largest matching image wins), download, gate (provenance + resolution +
    watermark via nolan.asset_gate, tier "archival"), stamp, and ingest for
    reuse. A gated-out hit falls through to the next-best hit. ``rejected``
    (if given) collects ``{"id", "url", "reasons"}`` for loud reporting.
    Returns "exact:<source>" or None (→ caller falls back to semantic).
    """
    from nolan.asset_gate import check_candidate, check_file

    query = getattr(scene, "search_query", None) or ""
    if len(_distinctive(query)) < 2:
        return None
    sid = getattr(scene, "id", "scene")

    def _reject(cand, reasons):
        if rejected is not None:
            rejected.append({"id": sid, "url": getattr(cand, "url", ""),
                             "reasons": list(reasons)})
        if log:
            log(f"{sid}: gate rejected {getattr(cand, 'url', '')[:60]} "
                f"({'; '.join(reasons)})")

    def _run(tier_sources: List[str]) -> Optional[str]:
        for variant in _query_variants_for_title(query):
            try:
                cands = client.search_assets(variant, media_type="image",
                                             sources=tier_sources,
                                             max_results=max_results)
            except Exception:
                cands = []
            scored = [(c, _title_match(query, getattr(c, "title", "") or ""))
                      for c in cands]
            hits = [(c, m) for c, m in scored if m >= match_gate]
            gated = []
            for c, m in hits:
                verdict = check_candidate(c, tier="archival")
                if verdict.ok:
                    gated.append((c, m))
                else:
                    _reject(c, verdict.reasons)
            gated.sort(key=lambda cm: (cm[1], (cm[0].width or 0) * (cm[0].height or 0)),
                       reverse=True)
            for best, match in gated:
                # Upgrade a lazily-returned candidate (e.g. artvee's preview) to
                # its full presigned download url before fetching — one detail
                # fetch per USED asset, not per search hit. No-op for providers
                # whose search url is already final (museums).
                try:
                    best = client.resolve_asset(best)
                except Exception:
                    pass
                # Strip presigned query params before taking the extension.
                suffix = Path(best.url.split("?", 1)[0]).suffix or ".jpg"
                dest = Path(out_dir) / f"{sid}{suffix}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                # Download to a temp name, verify the RETURN VALUE, then move into
                # place — a stale file at `dest` from an earlier pass must never be
                # mistaken for a successful download.
                tmp = dest.with_name(dest.stem + ".tmp" + dest.suffix)
                try:
                    got = client.download_image(best, tmp, prefer_large=True)
                except Exception:
                    got = None
                ok = got is not None and Path(got).exists() and Path(got).stat().st_size >= 1024
                if not ok and _curl_download(best.url, tmp):
                    got, ok = tmp, True
                if not ok:
                    tmp.unlink(missing_ok=True)
                    continue
                from nolan.asset_gate import needs_vision_check
                _vis = vision if needs_vision_check(best.url) else None
                verdict = check_file(Path(got), tier="archival", vision=_vis)
                if not verdict.ok:
                    _reject(best, verdict.reasons)
                    Path(got).unlink(missing_ok=True)
                    continue
                Path(got).replace(dest)
                scene.matched_asset = str(dest.relative_to(project_root)).replace("\\", "/")
                # license sidecar → attribution manifest + the ON-SCREEN
                # museum label (premium renders asset_license.title)
                try:
                    scene.extra["asset_license"] = {
                        "source": best.source, "license": best.license,
                        "source_url": best.source_url or best.url,
                        "title": best.title}
                except Exception:
                    pass
                if ingest_lib is not None:
                    try:
                        ingest_lib.add_result(best, query=query)
                    except Exception:
                        pass
                if log:
                    log(f"{sid}: exact title match — {getattr(best, 'title', '')[:60]} "
                        f"({best.source}, {match:.0%} tokens)")
                return f"exact:{best.source or '?'}"
        return None

    # Priority tiers: the high tier (artvee) is queried FIRST; the museum /
    # aggregator fallback tier is reached only when the high tier yields no
    # accepted title match. So an artvee hit for a named work is never
    # out-ranked by a museum result on pixel count — the museums aren't queried.
    primary = [s for s in img_sources if s in ART_SOURCES_PRIMARY]
    rest = [s for s in img_sources if s not in ART_SOURCES_PRIMARY]
    for tier in (t for t in (primary, rest) if t):
        got = _run(tier)
        if got:
            return got
    return None


def source_art_for_plan(scene_plan_path, project_root, config, *,
                        scene_types=DEFAULT_SCENE_TYPES,
                        img_sources: Optional[List[str]] = None,
                        max_results: int = 6, score_cap: int = 4,
                        sim_gate: float = 0.24,
                        log=None) -> Dict[str, Any]:
    """Source real artworks for every art-typed scene in a plan.

    Per scene: library-first (global + project imagelib, hybrid CLIP+BGE) →
    museum/Commons provider search → describe + ingest into the project
    library → best match stamped as ``scene.matched_asset`` with
    ``scene.resolved_source = "art:<kind>"``. Saves the plan in place.

    ``sim_gate`` is intentionally softer than generic b-roll matching: the
    scene queries here name SPECIFIC works, so provider hits are already
    on-subject and CLIP similarity on manuscripts/statues runs lower than on
    photographic footage.
    """
    from nolan.asset_gate import make_watermark_checker
    from nolan.external_assets import semantic_match_for_scene
    from nolan.scenes import ScenePlan

    project_root = Path(project_root)
    plan = ScenePlan.load(str(scene_plan_path))
    scenes = [s for section in plan.sections.values() for s in section]
    todo = [s for s in scenes if _needs_art(s, scene_types)]
    result: Dict[str, Any] = {"considered": len(todo), "matched": 0,
                              "by_kind": {}, "misses": [], "rejected": []}
    if not todo:
        return result

    client, scorer = _build_client(config)
    libs, ingest_lib = _build_libs(config, project_root.name)
    out_dir = project_root / "assets" / "art"
    vision = make_watermark_checker(config)

    for scene in todo:
        lead = [q for q in (getattr(scene, "search_query", None),) if q]
        # (1) exact-title pass: the query usually NAMES the work — find it by
        # title text (CLIP can't tell Bernini from any other marble).
        try:
            kind = exact_title_pass(
                scene, client=client, ingest_lib=ingest_lib, out_dir=out_dir,
                project_root=project_root, vision=vision,
                rejected=result["rejected"],
                img_sources=img_sources or ART_SOURCES, log=log)
        except Exception:
            kind = None
        # (2) semantic fallback: library-first + describe/ingest + CLIP.
        if not kind:
            try:
                kind = semantic_match_for_scene(
                    scene, libs=libs, client=client, scorer=scorer, vid_sources=[],
                    out_dir=out_dir, project_root=project_root,
                    describer=None,            # ingest_lib carries the describer
                    ingest_lib=ingest_lib, max_results=max_results,
                    score_cap=score_cap, sim_gate=sim_gate,
                    lead_queries=lead, img_sources=img_sources or ART_SOURCES,
                    tier="archival", log=log)
            except Exception as e:
                kind = None
                if log:
                    log(f"{getattr(scene, 'id', '?')}: art sourcing error: {e}")
        if kind:
            scene.resolved_source = f"art:{kind}"
            result["matched"] += 1
            base = kind.split(":", 1)[0]
            result["by_kind"][base] = result["by_kind"].get(base, 0) + 1
        else:
            result["misses"].append(getattr(scene, "id", "?"))

    plan.save(str(scene_plan_path))
    return result
