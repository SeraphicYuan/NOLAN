"""Two full rounds of the script loop, run by either executor, for a like-for-like comparison.

A round is: **judge → route → revise**. Round 2 then judges the draft round 1 produced, which is
the first time anything here has actually closed the loop — P8 only ever judged once.

Two things this exercises that a single judgement cannot:

  1. **The style-fidelity dimension against a draft that was revised WITH it.** Round 1 finds
     voice drift; round 2 says whether the revise pass fixed it or broke something else.
  2. **Fix-forward routing on real data.** P8 showed every better-with-regressions draft being
     reverted. Round 2 is where carrying the break forward either converges or does not.

    D:\\env\\nolan\\python.exe -X utf8 explore/.../two_round.py --executor fleet
    D:\\env\\nolan\\python.exe -X utf8 explore/.../two_round.py --executor api
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import context as ctx                                             # noqa: E402
import executors as ex                                            # noqa: E402
import loop_control as lc                                         # noqa: E402

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

CASES = [
    ("homer-braid", "homer"),                        # channel-great-books-explained · general
    ("ai-data-center-debate", "aidc"),               # channel-stickman-talks · long-form-argument
    ("the-ai-debate-golden", "golden"),              # channel-lufei-wang-eng · long-form-argument
]

_WPM = 145
_TOL = 0.05


def runs_root(executor: str) -> Path:
    """Each executor gets its OWN sandbox. Sharing one would let round 1 of the fleet run seed
    round 2 of the API run, and the comparison would be measuring a mixture."""
    return HERE / f"_runs_{executor}"


def stage(src_slug: str, dst_slug: str, root: Path) -> bool:
    src = REPO / "projects" / src_slug / "scriptgen"
    if not src.is_dir():
        print(f"  ! {src_slug}: no scriptgen"); return False
    dst = root / dst_slug
    shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True)
    shutil.copytree(src, dst / "scriptgen")
    meta_p = dst / "scriptgen" / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    meta["slug"] = dst_slug
    meta["name"] = f"{meta.get('name', src_slug)} [2ROUND]"
    meta_p.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    for p in (dst / "scriptgen" / "reviews").glob("*.pairwise.json"):
        p.unlink()                                   # a stale verdict would satisfy the wait
    return True


def revise_brief(slug: str, store, carry: list, next_n: int, why: str,
                 cur_words: int = 0) -> str:
    """The revise pass, aimed at the change set the router carried forward.

    This is NOT `tasks.revise_task`, which applies an approved `findings.json`. The loop's change
    set comes from the pairwise verdict — the beats this round broke — and the whole point of
    fix-forward is that the next pass targets exactly those and leaves the gains alone.

    ONE PASS, ONE JOB — and an earlier version of this brief broke that rule badly enough to
    invalidate a run. It said "leave everything else byte-identical" AND "length budget: ~2900
    words (±5%), anchored on the project target" to an agent holding a 3,756-word draft. Those
    are not both satisfiable. The agent obeyed the specific, checkable one, cut 876 words (23%)
    to land within 1% of the budget, and the judge correctly called the result WORSE: the cuts
    took discourse markers, tag-questions and spoken-cadence asides — the exact texture that
    channel's guide protects with a [5/5] "read like talking, not writing" rule.

    So surgery does not resize. The length constraint here is HOLD, not hit-a-target: whatever
    the draft currently weighs, come back at about the same weight. Being over the project's
    budget is real, but it is a separate job with its own brief — one that knows cutting is the
    point and can be judged on whether it cut fat or muscle — and it is the gate's business to
    say so, not a sentence buried in a surgical instruction.
    """
    base, sg = _paths(slug, store)
    meta = store.get(slug)
    target_min = float(meta.get("target_minutes") or 15)
    target_words = int(target_min * _WPM)
    items = "\n".join(
        f"{i}. **{c.get('beat', '?')}** (severity {c.get('severity', 'n/a')}) — "
        f"{c.get('what') or c.get('problem') or ''}"
        for i, c in enumerate(carry, 1)) or "(none — make no changes)"
    guide = REPO / "script_styles" / str(meta.get("style_id") or "") / "style_guide.md"
    return f"""# NOLAN REVISE (fix-forward): "{meta['name']}"

The previous round was judged **better overall**, so its gains are KEPT. It also broke the beats
listed below, and those — and only those — are this pass's job.

## Why you are being run
{why}

## Fix exactly these
{items}

## Rules
- **Do not rewrite the draft.** Change the named beats and leave everything else byte-identical.
  A diff of your output against the current draft should touch only what is listed.
- **Do not fix other things you notice.** A large change set is what caused the regression this
  pass exists to repair; if you spot something else, ignore it this round.
- **HOLD THE LENGTH. Do not resize the script.** The current draft is {cur_words} narration
  words; come back within ±2% of that. This pass is surgery, and surgery does not resize.
  {_length_note(cur_words, target_words, target_min)}
- **Style guide:** `{guide.relative_to(REPO).as_posix()}` — the voice is the channel's, and
  style fidelity is a scored dimension. Do not drift toward generic-essay register while fixing.
  In particular, discourse markers, tag-questions and spoken-cadence asides are LOAD-BEARING
  texture, not filler — cutting them to save words is a regression, not a tightening.

## Read
- current draft: `{sg}/drafts/draft-{next_n - 1:02d}.md`
- beatmap: `{sg}/beatmap.md` · facts: `{sg}/facts.md` · citations: `{sg}/citations.md`

## Write
`{sg}/drafts/draft-{next_n:02d}.md` — the COMPLETE revised draft, same beat headings and
timecode format as the current one.
"""


def _length_note(cur_words: int, target_words: int, target_min: float) -> str:
    """Say that the draft is over budget WITHOUT asking this pass to fix it.

    Naming the overrun and then demanding surgery in the same breath is what produced a 23% cut.
    An over-budget draft is a real problem and a DIFFERENT job — one whose whole purpose is to
    cut, which can therefore be judged on whether it cut fat or muscle. Here it is stated as a
    fact the writer should not act on, so the next pass inherits an accurate picture instead of
    a silently trimmed script.
    """
    if not cur_words or cur_words <= target_words * (1 + _TOL):
        return ""
    over = 100 * (cur_words - target_words) / target_words
    return (f"(FYI only — this draft is ~{over:.0f}% over the project's {target_min:.0f}-minute "
            f"budget of ~{target_words} words. **Do not fix that here.** Trimming to budget is a "
            f"separate pass; cutting while doing surgery is what damaged the previous attempt.)")


def _paths(slug: str, store):
    from nolan.scriptwriter.tasks import project_paths
    return project_paths(slug, store)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--executor", choices=("fleet", "api", "win"), required=True)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--model", default=None, help="api only; defaults to config.llm.model")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--only", default="", help="comma-separated slugs; rerun a subset without "
                                               "discarding the projects that already succeeded")
    args = ap.parse_args()

    from nolan.scriptwriter import ScriptProjectStore, pairwise, provenance, verdicts
    from nolan.scriptwriter import gate as sgate

    root = runs_root(args.executor)
    root.mkdir(parents=True, exist_ok=True)
    store = ScriptProjectStore(root)
    if args.executor == "fleet":
        if not ex.fk.ensure_tmux():
            print("tmux unreachable"); return 1
        ok, detail = ex.fk.wsl_repo_readable()
        if not ok:
            print(f"PREFLIGHT FAILED: {detail}"); return 1
        print(f"preflight: WSL can read {detail}")
        runner = ex.FleetExecutor(timeout_s=args.timeout)
        model_label = "claude (agent)"
    elif args.executor == "win":
        # No preflight and no tmux: a Windows subprocess reads D:\ directly, which is the
        # entire point — none of the transport failures that plagued the WSL fleet can occur.
        runner = ex.WinHeadlessExecutor(timeout_s=args.timeout)
        model_label = "claude (headless windows agent)"
    else:
        runner = ex.ApiExecutor(model=args.model)
        model_label = runner.model

    print(f"executor : {runner.name}   model: {model_label}   rounds: {args.rounds}")
    jobs = []
    only = {t.strip() for t in args.only.split(",") if t.strip()}
    for src, dst in CASES:
        if only and dst not in only:
            continue
        if stage(src, dst, root):
            jobs.append({"src": src, "slug": dst, "rounds": []})
    if not jobs:
        print("nothing staged"); return 1

    t_all = time.time()

    def run_project(j: dict) -> dict:
        out: list = []
        def say(s=""):
            out.append(s)
        slug = j["slug"]
        meta = store.get(slug)
        say(f"\n{'=' * 92}\n{j['src']}  ({meta.get('style_id')})\n{'=' * 92}")
        history = []
        for rnd in range(1, args.rounds + 1):
            num, _ = store.current_draft(slug)
            brief = pairwise.pairwise_task(slug, store)
            prov = provenance.judge_provenance(slug, store, brief=brief, draft_n=num,
                                               unattended=True, phase="review")
            provenance.write_provenance(store, slug, num, prov)
            want = verdicts.verdict_path(store, slug, num)
            want.unlink(missing_ok=True)
            r = runner.run(brief=brief, want=want, slug=slug, store=store,
                           label=f"judge{rnd}", expect="json")
            say(f"  R{rnd} judge  draft-{num:02d}  {r.seconds:6.1f}s  "
                  f"{'ok' if r.ok else 'FAILED: ' + r.detail}")
            if not r.ok:
                j["rounds"].append({"round": rnd, "error": r.detail}); break
            v = verdicts.read_verdict(store, slug, num)
            if v is None:
                j["rounds"].append({"round": rnd, "error": "verdict unparseable"}); break
            history.append(list(v.blockers))
            rep = sgate.run_gate(slug, store=store)
            gate_fail = [c.id for c in rep.checks if c.level == "fail"]
            act = lc.decide(v, round_n=rnd, rounds=history,
                            gate_ok=not gate_fail, gate_failures=gate_fail)
            style_hits = [b for b in v.blockers if "style" in str(b.get("dim", "")).lower()]
            j["rounds"].append({
                "round": rnd, "draft": num, "verdict": v.verdict,
                "gains": len(v.gains), "regressions": len(v.regressions),
                "blockers": len(v.blockers), "style_blockers": len(style_hits),
                "style_detail": [f"{b.get('beat')}: {str(b.get('problem'))[:90]}"
                                 for b in style_hits[:3]],
                "gate": gate_fail, "action": act.action, "why": act.why,
                "seconds": round(r.seconds, 1), "notes": r.notes,
            })
            say(f"       {verdicts.summarise(v)}")
            say(f"       style-fidelity blockers: {len(style_hits)}")
            for s in style_hits[:3]:
                say(f"         · {str(s.get('beat'))[:26]:28s} {str(s.get('problem'))[:70]}")
            say(f"       -> {act.action.upper()}: {act.why[:100]}")

            if rnd == args.rounds or act.action in (lc.STOP, lc.ASK):
                break
            carry = act.retry_with or v.blocking(min_severity="high") or v.blockers[:2]
            nxt = store.next_draft_number(slug)
            _, sg_rel = _paths(slug, store)
            dpath = root / slug / "scriptgen" / "drafts" / f"draft-{nxt:02d}.md"
            from nolan.scriptwriter.tasks import _narration_words
            cur_txt = (root / slug / "scriptgen" / "drafts" /
                       f"draft-{nxt - 1:02d}.md").read_text(encoding="utf-8")
            rb = revise_brief(slug, store, carry, nxt, act.why,
                              cur_words=_narration_words(cur_txt))
            r2 = runner.run(brief=rb, want=dpath, slug=slug, store=store,
                            label=f"revise{rnd}", expect="text")
            say(f"  R{rnd} revise -> draft-{nxt:02d}  {r2.seconds:6.1f}s  "
                  f"{'ok' if r2.ok else 'FAILED: ' + r2.detail}")
            if not r2.ok:
                j["rounds"].append({"round": rnd, "error": f"revise: {r2.detail}"}); break
        return {"job": j, "out": out}

    if runner.name in ("fleet", "win"):
        # THE MOUNT DIES ROUGHLY HOURLY, so wall-clock is a correctness concern and not just
        # comfort: three projects in sequence is ~3x the window in which drvfs can drop out
        # mid-run. The fleet ceiling is 3, which is exactly this job's width.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(run_project, jobs))
    else:
        results = [run_project(j) for j in jobs]
    for r in results:
        print("\n".join(r["out"]), flush=True)

    suffix = ("_" + "-".join(sorted(only))) if only else ""
    out = HERE / f"_result_{args.executor}{suffix}.json"
    out.write_text(json.dumps({"executor": runner.name, "model": model_label,
                               "seconds": round(time.time() - t_all, 1), "jobs": jobs},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{'=' * 92}\nwrote {out.relative_to(REPO).as_posix()}  "
          f"({time.time() - t_all:.0f}s total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
