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
#
# "By construction" is the load-bearing phrase. A source belongs here only if EVERYTHING it can
# hand us is open — not if it merely holds a lot of open material.
OPEN_ACCESS_SOURCES = frozenset({
    "wikimedia", "met", "artic", "cleveland", "rijksmuseum", "wellcome",
    "harvard", "europeana", "dpla", "smithsonian", "nga",
    "gutenberg", "internet_archive", "artvee",
})

# Sources that serve their OWN clean derivatives, so the banner heuristic is skipped on their
# thumbnails. A SEPARATE QUESTION from rights, and separating the two is the whole point.
#
# `OPEN_ACCESS_SOURCES` was doing both jobs, which is fine while they coincide and wrong the
# moment they don't. The Public Domain Image Archive serves unwatermarked images from its own
# CDN — but 16% of its rows carry a rights caveat (US-only, share-alike, no-known-copyright), so
# putting it in the set above would have made `_license_known_open` wave every one of them
# through on the strength of the source's name. That is precisely the mistake `loc` is recorded
# below for.
#
# Measured cost of NOT having this: the heuristic hunts "a near-uniform band, discontinuous with
# the body, carrying a few contrasting pixels", which on a 19th-century BOOK PLATE is the printed
# caption under the illustration. It retired 51 of the first 765 PDIA thumbnails — "The Octopus
# (Octopus vulgaris)", "Pontoppidan's Sea Serpent" — none of them watermarked, all of them from
# one book.
# `loc` joins for the same reason and NOT for the rights reason — the Library of Congress serves
# its own scans from its own tile server and does not watermark them, while its rights still vary
# per item (which is exactly why it is absent from OPEN_ACCESS_SOURCES above). Characterised
# before wiring, as the checklist requires: the refusals were inspected BY EYE and are the
# posters' own typography — a 1936 Federal Art Project exhibition poster carries a flat colour
# band with "EXHIBITION" set across it, which is precisely the heuristic's signature (a
# near-uniform band, discontinuous with the body, a few contrasting pixels). A poster is the
# worst possible subject for this check, because graphic design is made of such bands.
UNWATERMARKED_SOURCES = OPEN_ACCESS_SOURCES | frozenset({"pdia", "loc"})

# NOT uniformly open, and therefore NOT in the set above. `loc` used to be, which meant the gate
# waved through anything from the Library of Congress on the strength of the institution's name.
# The LoC holds an enormous amount of public-domain material AND a great deal that is restricted,
# rights-undetermined, or licensed only for research — its own rights advisories are written PER
# COLLECTION, not per institution.
#
# So rights are asserted per curated collection, and only for collections whose advisory has
# actually been read. Anything outside this table falls through to the normal license check,
# where "unknown" means refused at the archival tier — the safe direction.
#
# Sources of truth are the collection's own rights page; each entry records it so the assertion
# can be re-checked rather than trusted.
PER_COLLECTION_RIGHTS: dict = {
    "loc": {
        # https://www.loc.gov/collections/fsa-owi-black-and-white-negatives/about-this-collection/rights-and-restrictions/
        "fsa-owi-black-and-white-negatives": {
            "open": True,
            "note": "No known restrictions. ~171k items, US government work (FSA/OWI).",
        },
    },
}


def collection_is_open(source: Optional[str], collection: Optional[str]) -> Optional[bool]:
    """Rights for ONE curated collection of a not-uniformly-open institution.

    Returns True (asserted open), False (asserted restricted), or **None — unknown**, which is a
    real answer and must not be read as either. An institution that is open "mostly" is the exact
    shape that produces a rights incident.
    """
    table = PER_COLLECTION_RIGHTS.get((source or "").strip().lower())
    if not table:
        return None
    entry = table.get((collection or "").strip().lower())
    if entry is None:
        return None
    return bool(entry.get("open"))

# Providers whose platform license permits our use (attribution handled by
# the credits pipeline).
LICENSED_STOCK_SOURCES = frozenset({
    "pexels", "pexels_video", "pixabay", "pixabay_video", "unsplash",
})

# License strings that read as open regardless of provider.
#
# "no known RESTRICTIONS" sits beside "no known COPYRIGHT" because they are the same class of
# claim — an institution stating what it knows — and the Library of Congress uses the former as
# its standard machine-readable phrasing, per ITEM, in the field `rights_advisory`. Accepting the
# one while refusing the other would be a distinction about wording, not about rights.
#
# It is deliberately NOT the same as putting `loc` in OPEN_ACCESS_SOURCES. That would vouch for
# the institution, and the Library holds a great deal that is restricted or rights-undetermined
# (see the note on PER_COLLECTION_RIGHTS). This accepts the CLAIM, which each row carries or does
# not: `imagelib.loc._clears_rights` refuses an absent advisory outright, so silence never
# reaches here as permission.
_OPEN_LICENSE_RE = re.compile(
    r"public\s*domain|\bpd\b|cc0|cc[\s-]?by|creative\s*commons|"
    r"no\s+known\s+copyright|no\s+known\s+restrictions|open\s*access", re.I)

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
    # (see UNWATERMARKED_SOURCES below for the source-level equivalent)
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
    # NO RESOLUTION FLOOR — for sources where CURATION is the filter and a small scan is a
    # deliberate inclusion rather than a failure.
    #
    # Measured on the Public Domain Image Archive, a hand-curated 11,197-image collection: the
    # archival floor refused 37% of it, and the refusals were not junk. It rejected a 1024x661
    # print outright — 1024 wide, fine full-frame at 1080p and fine at any size as an inset —
    # because the floor tests the SHORT side. Worse, it cut curated sets in half: "Design No. 9",
    # "No. 19" and "No. 60" are plates from one book at 455x761, and admitting some while
    # refusing others fragments exactly the thing a collection view exists to show.
    #
    # This waives ONLY the floor. `curated` keeps archival-strength RIGHTS (see check_candidate),
    # because a permissive size rule must never become a permissive licence rule — and the real
    # size defence stays where it belongs, at promotion, where `check_file` measures actual bytes
    # for something a human has chosen to hold.
    "curated": (0, 0),
}
# Tiers that demand a KNOWN-OPEN licence rather than merely flagging an unknown one. Named as a
# set because "is this tier strict about rights?" and "what is this tier's pixel floor?" are two
# questions, and answering both from one string is how `curated` would have silently relaxed
# rights while only meaning to relax pixels.
STRICT_RIGHTS_TIERS = frozenset({"archival", "curated"})

# HIGH-ASPECT WAIVER. The short-side rule assumes roughly rectangular content, and a museum
# corpus is full of things that are legitimately long and thin — a halberd, a partisan, a basting
# spoon, a pillar print. Those can NEVER clear a minimum-dimension test however good the
# photograph, and the test was refusing them while they carried twice the required pixels:
# measured on a 500-row backfill, 5 of 6 refusals had >600k content pixels and failed on the
# short side alone (a halberd at 632x2034 = 1.29M px, a corsesca at 608x2250 = 1.37M px).
#
# So when content is genuinely elongated, total pixels decide. The short side still has an
# absolute floor — half the tier's minimum — because a 220px-wide sliver is unusable at any
# length, and that one (a partisan at 220x2118) stays refused.
_HIGH_ASPECT = 2.2
_HIGH_ASPECT_SHORT = 0.5


def clears_floor(w: int, h: int, tier: str = "stock") -> bool:
    """Does this content clear the tier's resolution floor?

    ONE implementation, called by both `check_candidate` (declared dimensions) and `check_file`
    (measured content) — a picture must not be admitted by one door and refused by the other.
    """
    min_dim, min_px = FLOORS.get(tier, FLOORS["stock"])
    if not w or not h:
        return True                      # unknown size is not a refusal; other checks still run
    if w * h < min_px:
        return False
    short, long_ = min(w, h), max(w, h)
    if short >= min_dim:
        return True
    return (long_ / short) >= _HIGH_ASPECT and short >= min_dim * _HIGH_ASPECT_SHORT

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
    # Visual Lib (the not-held tier) fetches bytes twice: a thumbnail at harvest and the real
    # image at promotion. Both are doors. An un-gated discovery tier would be a laundering route
    # into the library around the gate `add_url` applies — index the watermarked preview as
    # "metadata only", then promote it.
    "imagelib.add_discovery": {
        "file": "src/nolan/imagelib/store.py", "func": "def add_discovery",
        "calls": ["check_candidate", "banner_suspect"]},
    "imagelib.promote_to_held": {
        "file": "src/nolan/imagelib/store.py", "func": "def promote_to_held",
        "calls": ["check_file", "blocked_host"]},
    "attribution.build_attribution": {
        "file": "src/nolan/attribution.py", "func": "def build_attribution",
        "calls": ["scan_files"]},
    # The door moved, the gate did not. `nolan sfx add` was extracted into
    # nolan.sound.curate so the CLI, the /sfx webUI route and the source-adapter
    # registry drive ONE implementation (c6337c9); this entry kept pointing at the
    # CLI wrapper, which now only formats output. Re-adding a call in the CLI would
    # have been two gates for one decision (checklist class 4) — the manifest is
    # what was stale, not the wiring.
    "sfx_ingest.add": {
        "file": "src/nolan/sound/curate.py", "func": "def add_sound",
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
    # A not-uniformly-open institution may still vouch for a NAMED curated collection. Only an
    # explicit True counts — unknown falls through to the license string, where "unknown" is a
    # refusal at the archival tier.
    if collection_is_open(src, getattr(result, "collection", None)) is True:
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

    if tier in STRICT_RIGHTS_TIERS:
        if not _license_known_open(result):
            v.ok = False
            v.reasons.append(
                f"license unknown for {tier} tier (source="
                f"{getattr(result, 'source', None)!r}) — open-access required")
            return v
    else:
        if not _license_usable(result):
            v.flags.append("license-unknown")

    w = getattr(result, "width", None) or 0
    h = getattr(result, "height", None) or 0
    if w and h and not clears_floor(w, h, tier):
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


def content_dims(path) -> Optional[Tuple[int, int]]:
    """The dimensions the resolution floor must judge: the PICTURE, not the FILE.

    Museum object photography is an object on a plain sweep, so the file is routinely far larger
    than the asset. Measured over the live corpus: 22% of rows carry >=5% dead margin on some
    side and coins run 29-32%, which means a 3000x1511 coin photo at 31% content is really a
    2197x644 asset. The floor was reading the file and admitting those as archival-grade.

    Cropping cannot create pixels, which is why this REFUSES rather than merely flags: an asset
    whose content is 644px tall is 644px tall however it is trimmed.

    Falls back to the file's own dimensions whenever measurement is unavailable — an image the
    detector cannot read must not become an image the gate cannot refuse.
    """
    try:
        from nolan.pixels import measure
    except Exception:                                    # numpy/Pillow unavailable
        return _probe(Path(path))
    facts = measure(path)
    if facts is None:
        return _probe(Path(path))
    return facts.effective_dims


def watermark_risk(source: Optional[str]) -> str:
    """How much a WATERMARK claim from this source's own pixels should be trusted.

    The backstop for a measured weakness. A synthetic-watermark pass over 6 images x 3 styles
    (diagonal tile, corner credit bar, centre stamp) scored 23/24 with zero false positives on
    clean images — but the single miss was a white tile at 27% opacity on a pale fresco, nearly
    invisible at 512px. A faint watermark is still a RIGHTS signal even when it is not a pixel
    problem, so detection alone cannot be the whole answer.

    Provenance is the other half, and it is free:

      'trusted' — an institution serving its own open-access derivative cannot be serving an
                  agency watermark. Absence of detection is meaningful here.
      'suspect' — a scraped or unknown source. Absence of detection means only that we did not
                  see one at thumbnail size; treat it as unproven, not as clean.
    """
    src = (source or "").strip().lower()
    if src in OPEN_ACCESS_SOURCES or src in LICENSED_STOCK_SOURCES:
        return "trusted"
    return "suspect"


def check_file(path, tier: str = "stock",
               vision: Optional[Callable[[Path], Optional[bool]]] = None,
               source: Optional[str] = None) -> GateVerdict:
    """Gate a downloaded image file. Resolution floor → banner heuristic →
    optional vision watermark check (``vision(path) -> True/False/None``;
    None = unavailable, treated as unchecked, flagged).

    The floor judges CONTENT dimensions (see :func:`content_dims`), so dead margin cannot buy an
    asset a pass it has not earned.
    """
    v = GateVerdict(ok=True)
    p = Path(path)
    size = content_dims(p)
    if size:
        w, h = size
        if not clears_floor(w, h, tier):
            v.ok = False
            file_size = _probe(p)
            detail = ""
            if file_size and tuple(file_size) != (w, h):
                detail = f", file is {file_size[0]}x{file_size[1]} incl. dead margin"
            v.reasons.append(
                f"below resolution floor (content {w}x{h}{detail}, tier={tier})")
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
    elif watermark_risk(source) == "suspect":
        # No vision check ran and provenance does not vouch for this file. Say so rather than
        # letting a silent pass read as a clean bill of health — the measured detector miss was a
        # 27%-opacity tile on a pale fresco, which is exactly the case pixels alone lose.
        v.flags.append("watermark-unverified-source")
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
