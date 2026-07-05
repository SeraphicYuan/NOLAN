"""Picture library commands (images group).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


@main.group('images')
def images():
    """Picture library — persistent, searchable, license-aware image store.

    Global library lives in _library/images/; per-project in
    projects/<name>/imagelib/. Semantic search uses CLIP (text -> image).
    """
    pass


def _open_library(scope, project):
    from nolan.imagelib import ImageLibrary
    return ImageLibrary(scope=scope, project=project)


@images.command('search')
@click.argument('query')
@click.option('--scope', type=click.Choice(['global', 'project', 'both']), default='global')
@click.option('--project', '-p', default=None, help='Project name (for project/both scope).')
@click.option('--top', '-k', type=int, default=12, help='Number of results.')
@click.option('--license', 'license_contains', default=None, help='Only results whose license contains this text.')
def images_search(query, scope, project, top, license_contains):
    """Semantic search the picture library."""
    from nolan.imagelib import ImageLibrary, search_all
    if scope == 'both':
        hits = search_all(query, project=project, k=top, license_contains=license_contains)
    else:
        hits = ImageLibrary(scope=scope, project=project).search(
            query, k=top, license_contains=license_contains)
    click.echo(f"{len(hits)} result(s) for '{query}':")
    for h in hits:
        a = h.asset
        click.echo(f"  [{h.score:.3f}] #{a.id} {a.title or '(untitled)'} "
                   f"({a.width}x{a.height}) {a.license or '?'}")
        click.echo(f"          {a.path}  <- {a.source or '?'}")


@images.command('add')
@click.argument('url_or_manifest')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
@click.option('--source', default=None)
@click.option('--license', 'license_', default=None)
@click.option('--query', default=None, help='Tag with the query/topic this asset is for.')
def images_add(url_or_manifest, scope, project, source, license_, query):
    """Add an image URL, or ingest a manifest.json from `extract-assets`."""
    import json
    lib = _open_library(scope, project)
    added = skipped = 0
    if url_or_manifest.startswith('http'):
        try:
            a, created = lib.add_url(url_or_manifest, source=source, license=license_, query=query)
            added += int(created); skipped += int(not created)
            click.echo(f"{'Added' if created else 'Exists'} #{a.id}: {a.path}")
        except Exception as e:
            click.echo(f"Failed: {e}")
    else:
        data = json.loads(Path(url_or_manifest).read_text(encoding='utf-8'))
        items = data.get('results', data) if isinstance(data, dict) else data
        with click.progressbar(items, label='Ingesting') as bar:
            for it in bar:
                url = it.get('url')
                if not url:
                    continue
                local = it.get('local_path')  # prefer already-downloaded file (no re-fetch)
                try:
                    if local and Path(local).exists():
                        a, created = lib.add_file(
                            local, url=url, source=it.get('source') or source,
                            source_url=it.get('source_url'),
                            license=it.get('license') or license_,
                            title=it.get('title'), query=query)
                    else:
                        a, created = lib.add_url(
                            url, source=it.get('source') or source,
                            source_url=it.get('source_url'),
                            license=it.get('license') or license_,
                            title=it.get('title'), query=query)
                    added += int(created); skipped += int(not created)
                except Exception as e:
                    click.echo(f"\n  ! {url[:60]}: {e}")
        click.echo(f"Added {added}, skipped {skipped} (duplicates).")


@images.command('list')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
@click.option('--source', default=None)
@click.option('--license', 'license_contains', default=None)
@click.option('--status', default='active')
@click.option('--limit', '-n', type=int, default=30)
def images_list(scope, project, source, license_contains, status, limit):
    """List library assets."""
    lib = _open_library(scope, project)
    for a in lib.list(status=status, source=source, license_contains=license_contains, limit=limit):
        click.echo(f"  #{a.id} [{a.source or '?'}] {a.title or '(untitled)'} "
                   f"({a.width}x{a.height}) {a.license or '?'}")


@images.command('reject')
@click.argument('asset_id', type=int)
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
def images_reject(asset_id, scope, project):
    """Reject an asset (hidden from search; removed from the vector index)."""
    _open_library(scope, project).set_status(asset_id, 'rejected')
    click.echo(f"Rejected #{asset_id}.")


@images.command('promote')
@click.argument('asset_id', type=int)
@click.option('--project', '-p', required=True, help='Project the asset lives in.')
def images_promote(asset_id, project):
    """Copy a project-library asset into the global library."""
    from nolan.imagelib import promote_to_global
    try:
        asset, created = promote_to_global(project, asset_id)
    except Exception as e:
        click.echo(f"Failed: {e}")
        return
    click.echo(f"{'Promoted to' if created else 'Already in'} global #{asset.id}: {asset.title or asset.path}")


@images.command('stats')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
def images_stats(scope, project):
    """Show library counts."""
    click.echo(_open_library(scope, project).stats())


