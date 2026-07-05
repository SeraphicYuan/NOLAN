"""Article publishing command (publish).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


@main.command('publish')
@click.argument('source')
@click.option('--theme', default='press', help='reacticle theme (press/bodoni/tufte/freddie/vignelli/...)')
@click.option('--type', 'atype', default='explainer', help='article type (essay/explainer/longform/briefing/...)')
@click.option('--width', default='regular', help='narrow/regular/wide/full')
@click.option('--images', default='none', help='none/placeholders/ai-generated')
@click.option('--brand', default=None, help='brand seed hex color (recolors the theme via oklch), e.g. #3257d6')
@click.option('--slug', default=None, help='output workspace name (default: from the title)')
@click.option('--out', type=click.Path(), default=None, help='output dir (default: projects/_published)')
@click.option('--review', is_flag=True, help='scaffold + source only, then stop for authoring/review')
@click.option('--no-cover', is_flag=True, help='disable the book-style cover')
@click.pass_context
def publish_cmd(ctx, source, theme, atype, width, images, brand, slug, out, review, no_cover):
    """Turn a URL / doc / text into a self-contained, offline single-file HTML article."""
    from nolan.publish import Publisher, PublishConfig
    cfg = PublishConfig(theme=theme, type=atype, width=width, images=images,
                        brand_color=brand, cover=not no_cover,
                        mode='review' if review else 'auto', out_dir=out)
    pub = Publisher(cfg, nolan_config=ctx.obj['config'])
    res = asyncio.run(pub.run(source, slug=slug))
    if res.stopped_for_review:
        click.echo(f"Scaffolded {res.workspace}")
        click.echo("  Author the article (agent) then: build in that workspace.")
    elif res.ok:
        click.echo(f"Published -> {res.article_html}")
        click.echo(f"  {res.summary}")
    else:
        click.echo(f"Incomplete: {res.summary or res.notes}", err=True)
        ctx.exit(1)


