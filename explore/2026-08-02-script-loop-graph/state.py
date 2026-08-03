"""The state a script-review loop actually routes on.

REFERENCES AND CONTROL DATA, NEVER THE DRAFT. Copied deliberately from the rule the vendored
math-animation workflow states about its own LangGraph state ("graph state contains references
and control data, never mutable IR"), and it is not a style preference: a 2,500-word draft in the
state makes every checkpoint enormous, makes diffs unreadable, and tempts a node into editing
prose it should be asking a writer to edit. The loop's decisions need counts, severities and
paths — nothing here needs the words.

Everything in `RoundState` is derivable from files a real run already writes, which is what lets
the same shape drive a replay (Phase 0) and a live loop (Phase 2) without changing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# The judge's severity vocabulary, worst first. Ordered because several candidate policies ask
# "is anything at or above X still open?" and that question needs an ordering, not a set.
SEVERITIES = ("high", "med", "low")


@dataclass(frozen=True)
class RoundState:
    """One review round, reduced to what a routing decision can legitimately use."""

    n: int                                   # 1-based round number
    draft_path: str                          # a REFERENCE — never the text
    draft_words: int
    findings_by_severity: Dict[str, int] = field(default_factory=dict)
    findings_by_dim: Dict[str, int] = field(default_factory=dict)
    # How many findings the human approved, and of how many. `None` means the round was never
    # put in front of a human — which is a DIFFERENT state from "shown and approved none", and
    # collapsing the two is how a loop silently loses its interrupt.
    approved: Optional[int] = None
    reviewed: Optional[int] = None

    @property
    def total(self) -> int:
        return sum(self.findings_by_severity.values())

    @property
    def high(self) -> int:
        return self.findings_by_severity.get("high", 0)

    @property
    def med(self) -> int:
        return self.findings_by_severity.get("med", 0)

    @property
    def low(self) -> int:
        return self.findings_by_severity.get("low", 0)

    @property
    def human_saw_it(self) -> bool:
        return self.approved is not None

    @property
    def approval_rate(self) -> Optional[float]:
        """Fraction of findings the human accepted. A rate pinned at 1.0 across rounds says the
        interrupt is not DISCRIMINATING — it is a rubber stamp — and that is worth routing on."""
        if self.approved is None or not self.reviewed:
            return None
        return self.approved / self.reviewed

    def weighted(self, weights: Dict[str, int] = None) -> int:
        """A single severity-weighted score. Total-findings alone is misleading when a revision
        pass clears cheap findings and leaves expensive ones — which is exactly what the recorded
        Diamond Illusion run does."""
        w = weights or {"high": 9, "med": 3, "low": 1}
        return sum(w.get(s, 1) * n for s, n in self.findings_by_severity.items())


@dataclass
class LoopState:
    """The whole run: its fixed inputs, and every round so far.

    The fixed inputs are the things the operator chose before the loop started — style, archetype,
    spine, sources, target length, auto/semi-auto. They are carried because a stop policy may
    legitimately depend on them (a 15-minute long-form argument should not stop on the same
    evidence as a 6-minute explainer), and because a live graph needs them to dispatch work.
    """

    slug: str
    style_id: str = ""
    archetype: str = ""
    target_minutes: float = 0.0
    mode: str = ""                           # "auto" | "semi" — whether the human is in the loop
    n_sources: int = 0
    rounds: List[RoundState] = field(default_factory=list)
    # What the run ACTUALLY did, for scoring a policy against reality.
    promoted_draft: Optional[str] = None

    @property
    def last(self) -> Optional[RoundState]:
        return self.rounds[-1] if self.rounds else None

    def upto(self, n: int) -> "LoopState":
        """The state as it stood after round `n` — so a policy is asked to decide with only what
        was knowable at the time. Replaying a policy against the whole history would let it
        'decide' using rounds that only exist because of the decision it is being asked to make."""
        return LoopState(slug=self.slug, style_id=self.style_id, archetype=self.archetype,
                         target_minutes=self.target_minutes, mode=self.mode,
                         n_sources=self.n_sources, rounds=self.rounds[:n],
                         promoted_draft=self.promoted_draft)
