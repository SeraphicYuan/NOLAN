"""The registry of VIDEO source kinds — what a `kind` string means, in one place.

`kind` was a bare string branched on in 25 places across four files, and the branches were
*exclusion lists*: the Sources tile decided whether to offer Sync with `(archive||cc) ? "" : Sync`,
so a newly added kind inherited YouTube's behaviour unless someone remembered to name it. Adding
`tdf` already required hand-editing `_survey_key`, `_thumb_for` and `survey_channel`, and its tile
would have shipped a Sync button that called `list_channel("topdocumentaryfilms.com")`.

This is `imagelib.harvest.SourceAdapter`'s shape for video: declare what differs, so the UI and the
dispatchers can ASK instead of matching on strings.

**`ref_kind` is the distinction that actually matters.** Two shapes of source hide behind one word:

* `user` — you supply a reference. A channel URL, an @handle, a collection id. There can be many,
  and Sync re-enumerates that one reference.
* `singleton` — THE ADAPTER IS THE SOURCE. There is one topdocumentaryfilms.com; `_survey_key`
  ignores the ref entirely because it is a formality. You do not *add* one of these, you *enable*
  it, which is why the Sources tab lists them as connectors rather than behind a text box that
  asks for an identifier there is no second value for.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# How a kind is enumerated, and the constraint that comes with it. Mirrors
# `imagelib.harvest.ENUMERATION` — a job measured in hours should say up front what bounds it.
ENUMERATION: Dict[str, Dict[str, str]] = {
    "channel-listing": {
        "purpose": "Page a channel's uploads newest-first via yt-dlp.",
        "constraint": "Cheap and complete; a sync fetches only what is newer than the last crawl.",
    },
    "collection-search": {
        "purpose": "Page an archive.org collection via advancedsearch.",
        "constraint": "~10k deep-paging window per query — a bigger collection is split by "
                      "publicdate until every slice fits (see archive_source._date_partitions).",
    },
    "site-crawl": {
        "purpose": "A bespoke crawler for one site that indexes video hosted elsewhere.",
        "constraint": "Slowest and most fragile: a real browser, paced, and only as stable as the "
                      "site's markup. Prefer an incremental sync over a full re-crawl.",
    },
}


@dataclass(frozen=True)
class SourceKind:
    """One family of video source, and everything a caller needs to know without a string match."""
    id: str
    label: str
    icon: str
    # 'user'      — the caller supplies a reference (channel URL / @handle / collection id)
    # 'singleton' — the adapter IS the source; the ref is a formality
    ref_kind: str
    enumeration: str
    # Rows from this family are copyright-free unless a per-item licence says otherwise. Documentary
    # YouTube is NEVER free; a `youtube_cc` channel is free by definition; an archive collection is
    # free only when the curator asserted it when adding.
    copyright_free_default: bool = False
    # Can the length filter bite? It needs a duration, and where one comes from is per family:
    # youtube 100% (yt-dlp), archive ~14% (advancedsearch `runtime` is usually absent),
    # tdf 100% (the WordPress API publishes `runtime` in minutes).
    duration_coverage: str = "unknown"
    # Can a caller ask for only what is NEW since the last crawl?
    incremental_sync: bool = False
    ref_placeholder: str = ""
    notes: str = ""

    def __post_init__(self):
        if self.ref_kind not in ("user", "singleton"):
            raise ValueError(f"{self.id}: ref_kind must be 'user' or 'singleton'")
        if self.enumeration not in ENUMERATION:
            raise ValueError(f"{self.id}: unknown enumeration {self.enumeration!r} "
                             f"(known: {sorted(ENUMERATION)})")

    @property
    def is_singleton(self) -> bool:
        return self.ref_kind == "singleton"

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "label": self.label, "icon": self.icon, "ref_kind": self.ref_kind,
                "enumeration": self.enumeration,
                "enumeration_constraint": ENUMERATION[self.enumeration]["constraint"],
                "copyright_free_default": self.copyright_free_default,
                "duration_coverage": self.duration_coverage,
                "incremental_sync": self.incremental_sync,
                "ref_placeholder": self.ref_placeholder, "notes": self.notes,
                "singleton": self.is_singleton}


KINDS: Dict[str, SourceKind] = {
    "youtube": SourceKind(
        id="youtube", label="YouTube channel", icon="📺", ref_kind="user",
        enumeration="channel-listing", copyright_free_default=False,
        duration_coverage="every row (yt-dlp)", incremental_sync=True,
        ref_placeholder="channel URL / @handle / id — e.g. https://www.youtube.com/bloomberg",
        notes="A documentary or news channel. Copyrighted: a searchable REFERENCE, never usable "
              "b-roll — the acquire engine must not treat these as free.",
    ),
    "youtube_cc": SourceKind(
        id="youtube_cc", label="Copyright-free YouTube", icon="🆓", ref_kind="user",
        enumeration="channel-listing", copyright_free_default=True,
        duration_coverage="every row (yt-dlp)", incremental_sync=True,
        ref_placeholder="channel URL / @handle — e.g. https://www.youtube.com/@FreeHDvideos",
        notes="Stock / b-roll channels, every video treated as copyright-free. Often uncaptioned, "
              "so the visual tier and the downloadable clip are the value, not the transcript.",
    ),
    "archive": SourceKind(
        id="archive", label="archive.org collection", icon="🏛", ref_kind="user",
        enumeration="collection-search", copyright_free_default=False,
        duration_coverage="~14% of rows", incremental_sync=False,
        ref_placeholder="collection id / URL — e.g. prelinger",
        notes="Whisper ASR transcripts plus rich metadata (subject tags, runtime, licence). "
              "copyright_free is the CURATOR's assertion made when adding, because only ~18% of "
              "even a wholly-PD collection carries a per-item licence.",
    ),
    "tdf": SourceKind(
        id="tdf", label="topdocumentaryfilms.com", icon="🎞", ref_kind="singleton",
        enumeration="site-crawl", copyright_free_default=False,
        duration_coverage="every row (API `runtime`)", incremental_sync=True,
        notes="A curated INDEX over YouTube/Vimeo, not a host: every entry resolves to a video "
              "elsewhere, so ingest and transcripts reuse the YouTube path unchanged. Behind a "
              "Cloudflare managed challenge, so the crawl drives a real browser and recycles its "
              "context every ~2 navigations.",
    ),
}


def kind(kind_id: str) -> SourceKind:
    """The registered kind, or the youtube default. Unknown kinds fall back to the SAFEST family —
    `youtube` is copyright-free=False — because a wrong guess in the other direction would mark a
    copyrighted documentary as free footage."""
    return KINDS.get(kind_id) or KINDS["youtube"]


def all_kinds() -> List[SourceKind]:
    return [KINDS[k] for k in sorted(KINDS)]


def user_addable() -> List[SourceKind]:
    """Kinds the "add a source" box can offer — the ones that take a reference."""
    return [k for k in all_kinds() if k.ref_kind == "user"]


def connectors() -> List[SourceKind]:
    """Singleton site-crawlers. You enable these; there is no second instance to name."""
    return [k for k in all_kinds() if k.is_singleton]


def payload() -> Dict[str, Any]:
    """What the UI renders from — so a kind added here appears without touching a template."""
    return {"kinds": [k.to_dict() for k in all_kinds()],
            "addable": [k.id for k in user_addable()],
            "connectors": [k.id for k in connectors()],
            "enumeration": ENUMERATION}
