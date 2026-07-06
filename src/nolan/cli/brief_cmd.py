"""`nolan compile-brief` — (re)compile a project's brief.json from its style guide.

Backfill for projects authored before the brief compiler existed, and the
manual re-run after editing style_guide.md by hand.
"""

import asyncio
import json
from pathlib import Path

import click

from ._root import main


@main.command('compile-brief')
@click.argument('project', type=click.Path(exists=True, file_okay=False))
@click.option('--no-llm', is_flag=True, default=False,
              help='Skip descriptor extraction; fully deterministic compile.')
def compile_brief_cmd(project, no_llm):
    """Compile style_guide.md into a validated brief.json (theme/mood/voice)."""
    from nolan.project_brief import compile_brief, save_brief

    llm = None
    if not no_llm:
        try:
            from nolan.config import load_config
            from nolan.llm import create_text_llm
            llm = create_text_llm(load_config())
        except Exception as exc:
            click.echo(f"(no LLM available: {exc} — deterministic compile)")

    brief = asyncio.run(compile_brief(Path(project), llm=llm))
    path = save_brief(Path(project), brief)
    click.echo(json.dumps(brief, indent=2, ensure_ascii=False))
    click.echo(f"\nSaved: {path}")
