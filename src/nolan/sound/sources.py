"""SFX source-adapter registry — the extensible half of the sound library.

Each PROVIDER (Freesound today; more later) is an adapter exposing a typed set of CONTROL operations
(crawl / add / remove …) with declared param fields, plus a `run(op, params, log)` that drives the
shared curation core. The /sfx control tab renders whatever adapters register (fields → a form), so
adding a source is one adapter class + one `register_source(...)` line — the page changes nothing.

This mirrors the module-contract pattern used elsewhere (registry + typed capability + executor): the
registry is the single source of truth the UI + tests read (honesty-tested against the real ops).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Field:
    """One control parameter, self-describing so the UI can render it without per-source code."""
    name: str
    label: str
    type: str = "text"                 # text | int | number | bool | choice
    default: Any = None
    required: bool = False
    choices: Optional[List[str]] = None
    help: str = ""


@dataclass
class Control:
    """One operation a source exposes on the control tab (an op + its param fields)."""
    op: str
    label: str
    fields: List[Field] = field(default_factory=list)
    help: str = ""


class FreesoundSource:
    """The Freesound adapter — wraps the CC0 crawl + the shared curation core (add/remove)."""
    id = "freesound"
    label = "Freesound"

    def available(self) -> bool:
        try:
            from nolan.sound.crawl import api_key
            return bool(api_key())
        except Exception:
            return False

    def controls(self) -> List[Control]:
        from nolan.sound.registry import KINDS
        return [
            Control("crawl", "Crawl CC0 candidates",
                    help="Fetch the top CC0 sounds (downloads-desc) into the searchable candidate catalog. "
                         "Then hand-pick with Add.",
                    fields=[
                        Field("pages", "Pages", "int", 5, help="API pages ×150."),
                        Field("page_size", "Page size", "int", 150),
                        Field("min_downloads", "Min downloads", "int", 0),
                        Field("max_duration", "Max duration (s)", "number", None,
                              help="SFX are usually short; blank = no cap."),
                    ]),
            Control("add", "Add / curate a sound",
                    help="Fetch one sound by id, license-gate it, normalize to 48 kHz stereo, and add it to "
                         "the curated bank under a cue-kind.",
                    fields=[
                        Field("sound_id", "Sound id", "text", required=True, help="Freesound sound id."),
                        Field("kind", "Cue-kind", "choice", None, required=True, choices=list(KINDS)),
                        Field("rating", "Rating (1-5)", "int", 3),
                        Field("tags", "Extra tags", "text", ""),
                        Field("desc", "Description override", "text", ""),
                        Field("no_trim", "Keep lead silence", "bool", False,
                              help="For a bed/riser whose quiet lead-in is intentional."),
                    ]),
            Control("remove", "Remove a curated sound",
                    fields=[Field("sound_id", "Sound id", "text", required=True)]),
        ]

    def run(self, op: str, params: Dict[str, Any], log: Callable[[str], None]) -> Dict[str, Any]:
        if op == "crawl":
            from nolan.sound.crawl import crawl_cc0
            md = params.get("max_duration")
            res = crawl_cc0(
                pages=int(params.get("pages", 5) or 5),
                page_size=int(params.get("page_size", 150) or 150),
                min_downloads=int(params.get("min_downloads", 0) or 0),
                max_duration=float(md) if md not in (None, "", "None") else None,
            )
            log(f"crawled {res.get('crawled')} → catalog {res.get('catalog_total')} "
                f"({res.get('in_library')} in library)")
            return res
        if op == "add":
            from nolan.sound.curate import CurateError, add_sound
            try:
                res = add_sound(params.get("sound_id"), params.get("kind"),
                                rating=int(params.get("rating", 3) or 3),
                                tags=params.get("tags", "") or "", desc=params.get("desc", "") or "",
                                no_trim=bool(params.get("no_trim", False)))
            except CurateError as e:                           # loud, structured failure for the job UI
                raise RuntimeError(str(e))
            for n in res.get("notes", []):
                log(n)
            log(f"added [{res['kind']}] {res['file']} ({res['duration']:.1f}s)")
            return res
        if op == "remove":
            from nolan.sound.curate import remove_sound
            res = remove_sound(params.get("sound_id"))
            log(f"removed {res.get('file')}" if res.get("removed") else f"not in bank: {params.get('sound_id')}")
            return res
        raise ValueError(f"unknown op {op!r} for source {self.id!r}")

    def describe(self) -> Dict[str, Any]:
        """The registry-derived payload the control tab renders (single source of truth for the UI)."""
        return {"id": self.id, "label": self.label, "available": self.available(),
                "controls": [{"op": c.op, "label": c.label, "help": c.help,
                              "fields": [vars(f) for f in c.fields]} for c in self.controls()]}


_SOURCES: Dict[str, Any] = {}


def register_source(src) -> None:
    _SOURCES[src.id] = src


def get_source(source_id: str):
    return _SOURCES.get(source_id)


def list_sources() -> List[Any]:
    return list(_SOURCES.values())


register_source(FreesoundSource())
