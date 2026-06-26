"""Stage 5 — render each resolved scene to a normalized 1920x1080@30 clip.

Generalizes the validated build scripts: dispatches per scene to motion (Python/
Remotion), segment-search b-roll (extract+fade), or ComfyUI generation (+Ken Burns).
All outputs are 1920x1080 so `nolan assemble` can concat them.
"""
from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()


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


def _vf(ctx: RenderContext, fade: float, dur: float) -> str:
    v = (f"scale={ctx.width}:{ctx.height}:force_original_aspect_ratio=decrease,"
         f"pad={ctx.width}:{ctx.height}:(ow-iw)/2:(oh-ih)/2:black,fps={ctx.fps}")
    if fade > 0:
        v += f",fade=t=in:st=0:d={fade},fade=t=out:st={max(0,dur-fade):.3f}:d={fade}"
    return v


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


def _extract_broll(scene, ctx: RenderContext, out: Path) -> Path:
    mc = scene.matched_clip
    start, end = float(mc["clip_start"]), float(mc["clip_end"])
    dur = _scene_dur(scene)
    src = _resolve_video(mc.get("video_path") or (str(ctx.source_video) if ctx.source_video else None), ctx)
    cmd = [FF, "-y", "-ss", str(start), "-i", str(src), "-t", f"{dur:.3f}",
           "-vf", _vf(ctx, ctx.fade, dur), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
           "-r", str(ctx.fps), "-loglevel", "error", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"broll extract failed: {r.stderr[-300:]}")
    return out


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


def _fallback_card(scene, ctx: RenderContext, out: Path) -> Path:
    """Resilient fallback when generation is unavailable: a clean title card from the
    scene's intent, so the timeline never has a black hole."""
    from nolan.renderer.scenes import TitleRenderer
    # Prefer the spoken line (viewer-facing) over visual_description (a gen instruction).
    text = (scene.narration_excerpt or scene.visual_description or "").strip()
    text = (text[:70] + "…") if len(text) > 72 else text
    TitleRenderer(title=text or "—", width=ctx.width, height=ctx.height,
                  show_accent_line=True).render(str(out), duration=_scene_dur(scene), with_qa=False)
    return out


def render_scene_clip(scene, ctx: RenderContext) -> Optional[str]:
    """Render one scene; set scene.rendered_clip (path relative to clips_dir.parent) and return it."""
    ctx.clips_dir.mkdir(parents=True, exist_ok=True)
    out = ctx.clips_dir / f"{scene.id}.mp4"
    src = scene.resolved_source or ""

    # Resume-friendly: skip scenes already rendered to a non-empty clip.
    if scene.rendered_clip and out.exists() and out.stat().st_size > 256:
        return scene.rendered_clip

    if scene.motion_spec:
        from nolan.motion import render as render_motion
        render_motion(scene.motion_spec, out)
    elif scene.matched_clip:
        _extract_broll(scene, ctx, out)
    elif scene.comfyui_prompt and src.startswith("generated"):
        try:
            _gen_comfyui(scene, ctx, out)
        except Exception:
            _fallback_card(scene, ctx, out)   # gen down/slow -> a card beats a black hole
            scene.resolved_source = (scene.resolved_source or "generated") + "->card-fallback"
    else:
        return None  # no asset -> assemble fills black

    rel = f"{ctx.clips_dir.name}/{out.name}"
    scene.rendered_clip = rel
    return rel
