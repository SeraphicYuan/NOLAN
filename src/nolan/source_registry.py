"""Canonical visual asset-source registry and priority policy.

One source may participate in live provider search, Visual Lib harvesting,
HyperFrames recall, or key-asset precision. This module stays dependency-light
so every consumer can import the same policy without an application cycle.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, Optional, Tuple


ACQUISITION_TIERS = {
    "art": ["library", "clips_library", "transcript_lib", "transcript_frames", "visuallib",
            "rawpixel", "rawpixel_video", "artvee", "pdia", "wikimedia", "met", "artic",
            "rijksmuseum", "harvard", "cleveland", "wellcome", "europeana", "dpla",
            "smithsonian", "loc", "openverse", "ddgs"],
    "archival": ["library", "clips_library", "transcript_lib", "transcript_frames", "visuallib",
                 "rawpixel", "rawpixel_video", "archive", "archive_image", "pdia", "loc",
                 "smithsonian", "europeana", "dpla", "nasa", "nasa_video", "wikimedia",
                 "flickr", "pexels_video", "pixabay_video", "coverr_video", "ddgs"],
    "general": ["library", "clips_library", "transcript_lib", "transcript_frames", "rawpixel",
                "rawpixel_video", "pexels", "pixabay", "unsplash", "ddgs", "openverse",
                "pexels_video", "pixabay_video", "coverr_video", "flickr", "wikimedia", "nasa"],
}

HYBRID_PROVIDER_TIERS = {
    "art": ["rawpixel", "rawpixel_video", "artvee", "wikimedia", "met", "artic",
            "rijksmuseum", "harvard", "cleveland", "wellcome", "europeana", "dpla",
            "smithsonian", "loc", "openverse", "ddgs"],
    "archival": ["rawpixel", "rawpixel_video", "archive", "archive_image", "loc",
                 "smithsonian", "europeana", "dpla", "nasa", "nasa_video", "wikimedia",
                 "flickr", "pexels_video", "pixabay_video", "coverr_video", "ddgs"],
    "general": ["rawpixel", "rawpixel_video", "pexels", "pixabay", "unsplash", "ddgs",
                "openverse", "pexels_video", "pixabay_video", "coverr_video", "flickr",
                "wikimedia", "nasa", "nasa_video"],
}

KEY_ASSET_SOURCE_PREFERENCES = {
    "logo": ["rawpixel", "wikimedia", "openverse"],
    "portrait": ["rawpixel", "wikimedia", "loc", "smithsonian"],
    "artwork": ["rawpixel", "wikimedia", "met", "artvee", "artic", "rijksmuseum"],
    "document": ["rawpixel", "wikimedia", "archive_image", "loc"],
    "photo": ["rawpixel", "wikimedia", "archive_image", "loc", "smithsonian"],
    "map": ["rawpixel", "wikimedia", "loc"],
    "footage": ["rawpixel_video", "archive", "nasa_video"],
}

CURATED_SOURCES = {
    "visuallib", "rawpixel", "rawpixel_video", "artvee", "pdia", "artic", "met",
    "wellcome", "rijksmuseum", "harvard", "cleveland", "europeana", "dpla",
    "smithsonian", "loc", "nasa", "wikimedia",
}


@dataclass(frozen=True)
class SourceSpec:
    id: str
    title: str
    media: Tuple[str, ...] = ("image",)
    auth: str = "none"  # none | api_key | browser_session | local
    config_fields: Tuple[str, ...] = ()
    env_fields: Tuple[str, ...] = ()
    rights: str = "Per-item; acquisition gate required"
    docs_url: Optional[str] = None
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _s(source_id, title, **kwargs) -> SourceSpec:
    return SourceSpec(source_id, title, **kwargs)


SOURCE_SPECS: Dict[str, SourceSpec] = {
    "library": _s("library", "Picture Library", auth="local", rights="Locally held and gated"),
    "clips_library": _s("clips_library", "Clip Library", media=("video",), auth="local", rights="Locally held and gated"),
    "transcript_lib": _s("transcript_lib", "Transcript Library", media=("video",), auth="local", rights="Per source video"),
    "transcript_frames": _s("transcript_frames", "Transcript Frames", auth="local", rights="Derived locally from source video"),
    "visuallib": _s("visuallib", "Visual Lib", auth="local", rights="Per catalog item; fetched on demand"),
    "rawpixel": _s("rawpixel", "Rawpixel", auth="browser_session",
                   config_fields=("rawpixel_cdp_url", "rawpixel_cookie", "rawpixel_user_agent"),
                   env_fields=("RAWPIXEL_CDP_URL", "RAWPIXEL_COOKIE", "RAWPIXEL_USER_AGENT"),
                   rights="Free License or CC0/Public Domain per item", docs_url="https://www.rawpixel.com/",
                   description="Free + Public Domain structured search through authorised Chrome."),
    "rawpixel_video": _s("rawpixel_video", "Rawpixel Video", media=("video",), auth="browser_session",
                         config_fields=("rawpixel_cdp_url", "rawpixel_cookie", "rawpixel_user_agent"),
                         env_fields=("RAWPIXEL_CDP_URL", "RAWPIXEL_COOKIE", "RAWPIXEL_USER_AGENT"),
                         rights="Free License or CC0/Public Domain per item", docs_url="https://www.rawpixel.com/videos"),
    "ddgs": _s("ddgs", "DuckDuckGo Images", rights="Unknown/per-result; strict gate required"),
    "wikimedia": _s("wikimedia", "Wikimedia Commons", rights="Per-item open license or Public Domain", docs_url="https://commons.wikimedia.org/"),
    "loc": _s("loc", "Library of Congress", rights="Per-item rights advisory", docs_url="https://www.loc.gov/pictures/"),
    "nasa": _s("nasa", "NASA Images", rights="Mostly US Government/Public Domain", docs_url="https://images.nasa.gov/"),
    "nasa_video": _s("nasa_video", "NASA Video", media=("video",), rights="Mostly US Government/Public Domain", docs_url="https://images.nasa.gov/"),
    "openverse": _s("openverse", "Openverse", rights="Per-item Creative Commons/Public Domain", docs_url="https://openverse.org/"),
    "met": _s("met", "The Metropolitan Museum of Art", rights="Public Domain records only", docs_url="https://metmuseum.github.io/"),
    "artic": _s("artic", "Art Institute of Chicago", rights="CC0/Public Domain records only", docs_url="https://api.artic.edu/docs/"),
    "cleveland": _s("cleveland", "Cleveland Museum of Art", rights="CC0 records only", docs_url="https://openaccess-api.clevelandart.org/"),
    "wellcome": _s("wellcome", "Wellcome Collection", rights="Per-item open license", docs_url="https://developers.wellcomecollection.org/"),
    "artvee": _s("artvee", "Artvee", rights="Public Domain; basic download only", docs_url="https://artvee.com/"),
    "pdia": _s("pdia", "Public Domain Image Archive", rights="CC0/Public Domain", docs_url="https://pdimagearchive.org/"),
    "archive": _s("archive", "Internet Archive Video", media=("video",), rights="Per-item; strict gate required", docs_url="https://archive.org/"),
    "archive_image": _s("archive_image", "Internet Archive Images", rights="Per-item; strict gate required", docs_url="https://archive.org/"),
}


def _keyed(source_id, title, config_field, env_field, rights, docs_url, media=("image",)):
    SOURCE_SPECS[source_id] = _s(source_id, title, media=media, auth="api_key",
                                 config_fields=(config_field,), env_fields=(env_field,),
                                 rights=rights, docs_url=docs_url)


_keyed("pexels", "Pexels", "pexels_api_key", "PEXELS_API_KEY", "Pexels License", "https://www.pexels.com/api/")
_keyed("pexels_video", "Pexels Video", "pexels_api_key", "PEXELS_API_KEY", "Pexels License", "https://www.pexels.com/api/", ("video",))
_keyed("pixabay", "Pixabay", "pixabay_api_key", "PIXABAY_API_KEY", "Pixabay Content License", "https://pixabay.com/api/docs/")
_keyed("pixabay_video", "Pixabay Video", "pixabay_api_key", "PIXABAY_API_KEY", "Pixabay Content License", "https://pixabay.com/api/docs/", ("video",))
_keyed("smithsonian", "Smithsonian Open Access", "smithsonian_api_key", "SMITHSONIAN_API_KEY", "CC0/Open Access records", "https://www.si.edu/openaccess")
_keyed("europeana", "Europeana", "europeana_api_key", "EUROPEANA_API_KEY", "Per-item rights statement", "https://pro.europeana.eu/page/apis")
_keyed("dpla", "Digital Public Library of America", "dpla_api_key", "DPLA_API_KEY", "Per-item rights statement", "https://pro.dp.la/developers")
_keyed("flickr", "Flickr", "flickr_api_key", "FLICKR_API_KEY", "Per-item license", "https://www.flickr.com/services/api/")
_keyed("unsplash", "Unsplash", "unsplash_access_key", "UNSPLASH_ACCESS_KEY", "Unsplash License", "https://unsplash.com/developers")
_keyed("rijksmuseum", "Rijksmuseum", "rijksmuseum_api_key", "RIJKSMUSEUM_API_KEY", "Per-item open data rights", "https://data.rijksmuseum.nl/")
_keyed("harvard", "Harvard Art Museums", "harvard_art_api_key", "HARVARD_ART_API_KEY", "Per-item rights statement", "https://harvardartmuseums.org/collections/api")
_keyed("coverr_video", "Coverr Video", "coverr_api_key", "COVERR_API_KEY", "Coverr License", "https://coverr.co/", ("video",))


def _members(table: Dict[str, Iterable[str]]) -> set[str]:
    return {source for order in table.values() for source in order}


def all_source_ids() -> Tuple[str, ...]:
    ids = set(SOURCE_SPECS)
    ids.update(_members(ACQUISITION_TIERS))
    ids.update(_members(HYBRID_PROVIDER_TIERS))
    ids.update(_members(KEY_ASSET_SOURCE_PREFERENCES))
    return tuple(sorted(ids))


def source_spec(source_id: str) -> SourceSpec:
    return SOURCE_SPECS.get(source_id) or SourceSpec(source_id, source_id.replace("_", " ").title())


def source_roles(source_id: str) -> Tuple[str, ...]:
    roles = []
    if source_id in _members(ACQUISITION_TIERS): roles.append("acquisition")
    if source_id in _members(HYBRID_PROVIDER_TIERS): roles.append("hybrid_search")
    if source_id in _members(KEY_ASSET_SOURCE_PREFERENCES): roles.append("key_asset")
    if source_id in {"artic", "artvee", "cleveland", "loc", "met", "pdia", "rawpixel"}: roles.append("catalog_harvest")
    return tuple(roles)


def source_tier_positions(source_id: str) -> dict:
    def positions(table):
        return {intent: order.index(source_id) + 1 for intent, order in table.items() if source_id in order}
    return {"acquisition": positions(ACQUISITION_TIERS),
            "hybrid": positions(HYBRID_PROVIDER_TIERS),
            "key_asset": positions(KEY_ASSET_SOURCE_PREFERENCES)}


def tier_payload() -> dict:
    return {"acquisition": {k: list(v) for k, v in ACQUISITION_TIERS.items()},
            "hybrid": {k: list(v) for k, v in HYBRID_PROVIDER_TIERS.items()},
            "key_asset": {k: list(v) for k, v in KEY_ASSET_SOURCE_PREFERENCES.items()}}
