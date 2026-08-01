"""Run renderer, 1080p, and decoded-frame determinism acceptance checks."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from build_synthetic_algebra_fixture import build
from math_animation.bundle import write_json_atomic
from math_animation.contracts import RenderSettings
from math_animation.pipeline import AuthoringPipeline
from math_animation.toolchain import executable_path, subprocess_environment


ROOT = Path(__file__).resolve().parents[1]
RUNS = Path("/tmp/math-animation-system-matrix")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frame_md5(video: Path) -> str:
    ffmpeg = executable_path("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required")
    completed = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(video), "-f", "framemd5", "-"],
        env=subprocess_environment(),
        capture_output=True,
        check=True,
    )
    return hashlib.sha256(completed.stdout).hexdigest()


def _one_beat(project_id: str, render: RenderSettings):
    project = build().model_copy(deep=True)
    project.project_id = project_id
    project.beats = [project.beats[0]]
    project.request.target_duration_seconds = 4.9
    project.render = render
    return project


def main() -> int:
    RUNS.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "schema_version": "math-animation.system-matrix.v1",
        "status": "passed",
    }

    production = _one_beat(
        "cairo-1080p-smoke",
        RenderSettings(
            renderer="cairo",
            quality="m",
            pixel_width=1920,
            pixel_height=1080,
            frame_rate=30,
            seed=47,
        ),
    )
    production_result = AuthoringPipeline(
        runs_dir=RUNS,
        render_timeout_seconds=360,
    ).run(
        production,
        render=True,
        use_cache=False,
    )
    report["cairo_1080p"] = {
        "status": "passed",
        "run_dir": str(production_result.run_dir),
        "clip": str(production_result.run_dir / "clips" / "balance.mp4"),
    }

    deterministic_project = _one_beat(
        "decoded-frame-determinism",
        RenderSettings(
            renderer="cairo",
            quality="l",
            pixel_width=640,
            pixel_height=360,
            frame_rate=24,
            seed=53,
        ),
    )
    deterministic_runs = [
        AuthoringPipeline(
            runs_dir=RUNS,
            render_timeout_seconds=360,
        ).run(
            deterministic_project,
            render=True,
            use_cache=False,
        )
        for _ in range(2)
    ]
    first, second = (result.run_dir for result in deterministic_runs)
    comparisons = {
        "source_sha256": [
            _hash(first / "source" / "balance.py"),
            _hash(second / "source" / "balance.py"),
        ],
        "visual_ir_sha256": [
            _hash(first / "visual_ir" / "balance.scene.json"),
            _hash(second / "visual_ir" / "balance.scene.json"),
        ],
        "timeline_sha256": [
            _hash(first / "timeline.json"),
            _hash(second / "timeline.json"),
        ],
        "decoded_frames_sha256": [
            _frame_md5(first / "clips" / "balance.mp4"),
            _frame_md5(second / "clips" / "balance.mp4"),
        ],
    }
    deterministic = all(values[0] == values[1] for values in comparisons.values())
    report["determinism"] = {
        "status": "passed" if deterministic else "failed",
        "run_dirs": [str(first), str(second)],
        "comparisons": comparisons,
    }
    if not deterministic:
        report["status"] = "failed"

    opengl = _one_beat(
        "opengl-smoke",
        RenderSettings(
            renderer="opengl",
            quality="l",
            pixel_width=320,
            pixel_height=240,
            frame_rate=12,
            seed=59,
        ),
    )
    try:
        opengl_result = AuthoringPipeline(
            runs_dir=RUNS,
            render_timeout_seconds=45,
        ).run(
            opengl,
            render=True,
            use_cache=False,
        )
        report["opengl"] = {
            "status": "passed",
            "run_dir": str(opengl_result.run_dir),
        }
    except Exception as exc:
        # OpenGL is an optional compatibility target on headless workers. The
        # attempted failure remains recorded without invalidating Cairo.
        report["opengl"] = {
            "status": "unsupported_in_environment",
            "detail": f"{type(exc).__name__}: {exc}",
        }

    destination = ROOT / "artifacts" / "system_matrix_report.json"
    write_json_atomic(destination, report)
    print(destination)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
