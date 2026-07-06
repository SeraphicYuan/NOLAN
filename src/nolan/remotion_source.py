"""Curated Remotion source — discover + render compositions from Python.

This is the execution bridge behind the `remotion` route in `visual_router.py`.
Compositions live in the static Remotion project at `render-service/remotion-lib/`
(see its README). Rendering shells out to `render.mjs` via Node (the deps are
Windows-built, so on this box we use Windows `node.exe`).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

LIB = Path("render-service/remotion-lib")
REGISTRY = LIB / "registry.json"


def _node() -> str:
    """Locate a Node executable (Windows node.exe on this box)."""
    for c in ("node", "node.exe"):
        p = shutil.which(c)
        if p:
            return p
    win = Path(r"C:\Program Files\nodejs\node.exe")
    if win.exists():
        return str(win)
    raise RuntimeError("Node executable not found for Remotion rendering")


def list_compositions() -> List[Dict[str, Any]]:
    """All registered compositions with their visual_type + style schema."""
    return json.loads(REGISTRY.read_text(encoding="utf-8")).get("compositions", [])


def composition_for(visual_type: str) -> Optional[Dict[str, Any]]:
    vt = (visual_type or "").lower().strip()
    for c in list_compositions():
        if c.get("visual_type") == vt:
            return c
    return None


def render(
    comp: str,
    props: Dict[str, Any],
    out_name: str,
    duration_frames: int = 120,
    video: Optional[str] = None,
    image: Optional[str] = None,
    cards: Optional[List[Dict[str, Any]]] = None,
    background: Optional[str] = None,
    foreground: Optional[str] = None,
    codec: str = "h264",
    timeout: float = 180.0,
) -> Path:
    """Render a Remotion composition to mp4 and return its path.

    `video`/`image`/`background` are image/video paths staged into public/ for
    `<OffthreadVideo>` / basemap / table-texture use. `cards` is a list of
    photo-montage card dicts whose `src` image is staged (motion/style fields kept).
    """
    job: Dict[str, Any] = {"comp": comp, "out": out_name, "durationInFrames": duration_frames,
                           "codec": codec, "props": props}
    # a flow-shaped call (props.steps) may carry the NOLAN theme inside props;
    # stage.mjs reads it from the job top level, so lift it there.
    if isinstance(props, dict) and props.get("steps") and props.get("theme"):
        job["theme"] = props.pop("theme")
    if isinstance(props, dict) and props.get("steps") and props.get("lang"):
        job["lang"] = props.pop("lang")
    if video:
        job["video"] = video
    if image:
        job["image"] = image
    if background:
        job["background"] = background
    if foreground:
        job["foreground"] = foreground
    if cards:
        job["cards"] = cards

    jobs_dir = LIB / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_path = jobs_dir / f"_auto_{Path(out_name).stem}.json"
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [_node(), "remotion-lib/render.mjs", f"remotion-lib/jobs/{job_path.name}"],
        cwd="render-service", capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Remotion render failed for {comp}: {proc.stderr[-800:] or proc.stdout[-800:]}")
    out = LIB / "output" / out_name
    if not out.exists():
        raise RuntimeError(f"Remotion render produced no output at {out}")
    return out


def render_scene(scene, out_name: str, video: Optional[str] = None, image: Optional[str] = None) -> Path:
    """Render a Scene routed to Remotion. Expects scene.remotion_comp + scene.remotion_props
    (a dict), or falls back to composition_for(scene.visual_type)."""
    comp = getattr(scene, "remotion_comp", None)
    if not comp:
        entry = composition_for(getattr(scene, "visual_type", ""))
        comp = entry["id"] if entry else None
    if not comp:
        raise ValueError(f"No Remotion composition for visual_type={getattr(scene, 'visual_type', None)!r}")
    props = getattr(scene, "remotion_props", None) or {}
    dur = int(round((getattr(scene, "end_seconds", None) or 4.0) - (getattr(scene, "start_seconds", None) or 0.0)) * 30) or 120
    return render(comp, props, out_name, duration_frames=dur, video=video, image=image)
