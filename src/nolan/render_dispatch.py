"""Single per-scene render routing (pipeline consolidation P1b).

One place that decides which renderer handles a scene and runs it, shared by the
segment and orchestrator render paths. Works on a Scene **object** (segment) or a
raw **dict** (orchestrator/iterate keep dicts to preserve `layout_spec`).

Only the routing + render calls are shared — each caller keeps its own output-path
and return conventions, so `assemble` paths are unchanged. Routing order:

    motion_spec → matched_clip (b-roll) → layout_spec → comfyui (generated) → card
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional


def field(scene, key, default=None):
    """Read a field from a Scene object or a dict."""
    if isinstance(scene, dict):
        return scene.get(key, default)
    return getattr(scene, key, default)


def render_card(scene, out: Path, duration: float, width: int, height: int) -> Path:
    """Resilient fallback: a clean title card from the scene's intent (never black)."""
    from nolan.renderer.scenes import TitleRenderer
    text = (field(scene, "narration_excerpt") or field(scene, "visual_description") or "").strip()
    text = (text[:70] + "…") if len(text) > 72 else text
    TitleRenderer(title=text or "—", width=width, height=height,
                  show_accent_line=True).render(str(out), duration=duration, with_qa=False)
    return out


def render_one(scene, out, *, duration: float, width: int = 1920, height: int = 1080,
               fps: int = 30, fade: float = 0.4, source_video=None,
               resolve_src: Optional[Callable] = None,
               gen_fn: Optional[Callable] = None,
               lottie_service_url: Optional[str] = None) -> Optional[str]:
    """Render one scene to ``out``; return the kind rendered, or None if no asset.

    Kinds: "motion" | "broll" | "lottie" | "layout" | "generated" | "card" | None.
    `gen_fn(scene, out)` does ComfyUI generation when available; if it's None or
    raises, a title card is rendered instead of leaving a black hole.
    `resolve_src(src)` optionally maps a clip's video path cwd-independently.
    Lottie scenes (`lottie_asset`/`lottie_template`) render via the render-service.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    motion = field(scene, "motion_spec")
    if motion:
        from nolan.motion import render as render_motion
        render_motion(motion, out)
        return "motion"

    mc = field(scene, "matched_clip")
    if mc and mc.get("clip_start") is not None and mc.get("clip_end") is not None:
        from nolan.ffmpeg_utils import extract_subclip
        src = mc.get("video_path") or (str(source_video) if source_video else None)
        if resolve_src:
            src = resolve_src(src)
        extract_subclip(src, float(mc["clip_start"]), duration, out,
                        width=width, height=height, fps=fps, fade=fade)
        return "broll"

    if field(scene, "lottie_asset") or field(scene, "lottie_template"):
        from nolan.lottie_render import DEFAULT_SERVICE, render_lottie_for_scene
        if render_lottie_for_scene(scene, out, duration=duration, width=width, height=height,
                                   fps=fps, service_url=lottie_service_url or DEFAULT_SERVICE):
            return "lottie"
        # render-service down / customization failed → fall through to other branches

    layout = field(scene, "layout_spec")
    if layout:
        from nolan.orchestrator.render import render_layout
        res = render_layout({"id": field(scene, "id"), "layout_spec": layout},
                            out, duration, width, height, fps)
        return "layout" if res is not None else None

    prompt = field(scene, "comfyui_prompt")
    rs = str(field(scene, "resolved_source") or "")
    vt = field(scene, "visual_type") or ""
    if prompt and (rs.startswith("generated") or vt.startswith("generated")):
        if gen_fn:
            try:
                gen_fn(scene, out)
                return "generated"
            except Exception:
                render_card(scene, out, duration, width, height)
                return "card"
        render_card(scene, out, duration, width, height)
        return "card"

    return None
