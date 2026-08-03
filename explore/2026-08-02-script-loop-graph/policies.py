"""Candidate answers to the ONE question the script loop currently does not ask out loud:

    after this review round, do we revise again, stop, or hand it to a human?

Each policy is a pure function of `LoopState` -> `Decision`. Pure because that is what makes them
comparable: the replay can ask every policy the same question about the same recorded moment and
tabulate the disagreements.

NONE OF THESE IS THE ANSWER YET. The point of Phase 0 is to see what each WOULD have done against
runs that already happened, and let a human pick. Shipping one of them as the default before that
comparison exists would just encode a guess as policy — which is the thing the loop is currently
doing implicitly, and the reason round 3 of the Diamond Illusion promoted a draft with five
medium-severity findings open and no human in the loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from state import LoopState

# What a policy may decide. `ASK` is a first-class outcome, not a failure to decide — a loop that
# can only continue-or-stop has no way to express "this needs taste", which is precisely when a
# human should see it.
CONTINUE = "continue"
STOP = "stop"
ASK = "ask_human"

MAX_ROUNDS_HARD = 6          # a backstop every policy inherits; runaway loops cost real money


@dataclass(frozen=True)
class Decision:
    action: str
    why: str


Policy = Callable[[LoopState], Decision]


def _hard_stop(st: LoopState) -> Optional[Decision]:
    if len(st.rounds) >= MAX_ROUNDS_HARD:
        return Decision(STOP, f"hard backstop at {MAX_ROUNDS_HARD} rounds")
    return None


def actual(st: LoopState) -> Decision:
    """THE BASELINE — what the recorded run really did, reconstructed.

    Not a policy anyone designed; it is the behaviour that emerges from a human deciding round by
    round with no stated rule. It is in the table so every candidate has something to beat, and so
    the cost of having no policy is visible rather than assumed away.
    """
    # Reconstructed from the artifacts: the run continued while a further draft exists.
    return Decision(CONTINUE, "recorded run continued (reconstructed from artifacts)")


def no_high(st: LoopState) -> Decision:
    """Stop once nothing severe is open. The most permissive defensible rule."""
    if (hs := _hard_stop(st)):
        return hs
    r = st.last
    if r is None:
        return Decision(CONTINUE, "no rounds yet")
    if r.high == 0:
        return Decision(STOP, f"no high-severity findings ({r.med} med, {r.low} low remain)")
    return Decision(CONTINUE, f"{r.high} high-severity finding(s) open")


def no_high_or_med(st: LoopState) -> Decision:
    """Stop only when nothing above `low` is open. The strictest rule, and the one that would
    have caught the recorded run's ending."""
    if (hs := _hard_stop(st)):
        return hs
    r = st.last
    if r is None:
        return Decision(CONTINUE, "no rounds yet")
    if r.high == 0 and r.med == 0:
        return Decision(STOP, f"only {r.low} low-severity findings remain")
    return Decision(CONTINUE, f"{r.high} high + {r.med} med open")


def total_falling(st: LoopState) -> Decision:
    """Stop when total findings stop falling — the intuitive 'it has converged' rule.

    In the table to be REFUTED. Total findings fall monotonically in the recorded run (15 -> 10 ->
    8) while medium-severity ones do not (5 -> 4 -> 5), so this rule reads convergence off a
    number that is being driven by the cheapest findings.
    """
    if (hs := _hard_stop(st)):
        return hs
    if len(st.rounds) < 2:
        return Decision(CONTINUE, "need two rounds to see a trend")
    prev, cur = st.rounds[-2], st.rounds[-1]
    if cur.total >= prev.total:
        return Decision(STOP, f"findings stopped falling ({prev.total} -> {cur.total})")
    return Decision(CONTINUE, f"still falling ({prev.total} -> {cur.total})")


def weighted_falling(st: LoopState) -> Decision:
    """`total_falling`, but on a severity-weighted score (high=9, med=3, low=1).

    Same shape as the intuitive rule, with the thing it gets wrong corrected: clearing nine low
    findings no longer looks like progress when a high one is untouched.
    """
    if (hs := _hard_stop(st)):
        return hs
    if len(st.rounds) < 2:
        return Decision(CONTINUE, "need two rounds to see a trend")
    prev, cur = st.rounds[-2].weighted(), st.rounds[-1].weighted()
    if cur >= prev:
        return Decision(STOP, f"weighted severity stopped falling ({prev} -> {cur})")
    return Decision(CONTINUE, f"weighted severity falling ({prev} -> {cur})")


def rubber_stamp_detector(st: LoopState) -> Decision:
    """Escalate when the human interrupt has stopped discriminating.

    An approval rate pinned at 100% across rounds does not mean the findings are all good; it
    means the review step is no longer a filter. Measured on the recorded run: 15/15 then 10/10.
    When that happens the useful move is not another silent revision — it is to ask the human a
    DIFFERENT question ("is this done?") rather than the same one they have stopped answering.
    """
    if (hs := _hard_stop(st)):
        return hs
    seen = [r for r in st.rounds if r.human_saw_it]
    if len(seen) >= 2 and all((r.approval_rate or 0) >= 0.999 for r in seen[-2:]):
        return Decision(ASK, f"human approved 100% for {len(seen[-2:])} rounds — interrupt is "
                             f"not filtering; ask whether it is DONE, not what to fix")
    r = st.last
    if r is None:
        return Decision(CONTINUE, "no rounds yet")
    if r.high == 0 and r.med == 0:
        return Decision(STOP, f"only {r.low} low remain")
    return Decision(CONTINUE, f"{r.high} high + {r.med} med open")


def semi_auto(st: LoopState) -> Decision:
    """What `mode` should arguably already mean.

    In `auto` the loop runs to a severity floor unattended. In semi-auto it stops and ASKS at the
    same point instead of deciding alone. The recorded run is `mode: auto`, yet two of its three
    rounds were in fact human-gated and the third was not — so the declared mode and the observed
    behaviour disagree, which is a defect this policy exists to surface.
    """
    if (hs := _hard_stop(st)):
        return hs
    r = st.last
    if r is None:
        return Decision(CONTINUE, "no rounds yet")
    clean = r.high == 0 and r.med == 0
    if st.mode == "auto":
        return Decision(STOP if clean else CONTINUE,
                        "auto: severity floor reached" if clean else f"auto: {r.high}h/{r.med}m open")
    return Decision(ASK if clean else CONTINUE,
                    "semi: floor reached — confirm?" if clean else f"semi: {r.high}h/{r.med}m open")


# --- the composite the evidence asks for, with the operator's chosen constants ---------------
#
# THE FLOOR IS DELIBERATELY SET SO IT ALMOST NEVER FIRES — do not "fix" it upward without
# reading this. The lowest round-1 weighted score across all six recorded runs is 17, so a floor
# of 15 fires on NONE of them. That is the intended behaviour, chosen over a floor of 20 (which
# would stop homer-auto at 17 and homer-braid at 20) for a specific reason:
#
#   with six runs and no quality labels, a floor tight enough to fire is a floor fitted to noise.
#
# So the floor is a SAFETY VALVE for a genuinely clean first draft, and `MIN_GAIN` is the real
# terminator. The cost is stated rather than discovered: since a marginal-gain rule needs two
# rounds to see a trend, every run now does at least two — where five of six historically did
# one. That roughly doubles loop cost, and buys erring toward polish instead of toward shipping
# early, which is the safer direction to be wrong in while the thresholds are this unproven.
#
# Revisit once there are runs with quality labels attached, not before.
WEIGHTED_FLOOR = 15
# A round must move weighted severity by MORE than this to justify another. Diamond Illusion's
# round 3 moved it by 0 while adding 204 words — the case this exists for. n=1; treat as a first
# guess.
MIN_GAIN = 3


def severity_floor(st: LoopState) -> Decision:
    """STOP when nothing severe is open AND the residue is small; keep going while it pays.

    Three rules in priority order, each earned from the recorded runs:

    1. **A high-severity finding is never shippable.** Two runs promoted with one open
       (attention-is-all-you-need, aidebate-braid). Whatever else is true, that is the one
       verdict the judge is most likely to be right about.
    2. **At round 1 there is no trend**, so the decision has to be absolute. This is where 5 of
       6 runs actually end, so a policy that can only reason about trends is inert in the common
       case — which is what rules out `weighted_falling` as the whole answer despite it being the
       best diagnosis of the multi-round run.
    3. **After round 1, judge the ROUND, not the draft.** If a revision cycle did not move the
       weighted score by `MIN_GAIN`, another one probably will not either. Diamond's round 3
       moved it by zero while adding 204 words.
    """
    if (hs := _hard_stop(st)):
        return hs
    r = st.last
    if r is None:
        return Decision(CONTINUE, "no rounds yet")
    if r.high:
        return Decision(CONTINUE, f"{r.high} high-severity finding(s) — never ship these")
    w = r.weighted()
    if len(st.rounds) >= 2:
        gain = st.rounds[-2].weighted() - w
        # STRICTLY greater — a round has to beat the bar, not tie it.
        if gain <= MIN_GAIN:
            return Decision(STOP, f"round {r.n} moved weighted severity by {gain} "
                                  f"(not >{MIN_GAIN}) — further rounds are not paying")
    if w <= WEIGHTED_FLOOR:
        return Decision(STOP, f"no high, weighted {w} <= floor {WEIGHTED_FLOOR} "
                              f"({r.med} med, {r.low} low)")
    return Decision(CONTINUE, f"weighted {w} > floor {WEIGHTED_FLOOR} ({r.med} med, {r.low} low)")


POLICIES: dict[str, Policy] = {
    "actual (baseline)": actual,
    "no_high": no_high,
    "no_high_or_med": no_high_or_med,
    "total_falling": total_falling,
    "weighted_falling": weighted_falling,
    "rubber_stamp_detector": rubber_stamp_detector,
    "semi_auto": semi_auto,
    "severity_floor": severity_floor,
}
