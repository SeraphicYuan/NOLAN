"""`nolan package` / `nolan credits` — the deliverables around the video."""

import asyncio
import json
from pathlib import Path

import click

from ._root import main


@main.command('package')
@click.argument('project', type=click.Path(exists=True, file_okay=False))
@click.option('--no-llm', is_flag=True, default=False,
              help='Deterministic titles/description (no API call).')
@click.option('--no-thumb-render', is_flag=True, default=False,
              help='Skip the typographic thumbnail card render.')
def package(project, no_llm, no_thumb_render):
    """Build package/: thumbnails, titles, description, chapters, subs, credits."""
    from nolan.packaging import build_package
    llm = None
    if not no_llm:
        try:
            from nolan.config import load_config
            from nolan.llm import create_text_llm
            llm = create_text_llm(load_config())
        except Exception as exc:
            click.echo(f"(no LLM: {exc} — deterministic fallbacks)")
    inv = asyncio.run(build_package(Path(project), llm=llm,
                                    skip_thumb_render=no_thumb_render))
    click.echo(json.dumps(inv, indent=2, ensure_ascii=False))
    if inv["items"].get("unverified_assets"):
        click.echo(f"\n⚠ {inv['items']['unverified_assets']} asset(s) lack "
                   "license metadata — see CREDITS.md 'VERIFY BEFORE PUBLISH'.")


@main.command('credits')
@click.argument('project', type=click.Path(exists=True, file_okay=False))
@click.option('--verify-identity', is_flag=True, default=False,
              help='Vision cross-check named artworks (slow, remote).')
def credits(project, verify_identity):
    """(Re)build attribution.json + CREDITS.md; optional identity check."""
    from nolan.attribution import build_attribution, verify_named_assets
    manifest = build_attribution(Path(project))
    c = manifest["counts"]
    click.echo(f"{c['total']} assets, {c['unverified']} unverified — "
               f"CREDITS.md + attribution.json written")
    if verify_identity:
        results = asyncio.run(verify_named_assets(Path(project)))
        for r in results:
            click.echo(f"  [{r['verdict']:>9}] {r['scene']}: {r['query'][:60]}"
                       f" — {r['reason']}")
        bad = [r for r in results if r["verdict"] == "MISMATCH"]
        if bad:
            click.echo(f"⚠ {len(bad)} identity MISMATCH(es) — fix before publish")
