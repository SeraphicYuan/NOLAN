"""`nolan sfx` — the curated SFX library's crawl + ingest flow (crawl/add/list).

The sound umbrella's Layer-2 bank (docs/SOUND_DESIGN.md): `crawl` documents the
top CC0 sounds on Freesound; `add` pulls one hand-picked sound by id, GATES its
license, normalizes it to 48 kHz stereo (mix-safe for the concat path), tags it
with a registry `kind`, and records it in `projects/_library/sfx/sfx.json`;
`list` shows the curated bank as the mixer sees it.
"""

import json
import subprocess
import tempfile
from pathlib import Path

import click

from ._root import main
from nolan import asset_gate
from nolan.sound.crawl import crawl_cc0, fetch_sound, library_dir
from nolan.sound.registry import KINDS, BY_ID
from nolan.sfx_search import _get, _slug, FreesoundProvider

_MANIFEST = "sfx.json"


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _load_manifest(lib: Path):
    p = lib / _MANIFEST
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


@main.group()
def sfx():
    """Curated SFX library: crawl CC0 candidates, add hand-picked sounds, list."""


@sfx.command("crawl")
@click.option("--pages", type=int, default=5, show_default=True,
              help="API pages to fetch (×--page-size). 5×150 ≈ first 50 web pages.")
@click.option("--page-size", type=int, default=150, show_default=True,
              help="Sounds per page (Freesound max 150).")
@click.option("--min-downloads", type=int, default=0,
              help="Drop sounds below this download count.")
@click.option("--max-duration", type=float, default=None,
              help="Only sounds shorter than N seconds (SFX are usually short).")
def sfx_crawl(pages, page_size, min_downloads, max_duration):
    """Document the top CC0 sounds (downloads-desc) for hand-picking."""
    res = crawl_cc0(pages=pages, page_size=page_size,
                    min_downloads=min_downloads, max_duration=max_duration)
    click.echo(f"crawled {res['crawled']} → catalog now {res['catalog_total']:,} sounds "
               f"({res['in_library']} in library)")
    click.echo(f"  db:     {res['db']}")
    click.echo(f"  browse: {res['md']}")
    click.echo(f"  search: nolan sfx search \"<text>\"   |   add: nolan sfx add <id> --kind <k>")


@sfx.command("add")
@click.argument("sound_id")
@click.option("--kind", required=True, type=click.Choice(list(KINDS)),
              help="The registry cue-kind this sound serves (nolan.sound.KINDS).")
@click.option("--rating", type=int, default=3, show_default=True,
              help="Your quality rating 1-5 (selection prefers higher).")
@click.option("--tags", default="", help="Comma-separated extra tags.")
@click.option("--desc", default="", help="Override/augment the description (for search).")
@click.option("--no-trim", is_flag=True,
              help="Keep leading silence (for a bed/riser whose quiet lead-in is intentional).")
def sfx_add(sound_id, kind, rating, tags, desc, no_trim):
    """Fetch Freesound SOUND_ID, gate its license, normalize, curate it."""
    from nolan.sound.curate import CurateError, add_sound
    try:
        res = add_sound(sound_id, kind, rating=rating, tags=tags, desc=desc, no_trim=no_trim)
    except CurateError as e:
        click.echo(f"REJECTED sfx {e}", err=True)
        raise SystemExit(1)
    for note in res["notes"]:
        click.echo(f"  {note}")
    click.echo(f"added [{res['kind']}] {res['file']}  (rating {res['rating']}, {res['duration']:.1f}s)")


@sfx.command("doctor")
def sfx_doctor():
    """Scan the curated bank; flag files whose sound doesn't start at t≈0."""
    from nolan.sound import probe
    lib = library_dir()
    bank = [e for e in _load_manifest(lib) if e.get("curated")]
    if not bank:
        click.echo("bank empty."); return
    issues = 0
    for e in sorted(bank, key=lambda x: x.get("kind", "")):
        f = lib / e["file"]
        if not f.exists():
            click.echo(f"  ✗ MISSING  {e['file']}"); issues += 1; continue
        a = probe.analyze_silence(f)
        bad = a["lead_silence_s"] >= 0.05 or a["is_silent"]
        if bad:
            issues += 1
        flag = "⚠" if bad else "·"
        click.echo(f"  {flag} [{e.get('kind','?'):<13}] onset {a['lead_silence_s']:.2f}s  "
                   f"tail {a['trail_silence_s']:.2f}s  {a['duration']:.1f}s  {e['file']}")
    click.echo(f"\n{len(bank)} sounds, {issues} need attention"
               f"{' — re-add with a tighter source, or --no-trim if intentional' if issues else ''}.")


@sfx.command("remove")
@click.argument("sound_id")
def sfx_remove(sound_id):
    """Remove a curated sound from the bank (file + manifest + catalog flag)."""
    from nolan.sound.curate import remove_sound
    res = remove_sound(sound_id)
    if res["removed"]:
        click.echo(f"removed {sound_id} ({res.get('file')})")
    else:
        click.echo(f"not in bank: {sound_id}")


@sfx.command("search")
@click.argument("query", required=False, default="")
@click.option("--limit", type=int, default=20, show_default=True)
@click.option("--curated", is_flag=True, help="Only sounds already in our library.")
@click.option("--available", is_flag=True, help="Only sounds NOT yet curated.")
def sfx_search(query, limit, curated, available):
    """Query the local SFX catalog by text — no website hit."""
    from nolan.sound.catalog import SoundCatalog
    in_lib = True if curated else (False if available else None)
    cat = SoundCatalog()
    rows = cat.search(query, limit=limit, in_library=in_lib)
    stats = cat.stats()
    cat.close()
    if not rows:
        click.echo(f"no matches in {stats['total']:,}-sound catalog"
                   f"{' — crawl first: nolan sfx crawl' if not stats['total'] else ''}")
        return
    for r in rows:
        mark = "✓" if r.get("in_library") else " "
        kind = f"  [{r['library_kind']}]" if r.get("library_kind") else ""
        click.echo(f"{mark} {r['ext_id']:>9} {(r.get('num_downloads') or 0):>9,}↓ "
                   f"{(r.get('duration') or 0):>5.1f}s  {(r.get('name') or '')[:44]:<44}{kind}")
    click.echo(f"\n{len(rows)} of {stats['total']:,} catalog sounds "
               f"({stats['in_library']} curated).")


@sfx.command("list")
@click.option("--kind", type=click.Choice(list(KINDS)), default=None,
              help="Filter to one cue-kind.")
def sfx_list(kind):
    """The curated bank, grouped by cue-kind."""
    manifest = [e for e in _load_manifest(library_dir()) if e.get("curated")]
    if not manifest:
        click.echo(f"bank empty — crawl then add: nolan sfx crawl  (dir: {library_dir()})")
        return
    by_kind = {}
    for e in manifest:
        by_kind.setdefault(e.get("kind", "?"), []).append(e)
    for k in sorted(by_kind):
        if kind and k != kind:
            continue
        cue = BY_ID.get(k)
        click.echo(f"\n{k}  ({cue.purpose if cue else 'unknown kind'})")
        for e in sorted(by_kind[k], key=lambda x: -x.get("rating", 0)):
            click.echo(f"  ★{e.get('rating','-')} {e['file']:<48} "
                       f"{e.get('duration',0):.1f}s  {e.get('title','')[:40]}")
    n = len(manifest)
    click.echo(f"\n{n} curated sound{'s' if n != 1 else ''} across {len(by_kind)} kinds.")
