"""Shared CLI utilities."""

from pathlib import Path


def get_project_output_path(project: str = None, output: str = None, essay_path: Path = None) -> Path:
    """Determine output path from project name or output option.

    Priority: --output > --project > derived from essay name
    """
    if output:
        return Path(output)
    if project:
        return Path("projects") / project
    if essay_path:
        # Derive project name from essay filename
        project_name = essay_path.stem.lower().replace(" ", "-").replace("_", "-")
        return Path("projects") / project_name
    return Path("projects") / "default"


def ensure_scratch_dir() -> Path:
    """Ensure .scratch directory exists and return its path."""
    scratch = Path('.scratch')
    scratch.mkdir(exist_ok=True)
    return scratch
