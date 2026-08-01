"""Standalone artifact-first authoring pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from math_animation.bundle import (
    create_run_dir,
    sha256_json,
    utc_now,
    write_json_atomic,
)
from math_animation.cache import build_cache_report, reuse_cached_clip
from math_animation.compiler import CompilationResult, ManimCompiler
from math_animation.composer import compose_standalone
from math_animation.contracts import (
    CustomSceneBlock,
    ProjectSpec,
    RunManifest,
    SceneProgram,
)
from math_animation.handoff import write_nolan_handoff
from math_animation.math_validation import validate_math
from math_animation.pedagogy import PedagogyReport, evaluate_pedagogy
from math_animation.preflight import validate_latex, validate_local_inputs
from math_animation.renderer import ManimRenderer
from math_animation.style import StyleTokens, normalize_style
from math_animation.version import __version__


@dataclass(frozen=True)
class PipelineResult:
    run_dir: Path
    manifest: RunManifest
    compilation: CompilationResult
    final_video: Path | None
    pedagogy: PedagogyReport


def _contains_custom_python(project: ProjectSpec) -> bool:
    return any(
        isinstance(block, CustomSceneBlock)
        for beat in project.beats
        for block in beat.blocks
    )


class AuthoringPipeline:
    """Compile a typed project, optionally render clips and compose a full video."""

    def __init__(
        self,
        *,
        runs_dir: Path | str = Path("runs"),
        render_timeout_seconds: float = 1200,
        python_executable: str | Path | None = None,
    ):
        self.runs_dir = Path(runs_dir)
        # `python_executable` selects the interpreter that RENDERS. Everything
        # else in this pipeline runs in-process and needs only pydantic, so a
        # caller with a light authoring env can point this at the heavy
        # Manim/LaTeX env instead of installing it alongside.
        self.renderer = ManimRenderer(
            timeout_seconds=render_timeout_seconds,
            python_executable=python_executable,
        )

    def run(
        self,
        project: ProjectSpec,
        *,
        render: bool = False,
        compose: bool = False,
        allow_custom_python: bool = False,
        isolated_custom_renderer: bool = False,
        require_verified_math: bool = False,
        minimum_pedagogy_score: float | None = None,
        review: bool = True,
        use_cache: bool = True,
    ) -> PipelineResult:
        pipeline_started = time.perf_counter()
        performance: dict[str, object] = {
            "schema_version": "math-animation.performance.v1",
            "rendered_beats": {},
            "cache_reused_beats": [],
        }
        if compose and not render:
            raise ValueError("standalone composition requires render=True")
        if minimum_pedagogy_score is not None and not (
            0 <= minimum_pedagogy_score <= 1
        ):
            raise ValueError("minimum pedagogy score must be between 0 and 1")
        if (
            render
            and _contains_custom_python(project)
            and not isolated_custom_renderer
        ):
            raise ValueError(
                "custom Python may only render in an isolated worker; local "
                "rendering is limited to deterministic built-in blocks"
            )

        run_dir = create_run_dir(self.runs_dir, project.project_id)
        style = normalize_style(project.style)
        manifest = RunManifest(
            run_id=run_dir.name,
            project_id=project.project_id,
            status="compiling",
            created_utc=utc_now(),
            project_sha256=sha256_json(project),
            style_sha256=sha256_json(style),
            compiler_version=__version__,
            allow_custom_python=allow_custom_python,
        )
        manifest_path = run_dir / "manifest.json"
        write_json_atomic(manifest_path, manifest)
        write_json_atomic(run_dir / "project.lock.json", project)
        write_json_atomic(run_dir / "style.lock.json", style)
        schemas_dir = run_dir / "schemas"
        schemas_dir.mkdir()
        write_json_atomic(
            schemas_dir / "project.schema.json", ProjectSpec.model_json_schema()
        )
        write_json_atomic(
            schemas_dir / "scene-program.schema.json",
            SceneProgram.model_json_schema(),
        )

        compilation: CompilationResult | None = None
        final_video: Path | None = None
        pedagogy_report: PedagogyReport | None = None
        try:
            math_report = validate_math(project)
            write_json_atomic(run_dir / "math_validation.json", math_report)
            if math_report.status == "failed":
                raise ValueError(
                    "mathematical artifact validation failed: "
                    + "; ".join(math_report.errors)
                )
            if require_verified_math and math_report.status != "passed":
                raise ValueError(
                    "strict mathematical verification requested: "
                    + "; ".join(math_report.warnings)
                )
            pedagogy_report = evaluate_pedagogy(project)
            write_json_atomic(
                run_dir / "pedagogy.json",
                pedagogy_report,
            )
            if (
                minimum_pedagogy_score is not None
                and pedagogy_report.total_score < minimum_pedagogy_score
            ):
                raise ValueError(
                    "pedagogy acceptance score "
                    f"{pedagogy_report.total_score:.4f} is below required "
                    f"{minimum_pedagogy_score:.4f}"
                )
            compile_started = time.perf_counter()
            compilation = ManimCompiler(
                allow_custom_python=allow_custom_python
            ).compile(project, style, run_dir)
            performance["compile_seconds"] = time.perf_counter() - compile_started
            write_json_atomic(run_dir / "timeline.json", compilation.timeline)
            write_nolan_handoff(
                project,
                style,
                compilation.timeline,
                run_dir,
            )
            cache_report = build_cache_report(
                project,
                style,
                compilation,
                run_dir,
                self.runs_dir,
            )
            manifest.status = "compiled"
            manifest.artifacts = self._artifact_list(run_dir)
            write_json_atomic(manifest_path, manifest)

            if render:
                validate_local_inputs(project, require_audio=compose)
                latex_started = time.perf_counter()
                latex_report = validate_latex(
                    project, run_dir, self.renderer.python_executable
                )
                write_json_atomic(
                    run_dir / "preflight" / "latex-report.json",
                    latex_report,
                )
                performance["latex_preflight_seconds"] = (
                    time.perf_counter() - latex_started
                )
                manifest.status = "rendering"
                write_json_atomic(manifest_path, manifest)
                cache_entries = {
                    entry["beat_id"]: entry
                    for entry in cache_report["entries"]
                }
                for clip in compilation.timeline.clips:
                    cache_entry = cache_entries[clip.beat_id]
                    destination = run_dir / clip.expected_media_path
                    if use_cache and reuse_cached_clip(
                        cache_entry,
                        destination,
                        clip.expected_media_path,
                    ):
                        manifest.renders.append(
                            {
                                "beat_id": clip.beat_id,
                                "command": ["cache-reuse"],
                                "exit_code": 0,
                                "output_path": clip.expected_media_path,
                                "cache_hit": True,
                                "reused_from": cache_entry["reused_from"],
                            }
                        )
                        performance["cache_reused_beats"].append(clip.beat_id)
                        manifest.artifacts = self._artifact_list(run_dir)
                        write_json_atomic(manifest_path, manifest)
                        continue
                    record = self.renderer.render_clip(project, run_dir, clip)
                    performance["rendered_beats"][clip.beat_id] = (
                        record.elapsed_seconds
                    )
                    manifest.renders.append(record.to_dict())
                    manifest.artifacts = self._artifact_list(run_dir)
                    write_json_atomic(manifest_path, manifest)
                if compose:
                    compose_started = time.perf_counter()
                    final_video = compose_standalone(
                        project, style, compilation.timeline, run_dir
                    )
                    performance["compose_seconds"] = (
                        time.perf_counter() - compose_started
                    )
                if review:
                    from math_animation.review import review_rendered_project

                    review_started = time.perf_counter()
                    review_rendered_project(
                        project,
                        compilation.timeline,
                        run_dir,
                        final_video=final_video,
                    )
                    performance["review_seconds"] = (
                        time.perf_counter() - review_started
                    )

            performance["total_seconds"] = time.perf_counter() - pipeline_started
            write_json_atomic(run_dir / "performance.json", performance)
            manifest.status = "completed"
            manifest.completed_utc = utc_now()
            manifest.artifacts = self._artifact_list(run_dir)
            write_json_atomic(manifest_path, manifest)
        except Exception as exc:
            performance["total_seconds"] = time.perf_counter() - pipeline_started
            performance["failed"] = True
            write_json_atomic(run_dir / "performance.json", performance)
            manifest.status = "failed"
            manifest.error = f"{type(exc).__name__}: {exc}"
            manifest.completed_utc = utc_now()
            manifest.artifacts = self._artifact_list(run_dir)
            write_json_atomic(manifest_path, manifest)
            raise

        assert compilation is not None
        assert pedagogy_report is not None
        return PipelineResult(
            run_dir=run_dir,
            manifest=manifest,
            compilation=compilation,
            final_video=final_video,
            pedagogy=pedagogy_report,
        )

    @staticmethod
    def _artifact_list(run_dir: Path) -> list[str]:
        return sorted(
            path.relative_to(run_dir).as_posix()
            for path in run_dir.rglob("*")
            if path.is_file()
            and "_manim_media" not in path.relative_to(run_dir).parts
            and path.name != "manifest.json"
        )
