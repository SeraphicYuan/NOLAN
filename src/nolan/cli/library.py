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


# ------------------------------------------------------------- Visual Lib (not-held tier)
# `harvest` fills it, `discover` searches it, `fetch` promotes one row into the held library.
# Deliberately NOT folded into `images search`: the two tiers answer different questions, and a
# discovery hit is a POINTER (no file on disk) that no held-tier caller could use.

@images.command('harvest')
@click.argument('source')
@click.option('--limit', '-n', type=int, default=200, help='How many ROWS to index.')
@click.option('--query', default=None, help='Bias the harvest toward a theme.')
@click.option('--dept', default=None, help='Filter to one department.')
@click.option('--restart', is_flag=True,
              help='Ignore the saved cursor and re-walk from the beginning (refresh, not extend).')
@click.option('--no-pixels', is_flag=True,
              help='Phase A only: index catalog records, skip thumbnails (5.4x faster — '
                   '87ms/row vs 470ms). Fill them in later with `nolan images backfill`.')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
def images_harvest(source, limit, query, dept, restart, no_pixels, scope, project):
    """Harvest a collection into the discovery tier (metadata + thumbnail, no bytes).

    Resumes from the last run's cursor by default, so repeated calls EXTEND coverage instead of
    re-walking the same rows.
    """
    import json

    from nolan.imagelib.harvest import SOURCES, harvest
    if source not in SOURCES:
        click.echo(f"unknown source {source!r} (known: {', '.join(sorted(SOURCES))})")
        raise SystemExit(2)
    kw = {k: v for k, v in (('query', query), ('dept', dept)) if v}
    rep = harvest(source, limit=limit, scope=scope, project=project,
                  resume=not restart, pixels=not no_pixels, **kw)
    click.echo(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False))
    if rep.refused_gate or rep.errors:
        click.echo(f"NOTE: {rep.refused_gate} refused by the asset gate, {rep.errors} errored.")
    if no_pixels:
        click.echo("Phase A only — these rows are searchable by IDENTITY but carry no pixels, "
                   "so they cannot rank on LOOK yet. Run: nolan images backfill")


@images.command('backfill')
@click.option('--limit', '-n', type=int, default=200, help='How many rows to fetch pixels for.')
@click.option('--collection', '-c', type=int, default=None, help='Restrict to one collection id.')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
def images_backfill(limit, collection, scope, project):
    """PHASE B: fetch thumbnails for record-only discovery rows, so `look` search grows.

    Incremental by design — measured at 470 ms/row, the whole artic public-domain catalog is
    ~8 hours of pixels, so this is meant to be run repeatedly rather than as one job that must
    not fail. The gates Phase A could not run (watermark banner, content-resolution floor) run
    here, when the pixels first exist.
    """
    lib = _open_library(scope, project)
    res = lib.backfill_pixels(limit=limit, collection_id=collection)
    click.echo(f"attempted {res['attempted']}: fetched {res['fetched']}, "
               f"refused {res['refused']}, errors {res['errors']}")
    for r in res["reasons"]:
        click.echo(f"    {r}")
    st = lib.discovery_stats(collection_id=collection)
    click.echo(f"pixel coverage now {st['with_pixels']}/{st['discovery']} ({st['pixels_pct']}%)")


@images.command('dump')
@click.argument('source')
@click.option('--force', is_flag=True, help='Re-download even if a copy is cached.')
def images_dump(source, force):
    """Fetch a source's bulk data dump, so its rights filter can run OFFLINE.

    Only sources whose enumeration strategy is `bulk-dump` have one. For the Met that is a 318 MB
    CSV of 484,956 rows, of which 248,472 are public domain — downloading it is what turns a
    blind id walk into a filtered one, and it supplies the per-department coverage denominator.
    """
    from nolan.imagelib.harvest import SOURCES, met_download_csv

    adapter = SOURCES.get(source)
    if adapter is None:
        click.echo(f"unknown source {source!r} (known: {', '.join(sorted(SOURCES))})")
        raise SystemExit(2)
    if adapter.enumeration != "bulk-dump":
        click.echo(f"{source} enumerates by {adapter.enumeration!r}, not a bulk dump — "
                   f"nothing to download.")
        raise SystemExit(2)
    if source != "met":
        click.echo(f"no dump downloader registered for {source!r}")
        raise SystemExit(2)

    bar = {"last": 0}

    def prog(got, total):
        if got - bar["last"] >= 32 << 20:
            bar["last"] = got
            click.echo(f"  {got / 1e6:>6.0f} MB / {total / 1e6:.0f} MB")

    path = met_download_csv(force=force, progress=prog)
    click.echo(f"dump ready: {path} ({path.stat().st_size / 1e6:.0f} MB)")


@images.command('discover')
@click.argument('query')
@click.option('--top', '-k', type=int, default=12)
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
def images_discover(query, top, scope, project):
    """Search the NOT-HELD tier — 'this image exists, here, under these terms'."""
    lib = _open_library(scope, project)
    hits = lib.search_discovery(query, k=top)
    click.echo(f"{len(hits)} discovery result(s) for '{query}':")
    for h in hits:
        a = h.asset
        who = " / ".join(x for x in (a.creator, a.date_text) if x)
        click.echo(f"  [{h.score:.3f}] #{a.id} {a.title or '(untitled)'}"
                   + (f" — {who}" if who else ""))
        click.echo(f"          {a.source_ref}  {a.license or 'license?'}  {a.source_url or ''}")
    st = lib.discovery_stats()
    click.echo(f"({st['discovery']} indexed, {st['described_pct']}% captioned — "
               f"`images fetch <id>` to pull the bytes)")


@images.command('fetch')
@click.argument('asset_id', type=int)
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
@click.option('--tier', default='archival', type=click.Choice(['archival', 'stock']))
def images_fetch(asset_id, scope, project, tier):
    """Promote a discovery row into the held library (downloads + gates the real image)."""
    lib = _open_library(scope, project)
    try:
        asset, promoted = lib.promote_to_held(asset_id, tier=tier)
    except Exception as e:
        click.echo(f"Failed: {e}")
        raise SystemExit(1)
    verb = 'Fetched' if promoted else 'Already held (deduped by content hash) as'
    click.echo(f"{verb} #{asset.id}: {asset.title or asset.path} "
               f"({asset.width}x{asset.height}) -> {asset.path}")


@images.command('artists')
@click.option('--limit', '-n', type=int, default=25, help='How many LLM CALLS to spend.')
@click.option('--min-works', type=int, default=1, help='Skip creators with fewer works than this.')
@click.option('--collection', '-c', type=int, default=None)
@click.option('--show', is_flag=True, help='Just list what we already know, spend nothing.')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
def images_artists(limit, min_works, collection, show, scope, project):
    """Learn movement/period/style per ARTIST — one call each, spent across all their works.

    Bounded by CALLS, not rows: that is the whole point. Creators are enriched commonest-first,
    so a small budget covers the most rows. Style and movement are never asked of the vision
    model — they are facts about a person, not about a picture.
    """
    import asyncio

    lib = _open_library(scope, project)
    if show:
        known = lib.catalog.list_artists()
        hist = dict((k, n) for k, _, n in lib.catalog.creator_histogram(held=0))
        if not known:
            click.echo("nothing learned yet — run without --show")
            return
        for a in known:
            works = hist.get(a.name_key, 0)
            line = a.context_line() or "(not recognised)"
            click.echo(f"  {works:>4} works  {line}")
        click.echo(f"{len(known)} artists known")
        return

    from nolan.config import load_config
    from nolan.imagelib.artists import enrich_artists
    from nolan.llm import create_text_llm

    cfg = load_config()
    llm = create_text_llm(cfg)
    model = getattr(llm, "model", "llm")
    res = asyncio.run(enrich_artists(lib, limit=limit, llm=llm, model=model,
                                     collection_id=collection, min_works=min_works))
    for a in res["artists"][:20]:
        click.echo(f"  {a['works']:>4} works  {a['name']} — "
                   f"{a['movement'] or '?'} / {a['period'] or '?'}")
    click.echo(f"{res['called']} calls: {res['learned']} learned, "
               f"{res['unrecognised']} unrecognised, {res['failed']} failed")
    click.echo(f"covering {res['rows_covered']} rows — {res['leverage']} rows per call")


@images.command('rederive')
@click.option('--collection', '-c', type=int, default=None, help='Restrict to one collection id.')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
def images_rederive(collection, scope, project):
    """Recompute `image_kind` from the catalog columns already on disk (no network, no model).

    Run this after changing the taxonomy rules. It also prints the FALLTHROUGH rate, because a
    derivation whose `unknown` share nobody looks at is a silent cap.
    """
    lib = _open_library(scope, project)
    res = lib.rederive_kinds(collection_id=collection)
    for k, n in sorted(res["counts"].items(), key=lambda kv: -kv[1]):
        if n:
            click.echo(f"  {n:>7,} ({n / res['total'] * 100:>5.1f}%)  {k}")
    click.echo(f"{res['changed']} rows updated; unknown rate {res['unknown_pct']}%")


@images.command('collections')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
def images_collections(scope, project):
    """List harvested collections and their caption coverage."""
    lib = _open_library(scope, project)
    cols = lib.catalog.list_collections()
    if not cols:
        click.echo("No collections harvested yet — try: nolan images harvest artic --limit 500")
        return
    for c in cols:
        st = lib.discovery_stats(collection_id=c.id)
        # COVERAGE, not just a count. "841 indexed" reads as a finished collection; "841 of
        # 62,035 (1.4%)" cannot. An unknown denominator says so rather than implying completeness.
        cov = c.coverage
        cover = (f"{st['discovery']} of {c.upstream_count:,} upstream ({cov:.1%})"
                 if cov is not None else f"{st['discovery']} indexed, upstream total unknown")
        click.echo(f"  #{c.id} {c.slug} — {c.title}")
        click.echo(f"      {cover}; {st['pixels_pct']}% with pixels; "
                   f"{st['described_pct']}% captioned; "
                   f"rights: {c.rights or '?'}; last crawled {c.last_crawled or 'never'}")
        if c.cursor:
            click.echo(f"      resumes at {c.cursor} (set {c.cursor_at or '?'})")


