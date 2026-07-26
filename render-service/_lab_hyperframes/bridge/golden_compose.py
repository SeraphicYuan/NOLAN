"""Golden-HTML regression harness for the composer.

Composes EVERY frame of every spec it can find — the bridge's own `*_spec.json` fixtures plus every
shipped comp under `videos/*/compositions/frames/` — and hashes the emitted HTML. Capture a baseline
before a refactor, compare after: a change that is supposed to be mechanical must come back
byte-identical, and a change that is supposed to alter output must alter exactly the frames you
expect and no others.

    python -X utf8 golden_compose.py --out before.json      # capture
    ... make the change ...
    python -X utf8 golden_compose.py --compare before.json  # verify (exit 1 on any drift)

Written for the 2026-07-26 compose_extension -> compose merge, where it caught a real bug the move
introduced: un-qualifying `esc, num = compose.esc, compose._num` produced `esc, num = esc, _num`,
which makes `esc` a LOCAL and raises UnboundLocalError in 5 blocks. Nothing else in the suite would
have caught that before a 25-minute render died.

Compose failures are recorded as their exception text, so a change in FAILURE MODE is caught too.
`_allblocks_spec.json` exists because the shipped corpus exercises only 31 of 50 registered blocks;
it covers the rest, and both together are what makes "byte-identical" mean something.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIDEOS = HERE.parent / "videos"
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
import compose  # noqa: E402


def _specs():
    yield from sorted(HERE.glob("*_spec.json"))
    yield from sorted(VIDEOS.glob("*/compositions/frames/*.spec.json"))


def _frames(doc):
    """(frame_id, dur, scenes) from either spec shape."""
    if isinstance(doc, dict) and isinstance(doc.get("frames"), list):
        for fr in doc["frames"]:
            if isinstance(fr, dict) and isinstance(fr.get("scenes"), list):
                yield fr.get("id", "?"), float(fr.get("dur") or 0) or 30.0, fr["scenes"]
    elif isinstance(doc, dict) and isinstance(doc.get("scenes"), list):
        yield doc.get("id", "root"), float(doc.get("dur") or 30.0), doc["scenes"]


def capture():
    out, ok, err = {}, 0, 0
    for sp in _specs():
        try:
            doc = json.loads(sp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            out[sp.name] = {"<load>": f"ERR {type(e).__name__}: {e}"}
            continue
        rec = {}
        for fid, dur, scenes in _frames(doc):
            try:
                html = compose.compose_frame(fid, dur, scenes)
                rec[fid] = hashlib.sha256(html.encode("utf-8")).hexdigest()[:16] + f"/{len(html)}"
                ok += 1
            except Exception as e:                     # ANY composer failure is data, not a crash
                rec[fid] = f"ERR {type(e).__name__}: {e}"[:200]
                err += 1
        if rec:
            out[str(sp.relative_to(REPO)).replace("\\", "/")] = rec
    return out, ok, err


def main():
    ap = argparse.ArgumentParser(description="golden-HTML regression harness for compose.py")
    ap.add_argument("--out", help="write a baseline here")
    ap.add_argument("--compare", help="compare against a baseline (exit 1 on drift)")
    a = ap.parse_args()
    if not (a.out or a.compare):
        ap.error("need --out or --compare")

    got, ok, err = capture()
    print(f"specs={len(got)}  frames_ok={ok}  frames_err={err}")

    if a.out:
        Path(a.out).write_text(json.dumps(got, indent=1, sort_keys=True), encoding="utf-8")
        print(f"baseline -> {a.out}")

    if a.compare:
        want = json.loads(Path(a.compare).read_text(encoding="utf-8"))
        drift = []
        for spec in sorted(set(want) | set(got)):
            w, g = want.get(spec, {}), got.get(spec, {})
            for fid in sorted(set(w) | set(g)):
                if w.get(fid) != g.get(fid):
                    drift.append(f"  {spec} :: {fid}\n      was {w.get(fid, '<absent>')}\n      now {g.get(fid, '<absent>')}")
        if drift:
            print(f"\nDRIFT — {len(drift)} frame(s) changed:")
            print("\n".join(drift[:40]))
            if len(drift) > 40:
                print(f"  … and {len(drift) - 40} more")
            return 1
        print(f"OK — all {ok} frames byte-identical to {a.compare}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
