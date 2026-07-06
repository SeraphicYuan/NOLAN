"""`nolan music` — the music library's ingest flow (add/list).

The soundtrack stage is only as good as the library it selects from, and
until now music.json was hand-edited. `add` copies a license-safe track in,
estimates its energy from measured loudness when not given, and updates the
manifest; `list` shows what selection has to work with.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import click

from ._root import main

LIBRARY = Path("projects/_library/music")


def _measured_energy(path: Path) -> float:
    """Loudness-based energy estimate (overridable with --energy).

    Mean RMS maps roughly: quiet ambient (-30 dB) -> 0.2, driving (-12 dB)
    -> 0.9. Crude but honest — and recorded as 'estimated' in the manifest.
    """
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ff = "ffmpeg"
    r = subprocess.run([ff, "-i", str(path), "-af", "astats=metadata=1",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"RMS level dB: (-?[\d.]+)", r.stderr)
    if not m:
        return 0.5
    rms = float(m[-1])
    return round(min(0.95, max(0.05, (rms + 30.0) / 20.0)), 2)


@main.group()
def music():
    """Music library: add license-safe tracks, list what selection sees."""


@music.command("add")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--mood", default="", help="Mood tag, e.g. 'tense', 'contemplative'.")
@click.option("--energy", type=float, default=None,
              help="0..1 energy; measured from loudness when omitted.")
@click.option("--tags", default="", help="Comma-separated extra tags.")
def music_add(file, mood, energy, tags):
    """Copy FILE into the library and tag it in music.json."""
    src = Path(file)
    LIBRARY.mkdir(parents=True, exist_ok=True)
    dest = LIBRARY / src.name
    if dest.resolve() != src.resolve():
        shutil.copy2(src, dest)
    estimated = energy is None
    if estimated:
        energy = _measured_energy(dest)
    mpath = LIBRARY / "music.json"
    manifest = []
    if mpath.exists():
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest = [e for e in manifest if e.get("file") != dest.name]
    manifest.append({"file": dest.name,
                     "energy": round(float(energy), 2),
                     "mood": mood,
                     "tags": [t.strip() for t in tags.split(",") if t.strip()],
                     **({"energy_source": "measured"} if estimated else {})})
    mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    click.echo(f"added {dest.name}: energy {energy}"
               f"{' (measured — override with --energy)' if estimated else ''}"
               f", mood '{mood or '(none)'}'")


@music.command("list")
def music_list():
    """Tracks as the soundtrack selector sees them."""
    from nolan.audio_mix import load_music_library
    tracks = load_music_library()
    if not tracks:
        click.echo(f"library empty — add license-safe tracks: nolan music add "
                   f"<file> --mood <mood> (dir: {LIBRARY})")
        return
    for t in tracks:
        click.echo(f"  {t['file']:<44} energy {t['energy']:.2f}  "
                   f"mood '{t['mood']}'  tags {','.join(t['tags']) or '-'}")
