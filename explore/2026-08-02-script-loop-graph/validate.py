"""P8 — run the redesigned pairwise judge across several drafts, in parallel, and report.

Every conclusion in this experiment so far rests on ONE Homer script in one style. This runs the
new judge over three projects spanning three styles and two archetypes, concurrently on the fleet
(whose ceiling is 3, which is exactly the shape of this job).

It exercises, end to end and for real: the fleet's reservation ceiling, code-written provenance,
the pairwise brief, verdict parsing, and the routing in `loop_control` — the pieces built
separately in P1-P6.

    D:\\env\\nolan\\python.exe -X utf8 explore/.../validate.py --dry-run
    D:\\env\\nolan\\python.exe -X utf8 explore/.../validate.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fleet_kinds as fk                                          # noqa: E402
import loop_control as lc                                         # noqa: E402
from live_loop import assert_sandboxed, wsl                       # noqa: E402

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RUNS = HERE / "_runs"
RUN_ROOT_REL = RUNS.relative_to(REPO).as_posix()

# Three styles, two archetypes, each with a previous draft to compare against — the spread the
# single-script evidence has been missing.
CASES = [
    ("homer-braid", "v-homer-braid"),                 # channel-great-books-explained
    ("ai-data-center-debate", "v-aidc"),              # channel-stickman-talks
    ("the-ai-debate-golden", "v-ai-golden"),          # channel-lufei-wang-eng
]


def stage(src_slug: str, dst_slug: str) -> bool:
    """Copy a production project into the sandbox. Read production, write locally — never the
    other way round."""
    src = REPO / "projects" / src_slug / "scriptgen"
    if not src.is_dir():
        print(f"  ! {src_slug}: no scriptgen"); return False
    dst = RUNS / dst_slug
    shutil.rmtree(dst, ignore_errors=True)
    (dst).mkdir(parents=True)
    shutil.copytree(src, dst / "scriptgen")
    meta_p = dst / "scriptgen" / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    meta["slug"] = dst_slug
    meta["name"] = f"{meta.get('name', src_slug)} [VALIDATE]"
    meta_p.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    # A stale verdict would satisfy the wait instantly and report someone else's judgement.
    for p in (dst / "scriptgen" / "reviews").glob("*.pairwise.json"):
        p.unlink()
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=float, default=1500)
    args = ap.parse_args()

    from nolan.scriptwriter import ScriptProjectStore, pairwise, provenance, verdicts
    from nolan.scriptwriter import gate as sgate

    store = ScriptProjectStore(RUNS)
    jobs = []
    for src, dst in CASES:
        if not stage(src, dst):
            continue
        num, path = store.current_draft(dst)
        meta = store.get(dst)
        brief = assert_sandboxed(pairwise.pairwise_task(dst, store))
        prov = provenance.judge_provenance(dst, store, brief=brief, draft_n=num,
                                           unattended=True, phase="review")
        provenance.write_provenance(store, dst, num, prov)
        want = verdicts.verdict_path(store, dst, num)
        want.unlink(missing_ok=True)
        jobs.append({"slug": dst, "src": src, "n": num, "brief": brief, "want": want,
                     "style": meta.get("style_id"), "arch": prov["archetype"],
                     "brief_sha": prov["brief_sha256"][:12]})
        print(f"  staged {dst:16s} draft-{num:02d}  style={meta.get('style_id')[:26]:28s} "
              f"arch={prov['archetype']:20s} brief={prov['brief_sha256'][:8]}")

    if not jobs:
        print("nothing staged"); return 1
    if args.dry_run:
        for j in jobs:
            (HERE / f"_brief_{j['slug']}.md").write_text(j["brief"], encoding="utf-8")
        print(f"\nDRY RUN — {len(jobs)} briefs written, nothing spawned")
        return 0

    if not fk.ensure_tmux():
        print("tmux unreachable"); return 1

    # All three at once: the fleet ceiling is 3, so this also proves the ceiling is the real
    # constraint rather than an untested constant.
    for j in jobs:
        j["res"] = fk.reserve(fk.SCRIPT_LOOP, meta={"slug": j["slug"], "phase": "pairwise"})
        print(f"  agent  {j['slug']:16s} -> {j['res'].session if j['res'] else 'REFUSED (ceiling)'}")
    live = [j for j in jobs if j.get("res")]
    reserved = list(live)          # release what we RESERVED, not what we ended up dispatching to
    try:
        # NEVER a fixed sleep. Dispatching into an agent that has not reached a prompt throws the
        # brief away silently, and the run then spends its whole timeout waiting for an artifact
        # nobody was ever asked to write. That is exactly how this script burned 25 minutes and
        # reported "0/3 done" with no cause: all three agents were sitting in a settings-error
        # dialog, and the keystrokes went into a modal that does not read them.
        ready, stuck = [], []
        for j in live:
            try:
                fk.await_ready(j["res"])
                ready.append(j)
            except fk.NotReady as e:
                stuck.append((j, e))
        if stuck:
            print(f"\n{'!' * 92}")
            for j, e in stuck:
                print(f"! {j['slug']}: {e}")
            print(f"{'!' * 92}")
        if not ready:
            print("\nno agent ever reached a prompt — nothing was dispatched")
            return 1                                  # loud: the `finally` still releases them
        for j in ready:
            pf = HERE / f"_brief_{j['slug']}.md"
            pf.write_text(j["brief"], encoding="utf-8")
            fk.dispatch(j["res"], f"Read {wsl(pf)} and do exactly what it says. "
                                  f"Work only under {RUN_ROOT_REL}/ — never touch projects/.")
        live = ready
        print(f"\ndispatched {len(live)}; waiting (timeout {args.timeout:.0f}s)")
        t0 = time.time()
        while time.time() - t0 < args.timeout:
            done = [j for j in live if j["want"].exists()]
            if len(done) == len(live):
                break
            time.sleep(10)
            if int(time.time() - t0) % 120 < 10:
                print(f"   ...{int(time.time()-t0)}s, {len(done)}/{len(live)} done", flush=True)
        print(f"finished after {time.time()-t0:.0f}s")
    finally:
        for j in reserved:
            fk.release(j["res"])
        print(f"released {len(reserved)} agent(s)")

    print(f"\n{'=' * 92}\nVERDICTS\n{'=' * 92}")
    rows = []
    for j in live:
        v = verdicts.read_verdict(store, j["slug"], j["n"])
        rep = sgate.run_gate(j["slug"], store=store)
        gate_fail = [c.id for c in rep.checks if c.level == "fail"]
        act = lc.decide(v, round_n=j["n"], rounds=[[*(v.blockers if v else [])]],
                        gate_ok=not gate_fail, gate_failures=gate_fail)
        rows.append((j, v, gate_fail, act))
        print(f"\n{j['src']}  ({j['style']}, {j['arch']}, draft-{j['n']:02d})")
        if v is None:
            print("   no verdict produced")
        else:
            print(f"   {verdicts.summarise(v)}")
            print(f"   why: {v.why[:150]}")
            for g in v.gains[:2]:
                print(f"     + {str(g.get('beat'))[:22]:24s} {str(g.get('what'))[:80]}")
            for r in v.regressions[:2]:
                print(f"     - {str(r.get('beat'))[:22]:24s} {str(r.get('what'))[:80]}")
        print(f"   gate: {'FAIL ' + ','.join(gate_fail) if gate_fail else 'pass'}")
        print(f"   -> {act.action.upper()}: {act.why[:110]}")

    ok = sum(1 for _, v, _, _ in rows if v is not None)
    print(f"\n{'=' * 92}\n{ok}/{len(rows)} produced a verdict")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
