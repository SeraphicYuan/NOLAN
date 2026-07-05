"""Project management commands (projects group).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


# ==================== Project Management Commands ====================

@main.group()
def projects():
    """Manage projects for organizing video assets.

    Projects help organize your video library into separate collections.
    Each project has a slug (e.g., 'venezuela') for easy reference.
    """
    pass


@projects.command('init')
@click.argument('slug')
@click.option('--name', '-n', type=str, default=None,
              help='Display name for the project (defaults to slug).')
@click.option('--description', '-d', type=str, default=None,
              help='Project description.')
@click.option('--script', '-s', type=click.Path(exists=True, dir_okay=False), default=None,
              help='Path to an existing script.md to copy in.')
@click.option('--projects-root', type=click.Path(file_okay=False), default='projects',
              help='Parent directory for the new project (default: projects/).')
@click.pass_context
def projects_init(ctx, slug, name, description, script, projects_root):
    """Scaffold a new orchestrator-ready project folder.

    Creates `projects/<slug>/` with `project.yaml`, `script.md`, and the
    standard `source/`, `assets/`, `output/`, `.orchestrator/` subdirectories.

    Use this for greenfield orchestration. Subsequent `nolan index` calls scoped
    `--project <slug>` will populate the indexed library; `nolan orchestrate
    projects/<slug>` then drives the pipeline.

    Examples:

      nolan projects init venezuela --name "Venezuela Documentary"

      nolan projects init tutorials -d "Python tutorial series"

      nolan projects init tech-essay --script ./drafts/tech-essay.md
    """
    import shutil
    import yaml as yaml_lib

    project_dir = Path(projects_root) / slug
    if project_dir.exists():
        click.echo(f"Error: {project_dir} already exists. Pick a different slug or remove the folder.", err=True)
        ctx.exit(1)

    display_name = name or slug.replace('-', ' ').replace('_', ' ').title()

    # Create the directory tree
    project_dir.mkdir(parents=True)
    for sub in ("source", "assets", "output",
                ".orchestrator/instructions",
                ".orchestrator/feedback",
                ".orchestrator/history",
                ".orchestrator/modules"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    # project.yaml
    project_yaml_data = {
        "name": display_name,
        "slug": slug,
        "description": description or "",
        "source_videos": ["source/"],
        "output_dir": "output/",
        "assets_dir": "assets/",
    }
    (project_dir / "project.yaml").write_text(
        yaml_lib.safe_dump(project_yaml_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    # script.md — copied from --script flag, or a starter template
    if script:
        shutil.copy(script, project_dir / "script.md")
        script_msg = f"copied from {script}"
    else:
        starter = (
            f"# Video Script\n\n"
            f"**Total Duration:** _set after writing_\n\n"
            f"---\n\n"
            f"## Hook [0:00 - 0:??]\n\n"
            f"<paradox or contrast that frames the central question>\n\n"
            f"## Context [0:?? - ?:??]\n\n"
            f"<historical or definitional setup>\n\n"
            f"## Thesis [?:?? - ?:??]\n\n"
            f"<single sentence stating the argument; enumerate evidence sections>\n\n"
            f"## Evidence 1 [?:?? - ?:??]\n\n"
            f"<first lens / cause / pillar>\n\n"
            f"## Evidence 2 [?:?? - ?:??]\n\n"
            f"<second lens>\n\n"
            f"## Evidence 3 [?:?? - ?:??]\n\n"
            f"<third lens>\n\n"
            f"## Conclusion [?:?? - ?:??]\n\n"
            f"<synthesis + reflective close>\n"
        )
        (project_dir / "script.md").write_text(starter, encoding="utf-8")
        script_msg = "starter template"

    click.echo(f"Created project at {project_dir}")
    click.echo(f"  slug:        {slug}")
    click.echo(f"  name:        {display_name}")
    if description:
        click.echo(f"  description: {description}")
    click.echo(f"  script.md:   {script_msg}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Edit `{project_dir}/script.md`.")
    click.echo(f"  2. Drop source videos in `{project_dir}/source/` and run "
               f"`nolan index {project_dir}/source --project {slug}`.")
    click.echo(f"  3. Run `nolan orchestrate {project_dir}` to advance the pipeline "
               f"(or add `--auto` to run all steps).")


@projects.command('create')
@click.argument('name')
@click.option('--slug', '-s', type=str, default=None,
              help='Custom slug (auto-generated from name if not provided).')
@click.option('--description', '-d', type=str, default=None,
              help='Project description.')
@click.option('--path', '-p', type=click.Path(), default=None,
              help='Project directory path.')
@click.pass_context
def projects_create(ctx, name, slug, description, path):
    """Create a new project.

    NAME is the human-readable project name.

    Examples:

      nolan projects create "Venezuela Documentary"

      nolan projects create "Tutorial Series" -s tutorials -d "Python tutorials"

      nolan projects create "My Project" -p ./projects/my-project
    """
    config = ctx.obj['config']
    from nolan.indexer import VideoIndex

    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    try:
        project = index.create_project(name, slug=slug, description=description, path=path)
        click.echo(f"Created project:")
        click.echo(f"  Name: {project['name']}")
        click.echo(f"  Slug: {project['slug']}")
        click.echo(f"  ID:   {project['id']}")
        if project['path']:
            click.echo(f"  Path: {project['path']}")
        click.echo(f"\nUse this slug when indexing videos:")
        click.echo(f"  nolan index <videos> --project {project['slug']}")
    except ValueError as e:
        click.echo(f"Error: {e}")


@projects.command('list')
@click.pass_context
def projects_list(ctx):
    """List all projects.

    Shows project slug, name, and video count.
    """
    config = ctx.obj['config']
    from nolan.indexer import VideoIndex

    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    projects = index.list_projects()

    if not projects:
        click.echo("No projects found.")
        click.echo("Create one with: nolan projects create \"My Project\"")
        return

    click.echo(f"{'SLUG':<20} {'NAME':<30} {'VIDEOS':<8}")
    click.echo("-" * 60)
    for p in projects:
        click.echo(f"{p['slug']:<20} {p['name'][:28]:<30} {p['video_count']:<8}")


@projects.command('status')
@click.option('--root', type=click.Path(), default='projects', help='Projects directory.')
@click.pass_context
def projects_status(ctx, root):
    """Unified project view: capabilities + library-DB link (C1).

    One list across script/scenes/orchestrator/segment workflows, replacing the
    per-page fragmented views.
    """
    from nolan import projects as P
    from nolan.indexer import VideoIndex
    config = ctx.obj['config']
    idx = None
    db_path = Path(config.indexing.database).expanduser()
    if db_path.exists():
        try:
            idx = VideoIndex(db_path)
        except Exception:
            idx = None
    found = P.discover_projects(Path(root), index=idx)
    if not found:
        click.echo("No projects found under " + str(root))
        return
    click.echo(f"{'SLUG':<30} {'KINDS':<26} {'DB':<4} SCENES")
    click.echo("-" * 72)
    for p in found:
        kinds = ",".join(p.kinds) or "-"
        db = "yes" if p.library_project_id else "-"
        click.echo(f"{p.slug[:29]:<30} {kinds[:25]:<26} {db:<4} {p.scene_count}")


@projects.command('backfill')
@click.option('--root', type=click.Path(), default='projects', help='Projects directory.')
@click.option('--dry-run', is_flag=True, help='Show what would be linked without writing.')
@click.pass_context
def projects_backfill(ctx, root, dry_run):
    """Register a library-DB project row for each filesystem project missing one (C1).

    Closes the FS↔DB gap: script/orchestrator projects created on disk never had a
    DB row, so videos/clips couldn't attach. Idempotent.
    """
    from nolan import projects as P
    from nolan.indexer import VideoIndex
    config = ctx.obj['config']
    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)
    linked = skipped = 0
    for proj in P.discover_projects(Path(root), index=index):
        if proj.library_project_id:
            skipped += 1
            continue
        if dry_run:
            click.echo(f"  would link: {proj.slug}")
            linked += 1
            continue
        pid = P.link_db_project(index, proj)
        if pid:
            click.echo(f"  linked {proj.slug} -> {pid}")
            linked += 1
    verb = "would link" if dry_run else "linked"
    click.echo(f"{verb} {linked}, already-linked {skipped}.")


@projects.command('info')
@click.argument('slug')
@click.pass_context
def projects_info(ctx, slug):
    """Show project details.

    SLUG is the project slug or ID.

    Examples:

      nolan projects info venezuela

      nolan projects info fcaa7aa9
    """
    config = ctx.obj['config']
    from nolan.indexer import VideoIndex

    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    project = index.get_project(slug)

    if not project:
        click.echo(f"Project not found: {slug}")
        return

    click.echo(f"Name:        {project['name']}")
    click.echo(f"Slug:        {project['slug']}")
    click.echo(f"ID:          {project['id']}")
    click.echo(f"Description: {project['description'] or '(none)'}")
    click.echo(f"Path:        {project['path'] or '(none)'}")
    click.echo(f"Created:     {project['created_at']}")

    # Get video count
    videos = index.get_videos_by_project(project['id'])
    click.echo(f"\nVideos: {len(videos)}")
    for v in videos[:5]:
        path = Path(v['path']).name if v['path'] else 'Unknown'
        click.echo(f"  - {path}")
    if len(videos) > 5:
        click.echo(f"  ... and {len(videos) - 5} more")


@projects.command('delete')
@click.argument('slug')
@click.option('--delete-videos', is_flag=True,
              help='Also delete indexed videos from database.')
@click.option('--force', '-f', is_flag=True,
              help='Skip confirmation prompt.')
@click.pass_context
def projects_delete(ctx, slug, delete_videos, force):
    """Delete a project.

    SLUG is the project slug or ID.

    By default, only removes the project entry. Videos remain in the index
    but become unassociated. Use --delete-videos to also remove videos.

    Examples:

      nolan projects delete my-project

      nolan projects delete my-project --delete-videos -f
    """
    config = ctx.obj['config']
    from nolan.indexer import VideoIndex

    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    project = index.get_project(slug)
    if not project:
        click.echo(f"Project not found: {slug}")
        return

    if not force:
        videos = index.get_videos_by_project(project['id'])
        msg = f"Delete project '{project['name']}'?"
        if delete_videos and videos:
            msg += f" This will also delete {len(videos)} indexed video(s)."
        if not click.confirm(msg):
            click.echo("Cancelled.")
            return

    if index.delete_project(slug, delete_videos=delete_videos):
        click.echo(f"Deleted project: {project['name']}")
        if delete_videos:
            click.echo("Associated videos were also deleted from index.")
    else:
        click.echo("Failed to delete project.")


