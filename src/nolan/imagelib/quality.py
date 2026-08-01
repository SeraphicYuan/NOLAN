"""Per-source catalog quality — MEASURED, not asserted.

"Well curated" is at least three orthogonal things, and the live corpus shows they do not
correlate:

    catalog richness      can I FIND it?          artic leads (creator 81%, place 100%)
    image quality         resolution/derivatives  cleveland leads (3 derivatives, ~2850px print)
    collection weight     is the WORK worth it?   unmeasurable — that is what TIERS asserts

So this module measures the first, reads the second off the adapter registry (which already
carries `publishes_pixel_dims`, `rights_model`, `enumeration` as typed fields), and takes the
third from `acquire.engine.TIERS` rather than inventing a second opinion — two NOLAN rankings of
the same museums would drift, which is the two-dialect pitfall in the wiring checklist.

WHY MEASURE RATHER THAN HAND-MAINTAIN A TABLE: a hand-written quality table is wrong the day a
crawl extends, and nothing tells you. This is one SQL pass and can be re-run whenever, which is
what makes characterising a NEW source cheap — the seven-question probe protocol answers what a
crawl will cost, and this answers what it actually bought.

NOT ON THE READ PATH. Nothing in search, ranking or acquisition calls this: it is a report, run
from `nolan images quality` or the Sources tab, and it scans the whole discovery tier. Putting it
behind a search would put a full table scan on every keystroke — the same defect that made
`discovery_stats` materialise 97,610 rows per request and cost 90-second searches.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Coverage columns worth reporting, in the order a person reads them: what the thing IS, who made
# it, when, then how it is filed.
_COVERAGE = ("title", "creator", "date_text", "medium", "classification",
             "department", "culture", "place", "wikidata_qid")

# Columns NOLAN derives rather than receives. Reported separately because a low number here is
# OUR failure (a taxonomy that does not fit the source's vocabulary), not the museum's.
_DERIVED = ("image_kind", "year_from", "artist_key")


def _pct(n: int, total: int) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


def source_quality(library, *, held: int = 0) -> List[Dict[str, Any]]:
    """One row per source: measured coverage, declared capabilities, asserted rank.

    ONE SQL PASS for every source and every column — conditional aggregation grouped by source,
    rather than a COUNT per (source, column). The naive shape is ~15 full scans per source and
    was the first thing written; over 100k rows it is the difference between a report you run and
    one you avoid.
    """
    from nolan.imagelib.harvest import SOURCES

    cov = ", ".join(
        f"SUM(CASE WHEN {c} IS NOT NULL AND TRIM({c})<>'' THEN 1 ELSE 0 END) AS cov_{c}"
        for c in _COVERAGE)
    sql = f"""
        SELECT source,
               COUNT(*) AS n,
               {cov},
               SUM(CASE WHEN image_kind IS NOT NULL AND image_kind<>'unknown'
                        THEN 1 ELSE 0 END) AS der_image_kind,
               SUM(CASE WHEN year_from IS NOT NULL THEN 1 ELSE 0 END) AS der_year_from,
               SUM(CASE WHEN artist_key IS NOT NULL THEN 1 ELSE 0 END) AS der_artist_key,
               SUM(CASE WHEN width IS NOT NULL AND width>0 THEN 1 ELSE 0 END) AS has_dims,
               SUM(CASE WHEN thumb_path IS NOT NULL AND TRIM(thumb_path)<>''
                        THEN 1 ELSE 0 END) AS has_pixels,
               AVG(LENGTH(title)) AS avg_title
        FROM assets
        WHERE status='active' AND held=? AND source IS NOT NULL AND TRIM(source)<>''
        GROUP BY source
    """
    with library.catalog._lock:
        rows = library.catalog._conn.execute(sql, (int(held),)).fetchall()

    # How much of each source we have ACTUALLY walked. Without it the coverage percentages read
    # as facts about the museum when they can be facts about enumeration order: the Met's crawl
    # walks in Object ID order, which correlates with department, so a third-finished crawl
    # reported classification at 14% where the full dump carries 86.9%.
    crawled: Dict[str, Dict[str, Any]] = {}
    for c in library.catalog.list_collections():
        got = crawled.setdefault(c.source, {"indexed": 0, "upstream": 0, "exhausted": True})
        got["indexed"] = (got["indexed"] or 0) + (c.item_count or 0)
        if c.upstream_count:
            got["upstream"] = (got["upstream"] or 0) + c.upstream_count
        # A source is only walked-out if EVERY collection from it is. One mid-walk slice makes
        # the source's aggregate numbers an enumeration-order artifact again.
        if not c.exhausted:
            got["exhausted"] = False

    out = []
    for r in rows:
        src, n = r["source"], int(r["n"])
        adapter = SOURCES.get(src)
        walked = crawled.get(src, {})
        upstream = walked.get("upstream") or None
        entry: Dict[str, Any] = {
            "source": src,
            "rows": n,
            "upstream": upstream,
            # None, not 100, when the source cannot be asked how big it is — a guessed
            # denominator makes a partial crawl look finished.
            "crawled_pct": _pct(n, upstream) if upstream else None,
            "coverage": {c: _pct(int(r[f"cov_{c}"]), n) for c in _COVERAGE},
            "derived": {c: _pct(int(r[f"der_{c}"]), n) for c in _DERIVED},
            "pixel_dims_pct": _pct(int(r["has_dims"]), n),
            "thumbnails_pct": _pct(int(r["has_pixels"]), n),
            "avg_title_chars": round(float(r["avg_title"] or 0), 1),
            "tier_rank": tier_rank(src),
            # DECLARED by the adapter, not measured — kept visibly separate from the numbers
            # above so nobody reads a claim as a measurement.
            "declared": ({
                "enumeration": adapter.enumeration,
                "resumable": adapter.resumable,
                "publishes_pixel_dims": adapter.publishes_pixel_dims,
                "rights_model": adapter.rights_model,
            } if adapter else None),
            # A source with rows but no adapter is a crawl whose code was removed underneath it.
            "registered": adapter is not None,
        }
        # THE CAVEAT, carried in the data rather than left to the reader — and taken from whether
        # the walk REACHED THE END, not from a ratio. artic sits at 91% of upstream with its
        # listing fully walked (the rest was refused on rights or by the gate, uniformly), so its
        # percentages describe the collection; a ratio test called that partial and was wrong.
        # TRI-STATE, because "we never recorded it" is not the same claim as "it did not
        # finish". A collection crawled before this column existed reads as unknown, and the
        # ratio is then used as evidence rather than as proof.
        entry["exhausted"] = walked.get("exhausted")
        if entry["exhausted"] is True:
            entry["partial"] = False
        elif entry["crawled_pct"] is not None and entry["crawled_pct"] < 95:
            entry["partial"] = True
        else:
            entry["partial"] = entry["exhausted"] is False
        out.append(entry)
    out.sort(key=lambda e: -e["rows"])
    return out


def tier_rank(source: str, category: str = "art") -> Optional[int]:
    """This source's position in the SHARED acquisition tier, or None if it is not ranked.

    Deliberately imported from `acquire.engine` rather than restated. Two NOLAN opinions about
    whether the Met outranks the Art Institute is one opinion too many, and the one nobody looks
    at is the one that rots. `test_every_harvest_source_is_ranked` fails CI when a new adapter
    lands without a tier entry.
    """
    try:
        from nolan.acquire.engine import TIERS, source_rank
    except Exception:
        return None
    order = TIERS.get(category) or TIERS.get("general") or []
    r = source_rank(category, source)
    return r if r < len(order) else None


def unranked_sources(category: str = "art") -> List[str]:
    """Harvest sources missing from the shared tier — what the honesty test asserts is empty."""
    from nolan.imagelib.harvest import SOURCES
    return sorted(s for s in SOURCES if tier_rank(s, category) is None)
