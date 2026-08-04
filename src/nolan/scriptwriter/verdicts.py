"""Reading a pairwise verdict, and refusing to turn it back into a score.

The failure this guards against is the one that already happened once: a metric built on counting
findings rewarded the draft that asserted over the draft that argued, and would have stopped a run
that was working. Nothing here exposes a total, and `blockers` is deliberately awkward to reduce
to a number — the loop routes on the VERDICT and on whether anything REGRESSED, never on how many
items came back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

BETTER, WORSE, MIXED, SAME = "better", "worse", "mixed", "same"
_VALID = (BETTER, WORSE, MIXED, SAME)


@dataclass(frozen=True)
class Verdict:
    """One comparative judgement. Read-only, because a verdict is a record of what was said."""

    verdict: str
    vs_draft: Optional[str]
    confidence: str = "med"
    why: str = ""
    gains: List[Dict[str, Any]] = field(default_factory=list)
    regressions: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def improved(self) -> bool:
        return self.verdict == BETTER

    @property
    def regressed(self) -> bool:
        """Did the revision BREAK something?

        Not the same as `verdict == worse`. A draft can be better overall and still have broken a
        beat, and that beat is the cheapest thing in the loop to fix — it is a known, located,
        recent change. An overall verdict alone would hide it.
        """
        return bool(self.regressions) or self.verdict == WORSE

    def blocking(self, *, min_severity: str = "high") -> List[Dict[str, Any]]:
        """Blockers at or above a severity. THE ROUTING INPUT — a filtered list, never a count.

        `len()` of this is available to anyone determined to have it, and that is fine: the point
        is that no function here hands out a number that looks like a quality score, because that
        number is what inverted the metric last time.
        """
        order = {"high": 3, "med": 2, "low": 1}
        floor = order.get(min_severity, 3)
        return [b for b in self.blockers if order.get(b.get("severity"), 0) >= floor]


def parse_verdict(obj: Any) -> Verdict:
    """A judge's JSON into a `Verdict`, tolerating the shapes an agent actually emits.

    An unrecognised verdict string becomes `mixed` rather than raising: a malformed word is a
    reason to be cautious, not a reason to lose the gains, regressions and blockers alongside it.
    """
    if isinstance(obj, list):                       # a bare blocker list, no comparison made
        return Verdict(verdict=MIXED, vs_draft=None, blockers=list(obj))
    if not isinstance(obj, dict):
        return Verdict(verdict=MIXED, vs_draft=None)
    v = str(obj.get("verdict") or "").strip().lower()
    return Verdict(
        verdict=v if v in _VALID else MIXED,
        vs_draft=obj.get("vs_draft"),
        confidence=str(obj.get("confidence") or "med").strip().lower(),
        why=str(obj.get("why") or ""),
        gains=list(obj.get("gains") or []),
        regressions=list(obj.get("regressions") or []),
        blockers=list(obj.get("blockers") or []),
    )


def verdict_path(store, slug: str, draft_n: int) -> Path:
    return store.reviews_dir(slug) / f"review-{draft_n:02d}.pairwise.json"


def read_verdict(store, slug: str, draft_n: int) -> Optional[Verdict]:
    p = verdict_path(store, slug, draft_n)
    try:
        return parse_verdict(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def summarise(v: Verdict) -> str:
    """One line for a human or a log. Names counts of GAINS and REGRESSIONS — which are events,
    not a score — and never a total that could be mistaken for draft quality."""
    bits = [v.verdict.upper()]
    if v.vs_draft:
        bits.append(f"vs {v.vs_draft}")
    bits.append(f"{len(v.gains)} gain(s)")
    if v.regressions:
        bits.append(f"⚠ {len(v.regressions)} REGRESSION(s)")
    hi = v.blocking(min_severity="high")
    if hi:
        bits.append(f"{len(hi)} high blocker(s)")
    return " · ".join(bits)
