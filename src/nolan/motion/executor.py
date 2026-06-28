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


def render(spec: Dict[str, Any], out_path) -> Path:
    """Render a *validated* spec to out_path (mp4)."""
    out_path = Path(out_path)
    if spec.get("backend") == "python":
        return _render_python(spec, out_path)
    return _render_remotion(spec, out_path)
