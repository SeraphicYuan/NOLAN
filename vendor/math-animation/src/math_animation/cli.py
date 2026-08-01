"""Command-line interface for drafting, validating, compiling, and rendering."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from math_animation.blocks import available_blocks
from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    NarrationInput,
    ProjectSpec,
    SceneProgram,
    StyleTemplateRef,
)
from math_animation.draft import draft_from_script
from math_animation.expanded_planning import (
    ExpandedPlanner,
    HeuristicExpandedDecisionProvider,
)
from math_animation.pedagogy import PedagogyReport, evaluate_pedagogy
from math_animation.pipeline import AuthoringPipeline
from math_animation.planning import (
    ConstrainedPlanner,
    HeuristicDecisionProvider,
    PlanningRequest,
)
from math_animation.renderer import manim_available
from math_animation.toolchain import executable_path, runtime_executable_path


def _read_project(path: str) -> ProjectSpec:
    return ProjectSpec.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _enforce_pedagogy_score(score: float, minimum: float | None) -> None:
    if minimum is None:
        return
    if not 0 <= minimum <= 1:
        raise ValueError("minimum pedagogy score must be between 0 and 1")
    if score < minimum:
        raise ValueError(
            f"pedagogy score {score:.4f} is below required {minimum:.4f}"
        )


def _cmd_validate(args: argparse.Namespace) -> int:
    project = _read_project(args.project)
    print(
        f"valid project: {project.project_id} "
        f"({len(project.beats)} beat{'s' if len(project.beats) != 1 else ''})"
    )
    return 0


def _cmd_draft(args: argparse.Namespace) -> int:
    script = Path(args.script).read_text(encoding="utf-8")
    project = draft_from_script(
        script,
        project_id=args.project_id,
        title=args.title,
        audience=args.audience,
    )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(destination, project)
    print(f"drafted review project -> {destination}")
    return 0


def _cmd_compile(args: argparse.Namespace) -> int:
    project = _read_project(args.project)
    result = AuthoringPipeline(
        runs_dir=args.runs_dir,
        render_timeout_seconds=args.render_timeout,
    ).run(
        project,
        render=args.render,
        compose=args.compose,
        allow_custom_python=args.allow_custom_python,
        isolated_custom_renderer=args.isolated_custom_renderer,
        require_verified_math=args.require_verified_math,
        minimum_pedagogy_score=args.minimum_pedagogy_score,
        review=not args.skip_review,
        use_cache=not args.no_cache,
    )
    print(f"{result.manifest.status} -> {result.run_dir}")
    if result.final_video:
        print(f"video -> {result.final_video}")
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    if args.compose and not args.render:
        raise ValueError("--compose requires --render")
    script = Path(args.script).read_text(encoding="utf-8")
    narration = (
        NarrationInput.model_validate_json(
            Path(args.narration).read_text(encoding="utf-8")
        )
        if args.narration
        else NarrationInput()
    )
    if args.style:
        style_payload = json.loads(Path(args.style).read_text(encoding="utf-8"))
        style = (
            StyleTemplateRef.model_validate(style_payload)
            if "raw" in style_payload
            else StyleTemplateRef(raw=style_payload)
        )
    else:
        style = StyleTemplateRef()
    provider = _decision_provider(args.provider, args.model)
    result = ConstrainedPlanner(provider).plan(
        PlanningRequest(
            project_id=args.project_id,
            title=args.title,
            script=script,
            audience=args.audience,
            narration=narration,
            style=style,
        )
    )
    destination = Path(args.output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    write_json_atomic(destination / "planning.json", result.artifact)
    if hasattr(provider, "write_audit"):
        provider.write_audit(destination / "model-calls.json")
    project_path = destination / "project.json"
    write_json_atomic(project_path, result.project)
    pedagogy = evaluate_pedagogy(result.project)
    write_json_atomic(destination / "pedagogy.json", pedagogy)
    print(f"planned typed project -> {project_path}")
    print(f"planning evidence -> {destination / 'planning.json'}")
    print(f"pedagogy -> {pedagogy.status} ({pedagogy.total_score:.4f})")
    _enforce_pedagogy_score(
        pedagogy.total_score,
        args.minimum_pedagogy_score,
    )
    if args.render or args.compile:
        pipeline_result = AuthoringPipeline(
            runs_dir=args.runs_dir,
            render_timeout_seconds=args.render_timeout,
        ).run(
            result.project,
            render=args.render,
            compose=args.compose,
            minimum_pedagogy_score=args.minimum_pedagogy_score,
        )
        print(f"{pipeline_result.manifest.status} -> {pipeline_result.run_dir}")
        if pipeline_result.final_video:
            print(f"video -> {pipeline_result.final_video}")
    return 0


def _cmd_plan_expanded(args: argparse.Namespace) -> int:
    if args.compose and not args.render:
        raise ValueError("--compose requires --render")
    script = Path(args.script).read_text(encoding="utf-8")
    narration = (
        NarrationInput.model_validate_json(
            Path(args.narration).read_text(encoding="utf-8")
        )
        if args.narration
        else NarrationInput()
    )
    if args.style:
        style_payload = json.loads(Path(args.style).read_text(encoding="utf-8"))
        style = (
            StyleTemplateRef.model_validate(style_payload)
            if "raw" in style_payload
            else StyleTemplateRef(raw=style_payload)
        )
    else:
        style = StyleTemplateRef()
    provider = _expanded_decision_provider(args.provider, args.model)
    result = ExpandedPlanner(provider).plan(
        PlanningRequest(
            project_id=args.project_id,
            title=args.title,
            script=script,
            audience=args.audience,
            narration=narration,
            style=style,
        )
    )
    destination = Path(args.output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    write_json_atomic(destination / "expanded-planning.json", result.artifact)
    if hasattr(provider, "write_audit"):
        provider.write_audit(destination / "expanded-model-calls.json")
    project_path = destination / "project.json"
    write_json_atomic(project_path, result.project)
    pedagogy = evaluate_pedagogy(result.project)
    write_json_atomic(destination / "pedagogy.json", pedagogy)
    print(f"planned expanded typed project -> {project_path}")
    print(
        "expanded planning evidence -> "
        f"{destination / 'expanded-planning.json'}"
    )
    print(
        f"pedagogy -> {pedagogy.status} ({pedagogy.total_score:.4f})"
    )
    _enforce_pedagogy_score(
        pedagogy.total_score,
        args.minimum_pedagogy_score,
    )
    if args.render or args.compile:
        pipeline_result = AuthoringPipeline(
            runs_dir=args.runs_dir,
            render_timeout_seconds=args.render_timeout,
        ).run(
            result.project,
            render=args.render,
            compose=args.compose,
            minimum_pedagogy_score=args.minimum_pedagogy_score,
        )
        print(f"{pipeline_result.manifest.status} -> {pipeline_result.run_dir}")
        if pipeline_result.final_video:
            print(f"video -> {pipeline_result.final_video}")
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    report = evaluate_pedagogy(_read_project(args.project))
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(destination, report)
        print(f"pedagogy report -> {destination}")
    else:
        print(report.model_dump_json(indent=2))
    _enforce_pedagogy_score(report.total_score, args.minimum_score)
    return 0


def _cmd_repair(args: argparse.Namespace) -> int:
    # imported here, not at module scope: the repair workflow is the only
    # command needing the optional LangGraph extra, and every OTHER command
    # must stay usable in an env that does not carry it.
    from math_animation.workflow import BoundedRepairWorkflow

    project = _read_project(args.project)
    provider = _decision_provider(
        args.regeneration_provider,
        args.model,
        allow_none=True,
    )
    result = BoundedRepairWorkflow(
        runs_dir=args.runs_dir,
        render_timeout_seconds=args.render_timeout,
        regeneration_provider=provider,
    ).run(
        project,
        render=args.render,
        compose=args.compose,
        use_cache=not args.no_cache,
    )
    print(f"{result.status} -> {result.session_dir}")
    print(f"pipeline attempts: {result.pipeline_attempts}")
    if result.pipeline_result and result.pipeline_result.final_video:
        print(f"video -> {result.pipeline_result.final_video}")
    return 0 if result.status in {"completed", "completed_with_warnings"} else 2


def _decision_provider(
    provider: str,
    model: str | None,
    *,
    allow_none: bool = False,
):
    if provider == "none" and allow_none:
        return None
    if provider == "heuristic":
        return HeuristicDecisionProvider()
    if provider == "openai":
        if not model:
            raise ValueError("--model is required with the OpenAI provider")
        from math_animation.model_provider import (
            ModelProviderConfig,
            OpenAIResponsesDecisionProvider,
        )

        return OpenAIResponsesDecisionProvider(
            ModelProviderConfig(model=model)
        )
    raise ValueError(f"unsupported decision provider: {provider!r}")


def _expanded_decision_provider(provider: str, model: str | None):
    if provider == "heuristic":
        return HeuristicExpandedDecisionProvider()
    if provider == "openai":
        if not model:
            raise ValueError("--model is required with the OpenAI provider")
        from math_animation.expanded_model_provider import (
            OpenAIExpandedDecisionProvider,
        )
        from math_animation.model_provider import ModelProviderConfig

        return OpenAIExpandedDecisionProvider(
            ModelProviderConfig(model=model)
        )
    raise ValueError(f"unsupported expanded decision provider: {provider!r}")


def _cmd_blocks(_: argparse.Namespace) -> int:
    for name in available_blocks():
        print(name)
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    if args.kind == "project":
        model = ProjectSpec
    elif args.kind == "scene-program":
        model = SceneProgram
    elif args.kind == "expanded-decision":
        from math_animation.expanded_planning import ExpandedVisualDecision

        model = ExpandedVisualDecision
    else:
        model = PedagogyReport
    payload = model.model_json_schema()
    if args.output:
        write_json_atomic(Path(args.output), payload)
        print(f"schema -> {args.output}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


def _cmd_doctor(_: argparse.Namespace) -> int:
    checks = {
        "python": sys.executable,
        "manim": "available" if manim_available() else "missing",
        "ffmpeg": executable_path("ffmpeg") or "missing",
        "latex": runtime_executable_path("latex") or "missing",
        "dvisvgm": runtime_executable_path("dvisvgm") or "missing",
    }
    for name, value in checks.items():
        print(f"{name}: {value}")
    return 0 if all(value != "missing" for value in checks.values()) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="math-animation",
        description="Artifact-first mathematical animation authoring.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a project JSON file")
    validate.add_argument("project")
    validate.set_defaults(handler=_cmd_validate)

    draft = subparsers.add_parser(
        "draft", help="Create a conservative review project from a script"
    )
    draft.add_argument("script")
    draft.add_argument("--project-id", required=True)
    draft.add_argument("--title", required=True)
    draft.add_argument("--audience", default="general")
    draft.add_argument("-o", "--output", required=True)
    draft.set_defaults(handler=_cmd_draft)

    plan = subparsers.add_parser(
        "plan",
        help="Plan a script into constrained typed animation templates",
    )
    plan.add_argument("script")
    plan.add_argument("--project-id", required=True)
    plan.add_argument("--title", required=True)
    plan.add_argument("--audience", default="general")
    plan.add_argument("--narration", help="NarrationInput JSON with word timings")
    plan.add_argument("--style", help="StyleTemplateRef or raw style JSON")
    plan.add_argument("--output-dir", required=True)
    plan.add_argument("--compile", action="store_true")
    plan.add_argument("--render", action="store_true")
    plan.add_argument("--compose", action="store_true")
    plan.add_argument("--runs-dir", default="runs")
    plan.add_argument("--render-timeout", type=float, default=1200)
    plan.add_argument(
        "--provider",
        choices=("heuristic", "openai"),
        default="heuristic",
        help="Constrained visual-decision provider",
    )
    plan.add_argument(
        "--model",
        help="Model ID required when --provider=openai",
    )
    plan.add_argument("--minimum-pedagogy-score", type=float)
    plan.set_defaults(handler=_cmd_plan)

    expanded_plan = subparsers.add_parser(
        "plan-expanded",
        help="Plan with typed multi-step templates and pedagogy evidence",
    )
    expanded_plan.add_argument("script")
    expanded_plan.add_argument("--project-id", required=True)
    expanded_plan.add_argument("--title", required=True)
    expanded_plan.add_argument("--audience", default="general")
    expanded_plan.add_argument(
        "--narration",
        help="NarrationInput JSON with word timings",
    )
    expanded_plan.add_argument(
        "--style",
        help="StyleTemplateRef or raw style JSON",
    )
    expanded_plan.add_argument("--output-dir", required=True)
    expanded_plan.add_argument("--compile", action="store_true")
    expanded_plan.add_argument("--render", action="store_true")
    expanded_plan.add_argument("--compose", action="store_true")
    expanded_plan.add_argument("--runs-dir", default="runs")
    expanded_plan.add_argument("--render-timeout", type=float, default=1200)
    expanded_plan.add_argument(
        "--provider",
        choices=("heuristic", "openai"),
        default="heuristic",
        help="Expanded structured visual-decision provider",
    )
    expanded_plan.add_argument(
        "--model",
        help="Model ID required when --provider=openai",
    )
    expanded_plan.add_argument("--minimum-pedagogy-score", type=float)
    expanded_plan.set_defaults(handler=_cmd_plan_expanded)

    compile_parser = subparsers.add_parser(
        "compile", help="Compile a project into a run bundle"
    )
    compile_parser.add_argument("project")
    compile_parser.add_argument("--runs-dir", default="runs")
    compile_parser.add_argument("--render", action="store_true")
    compile_parser.add_argument("--compose", action="store_true")
    compile_parser.add_argument("--render-timeout", type=float, default=1200)
    compile_parser.add_argument(
        "--skip-review",
        action="store_true",
        help="Skip automatic post-render frame and decoder review",
    )
    compile_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Render every beat even when an identical cached clip exists",
    )
    compile_parser.add_argument("--allow-custom-python", action="store_true")
    compile_parser.add_argument(
        "--require-verified-math",
        action="store_true",
        help="Fail when any mathematical claim remains marked needs_review",
    )
    compile_parser.add_argument(
        "--minimum-pedagogy-score",
        type=float,
        help="Fail before rendering when the structural score is below this",
    )
    compile_parser.add_argument(
        "--isolated-custom-renderer",
        action="store_true",
        help="Assert that the caller has supplied a real isolated render worker",
    )
    compile_parser.set_defaults(handler=_cmd_compile)

    repair = subparsers.add_parser(
        "repair",
        help="Audit and run a bounded typed repair workflow",
    )
    repair.add_argument("project")
    repair.add_argument("--runs-dir", default="runs")
    repair.add_argument("--render", action="store_true")
    repair.add_argument("--compose", action="store_true")
    repair.add_argument("--render-timeout", type=float, default=1200)
    repair.add_argument(
        "--no-cache",
        action="store_true",
        help="Render every beat instead of reusing unchanged clips",
    )
    repair.add_argument(
        "--regeneration-provider",
        choices=("none", "openai"),
        default="none",
        help="Optional provider for typed beat regeneration",
    )
    repair.add_argument(
        "--model",
        help="Model ID required with --regeneration-provider=openai",
    )
    repair.set_defaults(handler=_cmd_repair)

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Evaluate structural pedagogy and optionally enforce a threshold",
    )
    evaluate.add_argument("project")
    evaluate.add_argument("-o", "--output")
    evaluate.add_argument("--minimum-score", type=float)
    evaluate.set_defaults(handler=_cmd_evaluate)

    blocks = subparsers.add_parser("blocks", help="List deterministic Manim blocks")
    blocks.set_defaults(handler=_cmd_blocks)

    schema = subparsers.add_parser(
        "schema", help="Print or write a public JSON Schema"
    )
    schema.add_argument(
        "--kind",
        choices=(
            "project",
            "scene-program",
            "expanded-decision",
            "pedagogy-report",
        ),
        default="project",
    )
    schema.add_argument("-o", "--output")
    schema.set_defaults(handler=_cmd_schema)

    doctor = subparsers.add_parser("doctor", help="Check the local render toolchain")
    doctor.set_defaults(handler=_cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, RuntimeError, ValueError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
