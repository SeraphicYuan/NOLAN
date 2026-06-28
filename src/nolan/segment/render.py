"""Stage 5 — render each resolved scene to a normalized 1920x1080@30 clip.

Generalizes the validated build scripts: dispatches per scene to motion (Python/
Remotion), segment-search b-roll (extract+fade), or ComfyUI generation (+Ken Burns).
All outputs are 1920x1080 so `nolan assemble` can concat them.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _run_async(coro):
    """Run a coroutine whether or not an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()


@dataclass
class RenderContext:
    clips_dir: Path
    work_dir: Path
    source_video: Optional[Path] = None
    fps: int = 30
    width: int = 1920
    height: int = 1080
    fade: float = 0.4
    comfyui_host: str = "127.0.0.1"
    comfyui_port: int = 8080
    comfyui_workflow: str = "workflows/image/flux-dev-fp8.json"
    comfyui_prompt_node: str = "6"
    comfyui_retries: int = 1   # 1 = no retry (a stuck gen times out slowly; fall back to a card)
    comfyui_timeout: float = 240.0


def _scene_dur(scene) -> float:
    return max(0.5, (scene.end_seconds or 0) - (scene.start_seconds or 0))


def _resolve_video(src, ctx: RenderContext):
    """Resolve a clip's source video cwd-independently (the index stores repo-root-
    relative paths). Try as-given, then repo-root-relative, then the context's source."""
    if src and Path(src).exists():
        return src
    if src:
        cand = Path(__file__).resolve().parents[3] / src   # segment -> nolan -> src -> repo
        if cand.exists():
            return str(cand)
    if ctx.source_video and Path(ctx.source_video).exists():
        return str(ctx.source_video)
    return src


def _gen_comfyui(scene, ctx: RenderContext, out: Path) -> Path:
    from nolan.comfyui import ComfyUIClient
    from nolan.renderer.scenes import KenBurnsRenderer
    png = ctx.work_dir / f"{scene.id}.png"

    async def _g():
        c = ComfyUIClient(host=ctx.comfyui_host, port=ctx.comfyui_port,
                          workflow_file=Path(ctx.comfyui_workflow), prompt_node=ctx.comfyui_prompt_node)
        if not await c.check_connection():
            raise RuntimeError("ComfyUI not reachable")
        await c.generate(scene.comfyui_prompt, png, timeout=ctx.comfyui_timeout)

    last = None
    for attempt in range(ctx.comfyui_retries):
        try:
            _run_async(_g())
            break
        except Exception as ex:  # noqa: BLE001 - transient timeouts under burst load -> retry
            last = ex
            import time as _t
            _t.sleep(2.0)
    else:
        raise RuntimeError(f"ComfyUI generate failed after {ctx.comfyui_retries} tries: {last}")
    KenBurnsRenderer(image_path=str(png), zoom_start=1.0, zoom_end=1.12, pan_direction="up").render(
        str(out), duration=_scene_dur(scene), with_qa=False)
    return out


def render_scene_clip(scene, ctx: RenderContext) -> Optional[str]:
    """Render one scene; set scene.rendered_clip (path relative to clips_dir.parent) and return it.

    Routing is shared via `render_dispatch.render_one`; segment keeps its
    `clips/<id>.mp4` path convention, ComfyUI generation, and resume-skip.
    """
    from nolan.render_dispatch import render_one

    ctx.clips_dir.mkdir(parents=True, exist_ok=True)
    out = ctx.clips_dir / f"{scene.id}.mp4"

    # Resume-friendly: skip scenes already rendered to a non-empty clip.
    if scene.rendered_clip and out.exists() and out.stat().st_size > 256:
        return scene.rendered_clip

    kind = render_one(
        scene, out, duration=_scene_dur(scene), width=ctx.width, height=ctx.height,
        fps=ctx.fps, fade=ctx.fade, source_video=ctx.source_video,
        resolve_src=lambda src: _resolve_video(src, ctx),
        gen_fn=lambda s, o: _gen_comfyui(s, ctx, o),
    )
    if kind is None:
        return None  # no asset -> assemble fills black
    if kind == "card":
        scene.resolved_source = (scene.resolved_source or "generated") + "->card-fallback"

    rel = f"{ctx.clips_dir.name}/{out.name}"
    scene.rendered_clip = rel
    return rel
