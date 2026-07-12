"""Global block planner — decompose the GLOBAL style contract CENTRALLY, so parallel frame workers fill
only copy/reveals instead of each trying to satisfy a whole-video constraint they can't see.

nolan4's structural finding after v3: block distribution, grounding %, and adjacency runs are GLOBAL —
a per-frame worker can't own them, so the orchestrator had to design the 44-scene block plan by hand and
the workers mostly transcribed it. Per NOLAN's capability routing that global assignment is COMPUTABLE:
given each beat's CANDIDATE blocks (an LLM pass proposes them from the beat's content) + the style-
contract targets, assign a contract-satisfying block skeleton (block + grounded, per beat). Workers then
author copy/reveals WITHIN the assignment — the taste part, parallelised; the global optimisation, central.

Input beats: [{"id", "candidates": [block, …] best-first, "groundable": bool, "tone"?: "light"|"dark"}].
  python -X utf8 -m nolan.hyperframes.block_plan beats.json
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Dict, List, Optional


def _alt(cands: List[str], avoid: set, used: Counter) -> Optional[str]:
    """A candidate not in `avoid` (neighbours to break a run / over-used blocks), least-used first."""
    opts = [c for c in cands if c not in avoid]
    if not opts:
        return None
    return min(opts, key=lambda c: (used.get(c, 0), cands.index(c)))


def plan_blocks(beats: List[Dict], *, max_run: int = 3, max_share: float = 0.5,
                coverage: tuple = (0.45, 0.95)) -> Dict:
    """Assign a contract-satisfying block skeleton. Greedy + repair: seed each beat with its top
    candidate, break adjacency runs, relieve over-concentrated blocks, then bring the grounded share
    into the coverage band. Returns {plan:[{id,block,grounded}], metrics, warnings}."""
    n = len(beats)
    if n == 0:
        return {"plan": [], "metrics": {}, "warnings": ["no beats"]}
    cand = {b["id"]: (b.get("candidates") or ["statement"]) for b in beats}
    groundable = {b["id"]: bool(b.get("groundable")) for b in beats}
    plan = [{"id": b["id"], "block": cand[b["id"]][0], "grounded": groundable[b["id"]]} for b in beats]
    warnings: List[str] = []

    # 1) break adjacency runs: never > max_run of the same block in a row
    run = 1
    for i in range(1, n):
        if plan[i]["block"] == plan[i - 1]["block"]:
            run += 1
            if run > max_run:
                avoid = {plan[i - 1]["block"]}
                if i + 1 < n:
                    avoid.add(plan[i + 1]["block"])
                a = _alt(cand[plan[i]["id"]], avoid, Counter(p["block"] for p in plan))
                if a:
                    plan[i]["block"] = a
                    run = 1
                else:
                    warnings.append(f"{plan[i]['id']}: no alternative block to break a run of {plan[i]['block']}")
        else:
            run = 1

    # 2) relieve over-concentration: no block may exceed max_share of the video
    cap = max(1, int(max_share * n))
    counts = Counter(p["block"] for p in plan)
    for blk, c in list(counts.items()):
        if c <= cap:
            continue
        for p in plan:
            if counts[blk] <= cap:
                break
            if p["block"] != blk:
                continue
            a = _alt(cand[p["id"]], {blk}, counts)
            if a:
                counts[blk] -= 1
                counts[a] += 1
                p["block"] = a
        if counts[blk] > cap:
            warnings.append(f"block '{blk}' still over cap ({counts[blk]}/{cap}) — beats lack alternatives")

    # 3) bring the grounded share into the coverage band (can only ground a groundable beat)
    lo, hi = coverage
    grounded_ids = [p["id"] for p in plan if p["grounded"]]
    frac = len(grounded_ids) / n
    if frac < lo:                                       # ground more (any groundable, currently typographic)
        for p in plan:
            if len(grounded_ids) / n >= lo:
                break
            if not p["grounded"] and groundable[p["id"]]:
                p["grounded"] = True
                grounded_ids.append(p["id"])
        if len(grounded_ids) / n < lo:
            warnings.append(f"coverage {len(grounded_ids)/n:.0%} < floor {lo:.0%} — not enough groundable beats")
    elif frac > hi:                                     # too grounded → let some ride as typography
        for p in plan:
            if len(grounded_ids) / n <= hi:
                break
            if p["grounded"]:
                p["grounded"] = False
                grounded_ids.remove(p["id"])

    final = Counter(p["block"] for p in plan)
    gfrac = sum(1 for p in plan if p["grounded"]) / n
    metrics = {"n": n, "coverage": round(gfrac, 3), "max_run": _max_run([p["block"] for p in plan]),
               "max_share": round(max(final.values()) / n, 3), "distinct_blocks": len(final),
               "block_dist": dict(final.most_common())}
    return {"plan": plan, "metrics": metrics, "warnings": warnings}


def _max_run(seq: List[str]) -> int:
    best = run = 0
    prev = None
    for x in seq:
        run = run + 1 if x == prev else 1
        best = max(best, run)
        prev = x
    return best


def main():
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: python -X utf8 -m nolan.hyperframes.block_plan <beats.json>")
    beats = json.loads(open(sys.argv[1], encoding="utf-8").read())
    r = plan_blocks(beats)
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
