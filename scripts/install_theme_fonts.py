"""Install the themes' typefaces so MANIM can set type in them.

The HTML half of a composition pulls its faces from Google Fonts at render time. Manim cannot:
it asks Pango, which only sees fonts INSTALLED on the machine. A theme face that is missing
falls back to generic Sans with mangled kerning, and Pango says so only on stderr — which a
successful render never surfaces. `nolan.mathanim.style` substitutes a personality-matched
system face and reports it, but the honest fix is to have the real face here.

Per-user install: files go to %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts and are registered under
HKCU, so no Administrator is needed. Idempotent — an already-installed face is left alone.

    python -X utf8 scripts/install_theme_fonts.py            # install every theme family
    python -X utf8 scripts/install_theme_fonts.py --check    # report only, install nothing
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
THEMES = REPO / "themes"
RAW = "https://raw.githubusercontent.com/google/fonts/main/{}"

# family -> path under the google/fonts repo. Variable fonts ([wght] etc.) carry the whole
# family in one file, which is what Pango wants; static families list their key weights.
GOOGLE_FONTS = {
    "Inter": ["ofl/inter/Inter[opsz,wght].ttf"],
    "JetBrains Mono": ["ofl/jetbrainsmono/JetBrainsMono[wght].ttf"],
    "Space Grotesk": ["ofl/spacegrotesk/SpaceGrotesk[wght].ttf"],
    "Manrope": ["ofl/manrope/Manrope[wght].ttf"],
    "Source Serif 4": ["ofl/sourceserif4/SourceSerif4[opsz,wght].ttf"],
    "Space Mono": ["ofl/spacemono/SpaceMono-Regular.ttf", "ofl/spacemono/SpaceMono-Bold.ttf"],
    "IBM Plex Mono": ["ofl/ibmplexmono/IBMPlexMono-Regular.ttf",
                      "ofl/ibmplexmono/IBMPlexMono-Bold.ttf"],
    "IBM Plex Sans": ["ofl/ibmplexsans/IBMPlexSans[wdth,wght].ttf"],
    "Fraunces": ["ofl/fraunces/Fraunces[SOFT,WONK,opsz,wght].ttf"],
    "Playfair Display": ["ofl/playfairdisplay/PlayfairDisplay[wght].ttf"],
    "Libre Franklin": ["ofl/librefranklin/LibreFranklin[wght].ttf"],
    "Archivo Black": ["ofl/archivoblack/ArchivoBlack-Regular.ttf"],
    "Patrick Hand": ["ofl/patrickhand/PatrickHand-Regular.ttf"],
    "Instrument Serif": ["ofl/instrumentserif/InstrumentSerif-Regular.ttf"],
    "Plus Jakarta Sans": ["ofl/plusjakartasans/PlusJakartaSans[wght].ttf"],
    "Outfit": ["ofl/outfit/Outfit[wght].ttf"],
    "Tektur": ["ofl/tektur/Tektur[wdth,wght].ttf"],
    "Chakra Petch": ["ofl/chakrapetch/ChakraPetch-Regular.ttf",
                     "ofl/chakrapetch/ChakraPetch-Bold.ttf"],
    "Syne": ["ofl/syne/Syne[wght].ttf"],
    "Fredoka One": ["ofl/fredoka/Fredoka[wdth,wght].ttf"],
    "Quicksand": ["ofl/quicksand/Quicksand[wght].ttf"],
    "Cormorant": ["ofl/cormorant/Cormorant[wght].ttf"],
    "Cormorant Garamond": ["ofl/cormorantgaramond/CormorantGaramond[wght].ttf"],
    "DM Mono": ["ofl/dmmono/DMMono-Regular.ttf", "ofl/dmmono/DMMono-Medium.ttf"],
    "DM Sans": ["ofl/dmsans/DMSans[opsz,wght].ttf"],
    "VT323": ["ofl/vt323/VT323-Regular.ttf"],
    "Big Shoulders Display": ["ofl/bigshouldersdisplay/BigShouldersDisplay[wght].ttf"],
    "Albert Sans": ["ofl/albertsans/AlbertSans[wght].ttf"],
    "Shrikhand": ["ofl/shrikhand/Shrikhand-Regular.ttf"],
    "Zilla Slab": ["ofl/zillaslab/ZillaSlab-Regular.ttf", "ofl/zillaslab/ZillaSlab-Bold.ttf"],
    "Caveat": ["ofl/caveat/Caveat[wght].ttf"],
    "Courier Prime": ["ofl/courierprime/CourierPrime-Regular.ttf"],
    "Work Sans": ["ofl/worksans/WorkSans[wght].ttf"],
}

# Families no open source can supply. Named so a missing face is a KNOWN gap, not a mystery:
# a silent omission here is how "the theme asked for X" becomes "nobody knows why it looks wrong".
NOT_ON_GOOGLE_FONTS = {
    "Clash Display": "Fontshare (Indian Type Foundry) — download manually from fontshare.com",
    "Satoshi": "Fontshare (Indian Type Foundry) — download manually from fontshare.com",
    "Tahoma": "ships with Windows",
    "Noto Sans SC": "large CJK family; install from Google Fonts manually if CJK type is needed",
}


def theme_families() -> dict:
    """Every family the themes declare -> the themes that ask for it."""
    wanted: dict = {}
    for path in sorted(THEMES.glob("*/theme.json")):
        try:
            fonts = (json.loads(path.read_text(encoding="utf-8")) or {}).get("fonts") or {}
        except (json.JSONDecodeError, OSError):
            continue
        for key in ("displayEn", "body", "mono", "cjk"):
            family = fonts.get(key)
            if family:
                wanted.setdefault(str(family), set()).add(path.parent.name)
    return wanted


def installed_families(python_executable: str | None = None) -> set:
    """What Pango can see, asked of the interpreter that actually renders."""
    from nolan.mathanim.render import available_fonts

    return {f.strip().lower() for f in available_fonts(python_executable)}


def _font_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise SystemExit("LOCALAPPDATA is unset — this installer targets Windows per-user fonts")
    directory = Path(local) / "Microsoft" / "Windows" / "Fonts"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _register(path: Path, family: str) -> None:
    """Register a per-user font under HKCU so Pango's win32 backend enumerates it."""
    import winreg

    key = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as handle:
        winreg.SetValueEx(handle, f"{family} (TrueType)", 0, winreg.REG_SZ, str(path))


def install(family: str, sources: list, font_dir: Path) -> list:
    """Download + register one family. Returns the notes to report."""
    notes = []
    for i, rel in enumerate(sources):
        url = RAW.format(urllib.parse.quote(rel))
        target = font_dir / Path(rel).name
        if target.is_file() and target.stat().st_size > 4096:
            notes.append(f"    {target.name} already present")
        else:
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = response.read()
            except (urllib.error.URLError, OSError) as exc:
                notes.append(f"    FAILED {rel}: {exc}")
                continue
            if len(data) < 4096:
                notes.append(f"    FAILED {rel}: {len(data)} bytes (not a font)")
                continue
            target.write_bytes(data)
            notes.append(f"    downloaded {target.name} ({len(data) // 1024} KB)")
        try:
            _register(target, family if i == 0 else f"{family} {Path(rel).stem.split('-')[-1]}")
        except OSError as exc:
            notes.append(f"    registry FAILED for {target.name}: {exc}")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(prog="install_theme_fonts")
    parser.add_argument("--check", action="store_true", help="report only; install nothing")
    args = parser.parse_args()

    wanted = theme_families()
    have = installed_families()
    missing = {f: t for f, t in wanted.items() if f.strip().lower() not in have}

    print(f"{len(wanted)} families across {len(list(THEMES.glob('*/theme.json')))} themes; "
          f"{len(wanted) - len(missing)} already visible to Manim")
    if not missing:
        print("nothing to install")
        return 0

    unavailable = {f: why for f, why in NOT_ON_GOOGLE_FONTS.items() if f in missing}
    installable = {f: GOOGLE_FONTS[f] for f in missing if f in GOOGLE_FONTS}
    unknown = sorted(set(missing) - set(installable) - set(unavailable))

    print(f"\n{len(installable)} installable from Google Fonts:")
    for family in sorted(installable):
        print(f"  {family:24} used by {', '.join(sorted(missing[family])[:3])}")
    if unavailable:
        print(f"\n{len(unavailable)} NOT on Google Fonts — install by hand or accept the "
              f"personality-matched substitute:")
        for family, why in sorted(unavailable.items()):
            print(f"  {family:24} {why}")
    if unknown:
        print(f"\n{len(unknown)} with no download mapping (add them to GOOGLE_FONTS): {unknown}")

    if args.check:
        return 0

    font_dir = _font_dir()
    print(f"\ninstalling into {font_dir}")
    for family, sources in sorted(installable.items()):
        print(f"  {family}")
        for note in install(family, sources, font_dir):
            print(note)

    after = installed_families()
    landed = sorted(f for f in installable if f.strip().lower() in after)
    still = sorted(f for f in installable if f.strip().lower() not in after)
    print(f"\nvisible to Manim now: {len(landed)}/{len(installable)}")
    if still:
        print(f"  still missing (a new process may be needed to pick them up): {still}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
