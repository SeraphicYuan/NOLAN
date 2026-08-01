"""Minimal LangGraph orchestration for bounded typed repair attempts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

# LangGraph is imported LAZILY, inside `_build_graph`. It is an optional extra
# (`.[workflow]`), but `RepairPolicy` below is a plain pydantic model that the
# frozen v0.5 golden-hash gate must be able to check anywhere. A module-level
# import made a schema-compatibility test depend on a graph runtime it never
# touches — see CLAUDE.md.

from math_animation.bundle import (
    create_run_dir,
    sha256_json,
    write_json_atomic,
)
from math_animation.contracts import ProjectSpec, StrictModel
from math_animation.pipeline import AuthoringPipeline, PipelineResult
from math_animation.planning import VisualDecisionProvider
from math_animation.regeneration import generate_regeneration_artifacts
from math_animation.repair import (
    Diagnostic,
    RepairPlan,
    analyze_project,
    apply_repair_plan,
    build_repair_plan,
    classify_exception,
)


class RepairPolicy(StrictModel):
    schema_version: Literal["math-animation.repair-policy.v1"] = (
        "math-animation.repair-policy.v1"
    )
    maximum_pipeline_attempts: int = 2
    maximum_repair_passes: int = 2
    repair_warnings: bool = True


class RepairWorkflowState(TypedDict, total=False):
    """Graph state contains references and control data, never mutable IR."""

    session_dir: str
    project_path: str
    status: str
    pipeline_attempt: int
    repair_pass: int
    diagnostics_path: str
    diagnostic_ids: list[str]
    last_run_dir: str
    final_video: str


@dataclass(frozen=True)
class RepairWorkflowResult:
    session_dir: Path
    status: Literal["completed", "completed_with_warnings", "refused", "failed"]
    project: ProjectSpec
    pipeline_result: PipelineResult | None
    diagnostics: tuple[Diagnostic, ...]
    repair_plans: tuple[RepairPlan, ...]
    pipeline_attempts: int


def _read_project(path: str) -> ProjectSpec:
    return ProjectSpec.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _read_diagnostics(path: str | None) -> list[Diagnostic]:
    if not path:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        Diagnostic.model_validate(item)
        for item in payload.get("diagnostics", [])
    ]


def _blocking(
    diagnostics: list[Diagnostic],
    *,
    repair_warnings: bool,
    regeneration_enabled: bool = False,
) -> list[Diagnostic]:
    return [
        item
        for item in diagnostics
        if item.severity in {"error", "refusal"}
        or (
            repair_warnings
            and item.severity == "warning"
            and (
                item.repairable
                or (
                    regeneration_enabled
                    and item.beat_id is not None
                    and "regenerate_beat" in item.suggested_repairs
                )
            )
        )
    ]


class BoundedRepairWorkflow:
    """Audit, repair, render, and review with at most two scoped attempts."""

    def __init__(
        self,
        *,
        runs_dir: Path | str = Path("runs"),
        render_timeout_seconds: float = 1200,
        policy: RepairPolicy | None = None,
        regeneration_provider: VisualDecisionProvider | None = None,
    ):
        self.runs_dir = Path(runs_dir)
        self.render_timeout_seconds = render_timeout_seconds
        self.policy = policy or RepairPolicy()
        self.regeneration_provider = regeneration_provider
        self._render = False
        self._compose = False
        self._use_cache = True
        self._last_pipeline_result: PipelineResult | None = None
        self._graph = self._build_graph()

    def _build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except ModuleNotFoundError as exc:  # pragma: no cover - env-dependent
            raise ModuleNotFoundError(
                "BoundedRepairWorkflow needs the optional LangGraph control "
                "plane: pip install -e '.[workflow]'"
            ) from exc
        graph = StateGraph(RepairWorkflowState)
        graph.add_node("audit", self._audit_node)
        graph.add_node("repair", self._repair_node)
        graph.add_node("execute", self._execute_node)
        graph.add_node("review", self._review_node)
        graph.add_node("finish", self._finish_node)
        graph.add_edge(START, "audit")
        graph.add_conditional_edges(
            "audit",
            self._route_after_audit,
            {"repair": "repair", "execute": "execute", "finish": "finish"},
        )
        graph.add_conditional_edges(
            "repair",
            self._route_after_repair,
            {"audit": "audit", "finish": "finish"},
        )
        graph.add_conditional_edges(
            "execute",
            self._route_after_execute,
            {"review": "review", "repair": "repair", "finish": "finish"},
        )
        graph.add_conditional_edges(
            "review",
            self._route_after_review,
            {"repair": "repair", "finish": "finish"},
        )
        graph.add_edge("finish", END)
        return graph.compile()

    def run(
        self,
        project: ProjectSpec,
        *,
        render: bool = False,
        compose: bool = False,
        use_cache: bool = True,
    ) -> RepairWorkflowResult:
        if compose and not render:
            raise ValueError("standalone composition requires render=True")
        self._render = render
        self._compose = compose
        self._use_cache = use_cache
        self._last_pipeline_result = None
        session_dir = create_run_dir(
            self.runs_dir,
            f"{project.project_id}-repair",
        )
        original_path = session_dir / "project.original.json"
        write_json_atomic(original_path, project)
        write_json_atomic(session_dir / "policy.json", self.policy)
        initial: RepairWorkflowState = {
            "session_dir": str(session_dir),
            "project_path": str(original_path),
            "status": "started",
            "pipeline_attempt": 0,
            "repair_pass": 0,
            "diagnostic_ids": [],
        }
        final_state = self._graph.invoke(
            initial,
            config={"recursion_limit": 24},
        )
        write_json_atomic(session_dir / "graph-state.json", final_state)
        if (
            self.regeneration_provider is not None
            and hasattr(self.regeneration_provider, "write_audit")
        ):
            self.regeneration_provider.write_audit(
                session_dir / "model-calls.json"
            )
        diagnostics = _read_diagnostics(final_state.get("diagnostics_path"))
        plans = tuple(
            RepairPlan.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted((session_dir / "repairs").glob("*.plan.json"))
        ) if (session_dir / "repairs").is_dir() else ()
        result = RepairWorkflowResult(
            session_dir=session_dir,
            status=final_state["status"],
            project=_read_project(final_state["project_path"]),
            pipeline_result=self._last_pipeline_result,
            diagnostics=tuple(diagnostics),
            repair_plans=plans,
            pipeline_attempts=final_state.get("pipeline_attempt", 0),
        )
        write_json_atomic(
            session_dir / "summary.json",
            {
                "schema_version": "math-animation.repair-run.v1",
                "status": result.status,
                "pipeline_attempts": result.pipeline_attempts,
                "repair_passes": final_state.get("repair_pass", 0),
                "original_project_sha256": sha256_json(project),
                "final_project_sha256": sha256_json(result.project),
                "diagnostic_ids": [
                    diagnostic.id for diagnostic in result.diagnostics
                ],
                "repair_plan_paths": [
                    path.relative_to(session_dir).as_posix()
                    for path in sorted((session_dir / "repairs").glob("*.plan.json"))
                ] if (session_dir / "repairs").is_dir() else [],
                "regeneration_artifact_paths": [
                    path.relative_to(session_dir).as_posix()
                    for path in sorted(
                        (session_dir / "repairs").glob(
                            "*.regenerations.json"
                        )
                    )
                ] if (session_dir / "repairs").is_dir() else [],
                "model_calls_path": (
                    "model-calls.json"
                    if (session_dir / "model-calls.json").is_file()
                    else None
                ),
                "last_run_dir": final_state.get("last_run_dir"),
                "final_video": final_state.get("final_video"),
            },
        )
        return result

    def _write_diagnostics(
        self,
        state: RepairWorkflowState,
        diagnostics: list[Diagnostic],
        *,
        label: str,
    ) -> RepairWorkflowState:
        root = Path(state["session_dir"]) / "diagnostics"
        root.mkdir(parents=True, exist_ok=True)
        sequence = len(list(root.glob("*.json"))) + 1
        destination = root / f"{sequence:02d}-{label}.json"
        write_json_atomic(
            destination,
            {
                "schema_version": "math-animation.diagnostic-set.v1",
                "diagnostics": [
                    item.model_dump(mode="json") for item in diagnostics
                ],
            },
        )
        return {
            "diagnostics_path": str(destination),
            "diagnostic_ids": [item.id for item in diagnostics],
        }

    def _audit_node(self, state: RepairWorkflowState) -> RepairWorkflowState:
        diagnostics = analyze_project(_read_project(state["project_path"]))
        update = self._write_diagnostics(state, diagnostics, label="audit")
        return {**update, "status": "audited"}

    def _route_after_audit(self, state: RepairWorkflowState) -> str:
        diagnostics = _read_diagnostics(state.get("diagnostics_path"))
        blockers = _blocking(
            diagnostics,
            repair_warnings=self.policy.repair_warnings,
            regeneration_enabled=self.regeneration_provider is not None,
        )
        if any(item.severity == "refusal" for item in blockers):
            return "finish"
        if any(item.repairable for item in blockers):
            if state.get("repair_pass", 0) < self.policy.maximum_repair_passes:
                return "repair"
            return "finish"
        if any(item.severity == "error" for item in blockers):
            return "finish"
        return "execute"

    def _repair_node(self, state: RepairWorkflowState) -> RepairWorkflowState:
        project = _read_project(state["project_path"])
        diagnostics = _read_diagnostics(state.get("diagnostics_path"))
        plan = build_repair_plan(
            project,
            diagnostics,
            enable_regeneration=self.regeneration_provider is not None,
        )
        repair_pass = state.get("repair_pass", 0) + 1
        root = Path(state["session_dir"]) / "repairs"
        root.mkdir(parents=True, exist_ok=True)
        plan_path = root / f"{repair_pass:02d}.plan.json"
        write_json_atomic(plan_path, plan)
        if not plan.operations:
            return {"repair_pass": repair_pass, "status": "repair_blocked"}
        regenerations = []
        if any(
            operation.type == "regenerate_beat"
            for operation in plan.operations
        ):
            if self.regeneration_provider is None:
                return {
                    "repair_pass": repair_pass,
                    "status": "repair_blocked",
                }
            try:
                regenerations = generate_regeneration_artifacts(
                    project,
                    plan,
                    diagnostics,
                    self.regeneration_provider,
                )
            except Exception as exc:
                update = self._write_diagnostics(
                    state,
                    [classify_exception(exc)],
                    label=f"repair-{repair_pass:02d}-provider-failure",
                )
                return {
                    **update,
                    "repair_pass": repair_pass,
                    "status": "repair_blocked",
                }
            write_json_atomic(
                root / f"{repair_pass:02d}.regenerations.json",
                {
                    "schema_version": (
                        "math-animation.regeneration-set.v1"
                    ),
                    "artifacts": [
                        artifact.model_dump(mode="json")
                        for artifact in regenerations
                    ],
                },
            )
        repaired = apply_repair_plan(
            project,
            plan,
            regenerations=regenerations,
        )
        repaired_path = root / f"{repair_pass:02d}.project.json"
        write_json_atomic(repaired_path, repaired)
        before = {
            beat.id: sha256_json(beat)
            for beat in project.beats
        }
        after = {
            beat.id: sha256_json(beat)
            for beat in repaired.beats
        }
        changed = sorted(
            beat_id
            for beat_id in before
            if before[beat_id] != after[beat_id]
        )
        if changed != plan.affected_beat_ids:
            raise RuntimeError(
                "typed repair changed beats outside its declared scope"
            )
        write_json_atomic(
            root / f"{repair_pass:02d}.diff.json",
            {
                "schema_version": "math-animation.repair-diff.v1",
                "before_project_sha256": sha256_json(project),
                "after_project_sha256": sha256_json(repaired),
                "changed_beat_ids": changed,
                "unchanged_beat_ids": sorted(set(before) - set(changed)),
                "before_beat_sha256": before,
                "after_beat_sha256": after,
            },
        )
        return {
            "project_path": str(repaired_path),
            "repair_pass": repair_pass,
            "status": "repaired",
        }

    @staticmethod
    def _route_after_repair(state: RepairWorkflowState) -> str:
        return "audit" if state.get("status") == "repaired" else "finish"

    def _execute_node(self, state: RepairWorkflowState) -> RepairWorkflowState:
        attempt = state.get("pipeline_attempt", 0) + 1
        # All attempts share one cache root. The content-addressed beat hashes
        # still prevent cross-project reuse, while unaffected beats survive a
        # scoped repair retry.
        attempt_root = self.runs_dir / "pipeline-runs"
        before = set(attempt_root.iterdir()) if attempt_root.is_dir() else set()
        pipeline = AuthoringPipeline(
            runs_dir=attempt_root,
            render_timeout_seconds=self.render_timeout_seconds,
        )
        try:
            result = pipeline.run(
                _read_project(state["project_path"]),
                render=self._render,
                compose=self._compose,
                review=True,
                use_cache=self._use_cache,
            )
        except Exception as exc:
            candidates = sorted(
                (
                    path
                    for path in attempt_root.glob("*")
                    if path.is_dir() and path not in before
                ),
                reverse=True,
            )
            run_dir = candidates[0] if candidates else None
            report_path = run_dir / "review" / "report.json" if run_dir else None
            if report_path is not None and report_path.is_file():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                diagnostics = [
                    Diagnostic.model_validate(item)
                    for item in report.get("diagnostics", [])
                ]
            else:
                diagnostics = [classify_exception(exc)]
            update = self._write_diagnostics(
                state,
                diagnostics,
                label=f"attempt-{attempt:02d}-failure",
            )
            return {
                **update,
                "pipeline_attempt": attempt,
                "last_run_dir": str(run_dir) if run_dir else "",
                "status": "pipeline_failed",
            }
        self._last_pipeline_result = result
        return {
            "pipeline_attempt": attempt,
            "last_run_dir": str(result.run_dir),
            "final_video": str(result.final_video) if result.final_video else "",
            "status": "rendered" if self._render else "compiled",
        }

    def _route_after_execute(self, state: RepairWorkflowState) -> str:
        if state["status"] != "pipeline_failed":
            return "review"
        diagnostics = _read_diagnostics(state.get("diagnostics_path"))
        if (
            state.get("pipeline_attempt", 0)
            < self.policy.maximum_pipeline_attempts
            and state.get("repair_pass", 0) < self.policy.maximum_repair_passes
            and any(item.repairable for item in diagnostics)
        ):
            return "repair"
        return "finish"

    def _review_node(self, state: RepairWorkflowState) -> RepairWorkflowState:
        run_dir = Path(state["last_run_dir"])
        report_path = run_dir / "review" / "report.json"
        if self._render and report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            diagnostics = [
                Diagnostic.model_validate(item)
                for item in report.get("diagnostics", [])
            ]
        else:
            diagnostics = []
        update = self._write_diagnostics(state, diagnostics, label="review")
        return {**update, "status": "reviewed"}

    def _route_after_review(self, state: RepairWorkflowState) -> str:
        diagnostics = _read_diagnostics(state.get("diagnostics_path"))
        blockers = _blocking(
            diagnostics,
            repair_warnings=self.policy.repair_warnings,
            regeneration_enabled=self.regeneration_provider is not None,
        )
        if (
            any(
                item.repairable
                or (
                    self.regeneration_provider is not None
                    and item.beat_id is not None
                    and "regenerate_beat" in item.suggested_repairs
                )
                for item in blockers
            )
            and state.get("pipeline_attempt", 0)
            < self.policy.maximum_pipeline_attempts
            and state.get("repair_pass", 0) < self.policy.maximum_repair_passes
        ):
            return "repair"
        return "finish"

    def _finish_node(self, state: RepairWorkflowState) -> RepairWorkflowState:
        diagnostics = _read_diagnostics(state.get("diagnostics_path"))
        if any(item.severity == "refusal" for item in diagnostics):
            status = "refused"
        elif any(item.severity == "error" for item in diagnostics):
            status = "failed"
        elif diagnostics:
            status = "completed_with_warnings"
        elif state.get("status") in {"compiled", "rendered", "reviewed"}:
            status = "completed"
        else:
            status = "failed"
        return {"status": status}
