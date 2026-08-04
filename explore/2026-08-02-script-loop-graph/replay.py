"""Replay recorded script-review runs through every candidate stop policy.

READ-ONLY. Reads `projects/<slug>/scriptgen/` and writes nothing back — an experiment that can
corrupt the thing it is measuring is not a benchmark.

NO LLM CALLS, NO FLEET. Every input already exists on disk because the runs already happened.
That is the whole point of doing this before the live loop: it separates "does the orchestration
decide correctly" from "does the writer write well", and only the first is answerable cheaply,
deterministically, and against ground truth.

    D:\\env\\nolan\\python.exe -X utf8 explore/2026-08-02-script-loop-graph/replay.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from policies import ASK, CONTINUE, POLICIES, STOP           # noqa: E402
from state import LoopState, RoundState                      # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PROJECTS = REPO / "projects"


def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _findings(obj) -> list:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("findings", "items", "results"):
            if isinstance(obj.get(k), list):
                return obj[k]
    return []


def load_run(slug: str, root: Path | None = None) -> LoopState | None:
    """One recorded run, reduced to `LoopState`. Returns None if it never reached a review.

    `root` defaults to `projects/`. The live loop passes its sandbox root so a fresh round is
    scored by EXACTLY the code that produced the benchmark — if scoring diverged between replay
    and live, every comparison between them would be meaningless.
    """
    sg = (root or PROJECTS) / slug / "scriptgen"
    meta = _load_json(sg / "meta.json") or {}
    reviews = sorted((sg / "reviews").glob("review-*.findings.json"))
    if not reviews:
        return None

    st = LoopState(
        slug=slug,
        style_id=meta.get("style_id") or "",
        archetype=meta.get("review_archetype") or "",
        target_minutes=float(meta.get("target_minutes") or 0),
        mode=meta.get("mode") or "",
        n_sources=len(meta.get("sources") or []),
        promoted_draft=meta.get("promoted_draft"),
    )
    for fp in reviews:
        n = int(re.search(r"review-(\d+)", fp.name).group(1))
        items = _findings(_load_json(fp))
        approved = _load_json(fp.with_name(f"review-{n:02d}.approved.json"))
        appr = _findings(approved) if approved is not None else None
        # The draft this round judged. Reference only — the words never enter the state.
        draft = sg / "drafts" / f"draft-{n:02d}.md"
        words = len(draft.read_text(encoding="utf-8").split()) if draft.exists() else 0
        st.rounds.append(RoundState(
            n=n,
            draft_path=str(draft.relative_to(REPO)) if draft.exists() else "",
            draft_words=words,
            findings_by_severity=dict(Counter((i.get("severity") or "?") for i in items)),
            findings_by_dim=dict(Counter((i.get("dim") or "?") for i in items)),
            approved=(len(appr) if appr is not None else None),
            reviewed=(len(items) if appr is not None else None),
        ))
    return st


def discover() -> list[str]:
    out = []
    for d in sorted(PROJECTS.glob("*/scriptgen/reviews")):
        if list(d.glob("review-*.findings.json")):
            out.append(d.parent.parent.name)
    return out


_MARK = {STOP: "STOP", CONTINUE: "cont", ASK: "ASK "}


def replay(st: LoopState) -> None:
    print(f"\n{'=' * 96}")
    hdr = (f"{st.slug}   style={st.style_id or '?'}  archetype={st.archetype or '?'}  "
           f"mode={st.mode or '?'}  {st.target_minutes:g}min  {st.n_sources} sources")
    print(hdr)
    print(f"{'=' * 96}")

    print("  what was RECORDED:")
    for r in st.rounds:
        appr = (f"human {r.approved}/{r.reviewed}" if r.human_saw_it else "NO human review")
        print(f"    round {r.n}: {r.total:2d} findings  "
              f"({r.high}h/{r.med}m/{r.low}l, weighted {r.weighted():3d})   "
              f"{r.draft_words:5d} words   {appr}")
    print(f"    promoted: {st.promoted_draft or '(none)'}")

    print("\n  what each POLICY would have decided, round by round:")
    width = max(len(n) for n in POLICIES)
    print(f"    {'policy':<{width}}  " + "  ".join(f"after r{r.n}" for r in st.rounds))
    for name, fn in POLICIES.items():
        cells = []
        for i in range(1, len(st.rounds) + 1):
            d = fn(st.upto(i))               # only what was knowable at the time
            cells.append(f"{_MARK.get(d.action, d.action):>8s}")
        print(f"    {name:<{width}}  " + "  ".join(cells))

    print("\n  reasons at the FINAL round:")
    for name, fn in POLICIES.items():
        d = fn(st)
        print(f"    {name:<{width}}  {_MARK.get(d.action, d.action)}  {d.why}")


def main() -> int:
    slugs = sys.argv[1:] or discover()
    if not slugs:
        print("no recorded review rounds found under projects/*/scriptgen/reviews/")
        return 1
    runs = [r for r in (load_run(s) for s in slugs) if r]
    print(f"replaying {len(runs)} recorded run(s), read-only, no LLM calls")
    for st in runs:
        replay(st)

    # The cross-run fact that matters more than any single verdict.
    multi = [r for r in runs if len(r.rounds) > 1]
    print(f"\n{'=' * 96}\nACROSS ALL RUNS")
    print(f"  runs with a review round      : {len(runs)}")
    print(f"  runs that iterated more than 1: {len(multi)}  "
          f"({', '.join(r.slug for r in multi) or 'none'})")
    seen = [(r.slug, rd.n, rd.approval_rate) for r in runs for rd in r.rounds if rd.human_saw_it]
    if seen:
        perfect = sum(1 for _, _, a in seen if (a or 0) >= 0.999)
        print(f"  human-reviewed rounds         : {len(seen)}, of which "
              f"{perfect} approved 100% of findings")
    never = [(r.slug, rd.n) for r in runs for rd in r.rounds if not rd.human_saw_it]
    if never:
        print(f"  rounds with NO human review   : {len(never)}  "
              f"({', '.join(f'{s} r{n}' for s, n in never)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
