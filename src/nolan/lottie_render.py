"""Render Lottie animations to MP4 (reintroduced into the unified core after P4).

Lottie→video has no local Python renderer here, so it goes through the node
render-service (the `lottie` engine). This module is the single "call Lottie" entry
point: a `render_one` branch (scenes with `lottie_asset`/`lottie_template`), a
reusable `render_lottie_to_mp4`, and the `nolan render-lottie` CLI.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

DEFAULT_SERVICE = "http://127.0.0.1:3010"


def _field(scene, key, default=None):
    return scene.get(key, default) if isinstance(scene, dict) else getattr(scene, key, default)


def render_lottie_to_mp4(lottie_json, out_path, *, service_url: str = DEFAULT_SERVICE,
                         width: int = 1920, height: int = 1080, fps: int = 30,
                         duration: float = 5.0, timeout: float = 180.0) -> Path:
    """Render a Lottie JSON file to MP4 via the render-service. Raises on failure.

    Uses the render-service's async job API: POST /render (remotion engine,
    data.lottie_path) → poll /render/status/:id → GET /render/result/:id.
    """
    import time

    import httpx

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lottie_abs = str(Path(lottie_json).resolve())
    with httpx.Client(timeout=60.0) as c:
        try:
            if c.get(f"{service_url}/health").status_code != 200:
                raise RuntimeError(f"render-service unhealthy at {service_url}")
        except httpx.HTTPError as e:
            raise RuntimeError(f"render-service not reachable at {service_url}: {e}")
        resp = c.post(f"{service_url}/render", json={
            "engine": "remotion",
            "data": {"lottie_path": lottie_abs, "fps": fps},
            "width": width, "height": height, "duration": duration,
        })
        resp.raise_for_status()
        job_id = resp.json().get("job_id")
        if not job_id:
            raise RuntimeError(f"render-service returned no job_id: {resp.text[:200]}")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            st = c.get(f"{service_url}/render/status/{job_id}").json()
            status = st.get("status")
            if status == "done":
                break
            if status in ("error", "failed"):
                raise RuntimeError(f"render-service job failed: {st.get('error')}")
            time.sleep(1.0)
        else:
            raise RuntimeError("render-service job timed out")
        vp = c.get(f"{service_url}/render/result/{job_id}").json().get("video_path")
    if not vp or not Path(vp).exists():
        raise RuntimeError("render-service produced no video file")
    shutil.copy(vp, out_path)
    return out_path


def prepare_lottie(template_path, out_json, config: Optional[dict] = None) -> Path:
    """Customize a Lottie template into a ready-to-render JSON from a lottie_config
    ({text:{old:new}, colors:{#a:#b}, duration, fps, width, height})."""
    from nolan.lottie import customize_lottie
    cfg = config or {}
    customize_lottie(
        template_path, out_json,
        text_replacements=cfg.get("text"),
        color_map=cfg.get("colors"),
        duration_seconds=cfg.get("duration"),
        fps=cfg.get("fps"), width=cfg.get("width"), height=cfg.get("height"),
    )
    return Path(out_json)


def render_lottie_for_scene(scene, out, *, duration: float, width: int = 1920,
                            height: int = 1080, fps: int = 30,
                            service_url: str = DEFAULT_SERVICE,
                            project_root: Optional[Path] = None,
                            work_dir: Optional[Path] = None) -> bool:
    """Render a scene's Lottie to ``out``. Uses ``lottie_asset`` (a prepared JSON)
    or customizes ``lottie_template`` with ``lottie_config``. Returns success."""
    out = Path(out)
    sid = _field(scene, "id", "scene")
    lottie_json: Optional[Path] = None

    asset = _field(scene, "lottie_asset")
    if asset:
        p = Path(asset)
        if not p.exists() and project_root:
            p = Path(project_root) / asset
        if p.exists():
            lottie_json = p

    if lottie_json is None:
        tmpl = _field(scene, "lottie_template")
        if tmpl and Path(tmpl).exists():
            wd = Path(work_dir or out.parent)
            wd.mkdir(parents=True, exist_ok=True)
            try:
                lottie_json = prepare_lottie(tmpl, wd / f"{sid}.lottie.json",
                                             _field(scene, "lottie_config"))
            except Exception:
                return False

    if lottie_json is None:
        return False
    try:
        render_lottie_to_mp4(lottie_json, out, service_url=service_url, width=width,
                             height=height, fps=fps, duration=duration)
        return True
    except Exception:
        return False
