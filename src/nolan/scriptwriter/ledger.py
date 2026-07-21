"""Review learning ledger — the script-side twin of the render taste loop.

docs/SCRIPT_REVIEW_PROGRAM.md §6. Every critique-gate decision (which findings the
producer approved vs rejected, plus the ad-hoc questions they attached) is appended to a
JSONL ledger. ``distill`` aggregates it into per-dimension approval rates and recurring
ad-hoc questions; ``draft_priors`` turns that into a short markdown block injected at
DRAFT time — so the *first* draft pre-empts what producers keep asking for and the loop
compounds instead of repeating itself.

This is deliberately self-contained (append + aggregate over a JSONL file); it mirrors the
render-side ledger→distill→prior pattern without coupling to it.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LEDGER_NAME = "_script_review_ledger.jsonl"


def _ledger_path(root: Path) -> Path:
    return Path(root) / LEDGER_NAME


def _norm_q(q: str) -> str:
    """Normalise an ad-hoc question for counting (lowercase, collapse whitespace/punct)."""
    return " ".join("".join(c if c.isalnum() else " " for c in (q or "").lower()).split())


def record_review_decision(slug: str, store, review_n: int, approved_ids: List[str]) -> Optional[dict]:
    """Append one critique-gate decision to the ledger. Returns the event, or None if the
    review has no findings to learn from. Best-effort — never raises into the request path."""
    try:
        fp = store.review_findings_path(slug, review_n)
        if not fp.exists():
            return None
        findings = json.loads(fp.read_text(encoding="utf-8"))
        if not isinstance(findings, list) or not findings:
            return None
        ids = set(approved_ids or [])
        meta = store.get(slug)
        event = {
            "ts": time.time(),
            "slug": slug,
            "style_id": meta.get("style_id", ""),
            "archetype": store.resolve_archetype(slug),
            "review_n": review_n,
            "approved": [{"dim": f.get("dim", ""), "severity": f.get("severity", "")}
                         for f in findings if f.get("id") in ids],
            "rejected": [{"dim": f.get("dim", ""), "severity": f.get("severity", "")}
                         for f in findings if f.get("id") not in ids],
            "ad_hoc": [q for q in (meta.get("ad_hoc_questions") or []) if q.strip()],
        }
        p = _ledger_path(store.root)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event
    except Exception as e:
        # learning must never block the gate — but don't fail SILENTLY (that hid a real miss once)
        logger.warning("review-ledger record failed for %s (review-%s): %s", slug, review_n, e)
        return None


def _read_events(root: Path) -> List[dict]:
    p = _ledger_path(root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def distill(root: Path = Path("projects"), *, archetype: Optional[str] = None,
            style_id: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate the ledger. Optionally scope to an archetype and/or style.

    Returns per-dimension approve counts/rate and the most common ad-hoc questions.
    """
    events = _read_events(root)
    if archetype:
        events = [e for e in events if e.get("archetype") == archetype]
    if style_id:
        events = [e for e in events if e.get("style_id") == style_id]

    approved = Counter()
    rejected = Counter()
    for e in events:
        for f in e.get("approved", []):
            approved[f.get("dim", "")] += 1
        for f in e.get("rejected", []):
            rejected[f.get("dim", "")] += 1

    by_dim = {}
    for dim in set(approved) | set(rejected):
        a, r = approved[dim], rejected[dim]
        by_dim[dim] = {"approved": a, "rejected": r,
                       "rate": round(a / (a + r), 2) if (a + r) else 0.0}

    q_counts = Counter()
    q_display: Dict[str, str] = {}
    for e in events:
        for q in set(e.get("ad_hoc", [])):          # once per event
            key = _norm_q(q)
            if key:
                q_counts[key] += 1
                q_display.setdefault(key, q)
    ad_hoc_common = [{"q": q_display[k], "count": c}
                     for k, c in q_counts.most_common() if c >= 1]

    return {"events": len(events), "by_dim": by_dim, "ad_hoc_common": ad_hoc_common}


def draft_priors(root: Path, archetype: str, style_id: str,
                 *, min_events: int = 2) -> str:
    """A short markdown 'producer priors' block for the DRAFT task, or '' if too little data.

    Combines: ad-hoc questions producers keep attaching (recurring → surface as standing
    notes) and rubric dimensions whose findings are almost always accepted (pre-empt them).
    """
    d = distill(root, archetype=archetype, style_id=style_id)
    if d["events"] < min_events:
        return ""
    lines: List[str] = []
    recurring = [x["q"] for x in d["ad_hoc_common"] if x["count"] >= 2]
    if recurring:
        lines.append("Producers on this style repeatedly ask for — pre-empt these while drafting:")
        lines += [f"  - {q}" for q in recurring[:6]]
    hot = sorted((k for k, v in d["by_dim"].items() if v["approved"] >= 3 and v["rate"] >= 0.7),
                 key=lambda k: -d["by_dim"][k]["approved"])
    if hot:
        lines.append("Review findings in these areas are almost always accepted here — get them "
                     "right the first time: " + ", ".join(hot[:6]) + ".")
    if not lines:
        return ""
    return ("## Producer priors (learned from past reviews of this style)\n"
            + "\n".join(lines))
