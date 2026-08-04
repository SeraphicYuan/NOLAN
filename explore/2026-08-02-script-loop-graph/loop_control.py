"""What the graph does after a round — including the action a replay could never have found.

TWO THINGS PHASE 2 ESTABLISHED, and both change the shape of the loop:

1. **A round can make the draft worse.** 23 findings applied at once fixed 7, left 11 untouched
   and introduced 8 new ones. After a round like that, `continue` and `stop` are BOTH wrong:
   continuing loops into a probably-worse draft, stopping ships the regression. The correct move
   is `revert` — go back to the draft that was better and try a smaller change set. No stop
   policy can express this, and no replay could have discovered it, because recorded runs only
   ever contain rounds that improved.

2. **A finding that VANISHES is ambiguous; one that PERSISTS is not.** It can disappear because
   it was fixed, because the sentence it referenced was cut, or because the judge simply did not
   mention it this time. But a finding at the same `(dim, beat)` present in round N and again in
   round N+1 survived a pass aimed squarely at it. Measured: 11 of 23 persisted, including 6 of
   the 7 high-severity ones. That is the signal worth acting on, and it needs no theory about
   why the others went away.

Nothing here counts blockers as a quality score — see `scriptwriter.verdicts` for why that metric
is inverted.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from nolan.scriptwriter.verdicts import Verdict           # noqa: E402

# Actions the graph may take after a round.
CONTINUE = "continue"        # revise again from the current draft
REVERT = "revert"            # the round made it worse — go back and retry smaller
STOP = "stop"                # good enough, or nothing more to gain
ASK = "ask_human"            # taste, or a blocker nothing has managed to shift

MAX_ROUNDS = 4
# Survive this many consecutive rounds aimed at it and a blocker stops being something the loop
# can fix. Two, because one survival is ordinary (a pass ran out of budget) and two is a pattern.
PERSIST_ESCALATE = 2
# What "retry smaller" narrows to. The hypothesis for the regression is that a large change set
# is a rewrite rather than surgery, so the retry applies only what is unambiguously severe.
RETRY_SEVERITY = "high"


@dataclass(frozen=True)
class Action:
    action: str
    why: str
    # Populated on REVERT: the change set the retry should apply, already narrowed.
    retry_with: List[dict] = field(default_factory=list)


def _key(item: dict) -> Tuple[str, str]:
    """What makes two findings 'the same finding' across rounds.

    `(dim, beat)` rather than the text: a judge rephrases, and matching on wording would report
    every persisted finding as newly discovered — which is precisely the blindness being fixed.
    """
    return (str(item.get("dim") or "?"), str(item.get("beat") or "?").strip().lower()[:48])


def persistence(rounds: List[List[dict]]) -> Dict[Tuple[str, str], int]:
    """`{(dim, beat): consecutive rounds survived}`, counting back from the latest round.

    Only a RUN of consecutive appearances counts. A blocker raised in round 1, fixed in round 2
    and raised again in round 3 is not one that resisted two passes — it is two separate events,
    and conflating them would escalate something the loop actually handled.
    """
    if not rounds:
        return {}
    counts: Dict[Tuple[str, str], int] = {}
    latest = {_key(i) for i in rounds[-1]}
    for k in latest:
        n = 0
        for prior in reversed(rounds):
            if k in {_key(i) for i in prior}:
                n += 1
            else:
                break
        counts[k] = n
    return counts


def stuck(rounds: List[List[dict]], threshold: int = PERSIST_ESCALATE) -> List[Tuple[str, str]]:
    """Blockers that have survived `threshold` consecutive passes aimed at them."""
    return sorted(k for k, n in persistence(rounds).items() if n >= threshold)


def decide(v: Optional[Verdict], *, round_n: int, rounds: List[List[dict]],
           gate_ok: bool = True, gate_failures: Optional[List[str]] = None) -> Action:
    """The graph's move after round `round_n`.

    Order matters, and each rule earned its place:

    1. **A failing deterministic gate is not a judgement call.** Collapsed timecodes and a
       declared duration 30% out are arithmetic; there is nothing for a human to weigh and no
       reason to ask a judge. Fix and continue.
    2. **A regression reverts.** Cheapest to act on while the change is recent and located.
    3. **A stuck blocker escalates.** Two passes aimed at it and still there means the loop is not
       the thing that can fix it.
    4. **Then the verdict**, which is a comparison and not a score.
    """
    failures = gate_failures or []
    if not gate_ok:
        return Action(CONTINUE,
                      f"deterministic gate failed ({', '.join(failures) or 'see gate'}) — "
                      f"arithmetic, not taste; fix it before spending another judgement")

    if round_n >= MAX_ROUNDS:
        # Its own terminal state, deliberately not 'stop': a run that hit the ceiling must never
        # read like one that converged.
        return Action(STOP, f"max_rounds_reached ({MAX_ROUNDS}) — ceiling, not convergence")

    if v is None:
        return Action(ASK, "no verdict was produced — nothing to route on")

    if v.regressed:
        keep = [b for b in v.blockers
                if str(b.get("severity")) == RETRY_SEVERITY] or v.blockers[:2]
        broke = ", ".join(str(r.get("beat"))[:20] for r in v.regressions[:3]) or "overall"
        return Action(REVERT,
                      f"the round made it worse ({broke}) — revert and retry with "
                      f"{len(keep)} {RETRY_SEVERITY}-severity item(s) instead of "
                      f"{len(v.blockers)}",
                      retry_with=keep)

    if (st := stuck(rounds)):
        names = ", ".join(f"{d}@{b}"[:28] for d, b in st[:3])
        return Action(ASK,
                      f"{len(st)} blocker(s) survived {PERSIST_ESCALATE} passes aimed at them "
                      f"({names}) — the loop is not what fixes these")

    high = v.blocking(min_severity="high")
    if high:
        return Action(CONTINUE,
                      f"{len(high)} high-severity blocker(s) and the draft improved — "
                      f"another pass is paying")
    if v.improved:
        return Action(STOP, "improved, and nothing high-severity is blocking")
    return Action(ASK, f"verdict '{v.verdict}' with no high blockers — a judgement call")


def summarise_run(actions: List[Action]) -> Dict[str, int]:
    """Terminal stats for a finished run. `max_rounds_reached` is counted separately from a
    clean stop so the two are never conflated in a report."""
    out = Counter(a.action for a in actions)
    out["max_rounds_reached"] = sum(
        1 for a in actions if a.action == STOP and "max_rounds_reached" in a.why)
    return dict(out)
