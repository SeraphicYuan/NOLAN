"""Validate every checked-in top-level and generated example project."""

from __future__ import annotations

from pathlib import Path

from math_animation.contracts import ProjectSpec


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    paths = sorted((ROOT / "examples").glob("*.json"))
    paths.extend(sorted((ROOT / "examples").glob("*/*.json")))
    project_paths = [
        path
        for path in paths
        if path.name.startswith("project")
        or path.parent == ROOT / "examples"
        or path.parent.name == "responsive_matrix"
    ]
    for path in project_paths:
        ProjectSpec.model_validate_json(path.read_text(encoding="utf-8"))
        print(path.relative_to(ROOT))
    print(f"validated {len(project_paths)} example projects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
