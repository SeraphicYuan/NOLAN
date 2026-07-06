"""Render a validated motion spec on its backend (python renderer or Remotion)."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

from .registry import normalize_position


def _render_python(spec: Dict[str, Any], out_path: Path) -> Path:
    from nolan.renderer import scenes as S
    cls = getattr(S, spec["target"])
    kwargs: Dict[str, Any] = dict(spec.get("content", {}))
    if "position" in spec:
        kwargs["position"] = normalize_position(spec["position"])  # {x,y}; Position.from_spec handles it
    style = spec.get("style", {})
    renderer = cls(**kwargs)
    # 'tone' style maps to a with_<tone>_style() method (e.g. CounterRenderer)
    tone = style.get("tone")
    if tone and tone != "neutral":
        m = getattr(renderer, f"with_{tone}_style", None)
        if m:
            renderer = m()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    renderer.render(str(out_path), duration=spec.get("duration", 4.0), with_qa=False)
    return out_path


def _render_remotion(spec: Dict[str, Any], out_path: Path) -> Path:
    from nolan import remotion_source
    props: Dict[str, Any] = dict(spec.get("content", {}))
    props.update(spec.get("style", {}))
    if "position" in spec:
        props["position"] = normalize_position(spec["position"])
    if "theme" in spec:
        props["theme"] = spec["theme"]
    if "accent" in spec:
        props["accent"] = spec["accent"]
    # a video/image given as a path is staged into public/; a bare name is left as a prop
    video = image = background = cards = None
    if isinstance(props.get("videoSrc"), str) and ("/" in props["videoSrc"] or props["videoSrc"].endswith(".mp4")):
        video = props.pop("videoSrc")
    if isinstance(props.get("mapSrc"), str) and ("/" in props["mapSrc"] or props["mapSrc"].endswith((".png", ".jpg"))):
        image = props.pop("mapSrc")
    # photo-montage: an array of card images + an optional table-texture background
    if isinstance(props.get("cards"), list):
        cards = props.pop("cards")
    bg = props.get("background")
    if isinstance(bg, str) and ("/" in bg or bg.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))):
        background = props.pop("background")  # an image path → stage it (a CSS color stays in props)

    frames = max(30, int(round(spec.get("duration", 4.0) * 30)))
    produced = remotion_source.render(spec["target"], props, out_path.name,
                                      duration_frames=frames, video=video, image=image,
                                      cards=cards, background=background)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(produced).resolve() != out_path.resolve():
        shutil.copy(produced, out_path)
    return out_path


def _render_still_family(spec: Dict[str, Any], out_path: Path) -> Path:
    """still-motion / split-screen / clip-montage — delegate to nolan.still_motion, which handles
    the rembg cutout (parallax/rack-focus) + staging that the generic Remotion path doesn't."""
    from nolan import still_motion
    c = {**spec.get("content", {}), **spec.get("style", {})}
    dur = spec.get("duration", 4.0)
    target = spec["target"]
    if target == "StillMotion":
        return still_motion.render_still(c["image"], c.get("treatment", "ken-burns-in"), out_path,
                                         duration=dur, direction=c.get("direction", "right"))
    if target == "SplitScreen":
        return still_motion.render_split(c["left"], c["right"], out_path, duration=dur,
                                         left_label=c.get("left_label", ""), right_label=c.get("right_label", ""))
    if target == "ClipMontage":
        return still_motion.render_clip_montage(c["clips"], out_path, transition=c.get("transition", "fade"),
                                                trans_frames=int(c.get("trans_frames", 16)))
    if target == "StatOver":
        return still_motion.render_stat_over(
            c["image"], c["value"], out_path, prefix=c.get("prefix", ""), suffix=c.get("suffix", ""),
            caption=c.get("caption", ""), decimals=int(c.get("decimals", 0)),
            theme=spec.get("theme"), accent=spec.get("accent", ""),
            kind=("video" if c.get("kind") == "video" else "image"), duration=dur)
    raise ValueError(f"unknown still-family target: {target}")


def _render_block(spec: Dict[str, Any], out_path: Path) -> Path:
    """Text/data intents served by the curated Remotion blocks (Phase 3).

    These effects share their param names with the same-named layout
    templates, so the layout->block adapters apply directly.
    """
    from nolan.layout_blocks import render_layout_block

    template = str(spec["effect"]).replace("-", "_")
    params = {**spec.get("content", {}), **spec.get("style", {})}
    clip = render_layout_block(template, params, spec.get("duration", 4.0),
                               out_path, scene_id=str(spec.get("effect")))
    if clip is None:
        raise ValueError(f"block adapter produced no mapping for {template}")
    return clip


def render(spec: Dict[str, Any], out_path) -> Path:
    """Render a *validated* spec to out_path (mp4)."""
    out_path = Path(out_path)
    if spec.get("target") in ("StillMotion", "SplitScreen", "ClipMontage", "StatOver"):
        return _render_still_family(spec, out_path)
    if spec.get("backend") == "block":
        return _render_block(spec, out_path)
    if spec.get("backend") == "python":
        return _render_python(spec, out_path)
    return _render_remotion(spec, out_path)


# --- Chapter hosting (render story v2) -------------------------------------------

# Registry target -> key in remotion-lib/src/comps.ts. PhotoMontage/PhotoGrid
# get "...Pro" keys because the blocks library carries same-named rebuilds.
_CHAPTER_TARGETS = {
    "Kinetic": "Kinetic", "BarCompare": "BarCompare", "KShape": "KShape",
    "AnnotateStat": "AnnotateStat", "AnnotateOverVideo": "AnnotateOverVideo",
    "RouteMap": "RouteMap", "PremiumCard": "PremiumCard",
    "SplitScreen": "SplitScreen", "StatOver": "StatOver",
    "PhotoMontage": "PhotoMontagePro", "PhotoGrid": "PhotoGridPro",
}

_MEDIA_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif",
               ".mp4", ".mov", ".webm", ".m4v")


def _abs_media(obj: Any, project_path: Path) -> Any:
    """Media-path strings made absolute against the project (stage.mjs
    existence-checks every path; node's CWD is render-service/)."""
    if isinstance(obj, dict):
        return {k: _abs_media(v, project_path) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_abs_media(v, project_path) for v in obj]
    if isinstance(obj, str) and obj.lower().endswith(_MEDIA_EXTS):
        p = Path(obj)
        return str(p if p.is_absolute() else Path(project_path) / p)
    return obj


def chapter_step_for_spec(spec: Dict[str, Any], project_path: Path):
    """(block, props) hosting this spec inside a Chapter, or None.

    None = the effect is real but not chapter-hostable (python renderers and
    the preprocessing comps StillMotion/ClipMontage) — the caller falls back
    to its still treatment. An INVALID spec raises ValueError with the
    validator's problems: bad authoring is named, never silently downgraded.
    """
    from .spec import validate
    normalized, problems = validate(spec)
    if problems:
        raise ValueError(f"motion_spec invalid: {'; '.join(problems)}")
    spec = normalized

    target = spec.get("target", "")
    backend = spec.get("backend", "remotion")
    if backend == "python" or target in ("StillMotion", "ClipMontage"):
        return None

    if backend == "block":
        from nolan.layout_blocks import adapt
        template = str(spec["effect"]).replace("-", "_")
        adapted = adapt(template, {**spec.get("content", {}), **spec.get("style", {})})
        return adapted if adapted else None

    if target not in _CHAPTER_TARGETS:
        return None

    content = dict(spec.get("content", {}))
    props: Dict[str, Any] = {}
    if target == "SplitScreen":
        props = {"background": content.get("left"), "foreground": content.get("right"),
                 "leftLabel": content.get("left_label", ""),
                 "rightLabel": content.get("right_label", "")}
    elif target == "StatOver":
        media = content.pop("image", None)
        props = dict(content)
        key = "video" if str(media).lower().endswith((".mp4", ".mov", ".webm", ".m4v")) else "background"
        props[key] = media
    else:
        props = content
        props.update(spec.get("style", {}))
        if "position" in spec:
            props["position"] = normalize_position(spec["position"])
    if spec.get("accent"):
        props["accent"] = spec["accent"]

    return _CHAPTER_TARGETS[target], _abs_media(props, Path(project_path))
