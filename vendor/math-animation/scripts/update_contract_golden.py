"""Regenerate the explicitly reviewed v0.3 compatibility baseline."""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

from math_animation.blocks import available_blocks
from math_animation.bundle import sha256_json, write_json_atomic
from math_animation.compiler import ManimCompiler
from math_animation.contracts import (
    MANIFEST_SCHEMA_VERSION,
    SCENE_PROGRAM_SCHEMA_VERSION,
    SCHEMA_VERSION,
    TIMELINE_SCHEMA_VERSION,
    ProjectSpec,
    SceneProgram,
)
from math_animation.style import normalize_style
from math_animation.repair import Diagnostic, RepairPlan
from math_animation.workflow import RepairPolicy
from math_animation.model_provider import ModelCallRecord, ModelProviderConfig
from math_animation.planning import PlanningBeatContext, VisualDecision
from math_animation.regeneration import RegenerationArtifact
from math_animation.expanded_model_provider import ExpandedModelCallRecord
from math_animation.expanded_planning import (
    ExpandedPlanningArtifact,
    ExpandedVisualDecision,
)
from math_animation.pedagogy import PedagogyReport


ROOT = Path(__file__).resolve().parents[1]


def _semantic_source_hash() -> str:
    project = ProjectSpec.model_validate_json(
        (ROOT / "examples" / "equation_project.json").read_text(
            encoding="utf-8"
        )
    )
    with tempfile.TemporaryDirectory() as directory:
        result = ManimCompiler().compile(
            project,
            normalize_style(project.style),
            Path(directory),
        )
        sources = []
        for source_path in result.source_files:
            source = source_path.read_text(encoding="utf-8")
            sources.append(
                re.sub(
                    r"math-animation [0-9]+\.[0-9]+\.[0-9]+",
                    "math-animation <VERSION>",
                    source,
                )
            )
    return sha256_json(sources)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="v0.3")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tests" / "golden" / "v0.3_contracts.json",
    )
    parser.add_argument(
        "--compiler-output",
        type=Path,
        default=ROOT / "tests" / "golden" / "v0.4_compiler.json",
    )
    parser.add_argument(
        "--repair-output",
        type=Path,
        default=ROOT / "tests" / "golden" / "v0.5_repair.json",
    )
    parser.add_argument(
        "--model-regeneration-output",
        type=Path,
        default=(
            ROOT / "tests" / "golden" / "v0.6_model_regeneration.json"
        ),
    )
    parser.add_argument(
        "--expanded-pedagogy-output",
        type=Path,
        default=ROOT / "tests" / "golden" / "v0.7_expanded_pedagogy.json",
    )
    args = parser.parse_args()
    payload = {
        "baseline": args.label,
        "project_schema_sha256": sha256_json(ProjectSpec.model_json_schema()),
        "scene_program_schema_sha256": sha256_json(
            SceneProgram.model_json_schema()
        ),
        "available_blocks": list(available_blocks()),
        "schema_versions": {
            "project": SCHEMA_VERSION,
            "scene_program": SCENE_PROGRAM_SCHEMA_VERSION,
            "timeline": TIMELINE_SCHEMA_VERSION,
            "manifest": MANIFEST_SCHEMA_VERSION,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(args.output, payload)
    write_json_atomic(
        args.compiler_output,
        {
            "baseline": "v0.4",
            "semantic_source_sha256": _semantic_source_hash(),
        },
    )
    write_json_atomic(
        args.repair_output,
        {
            "baseline": "v0.5",
            "diagnostic_schema_sha256": sha256_json(
                Diagnostic.model_json_schema()
            ),
            "repair_plan_schema_sha256": sha256_json(
                RepairPlan.model_json_schema()
            ),
            "repair_policy_schema_sha256": sha256_json(
                RepairPolicy.model_json_schema()
            ),
        },
    )
    write_json_atomic(
        args.model_regeneration_output,
        {
            "baseline": "v0.6",
            "planning_context_schema_sha256": sha256_json(
                PlanningBeatContext.model_json_schema()
            ),
            "visual_decision_schema_sha256": sha256_json(
                VisualDecision.model_json_schema()
            ),
            "model_provider_config_schema_sha256": sha256_json(
                ModelProviderConfig.model_json_schema()
            ),
            "model_call_schema_sha256": sha256_json(
                ModelCallRecord.model_json_schema()
            ),
            "regeneration_artifact_schema_sha256": sha256_json(
                RegenerationArtifact.model_json_schema()
            ),
        },
    )
    write_json_atomic(
        args.expanded_pedagogy_output,
        {
            "baseline": "v0.7",
            "expanded_visual_decision_schema_sha256": sha256_json(
                ExpandedVisualDecision.model_json_schema()
            ),
            "expanded_planning_artifact_schema_sha256": sha256_json(
                ExpandedPlanningArtifact.model_json_schema()
            ),
            "expanded_model_call_schema_sha256": sha256_json(
                ExpandedModelCallRecord.model_json_schema()
            ),
            "pedagogy_report_schema_sha256": sha256_json(
                PedagogyReport.model_json_schema()
            ),
        },
    )
    print(args.output)
    print(args.compiler_output)
    print(args.repair_output)
    print(args.model_regeneration_output)
    print(args.expanded_pedagogy_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
