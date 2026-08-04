"""Phase 2 — one real round: dispatch a review to a fleet agent, score it, decide.

    # plumbing only, no agent spawned, no tokens spent
    D:\\env\\nolan\\python.exe -X utf8 explore/.../live_loop.py --dry-run
    # the real thing
    D:\\env\\nolan\\python.exe -X utf8 explore/.../live_loop.py

WHAT THIS RUN IS ASKING. `homer-auto` scored weighted 17 at round 1 — two points above the chosen
floor of 15 — so `severity_floor` says CONTINUE where the real run stopped. A revision was in fact
written (draft-02 exists) but nobody ever reviewed it. So the open question is the policy's most
contentious prediction, on the cheapest possible case: **did that revision pay?**

  draft-02 scores well below 17  ->  the revision paid; continuing was right
  draft-02 scores at or above 17 ->  it did not; the floor is wrong and we learn it here

A DEFECT THIS WORKS AROUND, and it must be fixed before any of this is promoted:
`ScriptProjectStore(root=...)` is only HALF parameterised. The store honours the root — it found
this copy and correctly identified draft-02 as current — but `tasks.review_task` builds its paths
from a hardcoded `f"projects/{slug}/scriptgen"`. So a task generated against a non-default root
tells the agent to READ and WRITE production. Pointing the store elsewhere is not enough to
isolate a run, which is a trap for anyone who assumes the parameter means what it says.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fleet_kinds as fk                                    # noqa: E402
from policies import POLICIES                               # noqa: E402
from replay import load_run                                 # noqa: E402

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RUNS = HERE / "_runs"
RUN_ROOT_REL = RUNS.relative_to(REPO).as_posix()            # explore/<slug>/_runs
SLUG = "homer-auto"       # overridable with --slug, for the calibration run


def retarget(prompt: str, slug: str) -> str:
    """Point every path in a generated task at the RUN copy instead of production.

    Not cosmetic — without it the agent writes `review-02.findings.json` into
    `projects/homer-auto/`, corrupting the very run this experiment measures against. The
    assertion is part of the shim: silently missing one path is worse than not shimming at all,
    because the damage would land in production and look like a successful experiment.
    """
    out = prompt.replace(f"projects/{slug}/", f"{RUN_ROOT_REL}/{slug}/")
    leaked = sorted(set(re.findall(r"projects/[\w\-./]+", out)))
    if leaked:
        raise AssertionError(f"retarget missed {len(leaked)} production path(s): {leaked[:5]}")
    return out


def wsl(p: Path) -> str:
    s = str(p).replace("\\", "/")
    return f"/mnt/{s[0].lower()}{s[2:]}" if len(s) > 1 and s[1] == ":" else s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="build and verify the prompt; spawn nothing, spend nothing")
    ap.add_argument("--timeout", type=float, default=1200)
    ap.add_argument("--slug", default=SLUG)
    args = ap.parse_args()

    from nolan.scriptwriter import ScriptProjectStore, tasks

    slug = args.slug

    store = ScriptProjectStore(RUNS)
    meta = store.get(slug)
    num, draft = store.current_draft(slug)
    print(f"run root : {RUN_ROOT_REL}")
    print(f"project  : {meta['name']}  style={meta['style_id']}  mode={meta.get('mode')}")
    print(f"reviewing: draft-{num:02d} ({len(draft.read_text(encoding='utf-8').split())} words)")

    findings = RUNS / slug / "scriptgen" / "reviews" / f"review-{num:02d}.findings.json"
    if findings.exists():
        findings.unlink()                     # a stale artifact would satisfy the wait instantly

    prompt = retarget(tasks.review_task(slug, store, unattended=True), slug)
    print(f"prompt   : {len(prompt)} chars, 0 production paths (verified)")

    if args.dry_run:
        (HERE / "_last_prompt.md").write_text(prompt, encoding="utf-8")
        print("\nDRY RUN — nothing spawned. Prompt written to _last_prompt.md")
        return 0

    if not fk.ensure_tmux():
        print("tmux unreachable"); return 1
    res = fk.reserve(fk.SCRIPT_LOOP, meta={"slug": slug, "phase": f"review-{num:02d}"})
    if not res:
        print(f"no agent available (ceiling {fk.SCRIPT_LOOP.max_concurrent})"); return 1
    print(f"agent    : {res.session}")

    try:
        time.sleep(12)                        # let claude boot before it is typed at
        # The prompt is long and multi-line; hand it over as a FILE rather than as keystrokes.
        pf = HERE / "_last_prompt.md"
        pf.write_text(prompt, encoding="utf-8")
        fk.dispatch(res, f"Read {wsl(pf)} and do exactly what it says. "
                         f"Work only under {RUN_ROOT_REL}/ — never touch projects/.")
        print(f"dispatched; waiting for {findings.name} (timeout {args.timeout:.0f}s)")

        t0 = time.time()
        verdict = fk.await_done(
            res, lambda: findings.exists() and findings.stat().st_size > 2,
            timeout_s=args.timeout, poll_s=5,
            progress=lambda left: print(f"   ...{int(time.time()-t0)}s elapsed, "
                                        f"{int(left)}s left", flush=True)
            if int(time.time() - t0) % 60 < 5 else None)
        print(f"\nagent verdict: {verdict} after {time.time()-t0:.0f}s")
        if verdict != fk.DONE:
            return 1
    finally:
        fk.release(res)
        print(f"released {res.session}")

    # --- score it with the SAME code the replay used -------------------------------------------
    st = load_run(slug, root=RUNS)
    for rd in st.rounds:
        print(f"  round {rd.n}: {rd.total:2d} findings ({rd.high}h/{rd.med}m/{rd.low}l) "
              f"weighted {rd.weighted():3d}")
    print("\n  policy decisions after this round:")
    for name, fn in POLICIES.items():
        d = fn(st)
        print(f"    {name:24s} {d.action:9s} {d.why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
