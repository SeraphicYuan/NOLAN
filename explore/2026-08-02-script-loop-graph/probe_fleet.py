"""Exercise the fleet lifecycle against REAL tmux, with no Claude agent involved.

Same discipline as replaying recorded runs instead of generating new ones: test the mechanism
separately from the thing it orchestrates. Spawning a shell proves reserve/await/reap/ceiling
work; spawning an agent would prove that AND cost money AND take minutes, and a failure would be
ambiguous between the two.

    D:\\env\\nolan\\python.exe -X utf8 explore/2026-08-02-script-loop-graph/probe_fleet.py
"""

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fleet_kinds as fk           # noqa: E402
from nolan import fleet as _f      # noqa: E402

SCRATCH = Path(__file__).parent / "_probe_scratch"


def _cleanup():
    for r in fk.roster(fk.PROBE):
        fk.release(r)
    shutil.rmtree(SCRATCH, ignore_errors=True)


def main() -> int:
    # Wake WSL first, with a timeout that survives a cold VM boot — `_f._tmux` allows 8s and a
    # cold start exceeds it. See `fleet_kinds.ensure_tmux`.
    if not fk.ensure_tmux():
        print("tmux unreachable — skipping (needs wsl.exe tmux)")
        return 0
    _cleanup()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    ok = True

    # --- 1. reserve is atomic and names sequentially ------------------------------------------
    a = fk.reserve(fk.PROBE, meta={"role": "first"})
    b = fk.reserve(fk.PROBE, meta={"role": "second"})
    print(f"1. reserved: {a.session if a else None}, {b.session if b else None}")
    ok &= bool(a and b and a.session != b.session)
    print(f"   distinct sessions: {ok}")

    # --- 2. the ceiling actually refuses ------------------------------------------------------
    extra = [fk.reserve(fk.PROBE) for _ in range(fk.PROBE.max_concurrent)]
    granted = [r for r in extra if r]
    refused = [r for r in extra if r is None]
    print(f"2. ceiling {fk.PROBE.max_concurrent}: live={len(fk.live(fk.PROBE))}, "
          f"further grants={len(granted)}, refusals={len(refused)}")
    ok &= len(fk.live(fk.PROBE)) <= fk.PROBE.max_concurrent and bool(refused)
    print(f"   ceiling held: {len(fk.live(fk.PROBE)) <= fk.PROBE.max_concurrent and bool(refused)}")
    for r in granted:
        fk.release(r)

    # --- 3. await_done watches the ARTIFACT, not the agent ------------------------------------
    marker = SCRATCH / "artifact.txt"
    wsl_marker = str(marker).replace("\\", "/")
    wsl_marker = f"/mnt/{wsl_marker[0].lower()}{wsl_marker[2:]}"
    fk.dispatch(a, f"sleep 2 && echo done > {wsl_marker}")
    t0 = time.time()
    verdict = fk.await_done(a, lambda: marker.exists(), timeout_s=30, poll_s=0.5)
    print(f"3. await_done -> {verdict} in {time.time() - t0:.1f}s (artifact exists: {marker.exists()})")
    ok &= verdict == fk.DONE

    # --- 4. an agent that dies WITHOUT the artifact is `died`, not `timeout` -------------------
    fk.release(b)                                  # kill it out from under the wait
    v2 = fk.await_done(b, lambda: False, timeout_s=10, poll_s=0.5)
    print(f"4. dead agent, no artifact -> {v2}")
    ok &= v2 == fk.DIED

    # --- 5. reap clears orphans and kills stale ------------------------------------------------
    c = fk.reserve(fk.PROBE)
    c.started_at = time.time() - (fk.PROBE.ttl_s + 60)     # just past its TTL
    fk._write(c)
    killed = fk.reap(fk.PROBE)
    print(f"5. reap -> {killed}")
    ok &= any("stale" in k for k in killed)

    # --- 6. THE SAFETY INVARIANT: never touch a session we did not create ---------------------
    # nolan1..nolan6 are a human's, made by hand for other work. This is the test that says so.
    forged = fk.Reservation(kind=fk.PROBE.name, session="nolan3", started_at=0)
    try:
        fk.release(forged)
        print("6. FAILED — released a foreign session 'nolan3'")
        ok = False
    except fk.NotOurs as e:
        print(f"6. refused to kill 'nolan3': {str(e)[:72]}...")

    # ...and the second lock: a forged reservation FILE cannot grant authority either.
    fk.RESV_DIR.mkdir(parents=True, exist_ok=True)
    (fk.RESV_DIR / "nolan4.json").write_text(
        '{"kind":"probe","session":"nolan4","started_at":0,"meta":{}}', encoding="utf-8")
    try:
        fk.release(fk.Reservation(kind=fk.PROBE.name, session="nolan4", started_at=0))
        print("6b. FAILED — a forged reservation file granted authority over 'nolan4'")
        ok = False
    except fk.NotOurs:
        print("6b. refused 'nolan4' even WITH a reservation file (prefix lock held)")
    (fk.RESV_DIR / "nolan4.json").unlink(missing_ok=True)

    # --- 7. our names are invisible to the human's fleet board ---------------------------------
    d = fk.reserve(fk.PROBE)
    board = [a["agent"] for a in _f.fleet("nolan")]
    print(f"7. our session {d.session} on the nolan board? {d.session in board}  "
          f"(board: {board or 'empty'})")
    ok &= d.session not in board
    fk.release(d)

    _cleanup()
    print(f"\nlifecycle: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
