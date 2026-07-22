"""The Key-Assets KIND registry — the module contract's "registry entry".

Two typed vocabularies + their rules:
  ENTITY_KINDS — what a hero subject IS (person / organization / place / event / work / concept).
  ASSET_TYPES  — how we DEPICT it (portrait / logo / …), each carrying PROCESSING rules (cutout,
                 identity-verify, trim) and a RESOLUTION strategy (which sources to prefer in P2).

Decompose validates against this so the LLM can't invent kinds; P2 reads the processing/resolution
rules. Keep it the single source of truth — add a kind here, not in a prompt string.
"""
from __future__ import annotations

from typing import Dict, List

# What a hero subject IS.
ENTITY_KINDS = ("person", "organization", "place", "event", "work", "concept")

# How we depict it. `processing`: deterministic conditioning steps (P2/condition). `collage`: default
# for whether this type wants a background-removed cutout. `resolve`: preferred source order (P2/resolve)
# — institutional/named-work first, generic web last (a low-literal museum hit is a feature, not junk).
ASSET_TYPES: Dict[str, Dict] = {
    "portrait": {"processing": ["identity_verify"], "collage": False,
                 "resolve": ["title_match", "wikimedia", "institutional", "web"]},
    "logo":     {"processing": ["cutout", "trim"], "collage": True,
                 "resolve": ["wikimedia", "official", "web"]},
    "product":  {"processing": ["cutout", "trim"], "collage": True,
                 "resolve": ["official", "wikimedia", "web"]},
    "artwork":  {"processing": ["crop", "identity_verify"], "collage": False,
                 "resolve": ["title_match", "museum", "wikimedia", "web"]},
    "document": {"processing": ["crop"], "collage": False,
                 "resolve": ["archive", "wikimedia", "web"]},
    "photo":    {"processing": [], "collage": False,
                 "resolve": ["wikimedia", "archive", "web"]},
    "map":      {"processing": [], "collage": False,
                 "resolve": ["wikimedia", "web"]},
    "footage":  {"processing": ["trim"], "collage": False,
                 "resolve": ["archive_movies", "provider_video", "web"]},
}

# The default representation for a bare entity kind (used when the LLM names an entity but no asset).
DEFAULT_ASSET_BY_KIND: Dict[str, str] = {
    "person": "portrait", "organization": "logo", "place": "photo",
    "event": "footage", "work": "artwork", "concept": "photo",
}

PRIORITIES = ("hero", "supporting")
RELEVANCES = ("exact", "related")


def normalize_relevance(r: str) -> str:
    """Map a raw relevance onto RELEVANCES; default 'exact'. 'related' = a directionally-relevant
    clip/photo that fits the era/mood without being a specific named match."""
    r = (r or "").strip().lower()
    alias = {"literal": "exact", "direct": "exact", "specific": "exact", "match": "exact",
             "evocative": "related", "mood": "related", "thematic": "related",
             "tangential": "related", "adjacent": "related", "contextual": "related"}
    r = alias.get(r, r)
    return r if r in RELEVANCES else "exact"


def normalize_kind(k: str) -> str:
    """Map a raw LLM kind onto ENTITY_KINDS (with a few common synonyms); default 'concept'."""
    k = (k or "").strip().lower()
    alias = {"company": "organization", "org": "organization", "brand": "organization",
             "institution": "organization", "people": "person", "individual": "person",
             "location": "place", "city": "place", "country": "place", "moment": "event",
             "artifact": "work", "object": "work", "artwork": "work", "ad": "work",
             "campaign": "work", "idea": "concept", "theme": "concept"}
    k = alias.get(k, k)
    return k if k in ENTITY_KINDS else "concept"


def normalize_asset_type(t: str) -> str:
    """Map a raw LLM asset type onto ASSET_TYPES (with synonyms); default 'photo'."""
    t = (t or "").strip().lower()
    alias = {"headshot": "portrait", "face": "portrait", "person": "portrait",
             "brand": "logo", "logotype": "logo", "wordmark": "logo", "emblem": "logo",
             "painting": "artwork", "illustration": "artwork", "poster": "artwork", "ad": "document",
             "advertisement": "document", "print ad": "document", "letter": "document",
             "newspaper": "document", "chart": "document", "picture": "photo", "image": "photo",
             "video": "footage", "clip": "footage", "film": "footage", "reel": "footage"}
    t = alias.get(t, t)
    return t if t in ASSET_TYPES else "photo"


def normalize_priority(p: str) -> str:
    p = (p or "").strip().lower()
    return p if p in PRIORITIES else "supporting"


def collage_default(asset_type: str) -> bool:
    return bool(ASSET_TYPES.get(normalize_asset_type(asset_type), {}).get("collage", False))


def processing_for(asset_type: str) -> List[str]:
    return list(ASSET_TYPES.get(normalize_asset_type(asset_type), {}).get("processing", []))


def resolution_for(asset_type: str) -> List[str]:
    return list(ASSET_TYPES.get(normalize_asset_type(asset_type), {}).get("resolve", ["web"]))
