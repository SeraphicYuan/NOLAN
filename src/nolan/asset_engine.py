"""The asset engine — ONE per-scene source-resolution ladder for all pipelines.

Promoted from the segment builder's ``AssetResolver`` (Phase 2 of the
architecture consolidation), which encoded the "source mix adapts to scene
type" learning:

  - motion (Python/Remotion) for text/data/chart scenes (authored on demand)
  - archival-art scenes: exact-title museum pass (titles beat CLIP for named
    works), then the escalation ladder
  - footage scenes: library video search IF a match clears the threshold
  - else escalate: picture-library stills → external providers → ComfyUI
    generation → none

Every resolution is recorded on ``scene.resolved_source`` (no silent caps) —
uniformly, which the seven pre-consolidation front-doors never did.

Tier functions are injectable (the segment builder passes its own); callers
without bespoke needs use :meth:`AssetEngine.from_config`, whose default
factories are the proven implementations lifted from the builder. All
factories are lazy — models/clients load on the first scene that needs them.

Scene *dicts* (the orchestrator/iterate layer) resolve through
:meth:`resolve_dicts`, a lossless ``Scene`` round-trip — safe since the
Phase 0 contract (unknown keys survive in ``Scene.extra``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

FOOTAGE_TYPES = {"b-roll", "a-roll", "footage", "cinematic"}
GENERATED_TYPES = {"generated", "generated-image", "hero"}
ART_TYPES = {"archival-art"}


def _download_external_clip(matched_clip: dict, out_dir: Path,
                            scene_id: str) -> Optional[Path]:
    """Download an external video reference to a local mp4, or None."""
    url = (matched_clip or {}).get("external_url")
    if not url:
        return None
    try:
        import httpx
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{scene_id}.mp4"
        with httpx.stream("GET", url, timeout=120,
                          follow_redirects=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
        return dest if dest.stat().st_size > 10_000 else None
    except Exception as exc:
        logger.warning("external clip download failed (%s): %s", scene_id, exc)
        return None


@dataclass
class EngineConfig:
    search_threshold: float = 0.5
    enable_search: bool = True
    enable_generation: bool = True
    enable_external: bool = False          # stock/archival providers
    enable_library: bool = True            # picture-library stills
    library_threshold: float = 0.24        # hybrid-similarity floor for a usable still
    enable_motion: bool = True             # lazily author a motion_spec for graphic/text scenes
    enable_art: bool = True                # exact-title museum pass for archival-art scenes
    enable_bridge: bool = True             # operator query-expansion after a literal miss
    bridge_operators: tuple = ("tonal", "conceptual")   # judgment-safe operators for auto runs


class AssetEngine:
    def __init__(self, config: EngineConfig = None,
                 search_fn: Optional[Callable] = None,      # scene -> matched_clip dict|None (with similarity_score)
                 external_fn: Optional[Callable] = None,    # scene -> truthy kind|None; sets matched_clip/matched_asset
                 library_fn: Optional[Callable] = None,     # scene -> matched_asset path|None (picture library)
                 motion_fn: Optional[Callable] = None,      # scene -> motion_spec dict|None (lazy authoring)
                 art_fn: Optional[Callable] = None,         # scene -> truthy kind|None; sets matched_asset (exact-title art)
                 bridge_fn: Optional[Callable] = None):     # scene -> [metaphor query, ...] (operator bridge)
        self.cfg = config or EngineConfig()
        self.search_fn = search_fn
        self.external_fn = external_fn
        self.library_fn = library_fn
        self.motion_fn = motion_fn
        self.art_fn = art_fn
        self.bridge_fn = bridge_fn
        # No-reuse ledger: the same asset matched to two scenes reads as a
        # rerun, not an edit. A tier hit whose asset is already claimed is
        # treated as a MISS (logged) and escalation continues.
        self._used: set = set()

    def _claim(self, key) -> bool:
        """True if `key` was free (now claimed); False if already used."""
        if not key:
            return True
        key = str(key)
        if key in self._used:
            return False
        self._used.add(key)
        return True

    # --- public -----------------------------------------------------------
    def resolve(self, scene) -> str:
        """Populate the scene's asset field and return resolved_source."""
        src = self._resolve(scene)
        scene.resolved_source = src
        return src

    def resolve_all(self, scenes) -> dict:
        counts: dict = {}
        for s in scenes:
            src = self.resolve(s)
            head = src.split(":")[0].split("(")[0]
            counts[head] = counts.get(head, 0) + 1
        return counts

    def resolve_dicts(self, scene_dicts) -> dict:
        """Resolve raw scene dicts (orchestrator/iterate layer), losslessly.

        Each dict round-trips through ``Scene`` (unknown keys survive via the
        Phase 0 contract) and is updated in place, so callers holding
        references into a raw ``scene_plan.json`` structure see the results.
        """
        from nolan.scenes import Scene, ScenePlan

        counts: dict = {}
        for d in scene_dicts:
            scene = ScenePlan._scene_from_dict(dict(d))
            src = self.resolve(scene)
            d.clear()
            d.update(ScenePlan._scene_to_dict(scene))
            head = src.split(":")[0].split("(")[0]
            counts[head] = counts.get(head, 0) + 1
        return counts

    # --- internals ----------------------------------------------------------
    def _resolve(self, scene) -> str:
        if scene.motion_spec:
            return f"motion:{scene.motion_spec.get('effect', '?')}"

        vt = (scene.visual_type or "").lower().strip()

        if vt in ART_TYPES:
            if self.cfg.enable_art and self.art_fn:
                kind = None
                try:
                    kind = self.art_fn(scene)
                except Exception as exc:
                    logger.warning("art tier failed for %s: %s",
                                   getattr(scene, "id", "?"), exc)
                if kind:
                    kind = str(kind)
                    return kind if kind.startswith("art") else f"art:{kind}"
            return self._escalate(scene, reason="art-miss")

        if vt in FOOTAGE_TYPES:
            if self.cfg.enable_search and self.search_fn:
                mc = self.search_fn(scene)
                if (mc and float(mc.get("similarity_score", 1.0)) >= self.cfg.search_threshold
                        and self._claim(f"{mc.get('video_path')}@{mc.get('clip_start')}")):
                    scene.matched_clip = mc
                    return f"search({mc.get('similarity_score', 0):.2f})"
                # Operator bridge: the literal query missed — retry the search
                # tier with metaphor queries (tonal/conceptual by default).
                for probe, query in self._bridge_probes(scene):
                    mc = self.search_fn(probe)
                    if (mc and float(mc.get("similarity_score", 1.0)) >= self.cfg.search_threshold
                            and self._claim(f"{mc.get('video_path')}@{mc.get('clip_start')}")):
                        scene.matched_clip = mc
                        logger.info("bridge matched %s via %r",
                                    getattr(scene, "id", "?"), query)
                        return f"search-bridged({mc.get('similarity_score', 0):.2f})"
            return self._escalate(scene, reason="search-miss")

        if vt in GENERATED_TYPES:
            return self._generate(scene)

        # graphic/text/data scene with no motion_spec: author one on demand (lazy —
        # only for scenes that actually reach here, not an eager design-stage pass).
        if self.cfg.enable_motion and self.motion_fn:
            spec = self.motion_fn(scene)
            if spec:
                scene.motion_spec = spec
                return f"motion:{spec.get('effect', '?')}"

        return self._escalate(scene, reason=f"no-motion-for-{vt or 'unknown'}")

    def _bridge_probes(self, scene):
        """Yield (probe_scene, query) pairs for the operator bridge, lazily.

        The bridge runs at most once per scene (queries cached on the engine
        call), only when configured and wired. Probe scenes carry the metaphor
        as BOTH search_query and visual_description so embedding-based tiers
        rank on the metaphor, not the original literal text.
        """
        if not (self.cfg.enable_bridge and self.bridge_fn):
            return
        queries = getattr(scene, "_bridge_queries_cache", None)
        if queries is None:
            try:
                queries = list(self.bridge_fn(scene) or [])
            except Exception as exc:
                logger.warning("bridge failed for %s: %s",
                               getattr(scene, "id", "?"), exc)
                queries = []
            try:
                object.__setattr__(scene, "_bridge_queries_cache", queries)
            except Exception:
                pass
        if not queries:
            return
        from nolan.scenes import Scene
        for q in queries:
            yield Scene(id=getattr(scene, "id", "probe"),
                        visual_type=scene.visual_type or "b-roll",
                        search_query=q, visual_description=q,
                        narration_excerpt=""), q

    def _escalate(self, scene, reason: str) -> str:
        # Picture library (curated stills) before external providers / generation.
        if self.cfg.enable_library and self.library_fn:
            asset = self.library_fn(scene)
            if asset and self._claim(asset):
                scene.matched_asset = asset
                return f"library({reason})"
            for probe, query in self._bridge_probes(scene):
                asset = self.library_fn(probe)
                if asset and self._claim(asset):
                    scene.matched_asset = asset
                    logger.info("bridge matched still for %s via %r",
                                getattr(scene, "id", "?"), query)
                    return f"library-bridged({reason})"
        if self.cfg.enable_external and self.external_fn:
            # external_fn finds + attaches the asset (sets scene.matched_clip for a
            # video, or scene.matched_asset for an image) and returns a truthy kind.
            got = self.external_fn(scene)
            if got:
                key = (getattr(scene, "matched_asset", None)
                       or (getattr(scene, "matched_clip", None) or {}).get("source_url"))
                if self._claim(key):
                    return f"external({reason})"
                logger.info("external hit for %s already used elsewhere — skipping",
                            getattr(scene, "id", "?"))
                scene.matched_asset = None
                scene.matched_clip = None
        if self.cfg.enable_generation:
            return self._generate(scene, reason=reason)
        return f"none({reason})"

    def _generate(self, scene, reason: str = "") -> str:
        if not self.cfg.enable_generation:
            return f"none(gen-disabled{':' + reason if reason else ''})"
        scene.comfyui_prompt = scene.comfyui_prompt or scene.visual_description or scene.narration_excerpt
        tag = f"generated({reason})" if reason else "generated"
        return tag

    # --- default tier factories ----------------------------------------------
    # The proven implementations, lifted from SegmentBuilder._make_*_fn. Every
    # factory returns None when its inputs/config make the tier impossible, and
    # the returned fn is lazy (clients/models build on first use).

    @classmethod
    def from_config(cls, nolan_config, *,
                    config: EngineConfig = None,
                    project_path: Optional[Path] = None,
                    index_db: Optional[Path] = None,
                    project_id: Optional[str] = None,
                    llm_client=None) -> "AssetEngine":
        """Build an engine wired to the standard backends.

        - search_fn: ClipMatcher (pure vector) over ``index_db`` (or the
          configured global index). ``project_id`` scopes the INDEX search and
          must be an id the index actually knows — omit it for a global
          search (the Director's historical semantics). The project imagelib
          is discovered from ``project_path`` independently.
        - library_fn: imagelib hybrid search (global + project libraries).
        - external_fn: stock/archival providers via external_assets.
        - art_fn: exact-title museum pass (art_sourcing).
        - motion_fn: NL motion authoring when ``llm_client`` given.
        """
        cfg = config or EngineConfig()
        project_path = Path(project_path) if project_path else None
        db = index_db
        if db is None:
            try:
                db = Path(getattr(nolan_config.indexing, "database", "")).expanduser()
            except Exception:
                db = None
        return cls(
            cfg,
            search_fn=cls._default_search_fn(nolan_config, db, project_id),
            # The project imagelib lives at projects/<id>/imagelib — an explicit
            # project_id names it; else fall back to the project folder name.
            library_fn=cls._default_library_fn(
                cfg, project_id or (project_path.name if project_path else None)),
            external_fn=cls._default_external_fn(nolan_config, project_path) if cfg.enable_external else None,
            motion_fn=cls._default_motion_fn(llm_client) if llm_client else None,
            art_fn=cls._default_art_fn(nolan_config, project_path) if project_path else None,
            bridge_fn=cls._default_bridge_fn(nolan_config, cfg) if cfg.enable_bridge else None,
        )

    @staticmethod
    def _default_search_fn(nolan_config, index_db, project_id) -> Optional[Callable]:
        if not index_db or not Path(index_db).exists():
            return None
        state: dict = {}

        def fn(scene):
            if "cm" not in state:
                try:
                    from nolan.clip_matcher import ClipMatcher
                    from nolan.indexer import VideoIndex
                    from nolan.vector_search import VectorSearch
                    vs = VectorSearch(db_path=Path(index_db).parent / "vectors",
                                      index=VideoIndex(Path(index_db)))
                    # Pure vector matching (no LLM selection pass) — fast, free, robust.
                    state["cm"] = ClipMatcher(
                        vector_search=vs, llm_client=None,
                        config=getattr(nolan_config, "clip_matching", nolan_config))
                except Exception:
                    state["cm"] = None
            if not state.get("cm"):
                return None
            try:
                from nolan.segment.render import _run_async
                return _run_async(state["cm"].match_scene(scene, project_id=project_id))
            except Exception:
                return None
        return fn

    @staticmethod
    def _default_library_fn(cfg: EngineConfig, project_id) -> Optional[Callable]:
        state: dict = {}

        def fn(scene):
            if "libs" not in state:
                try:
                    from nolan.imagelib import ClipEmbedder, ImageLibrary
                    emb = ClipEmbedder()
                    libs = [ImageLibrary("global", embedder=emb)]
                    if project_id and (Path("projects") / project_id / "imagelib").exists():
                        libs.append(ImageLibrary("project", project=project_id, embedder=emb))
                    state["libs"] = libs
                except Exception:
                    state["libs"] = []
            libs = state["libs"]
            if not libs:
                return None
            q = (getattr(scene, "search_query", "") or scene.visual_description
                 or getattr(scene, "narration_excerpt", "") or "")
            if not q:
                return None
            best = None
            for lib in libs:
                try:
                    # Hybrid (CLIP + BGE description) — the strongest of the three
                    # pre-consolidation library lookups; falls back to CLIP-only
                    # inside search_hybrid when descriptions are absent.
                    for h in lib.search_hybrid(q, k=3):
                        if best is None or h.score > best[1]:
                            best = (str(lib.abs_path(h.asset)), h.score)
                except Exception:
                    pass
            if best and best[1] >= cfg.library_threshold:
                return best[0]
            return None
        return fn

    @staticmethod
    def _default_external_fn(nolan_config, project_path: Optional[Path]) -> Optional[Callable]:
        if project_path is None:
            return None
        state: dict = {}

        def fn(scene):
            if "client" not in state:
                try:
                    from nolan.cli_legacy import _scoring_vision_config
                    from nolan.image_search import ImageScorer, ImageSearchClient
                    img = getattr(nolan_config, "image_sources", None)
                    client = ImageSearchClient(
                        pexels_api_key=getattr(img, "pexels_api_key", None),
                        pixabay_api_key=getattr(img, "pixabay_api_key", None),
                        smithsonian_api_key=getattr(img, "smithsonian_api_key", None),
                        keys=img.provider_keys() if img and hasattr(img, "provider_keys") else None,
                    )
                    sv = _scoring_vision_config(nolan_config, "openrouter")
                    sv["model"] = "qwen/qwen3-vl-8b-instruct"
                    state["client"] = client
                    state["scorer"] = ImageScorer(vision_provider="openrouter", vision_config=sv)
                    state["vid"] = client.video_providers()
                except Exception:
                    state["client"] = None
            if not state.get("client"):
                return None
            from nolan.external_assets import external_match_for_scene
            try:
                # Vision-gated (the free quality filter alone matched lecture
                # footage to aerial queries in the 2-beat test); video first —
                # premium plays clips natively since render story v2.
                kind = external_match_for_scene(
                    scene, client=state["client"], scorer=state["scorer"],
                    vid_sources=state["vid"], out_dir=project_path / "assets" / "broll",
                    project_root=project_path, prefer_video=True,
                    use_vision=True, gate=4)
            except Exception:
                return None
            if kind and str(kind).startswith("video"):
                # materialize: premium's Video step needs a LOCAL file. A clip
                # that won't download is a miss, never a dangling reference.
                mc = getattr(scene, "matched_clip", None) or {}
                local = _download_external_clip(
                    mc, project_path / "assets" / "broll_video",
                    getattr(scene, "id", "scene"))
                if not local:
                    scene.matched_clip = None
                    return None
                mc["video_path"] = str(local)
                mc["clip_start"] = 0.0
            return kind
        return fn

    @staticmethod
    def _default_art_fn(nolan_config, project_path: Path) -> Optional[Callable]:
        state: dict = {}

        def fn(scene):
            if "client" not in state:
                try:
                    from nolan.art_sourcing import ART_SOURCES, _build_client, _build_libs
                    client, scorer = _build_client(nolan_config)
                    libs, ingest_lib = _build_libs(nolan_config, project_path.name)
                    state.update(client=client, scorer=scorer, libs=libs,
                                 ingest_lib=ingest_lib, sources=list(ART_SOURCES))
                except Exception:
                    state["client"] = None
            if not state.get("client"):
                return None
            from nolan.art_sourcing import exact_title_pass
            from nolan.external_assets import semantic_match_for_scene
            out_dir = project_path / "assets" / "art"
            # (1) exact-title: the query usually NAMES the work — title text
            # beats CLIP for named works.
            try:
                kind = exact_title_pass(
                    scene, client=state["client"], ingest_lib=state["ingest_lib"],
                    out_dir=out_dir, project_root=project_path,
                    img_sources=state["sources"])
            except Exception:
                kind = None
            if kind:
                return kind
            # (2) semantic fallback (library-first + describe/ingest), soft gate —
            # art queries are already on-subject.
            lead = [q for q in (getattr(scene, "search_query", None),) if q]
            try:
                return semantic_match_for_scene(
                    scene, libs=state["libs"], client=state["client"],
                    scorer=state["scorer"], vid_sources=[], out_dir=out_dir,
                    project_root=project_path, describer=None,
                    ingest_lib=state["ingest_lib"], max_results=6, score_cap=4,
                    sim_gate=0.24, lead_queries=lead, img_sources=state["sources"])
            except Exception:
                return None
        return fn

    @staticmethod
    def _default_bridge_fn(nolan_config, cfg: EngineConfig) -> Optional[Callable]:
        """Operator bridge (evoke_broll prompts) — metaphor queries for a scene.

        Lazy: the text LLM builds on the first bridged scene. One bridge call
        covers all retrieval tiers for that scene (the engine caches queries).
        """
        state: dict = {}

        def fn(scene):
            if "llm" not in state:
                try:
                    from nolan.llm import create_text_llm
                    state["llm"] = create_text_llm(nolan_config)
                except Exception:
                    state["llm"] = None
            if not state.get("llm"):
                return []
            line = (getattr(scene, "narration_excerpt", "") or
                    getattr(scene, "search_query", "") or
                    getattr(scene, "visual_description", "") or "").strip()
            if not line:
                return []
            from nolan.evoke_broll import bridge_queries
            from nolan.segment.render import _run_async
            return _run_async(bridge_queries(
                state["llm"], line, operators=tuple(cfg.bridge_operators)))
        return fn

    # --- shot-list fulfillment (the reader of tempo's shot cadence) ------------

    @staticmethod
    def fulfill_shots_wanted(scenes, *, nolan_config, project_path: Path,
                             log=None, client=None, fetch=None) -> int:
        """scene.extra['shots_wanted'] (tempo cadence) → scene.extra['shots'].

        A beat whose energy asks for N cuts needs N stills. The scene's
        resolved still anchors the list (heaviest weight); the extras come
        from stock search using the scene's broad→specific query variants —
        no vision scoring (same-query images; the contact gate + review cover
        quality). Scenes without a resolved still, or already carrying shots,
        are skipped with a log line. Returns the count of scenes fulfilled.
        """
        targets = [s for s in scenes
                   if int((s.extra or {}).get("shots_wanted") or 1) > 1
                   and not (s.extra or {}).get("shots")
                   and getattr(s, "matched_asset", None)]
        if not targets:
            return 0
        if client is None:
            try:
                from nolan.image_search import ImageSearchClient
                img = getattr(nolan_config, "image_sources", None)
                client = ImageSearchClient(
                    pexels_api_key=getattr(img, "pexels_api_key", None),
                    pixabay_api_key=getattr(img, "pixabay_api_key", None),
                    keys=img.provider_keys() if img and hasattr(img, "provider_keys") else None)
            except Exception as exc:
                logger.warning("shots_wanted unfulfilled — no search client: %s", exc)
                return 0
        import httpx
        from nolan.external_assets import build_query_variants

        if fetch is None:
            def fetch(url, dest):
                req = httpx.get(url, timeout=60, follow_redirects=True,
                                headers={"User-Agent": "Mozilla/5.0"})
                req.raise_for_status()
                dest.write_bytes(req.content)

        out_dir = Path(project_path) / "assets" / "broll"
        out_dir.mkdir(parents=True, exist_ok=True)
        used_urls: set = set()
        done = 0
        for s in targets:
            want = min(4, int(s.extra["shots_wanted"]))
            variants = build_query_variants(s) or [s.search_query or ""]
            extras = []
            for q in variants:
                if len(extras) >= want - 1:
                    break
                try:
                    for r in client.search(q, max_results=3):
                        if len(extras) >= want - 1:
                            break
                        if not r.url or r.url in used_urls:
                            continue
                        used_urls.add(r.url)
                        dest = out_dir / f"{s.id}_shot{len(extras) + 1}.jpg"
                        fetch(r.url, dest)
                        extras.append(dest)
                except Exception as exc:
                    logger.info("shot fetch failed for %s (%r): %s", s.id, q, exc)
            if not extras:
                if log:
                    log(f"{s.id}: shots_wanted={want} unfulfilled (no extra stills found)")
                continue
            shots = [{"src": str(s.matched_asset), "weight": 1.5}]
            shots += [{"src": str(p)} for p in extras]
            s.extra["shots"] = shots
            # provenance: AUTO shot lists yield to an explicit motion_spec at
            # render (the Homer run: the agent's montage lost to auto shots);
            # a human editing shots clears this flag (iterate.apply_patch)
            s.extra["shots_auto"] = True
            done += 1
            if log:
                log(f"{s.id}: shot list authored ({len(shots)} stills)")
        return done

    @staticmethod
    def _default_motion_fn(llm_client) -> Optional[Callable]:
        def fn(scene):
            brief = (getattr(scene, "visual_description", "") or
                     getattr(scene, "narration_excerpt", "") or "").strip()
            if not brief:
                return None
            try:
                from nolan.motion import compile_spec
                from nolan.segment.render import _run_async
                spec, _errors = _run_async(compile_spec(brief, llm_client))
            except Exception:
                return None
            return spec if spec.get("backend") else None
        return fn
