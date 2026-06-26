"""SegmentBuilder — wrap the validated asset-first pipeline into one orchestrator.

Stages: input -> design(+author_motion) -> timing -> resolve sources -> [review gate]
-> render -> assemble. Modes: "auto" (one shot) and "review" (stop after resolve so
you can edit the plan, then resume with build_from_plan).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# segment_meta.json stores paths relative to the NOLAN repo root, so resume works
# regardless of the caller's cwd (CLI from any dir, or the hub process).
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_meta_path(raw: Optional[str]) -> Optional[Path]:
    """Resolve a stored meta path independent of cwd (abs / cwd-relative / repo-relative)."""
    if not raw:
        return None
    p = Path(raw)
    if p.exists():
        return p
    cand = _REPO_ROOT / raw
    return cand if cand.exists() else p   # fall back to as-given (surfaced as missing)

from nolan.scenes import Scene, ScenePlan, SceneDesigner, ScriptSection
from .inputs import SegmentInput, assign_timing
from .resolver import AssetResolver, ResolverConfig
from .render import RenderContext, render_scene_clip


@dataclass
class BuildConfig:
    out_dir: Path
    mode: str = "auto"                  # auto | review
    resolver: ResolverConfig = field(default_factory=ResolverConfig)
    fps: int = 30
    width: int = 1920
    height: int = 1080
    fade: float = 0.4
    transition: str = "cut"             # passed to assemble (P3)
    music: Optional[Path] = None        # P3 background bed
    music_gain: float = 0.18
    comfyui_workflow: str = "workflows/image/flux-dev-fp8.json"
    comfyui_prompt_node: str = "6"
    comfyui_timeout: float = 240.0


@dataclass
class BuildResult:
    plan_path: Path
    manifest: dict
    stopped_for_review: bool = False
    final_path: Optional[Path] = None


class SegmentBuilder:
    def __init__(self, llm_client, config: BuildConfig, nolan_config=None,
                 search_fn: Optional[Callable] = None, tts_fn: Optional[Callable] = None):
        self.llm = llm_client
        self.cfg = config
        self.nolan_config = nolan_config
        self._search_fn = search_fn
        self._tts_fn = tts_fn
        self.cfg.out_dir = Path(self.cfg.out_dir)
        self.cfg.out_dir.mkdir(parents=True, exist_ok=True)

    # --- stages ---
    async def _design(self, seg: SegmentInput) -> List[Scene]:
        designer = SceneDesigner(self.llm)
        plan = await designer.design_full_plan(seg.sections, enrich=True, author_motion=True)
        scenes = plan.all_scenes
        assign_timing(scenes, seg.duration)
        return scenes

    def _make_search_fn(self, seg: SegmentInput) -> Optional[Callable]:
        if self._search_fn:
            return self._search_fn
        if not seg.index_db:
            return None
        if not Path(seg.index_db).exists():
            logger.warning("index_db not found at %s — b-roll scenes will escalate to "
                           "generation/card (no library search).", seg.index_db)
            return None
        try:
            from nolan.indexer import VideoIndex
            from nolan.vector_search import VectorSearch
            from nolan.clip_matcher import ClipMatcher
            vs = VectorSearch(db_path=Path(seg.index_db).parent / "vectors", index=VideoIndex(Path(seg.index_db)))
            # Pure vector matching (no LLM selection pass) — fast, free, and robust; mirrors
            # the orchestrator's select_clips step. (The LLM-selection path can return None.)
            cm = ClipMatcher(vector_search=vs, llm_client=None,
                             config=getattr(self.nolan_config, "clip_matching", self.nolan_config))

            from .render import _run_async

            def fn(scene):
                try:
                    # match_scene is async; the resolver calls this synchronously.
                    return _run_async(cm.match_scene(scene, project_id=seg.project_id))
                except Exception:
                    return None
            return fn
        except Exception:
            return None

    def _resolve(self, scenes, seg: SegmentInput) -> dict:
        resolver = AssetResolver(self.cfg.resolver, search_fn=self._make_search_fn(seg))
        return resolver.resolve_all(scenes)

    def _reresolve_unresolved(self, scenes, seg: SegmentInput) -> int:
        """Re-run the resolve stage for scenes whose asset pick was cleared (edited).

        A normally-built scene always has a truthy `resolved_source`; the iteration
        layer clears it (and `matched_clip`) when `search_query`/`visual_type` change,
        so this re-searches the library / re-escalates for exactly those scenes.
        """
        needing = [s for s in scenes if not s.resolved_source]
        if not needing:
            return 0
        resolver = AssetResolver(self.cfg.resolver, search_fn=self._make_search_fn(seg))
        for s in needing:
            resolver.resolve(s)
        return len(needing)

    def _render(self, scenes, seg: SegmentInput) -> None:
        ctx = RenderContext(clips_dir=self.cfg.out_dir / "clips", work_dir=self.cfg.out_dir / "work",
                            source_video=seg.source_video, fps=self.cfg.fps,
                            width=self.cfg.width, height=self.cfg.height, fade=self.cfg.fade,
                            comfyui_workflow=self.cfg.comfyui_workflow,
                            comfyui_prompt_node=self.cfg.comfyui_prompt_node,
                            comfyui_timeout=self.cfg.comfyui_timeout)
        for s in scenes:
            try:
                render_scene_clip(s, ctx)
            except Exception as ex:  # noqa: BLE001 - one bad scene shouldn't kill the build
                s.resolved_source = (s.resolved_source or "") + f" [render-failed: {type(ex).__name__}]"

    def _resolve_vo(self, seg: SegmentInput) -> Path:
        if seg.vo_path and Path(seg.vo_path).exists():
            return Path(seg.vo_path)
        if self._tts_fn:
            return Path(self._tts_fn(" ".join(s.narration for s in seg.sections), self.cfg.out_dir / "vo_tts.m4a"))
        from nolan.orchestrator.render import generate_silent_audio
        return generate_silent_audio(seg.duration, self.cfg.out_dir / "vo_silent.wav")

    def _assemble(self, plan_path: Path, vo: Path, out: Path) -> Path:
        cmd = [sys.executable, "-m", "nolan", "assemble", str(plan_path), str(vo),
               "-o", out.name, "-r", f"{self.cfg.width}x{self.cfg.height}", "--fps", str(self.cfg.fps),
               "-t", self.cfg.transition]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode or not out.exists():
            raise RuntimeError(f"assemble failed: {r.stderr[-400:] or r.stdout[-400:]}")
        if self.cfg.music and Path(self.cfg.music).exists():
            self._mix_music(out, Path(self.cfg.music), out.with_name("final_music.mp4"))
            return out.with_name("final_music.mp4")
        return out

    def _mix_music(self, video: Path, music: Path, out: Path) -> Path:
        """P3: duck a music bed under the existing VO."""
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [ff, "-y", "-i", str(video), "-i", str(music),
               "-filter_complex",
               f"[1:a]volume={self.cfg.music_gain}[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-shortest",
               "-loglevel", "error", str(out)]
        subprocess.run(cmd, check=True, capture_output=True)
        return out

    def _save_plan(self, scenes, seg: SegmentInput) -> Path:
        ScenePlan(sections={"segment": scenes}).save(str(self.cfg.out_dir / "scene_plan.json"))
        meta = {"duration": seg.duration,
                "vo_path": str(seg.vo_path) if seg.vo_path else None,
                "source_video": str(seg.source_video) if seg.source_video else None,
                "index_db": str(seg.index_db) if seg.index_db else None,
                "project_id": seg.project_id}
        (self.cfg.out_dir / "segment_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return self.cfg.out_dir / "scene_plan.json"

    def _manifest(self, scenes) -> dict:
        return {"scenes": [{"id": s.id, "t": [s.start_seconds, s.end_seconds],
                            "visual_type": s.visual_type, "source": s.resolved_source,
                            "narration": (s.narration_excerpt or "")[:60]} for s in scenes]}

    # --- public ---
    async def build(self, seg: SegmentInput) -> BuildResult:
        scenes = await self._design(seg)
        self._resolve(scenes, seg)
        plan_path = self._save_plan(scenes, seg)
        manifest = self._manifest(scenes)
        (self.cfg.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        if self.cfg.mode == "review":
            return BuildResult(plan_path, manifest, stopped_for_review=True)

        self._render(scenes, seg)
        ScenePlan(sections={"segment": scenes}).save(str(plan_path))   # persist rendered_clip
        vo = self._resolve_vo(seg)
        final = self._assemble(plan_path, vo, self.cfg.out_dir / "final.mp4")
        return BuildResult(plan_path, manifest, final_path=final)

    def build_from_plan(self, plan_path: Path) -> BuildResult:
        """Resume after a review/edit: render the (possibly edited) plan + assemble."""
        plan_path = Path(plan_path)
        plan = ScenePlan.load(str(plan_path))
        scenes = plan.all_scenes
        meta = json.loads((plan_path.parent / "segment_meta.json").read_text(encoding="utf-8"))
        seg = SegmentInput(sections=[], duration=meta["duration"],
                           vo_path=_resolve_meta_path(meta.get("vo_path")),
                           source_video=_resolve_meta_path(meta.get("source_video")),
                           index_db=_resolve_meta_path(meta.get("index_db")),
                           project_id=meta.get("project_id"))
        self.cfg.out_dir = plan_path.parent
        self._reresolve_unresolved(scenes, seg)   # edited search_query/visual_type -> re-pick asset
        self._render(scenes, seg)
        ScenePlan(sections={"segment": scenes}).save(str(plan_path))
        vo = self._resolve_vo(seg)
        final = self._assemble(plan_path, vo, plan_path.parent / "final.mp4")
        return BuildResult(plan_path, self._manifest(scenes), final_path=final)


# --- P2: suggest self-contained spans from a transcript -----------------------
SUGGEST_GUIDE = (
    "You are given a timed transcript of a video. Propose 1-5 self-contained ~60s segments "
    "that each make a complete point and would stand alone as a short essay. Output ONLY a JSON "
    'array: [{"start": <sec>, "end": <sec>, "title": "...", "reason": "..."}]. '
    "Each segment 40-90s, aligned to sentence boundaries."
)


async def suggest_spans(transcript_lines, llm_client) -> List[dict]:
    """transcript_lines: [(text, start, end)] -> candidate spans."""
    timed = "\n".join(f"[{s:.0f}-{e:.0f}] {t}" for (t, s, e) in transcript_lines)
    raw = await llm_client.generate(timed, system_prompt=SUGGEST_GUIDE)
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    return json.loads(m.group(0)) if m else []
