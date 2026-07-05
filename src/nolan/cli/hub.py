"""NOLAN Hub UI launcher (hub).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


@main.command()
@click.option('--projects', '-p', type=click.Path(), default='projects',
              help='Directory containing projects (default: projects/).')
@click.option('--host', default='127.0.0.1', help='Host to bind to.')
@click.option('--port', default=8011, type=int, help='Port to bind to (8001 is SPARTA).')
@click.pass_context
def hub(ctx, projects, host, port):
    """Launch the unified NOLAN Hub UI.

    A unified interface combining:
    - Video Library: Browse indexed videos, segments, and clusters
    - Motion Effects Showcase: Generate motion effects for video essays
    - Scene Viewer: Review scene plans with A/V script layout

    Projects are auto-discovered from the projects directory (default: ./projects).
    Each subdirectory containing a scene_plan.json is shown as a project.

    Examples:

      nolan hub

      nolan hub --projects /path/to/projects

      nolan hub --port 8080
    """
    config = ctx.obj['config']
    db_path = Path(config.indexing.database).expanduser()
    projects_dir = Path(projects) if projects else None

    from nolan.hub import create_hub_app, scan_projects
    import uvicorn

    click.echo(f"Starting NOLAN Hub at http://{host}:{port}")
    if db_path.exists():
        click.echo(f"Database: {db_path}")
    else:
        click.echo(f"Database not found - Library features will be limited")
    if projects_dir and projects_dir.exists():
        found_projects = scan_projects(projects_dir)
        click.echo(f"Projects directory: {projects_dir} ({len(found_projects)} projects found)")
    else:
        click.echo("Projects directory not found - Scene viewer will show no projects")
    click.echo("Render service should be running at http://127.0.0.1:3010")
    click.echo("Press Ctrl+C to stop.\n")

    app = create_hub_app(
        db_path=db_path if db_path.exists() else None,
        projects_dir=projects_dir,
    )
    uvicorn.run(app, host=host, port=port)


