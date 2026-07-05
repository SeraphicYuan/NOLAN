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
    enable_external: bool = True        # escalate footage misses to stock/archival providers (P2)
    transition: str = "cut"             # passed to assemble (P3)
    music: Optional[Path] = None        # P3 background bed
    music_gain: float = 0.18
    voice: Optional[str] = None         # voice_id for generated VO (overrides project/default)
    vo_tempo: float = 1.0               # pace for generated VO (ffmpeg atempo)
    captions: bool = True               # produce SRT/VTT/words.json alongside the VO
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
        # Motion is authored lazily in the resolver now (only for graphic scenes that
        # reach it), not as an eager design pass — so author_motion stays off here.
        designer = SceneDesigner(self.llm)
        plan = await designer.design_full_plan(seg.sections, enrich=True, author_motion=False)
        scenes = plan.all_scenes
        assign_timing(scenes, seg.duration)
        return scenes

    def _resolver(self, seg: SegmentInput) -> AssetResolver:
        """Build the shared asset engine wired to this segment's backends.

        The tier factories (ClipMatcher search, imagelib stills, external
        providers, lazy motion authoring) live in `nolan.asset_engine` now —
        one proven implementation for every pipeline. `search_fn` passed to
        the builder (tests) overrides the engine's default.
        """
        import dataclasses

        from nolan.asset_engine import AssetEngine

        rcfg = dataclasses.replace(self.cfg.resolver, enable_external=self.cfg.enable_external)
        if seg.index_db and not Path(seg.index_db).exists():
            logger.warning("index_db not found at %s — b-roll scenes will escalate to "
                           "generation/card (no library search).", seg.index_db)
        engine = AssetEngine.from_config(
            self.nolan_config, config=rcfg,
            project_path=Path(self.cfg.out_dir),
            index_db=Path(seg.index_db) if seg.index_db else None,
            project_id=seg.project_id, llm_client=self.llm)
        if not seg.index_db:
            # No segment index -> no clip search (from_config would otherwise
            # fall back to the global index, which is Director semantics).
            engine.search_fn = None
        if self._search_fn:
            engine.search_fn = self._search_fn
        return engine

    def _resolve(self, scenes, seg: SegmentInput) -> dict:
        return self._resolver(seg).resolve_all(scenes)

    def _reresolve_unresolved(self, scenes, seg: SegmentInput) -> int:
        """Re-run the resolve stage for scenes whose asset pick was cleared (edited).

        A normally-built scene always has a truthy `resolved_source`; the iteration
        layer clears it (and `matched_clip`) when `search_query`/`visual_type` change,
        so this re-searches the library / re-escalates for exactly those scenes.
        """
        needing = [s for s in scenes if not s.resolved_source]
        if not needing:
            return 0
        resolver = self._resolver(seg)
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

    def _voiceover_stage(self, seg: SegmentInput, scenes):
        """Produce the voiceover (existing source VO, or TTS) + captions.

        Returns (vo_path, words). `words` is the VO word-timeline (for scene
        alignment) or None. Order: this runs BEFORE render so scene timings are
        audio-accurate and TTS (which frees its VRAM on exit) precedes ComfyUI.
        """
        if seg.vo_path and Path(seg.vo_path).exists():
            return Path(seg.vo_path), None  # real source VO — keep its timing

        cfg = self.nolan_config
        if cfg and getattr(cfg, "tts", None) and cfg.tts.enabled and seg.sections:
            try:
                from nolan.tts import create_tts_provider
                from nolan import voiceover as vo
                provider = create_tts_provider(cfg.tts)
                ref_audio, ref_text, vid = vo.resolve_voice_ref(self.cfg.out_dir, cfg, self.cfg.voice)
                logger.info("Voiceover voice: %s", vid or "(OmniVoice default)")
                res = vo.produce_voiceover(
                    self.cfg.out_dir, seg.sections, provider,
                    ref_audio=ref_audio, ref_text=ref_text,
                    num_step=cfg.tts.omnivoice.num_step, tempo=self.cfg.vo_tempo)
                words = None
                if self.cfg.captions:
                    try:
                        words = vo.build_captions(self.cfg.out_dir, res["sections"])
                    except Exception as e:
                        logger.warning("caption step failed: %s", e)
                return Path(res["voiceover"]), words
            except Exception as e:
                logger.warning("TTS voiceover failed (%s) — falling back to silent", e)

        from nolan.orchestrator.render import generate_silent_audio
        return generate_silent_audio(seg.duration, self.cfg.out_dir / "vo_silent.wav"), None

    # --- public ---
    async def build(self, seg: SegmentInput) -> BuildResult:
        scenes = await self._design(seg)
        self._resolve(scenes, seg)

        # Voiceover + captions + audio-accurate timing — BEFORE render/save.
        vo, words = self._voiceover_stage(seg, scenes)
        seg.vo_path = str(vo)  # record so a review-resume reuses the same VO
        if words:
            from nolan.voiceover import align_scenes_from_words
            matched = align_scenes_from_words(scenes, words)
            logger.info("Aligned %d/%d scenes from voiceover", matched, len(scenes))

        plan_path = self._save_plan(scenes, seg)
        manifest = self._manifest(scenes)
        (self.cfg.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        if self.cfg.mode == "review":
            return BuildResult(plan_path, manifest, stopped_for_review=True)

        self._render(scenes, seg)
        ScenePlan(sections={"segment": scenes}).save(str(plan_path))   # persist rendered_clip
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
