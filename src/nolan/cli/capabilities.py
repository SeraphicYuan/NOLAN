"""`nolan capabilities` — the umbrella capability catalog, for agents and humans.

Prints the same machine-readable catalog /api/map serves (module contract):
every capability registry with its when_to_use craft guidance. Dispatch
briefs point agents here so they pick from what actually exists.
"""

import json

import click

from ._root import main


@main.command()
@click.option('--json', 'as_json', is_flag=True, default=False,
              help='Full catalog as JSON (the agent-facing form).')
@click.option('--umbrella', '-u', default=None,
              type=click.Choice(['editing', 'motion', 'pairing', 'blocks', 'themes', 'effects']),
              help='Limit to one umbrella.')
def capabilities(as_json, umbrella):
    """List every capability registry with when-to-use guidance."""
    from nolan.system_map import _umbrellas
    cat = _umbrellas()
    if umbrella:
        cat = {umbrella: cat.get(umbrella)}
    if as_json:
        click.echo(json.dumps(cat, indent=2, ensure_ascii=False))
        return
    for name, entries in cat.items():
        if isinstance(entries, dict) and entries.get("error"):
            click.echo(f"\n== {name} ==  ERROR: {entries['error']}")
            continue
        click.echo(f"\n== {name} ({len(entries)}) ==")
        if entries and isinstance(entries[0], dict):
            for e in entries:
                click.echo(f"  {e['id']}")
                guide = e.get('when_to_use') or e.get('purpose') or ''
                if guide:
                    click.echo(f"      {guide}")
        else:
            click.echo("  " + " · ".join(entries))
