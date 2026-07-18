"""`nolan effects` — the visual-effects umbrella (nolan.effects): fetch the CC0 overlay plates.

The fire/rain/smoke/… PLATE clips are gitignored (the repo excludes video), so a fresh clone repopulates
them from the committed manifest (projects/_library/overlays/overlays.json), which stores each plate's
direct CC0 download URL. No API key needed. Until fetched, element overlays show '(no plate)' and the
render-path executor skips them (no crash) — the honest degraded state.
"""
import json
import urllib.request

import click

from ._root import main


@main.group()
def effects():
    """Visual effects umbrella — colour grades, grain, and fire/rain overlay plates."""


@effects.command("fetch-plates")
@click.option("--force", is_flag=True, help="Re-download even if a plate file already exists.")
def fetch_plates(force):
    """Download the CC0 overlay plate clips named in projects/_library/overlays/overlays.json."""
    from nolan.effects.library import OVERLAY_LIBRARY
    manifest = OVERLAY_LIBRARY / "overlays.json"
    if not manifest.exists():
        raise click.ClickException(f"no manifest at {manifest}")
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    got = skipped = failed = 0
    for e in entries:
        dst = OVERLAY_LIBRARY / e["file"]
        if dst.exists() and not force:
            click.echo(f"  ✓ {e['file']} (present)"); skipped += 1; continue
        url = e.get("url")
        if not url:
            click.echo(f"  ✗ {e['file']}: no url in manifest (re-source it)"); failed += 1; continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})   # Pixabay CDN 403s the default UA
            with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
                f.write(r.read())
            click.echo(f"  ↓ {e['file']}  ({e.get('effect')}, {e.get('license', '')})"); got += 1
        except Exception as ex:
            click.echo(f"  ✗ {e['file']}: {type(ex).__name__}: {ex}"); failed += 1
    click.echo(f"plates: {got} fetched, {skipped} present, {failed} failed → {OVERLAY_LIBRARY}")
    if failed:
        raise SystemExit(1)
