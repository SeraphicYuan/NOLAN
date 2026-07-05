"""Command-line interface for NOLAN."""

import asyncio
import sys
from pathlib import Path

import click

# Fix Windows console encoding for Unicode filenames
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from nolan import __version__
from nolan.config import load_config


@click.group()
@click.version_option(version=__version__)
@click.pass_context
def main(ctx):
    """NOLAN - Video Essay Pipeline.

    Transform structured essays into video production packages.
    """
    ctx.ensure_object(dict)
    ctx.obj['config'] = load_config()
