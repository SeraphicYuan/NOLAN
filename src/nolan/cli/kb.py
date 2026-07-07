"""Knowledge-base commands (kb group).

A video-craft knowledge base backed by an Obsidian vault. `kb ingest` pulls a
url / youtube / file / text into raw/*.md; later phases distill + index it.
"""
import click

from ._root import main


@main.group("kb")
def kb():
    """NOLAN knowledge base — ingest + distill video-craft sources into an Obsidian vault."""
    pass


@kb.command("ingest")
@click.argument("src")
@click.option("--type", "source_type",
              type=click.Choice(["youtube", "url", "article", "file", "text"]),
              default=None, help="Force the source type (else auto-detected).")
def kb_ingest(src, source_type):
    """Ingest a SRC (url, youtube link, file path, or raw text) into the KB raw store."""
    from nolan.kb import ingest as do_ingest
    res = do_ingest(src, source_type=source_type)
    tag = "already ingested" if res.deduped else "ingested"
    click.echo(f"{tag}: [{res.source_type}] {res.title}")
    click.echo(f"  id:  {res.id}")
    click.echo(f"  raw: {res.raw_path}")


@kb.command("distill")
@click.argument("source_id", required=False)
@click.option("--all", "do_all", is_flag=True, help="Distill every raw source.")
@click.option("--force", is_flag=True, help="Re-distill even if already done.")
def kb_distill(source_id, do_all, force):
    """Distill raw source(s) into parsed insight notes."""
    from nolan.kb import KBCatalog
    from nolan.kb.distill import distill_source
    cat = KBCatalog()
    if do_all:
        # with --force, re-distill everything; otherwise only the raw ones
        status = None if force else "raw"
        targets = [s.id for s in cat.list(status=status, limit=1000)]
    elif source_id:
        targets = [source_id]
    else:
        raise click.UsageError("give a SOURCE_ID or --all")
    if not targets:
        click.echo("(nothing to distill)")
        return
    for sid in targets:
        try:
            r = distill_source(sid, catalog=cat, force=force)
            click.echo(f"distilled {sid}: {r.n_insights} techniques -> parsed/{r.source_note.name}")
        except Exception as e:
            click.echo(f"FAILED {sid}: {e}")


@kb.command("list")
@click.option("--status", type=click.Choice(["raw", "distilled"]), default=None)
@click.option("--type", "source_type", default=None)
@click.option("--limit", "-n", type=int, default=50)
def kb_list(status, source_type, limit):
    """List ingested sources."""
    from nolan.kb import KBCatalog
    cat = KBCatalog()
    rows = cat.list(status=status, source_type=source_type, limit=limit)
    if not rows:
        click.echo("(no sources)")
        return
    click.echo(f"{len(rows)} source(s):")
    for s in rows:
        click.echo(f"  [{s.status:9}] {s.source_type:8} {s.title[:60]}")
        click.echo(f"              {s.raw_path}")


@kb.command("reindex")
@click.option("--no-vectors", is_flag=True, help="Rebuild keyword index only (skip embeddings).")
def kb_reindex(no_vectors):
    """Rebuild the derived index (FTS + vectors) from the distillation sidecars."""
    from nolan.kb.index import KBIndex
    res = KBIndex().reindex(with_vectors=not no_vectors)
    click.echo(f"reindexed {res['insights']} insight(s) from {res['sources']} source(s)"
               + (" (keyword only)" if no_vectors else ""))


@kb.command("search")
@click.argument("query")
@click.option("--mode", type=click.Choice(["hybrid", "keyword", "semantic"]), default="hybrid")
@click.option("--category", default=None, help="Filter by craft category.")
@click.option("--hook", "nolan_hook", default=None, help="Filter by NOLAN capability hook.")
@click.option("--difficulty", type=click.Choice(["easy", "medium", "advanced"]), default=None)
@click.option("-k", "topk", type=int, default=12, help="How many results.")
def kb_search(query, mode, category, nolan_hook, difficulty, topk):
    """Search distilled insights (keyword + semantic hybrid by default)."""
    from nolan.kb.index import KBIndex
    filters = {k: v for k, v in
               {"category": category, "nolan_hook": nolan_hook, "difficulty": difficulty}.items() if v}
    hits = KBIndex().search(query, mode=mode, filters=filters or None, k=topk)
    if not hits:
        click.echo("(no matches)")
        return
    click.echo(f"{len(hits)} result(s) for '{query}' ({mode}):\n")
    for h in hits:
        r = h.row
        sig = "+".join(h.signals) if h.signals else "browse"
        click.echo(f"  {r.title}")
        click.echo(f"    {r.category} · {r.difficulty} · hook:{r.nolan_hook} · [{sig} {h.score:.4f}]")
        if r.core_idea:
            click.echo(f"    {r.core_idea[:150]}")
        click.echo(f"    ↳ {r.source_title}")
        click.echo("")
