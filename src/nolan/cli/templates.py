"""Lottie template catalog commands (templates group, route-scenes).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


# ==================== Template Catalog Commands ====================

@main.group()
def templates():
    """Manage Lottie animation templates.

    Browse, search, and render templates from the unified catalog.
    """
    pass


@templates.command('list')
@click.option('--category', '-c', type=str, default=None,
              help='Filter by category.')
@click.option('--source', '-s', type=str, default=None,
              help='Filter by source (lottiefiles, jitter, lottieflow).')
@click.option('--with-schema', is_flag=True,
              help='Only show templates with schemas.')
def templates_list(category, source, with_schema):
    """List all available templates.

    Examples:

      nolan templates list

      nolan templates list --category lower-thirds

      nolan templates list --source jitter --with-schema
    """
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()
    catalog.load_tags()

    if with_schema:
        items = catalog.list_with_schema()
    elif category:
        items = catalog.list_by_category(category)
    elif source:
        items = catalog.list_by_source(source)
    else:
        items = catalog.list_all()

    if not items:
        click.echo("No templates found.")
        return

    click.echo(f"{'ID':<40} {'CATEGORY':<20} {'SCHEMA':<6} {'TAGS'}")
    click.echo("-" * 90)
    for t in sorted(items, key=lambda x: (x.category, x.name)):
        schema = "Yes" if t.has_schema else "-"
        tags = ", ".join(t.tags[:3]) + ("..." if len(t.tags) > 3 else "")
        click.echo(f"{t.id[:38]:<40} {t.category[:18]:<20} {schema:<6} {tags}")

    click.echo(f"\nTotal: {len(items)} templates")


@templates.command('info')
@click.argument('template_id')
def templates_info(template_id):
    """Show detailed template information.

    TEMPLATE_ID is the template ID or local path.

    Examples:

      nolan templates info number-counter-ssLbxKeW8Z

      nolan templates info lower-thirds/simple.json
    """
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()
    catalog.load_tags()

    template = catalog.get(template_id) or catalog.get_by_path(template_id)

    if not template:
        click.echo(f"Template not found: {template_id}")
        return

    click.echo(f"Name:     {template.name}")
    click.echo(f"ID:       {template.id}")
    click.echo(f"Category: {template.category}")
    click.echo(f"Source:   {template.source}")
    click.echo(f"Path:     {template.local_path}")
    click.echo(f"Size:     {template.width}x{template.height}")
    click.echo(f"Duration: {template.duration_seconds}s @ {template.fps} fps")
    click.echo(f"Tags:     {', '.join(template.tags) if template.tags else '(none)'}")

    if template.has_schema:
        click.echo(f"\nSchema fields: {', '.join(template.schema_fields)}")
    else:
        click.echo("\nNo schema (use 'nolan templates generate-schema' to create one)")

    if template.color_palette:
        click.echo(f"Colors:   {', '.join(template.color_palette)}")


@templates.command('search')
@click.argument('query')
@click.option('--all', 'match_all', is_flag=True,
              help='Match all tags (default: match any).')
def templates_search(query, match_all):
    """Search templates by tags.

    QUERY is a comma-separated list of tags to search for.

    Examples:

      nolan templates search counter

      nolan templates search "loading,spinner"

      nolan templates search "icon,success" --all
    """
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()
    catalog.load_tags()

    tags = [t.strip() for t in query.split(",")]
    results = catalog.search_by_tags(tags, match_all=match_all)

    if not results:
        click.echo(f"No templates found matching: {', '.join(tags)}")
        return

    click.echo(f"{'ID':<40} {'CATEGORY':<20} {'TAGS'}")
    click.echo("-" * 80)
    for t in results:
        tags_str = ", ".join(t.tags[:4])
        click.echo(f"{t.id[:38]:<40} {t.category[:18]:<20} {tags_str}")

    click.echo(f"\nFound: {len(results)} templates")


@templates.command('categories')
def templates_categories():
    """List all template categories."""
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()

    summary = catalog.summary()

    click.echo("Template Categories:\n")
    for cat, count in sorted(summary['by_category'].items()):
        click.echo(f"  {cat:<25} {count} templates")

    click.echo(f"\nTotal: {summary['total']} templates across {len(summary['by_category'])} categories")


@templates.command('auto-tag')
def templates_auto_tag():
    """Auto-generate tags for all templates.

    Tags are generated based on category and name patterns.
    """
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()
    catalog.load_tags()  # Load existing first

    tags_added = catalog.auto_tag_all()
    path = catalog.save_tags()

    click.echo(f"Added {tags_added} new tags")
    click.echo(f"Saved to: {path}")


@templates.command('summary')
def templates_summary():
    """Show template catalog summary."""
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()
    catalog.load_tags()

    summary = catalog.summary()

    click.echo("=== Template Catalog Summary ===\n")
    click.echo(f"Total templates: {summary['total']}")
    click.echo(f"With schemas:    {summary['with_schema']}")
    click.echo()
    click.echo("By source:")
    for src, count in sorted(summary['by_source'].items()):
        click.echo(f"  {src:<15} {count}")
    click.echo()
    click.echo(f"Categories: {len(summary['by_category'])}")


@templates.command('index')
@click.option('--force', is_flag=True, help='Reindex all templates.')
def templates_index(force):
    """Index templates for semantic search.

    Creates vector embeddings for natural language search.
    """
    from nolan.template_catalog import TemplateCatalog, TemplateSearch

    catalog = TemplateCatalog()
    catalog.load_tags()
    catalog.auto_tag_all()  # Ensure tags are present

    search = TemplateSearch(catalog)

    click.echo("Indexing templates for semantic search...")
    indexed = search.index_templates(force=force)
    click.echo(f"Indexed {indexed} templates")


@templates.command('semantic-search')
@click.argument('query')
@click.option('-n', '--top', type=int, default=5, help='Number of results.')
@click.option('--category', '-c', type=str, default=None, help='Filter by category.')
@click.option('--with-schema', is_flag=True, help='Only templates with schemas.')
def templates_semantic_search(query, top, category, with_schema):
    """Search templates using natural language.

    QUERY is a natural language description of what you're looking for.

    Examples:

      nolan templates semantic-search "loading spinner animation"

      nolan templates semantic-search "show name at bottom" --with-schema

      nolan templates semantic-search "counting numbers" -n 10
    """
    from nolan.template_catalog import TemplateCatalog, TemplateSearch

    catalog = TemplateCatalog()
    catalog.load_tags()

    search = TemplateSearch(catalog)

    # Check if indexed
    try:
        results = search.search(query, top_k=top, category=category, with_schema_only=with_schema)
    except Exception as e:
        click.echo(f"Search failed: {e}")
        click.echo("Try running: nolan templates index")
        return

    if not results:
        click.echo("No results found. Try running: nolan templates index")
        return

    click.echo(f"{'SCORE':<8} {'ID':<35} {'CATEGORY':<20}")
    click.echo("-" * 70)
    for r in results:
        score_pct = f"{r.score * 100:.1f}%"
        click.echo(f"{score_pct:<8} {r.template.id[:33]:<35} {r.template.category[:18]:<20}")

    click.echo(f"\nFound: {len(results)} results")


@templates.command('match-scene')
@click.argument('visual_type')
@click.argument('description')
@click.option('-n', '--top', type=int, default=5, help='Number of results.')
@click.option('--with-schema', is_flag=True, help='Only templates with schemas.')
def templates_match_scene(visual_type, description, top, with_schema):
    """Find templates matching a scene specification.

    VISUAL_TYPE is the scene's visual type (lower-third, counter, title, etc.)
    DESCRIPTION is the visual description of what's needed.

    Examples:

      nolan templates match-scene lower-third "show speaker name"

      nolan templates match-scene counter "animated number statistic" --with-schema

      nolan templates match-scene title "chapter heading reveal"
    """
    from dataclasses import dataclass
    from nolan.template_catalog import (
        TemplateCatalog, TemplateSearch, find_templates_for_scene
    )

    @dataclass
    class MockScene:
        visual_type: str
        visual_description: str
        narration_excerpt: str = ''

    catalog = TemplateCatalog()
    catalog.load_tags()

    search = TemplateSearch(catalog)

    scene = MockScene(visual_type=visual_type, visual_description=description)
    results = find_templates_for_scene(
        scene, catalog, search, top_k=top, require_schema=with_schema
    )

    if not results:
        click.echo("No matching templates found.")
        return

    click.echo(f"{'SCORE':<8} {'NAME':<30} {'CATEGORY':<20} {'SCHEMA'}")
    click.echo("-" * 75)
    for r in results:
        score_pct = f"{r.score * 100:.1f}%"
        schema = "Yes" if r.template.has_schema else "-"
        click.echo(f"{score_pct:<8} {r.template.name[:28]:<30} {r.template.category[:18]:<20} {schema}")

    click.echo(f"\nTop match: {results[0].template.local_path}")


# ==================== Visual Router Commands ====================

@main.command('route-scenes')
@click.argument('scene_plan', type=click.Path(exists=True))
@click.option('--threshold', '-t', type=float, default=0.5,
              help='Template match threshold (0-1).')
def route_scenes(scene_plan, threshold):
    """Show routing decisions for each scene.

    SCENE_PLAN is the path to scene_plan.json.

    Displays which pipeline (template, library, generation, infographic)
    each scene will use based on its visual_type.

    Examples:

      nolan route-scenes scene_plan.json

      nolan route-scenes scene_plan.json --threshold 0.6
    """
    from pathlib import Path
    from nolan.scenes import ScenePlan
    from nolan.visual_router import VisualRouter

    plan = ScenePlan.load(scene_plan)
    router = VisualRouter(template_score_threshold=threshold)

    click.echo(f"{'SCENE':<25} {'TYPE':<15} {'ROUTE':<12} {'TEMPLATE/REASON'}")
    click.echo("-" * 80)

    all_scenes = []
    for section_name, scenes in plan.sections.items():
        for scene in scenes:
            all_scenes.append(scene)
            decision = router.route(scene)

            template_info = decision.reason[:25]
            if decision.template:
                template_info = f"{decision.template.name} ({decision.template_score:.0%})"

            scene_id = f"{section_name[:8]}:{scene.id[:14]}"
            click.echo(f"{scene_id:<25} {scene.visual_type:<15} {decision.route:<12} {template_info}")

    # Summary
    decisions = router.route_all(all_scenes)
    summary = router.summary(decisions)

    click.echo(f"\nTotal: {summary['total']} scenes")
    click.echo("By route:")
    for route, count in sorted(summary['by_route'].items()):
        click.echo(f"  {route:<12} {count}")


