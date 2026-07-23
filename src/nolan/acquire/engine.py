"""The acquisition engine — beat-driven, over-provisioned, multi-source, relevance-ranked,
fitness-gated. For each need it fans out to every source, over-fetches, scores each candidate for
RELEVANCE (CLIP) and FITNESS (overlay-safety/orientation/burned-text), de-duplicates semantically,
keeps the best per need, and GENERATES originals where stock/library is thin or off-topic.

All I/O (search / download / relevance / generate) is injected via `Context`, so the engine is
pure orchestration — testable with fakes, and degrades cleanly when an organ (CLIP, ComfyUI) is
absent. `context.build_context` wires the real organs; `pool.py` orchestrates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .config import AcquireConfig


@dataclass
class Candidate:
    ref: str                                    # url / library id / gen prompt
    source: str                                 # "stock:pexels" | "library" | "generate"
    modality: str = "image"                     # "image" | "video"
    path: Optional[Path] = None                 # local file (library = already local; others once fetched)
    meta: Dict = field(default_factory=dict)    # provider metadata (license, photographer, dims, duration…)
    rank: int = 0                               # fetch order (a cheap search-relevance proxy)
    relevance: float = 0.0
    fitness: Dict = field(default_factory=dict)
    score: float = 0.0


@dataclass
class Context:
    """Injectable organs. Any may be None (that source/scorer is skipped)."""
    search_stock: Optional[Callable] = None     # (need, n) -> [Candidate] (refs)
    search_library: Optional[Callable] = None   # (query, n) -> [Candidate] (local)
    search_clips: Optional[Callable] = None     # (need, n) -> [Candidate] (local video, materialised in download)
    download: Optional[Callable] = None          # (Candidate, dest_dir) -> bool  (fills .path)
    relevance: Optional[Callable] = None         # (text, path) -> float in [0,1]
    video_relevance: Optional[Callable] = None   # (text, video_path) -> float — cheap CLIP frame-relevance for video
    generate: Optional[Callable] = None          # (prompt, out_path) -> bool


# --- semantic dedup (average hash; no extra deps) -------------------------------------------------
def avg_hash(path: Path, size: int = 8) -> Optional[int]:
    try:
        from PIL import Image
        im = Image.open(path).convert("L").resize((size, size))
        px = list(im.getdata())
        avg = sum(px) / len(px)
        bits = 0
        for i, p in enumerate(px):
            if p >= avg:
                bits |= (1 << i)
        return bits
    except Exception:
        return None


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _near_dup(h: Optional[int], seen: List[int], threshold: int) -> bool:
    return h is not None and any(hamming(h, s) <= threshold for s in seen)


# --- scoring --------------------------------------------------------------------------------------
def fitness_score(fit: Dict) -> float:
    """0..1 usability for a full-bleed ground, from pool_curation tags."""
    if not fit:
        return 0.6                                # unknown (e.g. video) — neutral
    s = 1.0 if fit.get("overlay_safe") else 0.35
    s *= 0.0 if fit.get("has_burned_text") else 1.0
    s *= 1.0 if fit.get("orientation") == "landscape" else 0.75
    return round(s, 3)


# Curated source tiers per category — used to rank EVOCATIVE needs (where literal CLIP relevance is the
# WRONG signal: it demotes the non-literal art/library that makes abstract beats good). The saved
# library ranks first (on-brand + curated); then the category's best sources.
# "clips_library" = the LOCAL video library — curated, on-machine footage semantically matched by rich
# per-clip metadata; it ranks just below the saved image library (both are curated + local) and above
# remote stock, so real library footage leads a beat when it genuinely matches (the min-similarity floor
# in the source keeps weak clips out of the running entirely).
TIERS = {
    "art": ["library", "clips_library", "artvee", "wikimedia", "met", "artic", "rijksmuseum", "harvard",
            "cleveland", "wellcome", "europeana", "dpla", "smithsonian", "loc", "openverse", "ddgs"],
    "archival": ["library", "clips_library", "archive", "archive_image", "loc", "smithsonian", "europeana",
                 "dpla", "nasa", "nasa_video", "wikimedia", "flickr", "pexels_video", "pixabay_video", "coverr_video", "ddgs"],
    "general": ["library", "clips_library", "pexels", "pixabay", "unsplash", "ddgs", "openverse", "pexels_video",
                "pixabay_video", "coverr_video", "flickr", "wikimedia", "nasa"],
}


# Curated institutional/art providers — exempt from the generic-stock relevance floor, because for
# evocative beats their VALUE is precisely the non-literal match a low CLIP score would otherwise cull.
_CURATED = {"artvee", "artic", "met", "wellcome", "rijksmuseum", "harvard", "cleveland",
            "europeana", "dpla", "smithsonian", "loc", "nasa", "wikimedia"}


def _provider_of(source: str) -> str:
    return (source or "").split(":")[-1]


def source_rank(category: str, source: str) -> int:
    order = TIERS.get(category) or TIERS["general"]
    p = _provider_of(source)
    return order.index(p) if p in order else len(order) + 50


def _need_queries(need: Dict) -> List[str]:
    qs = need.get("queries") or [need.get("query", "")]
    return [q for q in qs if q][:6]


def _usable(c: Candidate, cfg: AcquireConfig) -> bool:
    return c.relevance >= cfg.relevance_floor and fitness_score(c.fitness) >= 0.5 if c.modality == "image" \
        else True


# --- per-need acquisition -------------------------------------------------------------------------
def acquire_need(need: Dict, ctx: Context, cfg: AcquireConfig, cand_dir: Path,
                 taken_hashes: List[int]) -> List[Candidate]:
    of = cfg.over_fetch_video if need.get("media_type") == "video" else cfg.over_fetch
    n_fetch = max(cfg.per_need * of, cfg.per_need)
    cands: List[Candidate] = []
    if "library" in cfg.sources and ctx.search_library:
        for q in _need_queries(need):
            cands += ctx.search_library(q, n_fetch) or []
    if "clips_library" in cfg.sources and ctx.search_clips:
        cands += ctx.search_clips(need, n_fetch) or []      # local video, materialised in download
    if "stock" in cfg.sources and ctx.search_stock:
        cands += ctx.search_stock(need, n_fetch) or []
    for i, c in enumerate(cands):
        c.rank = i

    # download whatever isn't already local, gate + keep decodable. CONCURRENT: downloads are network-bound
    # and independent (each writes a unique cand_dir path), so a bounded thread pool cuts the wall-clock of
    # the per-need fetch (the dominant cost) without touching the CLIP-scoring/dedup that follows. ex.map
    # preserves order, so `live` keeps the search-rank order.
    def _download(c: Candidate) -> Optional[Candidate]:
        if c.path is None and ctx.download:
            try:
                if not ctx.download(c, cand_dir):
                    return None
            except Exception:
                return None
        return c if (c.path and Path(c.path).exists()) else None

    if cands:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(8, len(cands))) as _ex:
            live: List[Candidate] = [c for c in _ex.map(_download, cands) if c is not None]
    else:
        live = []

    # score each candidate. CONCRETE needs → literal CLIP relevance (a real photo of the thing wins).
    # EVOCATIVE needs → a TIER-dominant blend: curated sources (library/artvee/museums) lead, but
    # relevance still counts so no single source floods the beat with off-topic hits. Both nudged by
    # fitness + search order.
    from nolan import pool_curation
    text = need.get("query", "")
    evocative = bool(need.get("evocative"))
    category = need.get("category", "general")
    for c in live:
        if c.modality == "image":
            try:
                c.fitness = pool_curation.score_asset(c.path)
            except Exception:
                c.fitness = {}
            if ctx.relevance:
                try:
                    c.relevance = float(ctx.relevance(text, c.path))
                except Exception:
                    c.relevance = 0.0
            # NAMED-WORK retrieval: a strong TITLE/metadata match is high-precision evidence CLIP can't
            # provide — all 46 Holbein woodcuts cluster at CLIP 0.29-0.36 for any query, but the asset
            # titled 'THE PLOUGHMAN' is an exact match. Let it stand in for relevance (max, not replace,
            # so a title match never DEMOTES a strong CLIP hit) so the right named artifact leads AND
            # clears the library floor below, instead of relying on the VLM cull to rescue it.
            tcover = float(c.meta.get("title_cover", 0) or 0)
            if c.source == "library" and tcover > 0:
                c.relevance = max(c.relevance, tcover)
        elif c.modality == "video" and c.source == "clips_library" and ctx.video_relevance:
            # CULL CASCADE: cheap CLIP frame-relevance so off-topic library clips are dropped in _keep
            # (before the expensive VLM), and this real relevance also feeds the video score below.
            try:
                c.relevance = float(ctx.video_relevance(text, c.path))
            except Exception:
                c.relevance = 0.0
        if evocative:
            # evocative beats want CURATED/artistic sources (library, artvee, museums) — literal CLIP
            # relevance would wrongly DEMOTE the non-literal art. But tier ALONE lets one source flood a
            # beat: the library always returns k cosine hits however weak, so pure-tier fills all slots
            # with off-topic library images and shuts out museums + generated. So tier is the dominant
            # term (normalised 0..1) while relevance breaks ties across+within tiers and fitness nudges —
            # a much-more-relevant lower-tier item can overtake a barely-relevant top-tier one.
            order = TIERS.get(category) or TIERS["general"]
            tier_bonus = 1.0 - source_rank(category, c.source) / max(len(order), 1)   # 0..1 (library≈1)
            c.score = tier_bonus + 0.7 * c.relevance + cfg.w_fitness * fitness_score(c.fitness) - 0.02 * c.rank
        else:
            c.score = (cfg.w_relevance * c.relevance) + (cfg.w_fitness * fitness_score(c.fitness)) - 0.01 * c.rank

    # relevance gates (only when CLIP is available). Two kinds of source lie about relevance:
    #   • the LIBRARY returns k-nearest for ANY query — an off-domain global store floods a beat at tier-0;
    #   • GENERIC stock (pexels/pixabay/ddgs/unsplash) matches keywords literally — abstract queries drag
    #     in junk ("fast track"→race car). Both must clear a floor. CURATED museum/art sources are EXEMPT:
    #     evocative art is deliberately non-literal, so a low CLIP score there is a feature, not junk.
    if ctx.relevance:
        def _keep(c: Candidate) -> bool:
            if c.modality != "image":
                if c.source == "clips_library" and ctx.video_relevance:
                    return c.relevance >= cfg.clip_lib_relevance_floor  # cheap CLIP gate BEFORE the VLM
                return True                                   # other video is unscored — keep
            prov = _provider_of(c.source)
            if c.source == "library":
                return c.relevance >= cfg.library_min_relevance
            if prov in _CURATED and category in ("art", "archival"):
                return True                                   # museum art IS the point of an art/archival beat
            return c.relevance >= cfg.stock_relevance_floor   # else (incl. museums on a GENERAL beat) be on-topic
        live = [c for c in live if _keep(c)]

    live.sort(key=lambda c: c.score, reverse=True)

    # semantic dedup (within need + across the whole pool via taken_hashes)
    kept: List[Candidate] = []
    seen = list(taken_hashes)
    for c in live:
        if len(kept) >= cfg.per_need:
            break
        h = avg_hash(c.path) if c.modality == "image" else None
        if _near_dup(h, seen, cfg.dedup_hamming):
            continue
        if h is not None:
            seen.append(h)
        kept.append(c)
    taken_hashes[:] = seen

    # generate originals where a beat is thin or off-topic (evocative, floor-gated)
    best_rel = max((c.relevance for c in kept), default=0.0)
    usable = [c for c in kept if _usable(c, cfg)]
    if (need.get("evocative") and cfg.generate_evocative and ctx.generate
            and (len(usable) < cfg.min_usable or best_rel < cfg.relevance_floor)):
        for k in range(cfg.generate_n):
            out = cand_dir / f"{need['id']}_gen{k}.png"
            gp = need.get("gen_prompt") or text                # the art-directed (enhanced) prompt we generate from
            try:
                if ctx.generate(gp, out, negative=need.get("gen_negative")) and out.exists():
                    kept.append(Candidate(ref=str(out), source="generate", modality="image", path=out,
                                          meta={"license": "generated", "source": "krea2 (generated)",
                                                "gen_prompt": gp, "gen_negative": need.get("gen_negative") or ""}))
            except Exception:
                pass
    return kept


def acquire_pool(needs: List[Dict], ctx: Context, cfg: Optional[AcquireConfig] = None,
                 cand_dir: Optional[Path] = None, log: Callable = print) -> List[Candidate]:
    """Acquire the whole pool. Returns the kept Candidates (with .path); the caller places + captions them."""
    cfg = cfg or AcquireConfig()
    cand_dir = Path(cand_dir or ".")
    cand_dir.mkdir(parents=True, exist_ok=True)
    taken: List[int] = []
    out: List[Candidate] = []
    for need in needs:
        got = acquire_need(need, ctx, cfg, cand_dir, taken)
        for c in got:
            c.meta.setdefault("need", need["id"])
        n_gen = sum(1 for c in got if c.source == "generate")
        log(f"  [{need['id']}] {len(got)} kept "
            f"(rel≈{max((c.relevance for c in got), default=0):.2f}"
            + (f", +{n_gen} generated" if n_gen else "") + ")")
        out += got
    return out
