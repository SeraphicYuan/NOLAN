"""Provenance & quality gate for acquired assets.

Born from a real incident (2026-07): the Homer test project shipped a beat
whose full-frame artwork was an **Alamy preview with the watermark banner
baked in** — downloaded by an ungated matching path, stamped straight into
``scene.matched_asset`` with ``license: null``. Attribution listed it under
"VERIFY BEFORE PUBLISH", but nothing *blocked*.

This module is the ONE place that decides whether an acquired image/clip is
usable (wiring-checklist rule 4: one registry per decision). Acquisition
doors call it at two moments:

- ``check_candidate(result, tier)`` — BEFORE download: rights-managed
  stock-preview domains are rejected outright (their public URLs are
  watermarked previews by construction), and the archival tier requires a
  known-open source or license.
- ``check_file(path, tier, vision=...)`` — AFTER download: resolution floor,
  watermark-banner heuristic, optional vision watermark check.

Every acceptance door is named in :data:`ASSET_GATE_DOORS`;
``tests/test_asset_gate.py`` grep-verifies each door actually calls the gate
(docs claim, tests enforce). Rejections are LOUD: doors log what they dropped
and report it in their result payloads — no silent caps.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Policy tables
# --------------------------------------------------------------------------

# Rights-managed stock agencies: anything their public CDNs serve is a
# watermarked preview and/or unlicensed. Never usable, any tier.
STOCK_PREVIEW_HOSTS: Tuple[str, ...] = (
    "alamy.com", "alamyimages.fr", "alamy.de", "alamy.es", "alamy.it",
    "shutterstock.com", "gettyimages.", "istockphoto.com", "dreamstime.com",
    "stock.adobe.com", "ftcdn.net",            # Adobe Stock CDN
    "123rf.com", "depositphotos.com", "bigstockphoto.com",
    "agefotostock.com", "superstock.com", "mediastorehouse.com",
    "bridgemanimages.com", "canstockphoto.com", "colourbox.com",
    "stocksy.com", "pond5.com", "storyblocks.com", "envato.com",
    "elements.envato.com", "granger.com", "artres.com", "akg-images.",
)

# Providers whose results are open-access / public-domain by construction.
OPEN_ACCESS_SOURCES = frozenset({
    "wikimedia", "met", "artic", "cleveland", "rijksmuseum", "wellcome",
    "loc", "harvard", "europeana", "dpla", "smithsonian", "nga",
    "gutenberg", "internet_archive", "artvee",
})

# Providers whose platform license permits our use (attribution handled by
# the credits pipeline).
LICENSED_STOCK_SOURCES = frozenset({
    "pexels", "pexels_video", "pixabay", "pixabay_video", "unsplash",
})

# License strings that read as open regardless of provider.
_OPEN_LICENSE_RE = re.compile(
    r"public\s*domain|\bpd\b|cc0|cc[\s-]?by|creative\s*commons|"
    r"no\s+known\s+copyright|open\s*access", re.I)

# Sound-license policy (CC0-first, see docs/SOUND_DESIGN.md). Order matters:
# NC/ND must reject BEFORE the CC-BY matcher (a "by-nc" string contains "by").
_SND_NONFREE_RE = re.compile(
    r"non[\s-]?commercial|\bnc\b|no[\s-]?deriv(atives)?|\bnd\b|"
    r"licenses/by-nc|licenses/by-nd", re.I)
_SND_CC0_RE = re.compile(
    r"cc0|creative\s*commons\s*0|publicdomain/zero|public\s*domain|"
    r"no\s+known\s+copyright", re.I)
_SND_CCBY_RE = re.compile(r"licenses/by\b|attribution|cc[\s-]?by\b", re.I)

# Museum/institutional download hosts that never watermark their open-access
# derivatives — the VISION watermark check (~7s/asset) is skipped for these;
# the free banner heuristic still runs on everything. Aggregators (artvee,
# europeana redirects, unknown CDNs) keep the vision check.
TRUSTED_MEDIA_HOSTS: Tuple[str, ...] = (
    "upload.wikimedia.org", "images.metmuseum.org", "artic.edu",
    "clevelandart.org", "rijksmuseum.nl", "iiif.wellcomecollection.org",
    "tile.loc.gov", "ids.lib.harvard.edu", "media.nga.gov",
)


def needs_vision_check(url: Optional[str]) -> bool:
    """False when the file came from a trusted museum host (see above)."""
    if not url:
        return True
    u = str(url).lower()
    return not any(h in u for h in TRUSTED_MEDIA_HOSTS)


# Resolution floors per tier: (min shorter side, min total pixels).
# Archival art renders full-frame with camera zooms — it needs real pixels.
FLOORS = {
    "archival": (700, 600_000),
    "stock": (480, 300_000),
}

# --------------------------------------------------------------------------
# The doors manifest — every acquisition point that must call this gate.
# tests/test_asset_gate.py greps each named function/module for the calls.
# --------------------------------------------------------------------------
ASSET_GATE_DOORS = {
    "image_search.download_image": {
        "file": "src/nolan/image_search.py", "func": "def download_image",
        "calls": ["check_candidate"]},
    "art_sourcing.exact_title_pass": {
        "file": "src/nolan/art_sourcing.py", "func": "def exact_title_pass",
        "calls": ["check_candidate", "check_file"]},
    "external_assets.semantic_match_for_scene": {
        "file": "src/nolan/external_assets.py",
        "func": "def semantic_match_for_scene", "calls": ["check_candidate"]},
    "external_assets.external_match_for_scene": {
        "file": "src/nolan/external_assets.py",
        "func": "def external_match_for_scene", "calls": ["check_candidate"]},
    "asset_engine.external_clip": {
        "file": "src/nolan/asset_engine.py", "func": "def _download_external_clip",
        "calls": ["check_candidate"]},
    "asset_engine.fulfill_shots_wanted": {
        "file": "src/nolan/asset_engine.py", "func": "def fulfill_shots_wanted",
        "calls": ["check_candidate", "check_file"]},
    "cli_assets.match_broll": {
        "file": "src/nolan/cli/assets.py", "func": "def match_broll",
        "calls": ["check_candidate", "check_file"]},
    "evoke_broll.retrieve_stock": {
        "file": "src/nolan/evoke_broll.py", "func": "def _retrieve_stock",
        "calls": ["check_candidate"]},
    "imagelib.add_url": {
        "file": "src/nolan/imagelib/store.py", "func": "def add_url",
        "calls": ["check_file"]},
    "attribution.build_attribution": {
        "file": "src/nolan/attribution.py", "func": "def build_attribution",
        "calls": ["scan_files"]},
    "sfx_ingest.add": {
        "file": "src/nolan/cli/sfx.py", "func": "def sfx_add",
        "calls": ["check_sound"]},
    "sfx_search.fetch_to_library": {
        "file": "src/nolan/sfx_search.py", "func": "def fetch_to_library",
        "calls": ["check_sound"]},
}


@dataclass
class GateVerdict:
    ok: bool
    reasons: List[str] = field(default_factory=list)   # why it was rejected
    flags: List[str] = field(default_factory=list)     # non-blocking warnings

    def __bool__(self) -> bool:
        return self.ok


def clean_title(title) -> str:
    """Provider titles are often FILENAMES — 'Vergilius Vaticanus, fol 52r -
    wm-removed.jpg' rendered verbatim into an on-screen museum label. Strip
    extensions and technical suffixes; keep the human part."""
    t = str(title or "").strip()
    t = re.sub(r"\.(jpe?g|png|webp|tiff?|gif)$", "", t, flags=re.I)
    t = re.sub(r"\s*[-–—_]\s*(wm[- ]?removed|watermark[- ]?removed|cropped|"
               r"restored|edited|scan(ned)?|copy)\s*$", "", t, flags=re.I)
    t = re.sub(r"[_]+", " ", t)
    return t.strip(" -–—_")


# --------------------------------------------------------------------------
# Candidate-level checks (pre-download, metadata only)
# --------------------------------------------------------------------------

def blocked_host(url: Optional[str]) -> Optional[str]:
    """Return the matching blocklisted host fragment, or None."""
    if not url:
        return None
    u = str(url).lower()
    for host in STOCK_PREVIEW_HOSTS:
        if host in u:
            return host
    return None


def _license_known_open(result) -> bool:
    src = (getattr(result, "source", None) or "").lower()
    lic = getattr(result, "license", None) or ""
    if src in OPEN_ACCESS_SOURCES:
        return True
    return bool(_OPEN_LICENSE_RE.search(lic))


def _license_usable(result) -> bool:
    src = (getattr(result, "source", None) or "").lower()
    return src in LICENSED_STOCK_SOURCES or _license_known_open(result)


def check_sound(result, source: str = "freesound") -> GateVerdict:
    """Gate an AUDIO asset before it enters the curated SFX library.

    The audio door (asset_gate is otherwise image-only). License policy is
    CC0-first (docs/SOUND_DESIGN.md):
      - CC0 / public domain            → pass, no attribution needed.
      - a source in LICENSED_STOCK_SOURCES → pass (platform license; no credit).
      - CC-BY / attribution family      → pass ONLY with a non-empty attribution
        line (flagged for the credits pipeline); reject if the credit is missing.
      - NonCommercial / NoDerivatives / unknown → reject (unusable for SFX).

    `result` is an SFXResult-like object or a dict carrying `license`,
    `attribution`, and optionally `source`.
    """
    def _g(key):
        if isinstance(result, dict):
            return result.get(key)
        return getattr(result, key, None)

    v = GateVerdict(ok=True)
    lic = (_g("license") or "").strip()
    attr = (_g("attribution") or "").strip()
    src = (_g("source") or source or "").lower()

    if not lic:
        v.ok = False
        v.reasons.append("no license string on the sound")
        return v
    if src in LICENSED_STOCK_SOURCES:
        return v
    if _SND_NONFREE_RE.search(lic):
        v.ok = False
        v.reasons.append(f"non-commercial / no-derivatives license unusable for SFX: {lic!r}")
        return v
    if _SND_CC0_RE.search(lic):
        return v
    if _SND_CCBY_RE.search(lic):
        if not attr:
            v.ok = False
            v.reasons.append(f"attribution required for {lic!r} but none captured")
        else:
            v.flags.append("attribution-required")   # credits pipeline must emit it
        return v
    v.ok = False
    v.reasons.append(f"license not recognized as SFX-usable: {lic!r}")
    return v


def check_candidate(result, tier: str = "stock") -> GateVerdict:
    """Gate a search result BEFORE downloading it.

    - Blocklisted stock-preview domain → reject (any tier).
    - tier="archival": license must be known-open (open-access source or an
      open license string) — a named artwork with unknown rights is exactly
      the Alamy failure mode.
    - tier="stock": unknown license is allowed but FLAGGED (credits pipeline
      lists it under VERIFY BEFORE PUBLISH).
    - Metadata resolution below the tier floor → reject (saves the download).
    """
    v = GateVerdict(ok=True)
    for url in (getattr(result, "url", None), getattr(result, "source_url", None),
                getattr(result, "thumbnail_url", None)):
        host = blocked_host(url)
        if host:
            v.ok = False
            v.reasons.append(f"stock-preview domain: {host}")
            return v

    if tier == "archival":
        if not _license_known_open(result):
            v.ok = False
            v.reasons.append(
                f"license unknown for archival tier (source="
                f"{getattr(result, 'source', None)!r}) — open-access required")
            return v
    else:
        if not _license_usable(result):
            v.flags.append("license-unknown")

    w = getattr(result, "width", None) or 0
    h = getattr(result, "height", None) or 0
    if w and h:
        min_dim, min_px = FLOORS.get(tier, FLOORS["stock"])
        if min(w, h) < min_dim or w * h < min_px:
            v.ok = False
            v.reasons.append(f"below resolution floor ({w}x{h}, tier={tier})")
    return v


# --------------------------------------------------------------------------
# File-level checks (post-download, pixels)
# --------------------------------------------------------------------------

def _probe(path: Path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def banner_suspect(path: Path) -> bool:
    """Detect an agency banner strip (the Alamy signature): a near-uniform
    very dark or very bright band at the top or bottom edge carrying
    high-contrast glyphs. Deterministic and free — runs on every download.
    """
    try:
        from PIL import Image
        with Image.open(path) as im:
            g = im.convert("L")
            w, h = g.size
            if w < 64 or h < 64:
                return False
            band_h = max(8, int(h * 0.07))
            px = list(g.getdata())

            def band(rows):
                vals = []
                for y in rows:
                    vals.extend(px[y * w:(y + 1) * w])
                return vals

            edges = (
                (range(0, band_h), range(band_h, 2 * band_h)),
                (range(h - band_h, h), range(h - 2 * band_h, h - band_h)),
            )
            for rows, inner_rows in edges:
                vals = band(rows)
                n = len(vals)
                if not n:
                    continue
                mean = sum(vals) / n
                dark = mean < 48
                bright = mean > 215
                if not (dark or bright):
                    continue
                # a banner is a STRIP, discontinuous with the image body; a
                # museum photo on black continues dark past the band (the
                # Douris-kylix false positive)
                inner = band(inner_rows)
                if inner:
                    inner_mean = sum(inner) / len(inner)
                    if abs(mean - inner_mean) < 30:
                        continue
                # glyphs = a small share of strongly contrasting pixels
                if dark:
                    contrast = sum(1 for v in vals if v > 170)
                else:
                    contrast = sum(1 for v in vals if v < 90)
                # a plain letterbox bar is ~0% contrast pixels; glyphs/logos
                # run 0.2%–35% of the band
                share = contrast / n
                if 0.002 <= share <= 0.35:
                    return True
    except Exception:
        return False
    return False


def check_file(path, tier: str = "stock",
               vision: Optional[Callable[[Path], Optional[bool]]] = None) -> GateVerdict:
    """Gate a downloaded image file. Resolution floor → banner heuristic →
    optional vision watermark check (``vision(path) -> True/False/None``;
    None = unavailable, treated as unchecked, flagged)."""
    v = GateVerdict(ok=True)
    p = Path(path)
    size = _probe(p)
    if size:
        w, h = size
        min_dim, min_px = FLOORS.get(tier, FLOORS["stock"])
        if min(w, h) < min_dim or w * h < min_px:
            v.ok = False
            v.reasons.append(f"below resolution floor ({w}x{h}, tier={tier})")
            return v
    if banner_suspect(p):
        v.ok = False
        v.reasons.append("watermark banner strip detected")
        return v
    if vision is not None:
        try:
            verdict = vision(p)
        except Exception as e:
            verdict = None
            logger.warning("vision watermark check failed for %s: %s", p, e)
        if verdict is True:
            v.ok = False
            v.reasons.append("vision: watermark/logo overlay detected")
        elif verdict is None:
            v.flags.append("watermark-vision-unavailable")
    return v


# --------------------------------------------------------------------------
# Vision watermark checker (same provider plumbing as imagelib's describer)
# --------------------------------------------------------------------------

WATERMARK_PROMPT = (
    "Does this image contain a stock-photo watermark, agency logo overlay, "
    "repeated semi-transparent text, or an attribution banner strip "
    "(e.g. alamy, shutterstock, getty, dreamstime)? Look carefully at "
    "corners, edges and any diagonal tiled text. Answer with exactly one "
    "word: YES or NO."
)


def make_watermark_checker(config, *, provider: Optional[str] = None
                           ) -> Optional[Callable[[Path], Optional[bool]]]:
    """Build a sync ``check(path) -> bool|None`` vision watermark checker.

    Returns None when no vision provider can be built (gate then runs
    deterministic checks only and flags the file unchecked).
    """
    try:
        from nolan.vision import create_vision_provider
        from nolan.webui.operations import _select_vision
        prov_name = provider or getattr(getattr(config, "vision", None),
                                        "provider", None)
        if not prov_name:
            return None
        vcfg = _select_vision(config, prov_name, None, None, None)
        vprovider = create_vision_provider(vcfg)
    except Exception:
        return None

    def check(path) -> Optional[bool]:
        from nolan.segment.render import _run_async
        try:
            text = _run_async(vprovider.describe_image(Path(path), WATERMARK_PROMPT))
        except Exception:
            return None
        t = (text or "").strip().upper()
        if t.startswith("YES"):
            return True
        if t.startswith("NO"):
            return False
        return None

    return check


# --------------------------------------------------------------------------
# Post-hoc scanning (credits pipeline: catch what predates the gate)
# --------------------------------------------------------------------------

def scan_files(paths, *, vision=None) -> List[dict]:
    """Banner-scan existing asset files (legacy, pre-gate). Returns a list of
    ``{"path", "reasons"}`` for suspects — the credits pipeline surfaces them
    as WATERMARK SUSPECT entries."""
    out = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        reasons = []
        if banner_suspect(p):
            reasons.append("watermark banner strip detected")
        if not reasons and vision is not None:
            try:
                if vision(p) is True:
                    reasons.append("vision: watermark/logo overlay detected")
            except Exception:
                pass
        if reasons:
            out.append({"path": str(p), "reasons": reasons})
    return out
