"""`nolan effects` — the visual-effects umbrella (nolan.effects): fetch the CC0 overlay plates.

The fire/rain/smoke/… PLATE clips are gitignored (the repo excludes video), so a fresh clone repopulates
them from the committed manifest (projects/_library/overlays/overlays.json), which stores each plate's
direct CC0 download URL. No API key needed. Until fetched, element overlays show '(no plate)' and the
render-path executor skips them (no crash) — the honest degraded state.
"""
import json
import subprocess
import urllib.request
from pathlib import Path

import click

from ._root import main


def _dechroma(src, color):
    """Chroma-key a GREEN-SCREEN plate → black. `color`='auto' samples the top-left corner, else 0xRRGGBB.
    Writes a keyed .mp4 in projects/_library/overlays/. Returns (keyed_path, resolved_hex) so the resolved
    colour can be stored in the manifest — `fetch-plates` re-keys the re-downloaded green original with it."""
    from nolan.effects.library import OVERLAY_LIBRARY
    from nolan.ffmpeg_utils import FFMPEG
    ff = str(Path(FFMPEG))
    probe = Path(FFMPEG).with_name("ffprobe.exe")
    probe_exe = str(probe) if probe.exists() else "ffprobe"
    col = color
    if color == "auto":                                        # sample the averaged top-left corner
        raw = subprocess.run([ff, "-i", str(src), "-frames:v", "1", "-vf",
                              "crop=40:40:0:0,scale=1:1,format=rgb24", "-f", "rawvideo", "-"], capture_output=True).stdout
        if len(raw) >= 3:
            col = f"0x{raw[0]:02x}{raw[1]:02x}{raw[2]:02x}"
    dm = subprocess.run([probe_exe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=width,height", "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout.strip()
    w, h = (dm.split(",") + ["1920", "1080"])[:2]
    OVERLAY_LIBRARY.mkdir(parents=True, exist_ok=True)
    keyed = OVERLAY_LIBRARY / f"_key_{Path(src).stem}.mp4"
    subprocess.run([ff, "-y", "-i", str(src), "-f", "lavfi", "-i", f"color=black:s={w}x{h}",
                    "-filter_complex", f"[0:v]chromakey={col}:0.30:0.12[ck];[1:v][ck]overlay=shortest=1,format=yuv420p[o]",
                    "-map", "[o]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(keyed)], capture_output=True)
    return keyed, col


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
        if dst.exists() and dst.stat().st_size > 0 and not force:   # 0-byte = broken → re-fetch
            click.echo(f"  ✓ {e['file']} (present)"); skipped += 1; continue
        url = e.get("url")
        if not url:
            click.echo(f"  · {e['file']} (local-only — no fetch url)"); skipped += 1; continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})   # Pixabay CDN 403s the default UA
            tmpdl = dst.with_name(dst.stem + ".dl.mp4") if e.get("chroma") else dst
            with urllib.request.urlopen(req, timeout=120) as r, open(tmpdl, "wb") as f:
                f.write(r.read())
            if e.get("chroma"):                              # green-screen plate → re-key the download to black
                keyed, _ = _dechroma(tmpdl, e["chroma"])
                keyed.replace(dst); tmpdl.unlink(missing_ok=True)
            click.echo(f"  ↓ {e['file']}  ({e.get('effect')}, {e.get('license', '')})"); got += 1
        except Exception as ex:
            click.echo(f"  ✗ {e['file']}: {type(ex).__name__}: {ex}"); failed += 1
    click.echo(f"plates: {got} fetched, {skipped} present, {failed} failed → {OVERLAY_LIBRARY}")
    if failed:
        raise SystemExit(1)


@effects.command("add-plate")
@click.argument("source")
@click.option("--effect", "-e", required=True, help="Effect tag this plate is for (fire, rain, snow, … or a NEW element tag).")
@click.option("--blend", default="screen", show_default=True,
              type=click.Choice(["screen", "multiply", "overlay", "soft-light", "lighten", "color-dodge"]),
              help="mix-blend-mode (screen = an element on black; multiply = a texture/vignette).")
@click.option("--pixabay-id", default=None, help="Pixabay video id for provenance + a re-fetch URL (auto-detected from a <id>… filename).")
@click.option("--chroma", default=None, help="GREEN-SCREEN plate: key a bg colour → black so a screen blend works. 'auto' samples the top-left corner, or pass 0xRRGGBB.")
@click.option("--license", "lic", default=None, help="License note for a non-Pixabay plate (e.g. 'Pexels License (free)'). Pixabay is auto-detected.")
def add_plate(source, effect, blend, pixabay_id, chroma, lic):
    """Add or REPLACE the overlay plate for EFFECT from a local file, an http(s) URL, or a Pixabay id.

    Verifies it's a video, copies/downloads it into projects/_library/overlays/, records provenance +
    a direct re-fetch URL in overlays.json, and warns if EFFECT isn't a registered effect (add a
    _plate(...) entry in nolan/effects/registry.py so it appears in the catalog + fx UI).
    """
    import json
    import re
    import subprocess
    import urllib.parse
    import urllib.request
    from pathlib import Path

    from nolan.effects import library as fxlib
    from nolan.effects.registry import REGISTRY
    from nolan.ffmpeg_utils import FFMPEG

    src = Path(source)
    if not pixabay_id:                                          # detect id from 299595_medium.mp4 / 140842-….mp4
        m = re.match(r"(\d+)", src.stem)
        if m:
            pixabay_id = m.group(1)
    prov = {}
    if pixabay_id:
        try:
            from nolan.config import load_config
            key = load_config().image_sources.pixabay_api_key
            hits = json.loads(urllib.request.urlopen("https://pixabay.com/api/videos/?" + urllib.parse.urlencode(
                {"key": key, "id": str(pixabay_id)}), timeout=20).read()).get("hits", [])
            if hits:
                h = hits[0]
                v = h["videos"].get("medium") or h["videos"].get("large") or h["videos"].get("small")
                prov = {"pixabay_id": int(pixabay_id), "url": v["url"], "source": h.get("pageURL"),
                        "tags": h.get("tags", "").split(", "), "w": v.get("width"), "h": v.get("height"),
                        "duration": h.get("duration"), "license": "Pixabay License (free, no attribution)"}
                click.echo(f"  provenance: {h.get('tags')}")
        except Exception as ex:
            click.echo(f"  (provenance lookup failed: {ex})")
    prov.setdefault("license", lic or "user-provided (local)")  # non-Pixabay (e.g. Pexels): keep a license + source
    prov.setdefault("source", source)

    tmp = None                                                  # resolve SOURCE → a local file
    if source.lower().startswith("http") or (not src.exists() and prov.get("url")):
        url = source if source.lower().startswith("http") else prov["url"]
        fxlib.OVERLAY_LIBRARY.mkdir(parents=True, exist_ok=True)
        tmp = fxlib.OVERLAY_LIBRARY / f"_dl_{pixabay_id or 'plate'}.mp4"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})   # Pixabay CDN 403s the default UA
        with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as f:
            f.write(r.read())
        prov.setdefault("url", url)
        src = tmp
    if not src.exists():
        raise click.ClickException(f"can't resolve source {source!r} (not a file / URL / known Pixabay id)")

    ff = Path(FFMPEG)
    probe = ff.with_name("ffprobe.exe")
    probe_exe = str(probe) if probe.exists() else "ffprobe"

    if chroma:                                                  # GREEN-SCREEN plate → key the bg colour to black
        keyed, col = _dechroma(src, chroma)
        if not (keyed.exists() and keyed.stat().st_size > 0):
            raise click.ClickException("chroma-key failed (check the --chroma colour)")
        click.echo(f"  keyed {col} → black")
        prov["chroma"] = col                                    # so fetch-plates re-keys the re-downloaded original
        if tmp:
            tmp.unlink(missing_ok=True)
        tmp = src = keyed

    pr = subprocess.run([probe_exe, "-v", "error", "-select_streams", "v:0",   # verify it's a real video
                         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(src)], capture_output=True, text=True)
    if pr.returncode != 0 or "," not in (pr.stdout or ""):
        if tmp:
            tmp.unlink(missing_ok=True)
        raise click.ClickException(f"not a valid video: {(pr.stderr or '').strip()[:140]}")

    entry = fxlib.add_plate(src, effect, blend=blend, provenance=prov, replace=True)
    if tmp:
        tmp.unlink(missing_ok=True)
    click.echo(f"  ✓ {entry['file']}  (effect={effect}, blend={blend}, {pr.stdout.strip()})")
    if effect not in {e.plate for e in REGISTRY if e.plate}:
        click.echo(f"  ⚠ '{effect}' is NOT a registered effect yet — add a _plate('{effect}', …) entry in "
                   f"src/nolan/effects/registry.py so it appears in the catalog + fx UI.")
    click.echo(f"plate ready → {fxlib.OVERLAY_LIBRARY / entry['file']}  ·  commit overlays.json to share it")
