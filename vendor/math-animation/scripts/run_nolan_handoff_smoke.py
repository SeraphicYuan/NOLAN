"""Render an alpha Manim overlay beside a synthetic Nolan/GSAP asset."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from build_synthetic_algebra_fixture import build
from math_animation.bundle import write_json_atomic
from math_animation.contracts import AssetRef, RenderSettings, RequestSpec
from math_animation.pipeline import AuthoringPipeline
from math_animation.toolchain import executable_path, subprocess_environment


ROOT = Path(__file__).resolve().parents[1]


def _ensure_gsap_placeholder(path: Path) -> str:
    ffmpeg = executable_path("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x2b3440:s=640x360:r=24:d=4.9",
            "-vf",
            "drawbox=x='mod(t*90,520)':y=145:w=120:h=70:"
            "color=0xe6b85c:t=fill",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        env=subprocess_environment(),
        check=True,
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    asset_path = ROOT / "examples" / "assets" / "gsap_placeholder.mp4"
    checksum = _ensure_gsap_placeholder(asset_path)
    project = build().model_copy(deep=True)
    project.project_id = "nolan-alpha-handoff-smoke"
    project.title = "Transparent Manim overlay handoff"
    project.request = RequestSpec(
        content=(
            "Deliver one transparent Manim beat and one opaque GSAP placeholder "
            "as independently orchestratable Nolan assets."
        ),
        script_policy="locked",
        target_duration_seconds=4.9,
    )
    project.beats = [project.beats[0]]
    project.narration.utterances = [
        utterance
        for utterance in project.narration.utterances
        if utterance.id == "u1"
    ]
    project.math_ledger.formulas = [
        formula
        for formula in project.math_ledger.formulas
        if formula.id == "formula.balance"
    ]
    project.assets = [
        AssetRef(
            id="gsap.placeholder",
            path=str(asset_path),
            media_type="video",
            sha256=checksum,
            attribution="Synthetic Nolan/GSAP handoff fixture",
        )
    ]
    project.render = RenderSettings(
        renderer="cairo",
        quality="l",
        pixel_width=640,
        pixel_height=360,
        frame_rate=24,
        transparent=True,
        seed=43,
    )
    spec_path = ROOT / "examples" / "nolan_alpha_handoff_project.json"
    write_json_atomic(spec_path, project)
    result = AuthoringPipeline(
        runs_dir=Path("/tmp/math-animation-nolan-handoff"),
        render_timeout_seconds=360,
    ).run(
        project,
        render=True,
        compose=False,
        use_cache=False,
    )
    print(result.run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
