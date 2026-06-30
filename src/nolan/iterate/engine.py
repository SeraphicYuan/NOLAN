"""Pipeline detection + selective invalidate/re-render driver.

The two NOLAN pipelines write the same `scene_plan.json` but render and assemble
differently. This module detects which one a plan belongs to and re-renders only
the named scenes, reusing each pipeline's existing render/assemble code.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, List, Optional, Tuple


# ---------------------------------------------------------------- raw plan I/O
# We deliberately read/write the raw JSON (not via ScenePlan/Scene) so that
# orchestrator-only fields like `layout_spec` survive the round-trip. The Scene
# dataclass has no `layout_spec`, so ScenePlan.load -> save would drop it.

def load_plan_raw(plan_path) -> dict:
    return json.loads(Path(plan_path).read_text(encoding="utf-8"))


def save_plan_raw(plan_path, data: dict) -> None:
    Path(plan_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def iter_scenes(data: dict) -> Iterator[Tuple[str, dict]]:
    """Yield (section_name, scene_dict) for every scene in the plan."""
    for section, scenes in (data.get("sections") or {}).items():
        if isinstance(scenes, list):
            for scene in scenes:
                if isinstance(scene, dict):
                    yield section, scene


def find_scene(data: dict, scene_id: str) -> Optional[dict]:
    for _, scene in iter_scenes(data):
        if scene.get("id") == scene_id:
            return scene
    return None


# ---------------------------------------------------------------- detection

def detect_pipeline(plan_path) -> str:
    """Return "segment" or "orchestrator" for a scene_plan.json on disk.

    Primary signals are reliable: the segment builder always writes a sibling
    `segment_meta.json`; the orchestrator always has a `.orchestrator/` dir in
    the project root. Falls back to `layout_spec` presence, then to "segment".
    """
    p = Path(plan_path)
    parent = p.parent
    if (parent / "flow.spec.json").exists():
        return "flow"
    if (parent / "segment_meta.json").exists():
        return "segment"
    if (parent / ".orchestrator").exists():
        return "orchestrator"
    try:
        data = load_plan_raw(p)
        for _, scene in iter_scenes(data):
            if scene.get("layout_spec"):
                return "orchestrator"
    except (OSError, json.JSONDecodeError):
        pass
    return "segment"


# ---------------------------------------------------------------- invalidation

def _clip_path(plan_path, scene: dict, pipeline: str) -> Path:
    """Where this scene's rendered clip lives on disk (so we can delete it)."""
    parent = Path(plan_path).parent
    sid = scene.get("id", "unknown")
    if pipeline == "segment":
        return parent / "clips" / f"{sid}.mp4"
    return parent / "assets" / "rendered" / f"{sid}.mp4"


def invalidate_scene(plan_path, scene: dict, pipeline: str) -> None:
    """Clear `rendered_clip` and delete the clip file so a re-render is forced."""
    scene["rendered_clip"] = None
    cp = _clip_path(plan_path, scene, pipeline)
    try:
        if cp.exists():
            cp.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------- re-render

def rerender_scenes(
    plan_path,
    scene_ids: List[str],
    *,
    pipeline: Optional[str] = None,
    llm_client=None,
    nolan_config=None,
    comfyui_workflow: str = "workflows/image/flux-dev-fp8.json",
    comfyui_prompt_node: str = "6",
    comfyui_timeout: float = 240.0,
) -> Optional[Path]:
    """Invalidate the named scenes, re-render only those, then reassemble.

    Untouched scenes keep their existing clips. Returns the final video path.
    """
    plan_path = Path(plan_path)
    pipeline = pipeline or detect_pipeline(plan_path)
    ids = set(scene_ids)
    if pipeline == "flow":
        return _rerender_flow(plan_path, ids)
    if pipeline == "segment":
        return _rerender_segment(
            plan_path, ids, llm_client=llm_client, nolan_config=nolan_config,
            comfyui_workflow=comfyui_workflow, comfyui_prompt_node=comfyui_prompt_node,
            comfyui_timeout=comfyui_timeout,
        )
    return _rerender_orchestrator(plan_path, ids, llm_client=llm_client, nolan_config=nolan_config)


def _rerender_flow(plan_path: Path, ids: set) -> Optional[Path]:
    """Flow pipeline (chapter-block): re-render ONLY the selected beats, then re-concat.

    A beat is independently re-renderable (its duration is pinned to its VO segment), so
    untouched beats keep their existing clips and only the named beats are re-rendered.
    """
    from nolan.flows.render import render_beats, concat_beats
    from nolan.flows.scene_view import beat_index, build_scene_plan

    project = plan_path.parent
    job = project / "flow.job.json"
    work = project / ".flow" / "clips"
    n = len(json.loads(job.read_text(encoding="utf-8")).get("props", {}).get("steps", []))

    sel = sorted({beat_index(s) for s in ids if s.startswith("beat_")})
    render_beats(job, work, only=sel)                      # re-render selected only
    clips = [work / f"beat_{i:02d}.mp4" for i in range(n)]
    missing = [c for c in clips if not c.exists()]
    if missing:
        raise FileNotFoundError(f"missing beat clips (run a full render first): {missing}")

    out_name = json.loads(job.read_text(encoding="utf-8")).get("out", "final.mp4")
    final = project / "video" / out_name
    concat_beats(clips, final)
    build_scene_plan(project)                              # refresh the Scene-page view
    return final


def _rerender_segment(plan_path: Path, ids: set, *, llm_client, nolan_config,
                      comfyui_workflow, comfyui_prompt_node, comfyui_timeout) -> Optional[Path]:
    """Re-render ONLY the named scenes, then reassemble.

    Renders exactly the selected scenes (not the whole plan) so it is safe on
    plans not produced by the segment builder — whose clip filenames don't match
    the skip-guard, which would otherwise re-render everything.
    """
    from nolan.segment.builder import SegmentBuilder, BuildConfig, _resolve_meta_path
    from nolan.segment.inputs import SegmentInput
    from nolan.scenes import ScenePlan

    meta_path = plan_path.parent / "segment_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(
            f"{meta_path} missing — this plan wasn't built by the segment pipeline. "
            "Add a segment_meta.json (duration/vo_path/source_video/index_db) to iterate on it.")

    cfg = BuildConfig(out_dir=plan_path.parent, comfyui_workflow=comfyui_workflow,
                      comfyui_prompt_node=comfyui_prompt_node, comfyui_timeout=comfyui_timeout)
    builder = SegmentBuilder(llm_client, cfg, nolan_config=nolan_config)

    plan = ScenePlan.load(str(plan_path))
    selected = [s for s in plan.all_scenes if s.id in ids]
    # Invalidate selected (clear clip + delete file); untouched scenes keep theirs.
    for s in selected:
        s.rendered_clip = None
        clip = plan_path.parent / "clips" / f"{s.id}.mp4"
        if clip.exists():
            clip.unlink()

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    seg = SegmentInput(sections=[], duration=meta["duration"],
                       vo_path=_resolve_meta_path(meta.get("vo_path")),
                       source_video=_resolve_meta_path(meta.get("source_video")),
                       index_db=_resolve_meta_path(meta.get("index_db")),
                       project_id=meta.get("project_id"))

    builder._reresolve_unresolved(selected, seg)   # re-pick assets for the selected only
    builder._render(selected, seg)                 # render ONLY the selected scenes
    ScenePlan(sections=plan.sections).save(str(plan_path))   # persist (full plan)
    vo = builder._resolve_vo(seg)
    return builder._assemble(plan_path, vo, plan_path.parent / "final.mp4")


def _reresolve_broll_dicts(stale: list, llm_client, nolan_config) -> int:
    """Re-match stale b-roll scene *dicts* to library clips via ClipMatcher.

    Operates on raw dicts (a temp Scene is built only to call the matcher) so the
    orchestrator's `layout_spec` scenes are never round-tripped/lost.
    """
    if not (stale and llm_client and nolan_config):
        return 0
    try:
        from nolan.scenes import Scene
        from nolan.clip_matcher import ClipMatcher
        from nolan.vector_search import VectorSearch
        from nolan.indexer import VideoIndex
        db = Path(nolan_config.indexing.database).expanduser()
        if not db.exists():
            return 0
        vs = VectorSearch(db_path=db.parent / "vectors", index=VideoIndex(db))
        # Pure vector matching (llm_client=None) — fast/free/robust, like select_clips.
        cm = ClipMatcher(vector_search=vs, llm_client=None,
                         config=getattr(nolan_config, "clip_matching", nolan_config))
        from nolan.segment.render import _run_async
    except Exception:  # noqa: BLE001 - no index/vectors -> skip, render uses existing pick
        return 0
    n = 0
    for d in stale:
        try:
            sc = Scene(id=d.get("id", "x"), visual_type=d.get("visual_type", "b-roll"),
                       search_query=d.get("search_query", ""),
                       visual_description=d.get("visual_description", ""),
                       narration_excerpt=d.get("narration_excerpt", ""))
            mc = _run_async(cm.match_scene(sc, project_id=None))   # match_scene is async
            if mc:
                d["matched_clip"] = mc
                n += 1
        except Exception:  # noqa: BLE001 - one bad match shouldn't abort the batch
            pass
    return n


def _rerender_orchestrator(plan_path: Path, ids: set, *, llm_client=None, nolan_config=None) -> Optional[Path]:
    from nolan.orchestrator import render as render_mod

    project_path = plan_path.parent
    rendered_dir = project_path / "assets" / "rendered"
    rendered_dir.mkdir(parents=True, exist_ok=True)

    data = load_plan_raw(plan_path)
    selected = []
    for _, scene in iter_scenes(data):
        if scene.get("id") in ids:
            invalidate_scene(plan_path, scene, "orchestrator")
            selected.append(scene)

    # Re-pick library footage for edited b-roll scenes whose match was cleared.
    stale = [s for s in selected if s.get("visual_type") == "b-roll" and not s.get("matched_clip")
             and (s.get("search_query") or s.get("visual_description"))]
    _reresolve_broll_dicts(stale, llm_client, nolan_config)

    # Render ONLY the selected scenes; annotate leaves untouched scenes' clips alone
    # (it only sets rendered_clip for ids present in `outcomes`).
    outcomes = [render_mod.render_scene(s, project_path, rendered_dir) for s in selected]
    total_duration, _ = render_mod.annotate_scene_plan(data, outcomes)
    save_plan_raw(plan_path, data)

    scratch = project_path / ".orchestrator" / "modules" / "render"
    scratch.mkdir(parents=True, exist_ok=True)
    silent = scratch / "silent.wav"
    render_mod.generate_silent_audio(total_duration, silent)

    output_dir = project_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    final = output_dir / "final.mp4"
    repo_root = Path(__file__).resolve().parents[3]   # src/nolan/iterate -> repo root
    render_mod.call_assemble(
        project_path=project_path, scene_plan_path=plan_path,
        audio_path=silent, output_path=final, repo_root=repo_root,
    )
    return final
