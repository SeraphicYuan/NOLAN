"""`nolan lint` — retention lint for a project's scene plan."""

from pathlib import Path

import click

from ._root import main


@main.command('lint')
@click.argument('project', type=click.Path(exists=True, file_okay=False))
def lint(project):
    """Measure the plan for attention rot (monotony, plateaus, pacing)."""
    from nolan.retention import lint_project, render_report
    result = lint_project(Path(project))
    click.echo(render_report(result, title=f"Retention lint — {Path(project).name}"))
