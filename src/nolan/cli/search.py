"""Semantic search commands (sync-vectors, semantic-search).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


# ==================== Semantic Search Commands ====================

@main.command('sync-vectors')
@click.option('--project', '-p', type=str, default=None,
              help='Only sync videos from this project slug.')
@click.option('--clear', is_flag=True,
              help='Clear existing vectors before syncing.')
@click.option('--force', '-f', is_flag=True,
              help='Force full sync, ignoring fingerprints (re-embed everything).')
@click.pass_context
def sync_vectors(ctx, project, clear, force):
    """Sync video index to vector database for semantic search.

    This command populates ChromaDB with embeddings from your indexed
    video segments and clusters, enabling semantic search.

    By default, uses incremental sync - only re-embeds videos whose
    fingerprints have changed since last sync. Use --force to re-embed all.

    This is automatically called after 'nolan index' completes.

    Examples:

      nolan sync-vectors

      nolan sync-vectors --project venezuela

      nolan sync-vectors --clear

      nolan sync-vectors --force  # Re-embed everything
    """
    config = ctx.obj['config']
    _sync_vectors_impl(config, project, clear, force)


def _sync_vectors_impl(config, project=None, clear=False, force=False, quiet=False):
    """Implementation of vector sync (shared by CLI and auto-sync)."""
    from nolan.indexer import VideoIndex
    from nolan.vector_search import VectorSearch

    db_path = Path(config.indexing.database).expanduser()
    if not db_path.exists():
        if not quiet:
            click.echo(f"Error: Database not found at {db_path}")
        return False

    index = VideoIndex(db_path)

    # Vector DB path alongside SQLite
    vector_db_path = db_path.parent / "vectors"
    if not quiet:
        click.echo(f"SQLite: {db_path}")
        click.echo(f"Vector DB: {vector_db_path}")

    # Resolve project
    project_id = None
    if project:
        proj = index.get_project(project)
        if not proj:
            if not quiet:
                click.echo(f"Error: Project '{project}' not found.")
            return False
        project_id = proj['id']
        if not quiet:
            click.echo(f"Project: {proj['name']} ({proj['slug']})")

    # Initialize vector search
    vector_search = VectorSearch(vector_db_path, index=index)

    # Clear if requested
    if clear:
        if not quiet:
            click.echo("Clearing existing vectors...")
        vector_search.clear()

    # Show current stats
    stats = vector_search.get_stats()
    if not quiet:
        click.echo(f"Current vectors: {stats['segments']} segments, {stats['clusters']} clusters")

    # Sync
    if not quiet:
        click.echo("\nSyncing to vector database...")
        if stats['segments'] == 0:
            click.echo("(First run will download embedding model ~440MB)")

    def progress(current, total, msg):
        if not quiet:
            click.echo(f"\r  [{current}/{total}] {msg[:50]:<50}", nl=False)

    result = vector_search.sync_from_index(
        project_id=project_id,
        progress_callback=progress,
        incremental=not force
    )
    if not quiet:
        click.echo()  # newline after progress

    skipped = result.get('skipped', 0)
    if not quiet:
        if skipped > 0:
            click.echo(f"\nSynced: {result['segments']} segments, {result['clusters']} clusters (skipped {skipped} unchanged)")
        else:
            click.echo(f"\nSynced: {result['segments']} segments, {result['clusters']} clusters")

    # Final stats
    stats = vector_search.get_stats()
    if not quiet:
        click.echo(f"Total vectors: {stats['segments']} segments, {stats['clusters']} clusters")

    return True


@main.command('semantic-search')
@click.argument('query')
@click.option('--limit', '-n', type=int, default=10,
              help='Maximum number of results.')
@click.option('--level', '-l', type=click.Choice(['segments', 'clusters', 'both']),
              default='both', help='Search level: segments, clusters, or both.')
@click.option('--project', '-p', type=str, default=None,
              help='Filter by project slug.')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output JSON file for results.')
@click.pass_context
def semantic_search(ctx, query, limit, level, project, output):
    """Semantic search across your video library.

    QUERY is a natural language description of what you're looking for.

    Unlike keyword search, semantic search understands meaning:
    - "person looking worried" finds "anxious expression", "concerned face"
    - "establishing shot of city" finds "urban skyline", "downtown aerial"

    Run 'nolan sync-vectors' first to populate the vector database.

    Examples:

      nolan semantic-search "person speaking to camera"

      nolan semantic-search "dramatic landscape" --level clusters

      nolan semantic-search "historical footage" --project venezuela -n 20

      nolan semantic-search "emotional moment" -o results.json
    """
    import json
    config = ctx.obj['config']
    from nolan.indexer import VideoIndex
    from nolan.vector_search import VectorSearch

    db_path = Path(config.indexing.database).expanduser()
    if not db_path.exists():
        click.echo(f"Error: Database not found at {db_path}")
        return

    vector_db_path = db_path.parent / "vectors"
    if not vector_db_path.exists():
        click.echo(f"Error: Vector database not found at {vector_db_path}")
        click.echo("Run 'nolan sync-vectors' first to create embeddings.")
        return

    index = VideoIndex(db_path)
    vector_search = VectorSearch(vector_db_path, index=index)

    # Check if vectors exist
    stats = vector_search.get_stats()
    if stats['segments'] == 0 and stats['clusters'] == 0:
        click.echo("Error: Vector database is empty.")
        click.echo("Run 'nolan sync-vectors' first to create embeddings.")
        return

    # Resolve project
    project_id = None
    if project:
        proj = index.get_project(project)
        if not proj:
            click.echo(f"Error: Project '{project}' not found.")
            return
        project_id = proj['id']
        click.echo(f"Project: {proj['name']}")

    click.echo(f"Query: \"{query}\"")
    click.echo(f"Level: {level}")
    click.echo(f"Searching...")

    # Perform search
    results = vector_search.search(
        query=query,
        limit=limit,
        search_level=level,
        project_id=project_id
    )

    if not results:
        click.echo("No results found.")
        return

    click.echo(f"\nFound {len(results)} results:\n")

    # Display results
    for i, r in enumerate(results, 1):
        score_pct = f"{r.score * 100:.1f}%"
        time_str = f"{int(r.timestamp_start // 60):02d}:{int(r.timestamp_start % 60):02d}"
        video_name = Path(r.video_path).name if r.video_path else "Unknown"

        type_badge = f"[{r.content_type.upper()}]"
        click.echo(f"  {i}. {type_badge} {score_pct} @ {time_str}")
        click.echo(f"     Video: {video_name[:50]}")

        desc = r.description[:100] + "..." if len(r.description or "") > 100 else (r.description or "")
        click.echo(f"     {desc}")

        if r.people:
            click.echo(f"     People: {', '.join(r.people[:3])}")
        if r.location:
            click.echo(f"     Location: {r.location}")
        click.echo()

    # Save to JSON if requested
    if output:
        output_path = Path(output)
        output_data = {
            "query": query,
            "level": level,
            "project": project,
            "results": [
                {
                    "score": r.score,
                    "content_type": r.content_type,
                    "video_path": r.video_path,
                    "timestamp_start": r.timestamp_start,
                    "timestamp_end": r.timestamp_end,
                    "description": r.description,
                    "transcript": r.transcript,
                    "people": r.people,
                    "location": r.location,
                    "objects": r.objects,
                }
                for r in results
            ]
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        click.echo(f"Results saved to: {output_path}")


