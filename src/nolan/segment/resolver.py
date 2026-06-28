"""Stage 4 — per-scene asset source resolution (the asset-first core).

Routes each scene to the best source with a fallback chain + relevance threshold,
encoding the "source mix adapts to segment type" learning from the experiments:
  - motion (Python/Remotion) for text/data/chart/annotation (already set by author_motion)
  - segment search for footage IF a match clears the threshold
  - else escalate: external footage (P2) -> ComfyUI generation -> black
The chosen source + reason is recorded on `scene.resolved_source` (no silent caps).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

FOOTAGE_TYPES = {"b-roll", "a-roll", "footage", "cinematic"}
GENERATED_TYPES = {"generated", "generated-image", "hero"}


@dataclass
class ResolverConfig:
    search_threshold: float = 0.5
    enable_search: bool = True
    enable_generation: bool = True
    enable_external: bool = False          # P2
    enable_library: bool = True            # picture-library stills (CLIP)
    library_threshold: float = 0.24        # CLIP cosine floor for a usable still
    enable_motion: bool = True             # lazily author a motion_spec for graphic/text scenes


class AssetResolver:
    def __init__(self, config: ResolverConfig = None,
                 search_fn: Optional[Callable] = None,      # scene -> matched_clip dict|None (with similarity_score)
                 external_fn: Optional[Callable] = None,    # scene -> truthy kind|None; sets matched_clip/matched_asset (P2)
                 library_fn: Optional[Callable] = None,     # scene -> matched_asset path|None (picture library)
                 motion_fn: Optional[Callable] = None):     # scene -> motion_spec dict|None (lazy authoring)
        self.cfg = config or ResolverConfig()
        self.search_fn = search_fn
        self.external_fn = external_fn
        self.library_fn = library_fn
        self.motion_fn = motion_fn

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

    # --- internals ---
    def _resolve(self, scene) -> str:
        if scene.motion_spec:
            return f"motion:{scene.motion_spec.get('effect', '?')}"

        vt = (scene.visual_type or "").lower().strip()

        if vt in FOOTAGE_TYPES:
            if self.cfg.enable_search and self.search_fn:
                mc = self.search_fn(scene)
                if mc and float(mc.get("similarity_score", 1.0)) >= self.cfg.search_threshold:
                    scene.matched_clip = mc
                    return f"search({mc.get('similarity_score', 0):.2f})"
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

    def _escalate(self, scene, reason: str) -> str:
        # Picture library (curated stills) before external providers / generation.
        if self.cfg.enable_library and self.library_fn:
            asset = self.library_fn(scene)
            if asset:
                scene.matched_asset = asset
                return f"library({reason})"
        if self.cfg.enable_external and self.external_fn:
            # external_fn finds + attaches the asset (sets scene.matched_clip for a
            # video, or scene.matched_asset for an image) and returns a truthy kind.
            got = self.external_fn(scene)
            if got:
                return f"external({reason})"
        if self.cfg.enable_generation:
            return self._generate(scene, reason=reason)
        return f"none({reason})"

    def _generate(self, scene, reason: str = "") -> str:
        if not self.cfg.enable_generation:
            return f"none(gen-disabled{':' + reason if reason else ''})"
        scene.comfyui_prompt = scene.comfyui_prompt or scene.visual_description or scene.narration_excerpt
        tag = f"generated({reason})" if reason else "generated"
        return tag
