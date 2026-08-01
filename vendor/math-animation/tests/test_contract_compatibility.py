import json
import re
import tempfile
from pathlib import Path

from math_animation.blocks import available_blocks
from math_animation.bundle import sha256_json
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
BASELINE = json.loads(
    (ROOT / "tests" / "golden" / "v0.3_contracts.json").read_text(
        encoding="utf-8"
    )
)
COMPILER_BASELINE = json.loads(
    (ROOT / "tests" / "golden" / "v0.4_compiler.json").read_text(
        encoding="utf-8"
    )
)
REPAIR_BASELINE = json.loads(
    (ROOT / "tests" / "golden" / "v0.5_repair.json").read_text(
        encoding="utf-8"
    )
)
MODEL_REGENERATION_BASELINE = json.loads(
    (
        ROOT / "tests" / "golden" / "v0.6_model_regeneration.json"
    ).read_text(encoding="utf-8")
)
EXPANDED_PEDAGOGY_BASELINE = json.loads(
    (ROOT / "tests" / "golden" / "v0.7_expanded_pedagogy.json").read_text(
        encoding="utf-8"
    )
)


def test_v03_public_schemas_remain_frozen() -> None:
    assert sha256_json(ProjectSpec.model_json_schema()) == BASELINE[
        "project_schema_sha256"
    ]
    assert sha256_json(SceneProgram.model_json_schema()) == BASELINE[
        "scene_program_schema_sha256"
    ]


def test_v03_block_catalog_and_schema_versions_remain_compatible() -> None:
    assert list(available_blocks()) == BASELINE["available_blocks"]
    assert {
        "project": SCHEMA_VERSION,
        "scene_program": SCENE_PROGRAM_SCHEMA_VERSION,
        "timeline": TIMELINE_SCHEMA_VERSION,
        "manifest": MANIFEST_SCHEMA_VERSION,
    } == BASELINE["schema_versions"]


def test_v04_semantic_compiler_output_remains_stable() -> None:
    project = ProjectSpec.model_validate_json(
        (ROOT / "examples" / "equation_project.json").read_text(
            encoding="utf-8"
        )
    )
    with tempfile.TemporaryDirectory() as directory:
        compilation = ManimCompiler().compile(
            project,
            normalize_style(project.style),
            Path(directory),
        )
        sources = [
            re.sub(
                r"math-animation [0-9]+\.[0-9]+\.[0-9]+",
                "math-animation <VERSION>",
                path.read_text(encoding="utf-8"),
            )
            for path in compilation.source_files
        ]
    assert sha256_json(sources) == COMPILER_BASELINE["semantic_source_sha256"]


def test_v05_repair_artifact_schemas_remain_stable() -> None:
    assert sha256_json(Diagnostic.model_json_schema()) == REPAIR_BASELINE[
        "diagnostic_schema_sha256"
    ]
    assert sha256_json(RepairPlan.model_json_schema()) == REPAIR_BASELINE[
        "repair_plan_schema_sha256"
    ]
    assert sha256_json(RepairPolicy.model_json_schema()) == REPAIR_BASELINE[
        "repair_policy_schema_sha256"
    ]


def test_v06_model_and_regeneration_schemas_remain_stable() -> None:
    pairs = {
        "planning_context_schema_sha256": PlanningBeatContext,
        "visual_decision_schema_sha256": VisualDecision,
        "model_provider_config_schema_sha256": ModelProviderConfig,
        "model_call_schema_sha256": ModelCallRecord,
        "regeneration_artifact_schema_sha256": RegenerationArtifact,
    }
    for key, model in pairs.items():
        assert sha256_json(model.model_json_schema()) == (
            MODEL_REGENERATION_BASELINE[key]
        )


def test_v07_expanded_planning_and_pedagogy_schemas_remain_stable() -> None:
    pairs = {
        "expanded_visual_decision_schema_sha256": ExpandedVisualDecision,
        "expanded_planning_artifact_schema_sha256": ExpandedPlanningArtifact,
        "expanded_model_call_schema_sha256": ExpandedModelCallRecord,
        "pedagogy_report_schema_sha256": PedagogyReport,
    }
    for key, model in pairs.items():
        assert sha256_json(model.model_json_schema()) == (
            EXPANDED_PEDAGOGY_BASELINE[key]
        )
