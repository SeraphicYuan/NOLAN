from pathlib import Path

from math_animation.cli import main


def test_plan_expanded_cli_writes_evidence_and_enforces_score(
    tmp_path: Path,
) -> None:
    script = tmp_path / "script.txt"
    script.write_text(
        "Derive step by step: $3x+5=20$, then $3x=15$, then $x=5$.\n\n"
        "Compare $y=x^2$ versus $y=2x^2$.",
        encoding="utf-8",
    )
    output = tmp_path / "planned"
    assert (
        main(
            [
                "plan-expanded",
                str(script),
                "--project-id",
                "cli-expanded",
                "--title",
                "CLI expanded",
                "--output-dir",
                str(output),
                "--minimum-pedagogy-score",
                "0.9",
            ]
        )
        == 0
    )
    assert (output / "project.json").is_file()
    assert (output / "expanded-planning.json").is_file()
    assert (output / "pedagogy.json").is_file()


def test_plan_expanded_cli_returns_two_when_gate_fails(
    tmp_path: Path,
) -> None:
    script = tmp_path / "script.txt"
    script.write_text("Introduce the topic.", encoding="utf-8")
    assert (
        main(
            [
                "plan-expanded",
                str(script),
                "--project-id",
                "cli-gate",
                "--title",
                "CLI gate",
                "--output-dir",
                str(tmp_path / "planned"),
                "--minimum-pedagogy-score",
                "0.99",
            ]
        )
        == 2
    )
