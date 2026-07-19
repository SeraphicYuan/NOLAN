"""Freesound CC0 crawler — document the top CC0 sounds so a human can curate.

Mirrors the freesound.org web search "Downloads (most first)" filtered to
Creative Commons 0, but over the APIv2 (`FREESOUND_API_KEY`) — far more robust
than scraping the HTML search page, with clean pagination and structured
metadata + directly-fetchable preview links.

    from nolan.sound.crawl import crawl_cc0
    crawl_cc0(pages=5)   # ~750 candidates → projects/_library/sfx/_candidates/

Writes two files under ``projects/_library/sfx/_candidates/``:
  - ``freesound_cc0.json``  — full records (machine SSOT for picking)
  - ``freesound_cc0.md``    — a browsable pick-and-choose table

Then curate with ``nolan sfx add <id> --kind <kind>``.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from nolan.sfx_search import _get  # shared stdlib HTTP getter

logger = logging.getLogger(__name__)

_API = "https://freesound.org/apiv2"
# Repo-root-anchored (NOT cwd) so it never reads/writes an empty library from a
# bridge/sub-dir — the library-CWD class of bug. crawl.py = src/nolan/sound/*.
_REPO = Path(__file__).resolve().parents[3]
_FIELDS = ("id,name,description,tags,license,type,duration,filesize,"
           "num_downloads,username,url,previews")


def library_dir() -> Path:
    """The curated SFX bank dir, anchored to the repo root."""
    return _REPO / "projects" / "_library" / "sfx"


def candidates_dir() -> Path:
    return library_dir() / "_candidates"


def api_key(explicit: Optional[str] = None) -> str:
    """Resolve FREESOUND_API_KEY (arg → env → .env), matching FreesoundProvider."""
    key = explicit or os.getenv("FREESOUND_API_KEY", "")
    if not key:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            key = os.getenv("FREESOUND_API_KEY", "")
        except ImportError:
            pass
    return key


def _request(path: str, params: Dict[str, str]) -> Dict[str, Any]:
    url = f"{_API}/{path}?" + urllib.parse.urlencode(params)
    try:
        return json.loads(_get(url))
    except urllib.error.HTTPError as e:  # clearer than a raw traceback
        if e.code == 401:
            raise RuntimeError("Freesound 401 — bad/absent FREESOUND_API_KEY") from e
        if e.code == 429:
            raise RuntimeError("Freesound 429 — rate limited (60/min, 2000/day)") from e
        raise RuntimeError(f"Freesound HTTP {e.code} for {path}") from e


def _record(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    prev = r.get("previews", {}) or {}
    dl = prev.get("preview-hq-mp3") or prev.get("preview-lq-mp3") or ""
    if not dl:
        return None  # nothing fetchable — skip
    return {
        "id": str(r.get("id")),
        "name": r.get("name", ""),
        "description": (r.get("description") or "").strip(),
        "tags": list(r.get("tags", []))[:16],
        "license": r.get("license", ""),
        "type": r.get("type", ""),
        "duration": round(float(r.get("duration") or 0.0), 2),
        "filesize": int(r.get("filesize") or 0),
        "num_downloads": int(r.get("num_downloads") or 0),
        "username": r.get("username", ""),
        "page_url": r.get("url", ""),
        "preview_hq_mp3": dl,
    }


def crawl_cc0(pages: int = 5, page_size: int = 150, *,
              min_downloads: int = 0, max_duration: Optional[float] = None,
              out_dir: Optional[Path] = None, throttle_s: float = 1.1,
              key: Optional[str] = None) -> Dict[str, Any]:
    """Crawl the top CC0 sounds (sorted by downloads, most first) and document them.

    `pages` × `page_size` candidates (page_size ≤ 150). Default 5×150 ≈ 750 — the
    equivalent of the first ~50 freesound web-search pages. Paginates by `page`
    until Freesound reports no `next` or an empty page. No audio is downloaded;
    only metadata + the preview link are recorded.
    """
    k = api_key(key)
    if not k:
        raise RuntimeError("FREESOUND_API_KEY not set — get one at "
                           "https://freesound.org/apiv2/apply/ and put it in .env")
    page_size = max(1, min(page_size, 150))
    base = {
        "query": "",
        "filter": 'license:"Creative Commons 0"',
        "sort": "downloads_desc",
        "fields": _FIELDS,
        "page_size": str(page_size),
        "token": k,
    }
    if max_duration:
        base["filter"] += f" duration:[0 TO {max_duration}]"

    records: List[Dict[str, Any]] = []
    seen: set = set()
    total = None
    for page in range(1, pages + 1):
        if page > 1:
            time.sleep(throttle_s)   # polite: stay well under 60 req/min
        data = _request("search/text/", {**base, "page": str(page)})
        total = data.get("count", total)
        results = data.get("results", []) or []
        if not results:
            break
        for r in results:
            rec = _record(r)
            if not rec or rec["id"] in seen:
                continue
            if rec["num_downloads"] < min_downloads:
                continue
            seen.add(rec["id"])
            records.append(rec)
        logger.info("freesound CC0 crawl: page %d/%d, %d records so far (of %s total)",
                    page, pages, len(records), total)
        if not data.get("next"):
            break

    # The catalog DB is the durable SSOT (queryable via `nolan sfx search`);
    # the .md is a human browse-and-pick export generated from it.
    from nolan.sound.catalog import SoundCatalog
    cat = SoundCatalog()
    cat.upsert_many(records)
    # reconcile curation flags from the curated manifest (sfx.json), so an
    # already-added sound shows as in_library even if this crawl re-inserted it.
    try:
        man = json.loads((library_dir() / "sfx.json").read_text(encoding="utf-8"))
        for e in man:
            if e.get("curated") and e.get("id") and cat.get(str(e["id"]), e.get("source", "freesound")):
                cat.mark_in_library(str(e["id"]), e.get("kind", ""), e.get("file", ""),
                                    int(e.get("rating") or 0), provider=e.get("source", "freesound"))
    except Exception:
        pass
    stats = cat.stats()
    out = Path(out_dir) if out_dir else candidates_dir()
    out.mkdir(parents=True, exist_ok=True)
    top = cat.top(limit=max(len(records), 1000))
    (out / "freesound_cc0.md").write_text(
        _to_markdown(top, stats["total"]), encoding="utf-8")
    db_path = str(cat.db_path)
    cat.close()
    return {"crawled": len(records), "catalog_total": stats["total"],
            "in_library": stats["in_library"], "db": db_path,
            "md": str(out / "freesound_cc0.md")}


def fetch_sound(sound_id: str, key: Optional[str] = None) -> Dict[str, Any]:
    """One sound's metadata by id (for `nolan sfx add`). Raises on a bad id/key.

    Uses the text-search endpoint with ``filter=id:<id>`` rather than the
    ``sound/<id>/`` instance endpoint — the latter 404s under our API access,
    while the search path (the same one the crawl uses) resolves a single id
    reliably.
    """
    k = api_key(key)
    if not k:
        raise RuntimeError("FREESOUND_API_KEY not set (see .env)")
    data = _request("search/text/", {"filter": f"id:{sound_id}",
                                      "fields": _FIELDS, "token": k})
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"freesound sound {sound_id} not found")
    rec = _record(results[0])
    if not rec:
        raise RuntimeError(f"freesound sound {sound_id} has no fetchable preview")
    return rec


def _to_markdown(rows: List[Dict[str, Any]], total: Optional[int]) -> str:
    """Browse-and-pick table from catalog rows (dicts; tags is a comma-string)."""
    lines = [
        "# Freesound CC0 candidates (sorted by downloads, most first)",
        "",
        f"Catalog: {total:,} CC0 sounds" if total else "Catalog",
        f"({len(rows)} shown; the full set is queryable — `nolan sfx search <text>`). "
        "✓ = already in our library. Pick the good ones and curate:",
        "",
        "```",
        "nolan sfx add <id> --kind <cue-kind> --rating <1-5> [--tags a,b]",
        "```",
        "",
        "| ✓ | id | ↓ downloads | dur | type | name | tags |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        tags = ", ".join((r.get("tags") or "").split(", ")[:6])
        name = (r.get("name") or "").replace("|", "／")[:60]
        mark = "✓" if r.get("in_library") else ""
        lines.append(
            f"| {mark} | [{r['ext_id']}]({r.get('page_url') or ''}) | "
            f"{(r.get('num_downloads') or 0):,} | {(r.get('duration') or 0):.1f}s | "
            f"{r.get('type') or ''} | {name} | {tags} |")
    lines.append("")
    return "\n".join(lines)
