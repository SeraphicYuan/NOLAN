from __future__ import annotations

import json
from pathlib import Path

import pytest

from math_animation.draft import draft_from_script
from math_animation.pipeline import AuthoringPipeline


def test_script_draft_compiles_to_inspectable_run_bundle(tmp_path: Path) -> None:
    project = draft_from_script(
        "A derivative measures local change.\n\n"
        r"The difference quotient is $\frac{f(a+h)-f(a)}{h}$.",
        project_id="derivative-demo",
        title="Derivative demo",
    )
    result = AuthoringPipeline(runs_dir=tmp_path).run(project)
    assert result.manifest.status == "completed"
    assert (result.run_dir / "project.lock.json").is_file()
    assert (result.run_dir / "style.lock.json").is_file()
    assert (result.run_dir / "timeline.json").is_file()
    assert (result.run_dir / "schemas" / "scene-program.schema.json").is_file()
    assert len(result.compilation.source_files) == 2
    manifest = json.loads(
        (result.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert "timeline.json" in manifest["artifacts"]
    assert manifest["project_sha256"]
    assert (result.run_dir / "pedagogy.json").is_file()
    assert result.pedagogy.schema_version == (
        "math-animation.pedagogy-report.v1"
    )


def test_pipeline_can_gate_on_structural_pedagogy_score(
    tmp_path: Path,
) -> None:
    project = draft_from_script(
        "A static introduction.",
        project_id="pedagogy-gate",
        title="Pedagogy gate",
    )
    with pytest.raises(ValueError, match="below required"):
        AuthoringPipeline(runs_dir=tmp_path).run(
            project,
            minimum_pedagogy_score=0.99,
        )
    run_dir = next(tmp_path.iterdir())
    assert (run_dir / "pedagogy.json").is_file()
