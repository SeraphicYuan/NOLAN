"""The render manifest — ONE place that knows which file is the deliverable, and whether it is current.

WHY THIS MODULE EXISTS (a wrong answer, not a preference).

`renders/` had no canonical name. `render_incremental` defaulted to `renders/<comp>.mp4` while
`finish.py` passed `out=renders/video.mp4` — one function, two names, no marker saying which one you
would publish. Across the lab that left 2-4 top-level mp4s per comp.

Then both QA gates resolved their input like this:

    vids = sorted(rd.glob("*.mp4")); return vids[0] if vids else None

Alphabetically first. Almost every composition id sorts before "video", so the perceptual and temporal
gates — the "verify like an editor" layer — were scoring a file nobody ships:

    homer-hf                 -> homer-hf-sfx-preview.mp4   (an SFX preview)
    aeneid-essay             -> aeneid-essay.mp4
    ai-datacenter-debate-v5  -> v46.mp4
    the-openai-debate        -> the-openai-debate.mp4

That is a silent FALSE NEGATIVE: a bad render passes because a good preview scored. Any module that
needs "the render" asks HERE; a private resolver is the fork that created this (WIRING_CHECKLIST #4).

STALENESS. `renders/.done` was `{"comp": ..., "rendered": true}` — a boolean where a comparison is
needed. The manifest records a PER-FRAME fingerprint instead, so staleness is not "6 edits behind" but
"frames 04-invent-the-tradition and 07-the-test are stale" — which names what to re-render.

Each fingerprint combines two things, because they answer different questions and one alone is wrong:
`incremental.frame_sig` (the composed HTML + mounted elements — "must I re-render this clip?") AND the
spec file's bytes. Using `frame_sig` alone reports `current` for a frame whose spec was edited but not
yet recomposed; using the spec alone flags edits that change no pixels. See `frame_sigs`.

The manifest also ABSORBS `.done`: its presence is the completion signal a detached `hf-finish` keys
on. Two staleness markers would be two dialects for one decision.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

MANIFEST = "render.json"
DELIVERABLE = "video.mp4"          # the ONE name. See CUT 6 in docs/DELIVERABLE_AND_SHIP_PROGRAM.md
PREVIOUS = "previous.mp4"
WORK_DIR = "_work"

# Everything permitted at the top level of renders/. Anything else is an intermediate that leaked out
# of _work/ or a second deliverable — both of which this module exists to prevent.
ALLOWED_TOP_LEVEL = {MANIFEST, DELIVERABLE, PREVIOUS, WORK_DIR, "history",
                     ".done",                       # legacy sentinel, tolerated on read, never written
                     ".captions_overlay.sig", "captions_overlay.webm", ".clipcache.json"}


def renders_dir(comp_dir) -> Path:
    return Path(comp_dir) / "renders"


def work_dir(comp_dir) -> Path:
    d = renders_dir(comp_dir) / WORK_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def manifest_path(comp_dir) -> Path:
    return renders_dir(comp_dir) / MANIFEST


def load(comp_dir) -> Optional[Dict[str, Any]]:
    p = manifest_path(comp_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def deliverable(comp_dir, *, must_exist: bool = True) -> Optional[Path]:
    """THE render — the file you would publish. Every consumer asks this; nobody globs.

    Falls back to `video.mp4` when there is no manifest (a comp rendered before this existed), and
    returns None rather than guessing when even that is absent. It never picks "some mp4 in the
    directory" — that is precisely the bug this replaces, and a wrong file scored silently is worse
    than an honest None.
    """
    rd = renders_dir(comp_dir)
    m = load(comp_dir)
    name = (m or {}).get("deliverable") or DELIVERABLE
    p = rd / name
    if p.exists() or not must_exist:
        return p
    legacy = rd / DELIVERABLE
    return legacy if legacy.exists() else None


def frame_sigs(comp: str) -> Dict[str, str]:
    """Per-frame fingerprints: the RENDER hash and the SPEC bytes, combined.

    Two different questions, and using one answer for both is wrong in a way a test caught:

      * `incremental.frame_sig` hashes the COMPOSED HTML + the mounted elements — "do I need to
        re-render this clip?". Correct as a render cache key, and deliberately untouched here
        (changing it would invalidate every cached clip in the lab).
      * staleness asks "does the deliverable reflect the author's current SPECS?" — and a spec edit
        that has not been recomposed yet leaves the composed HTML identical, so `frame_sig` alone
        reports `current` for a frame the author has already changed.

    Accepting a proposal recomposes, so in practice the two track each other; but the guard exists
    precisely for the case where they have drifted, so it hashes both.
    """
    from .edit import _frame_index, list_frames
    from .incremental import frame_sig
    try:
        idx, frames = _frame_index(comp), list_frames(comp)
    except Exception:
        return {}          # a render SUCCEEDED; failing to enumerate frames must not lose the
                           # completion signal. An empty map reads as stale once frames reappear.
    out: Dict[str, str] = {}
    for fr in frames:
        fid = fr.get("id") if isinstance(fr, dict) else fr
        h = hashlib.sha1()
        try:
            h.update(frame_sig(comp, fid).encode())
        except Exception:
            h.update(b"?")          # unhashable → reads as changed rather than silently equal
        try:
            h.update(Path(idx[fid]["spec_file"]).read_bytes())
        except (KeyError, OSError):
            h.update(b"?")
        out[fid] = h.hexdigest()[:16]
    return out


def compute_sig(sigs: Dict[str, str]) -> str:
    h = hashlib.sha1()
    for fid in sorted(sigs):
        h.update(f"{fid}={sigs[fid]};".encode())
    return h.hexdigest()[:16]


def write(comp: str, comp_dir, *, mode: str, duration_s: Optional[float] = None,
          gates: Optional[Dict[str, Any]] = None, name: str = DELIVERABLE) -> Dict[str, Any]:
    """Record what was just rendered. Written on SUCCESS only — its presence is the completion signal."""
    sigs = frame_sigs(comp)
    man = {"version": 1, "comp": comp, "deliverable": name,
           "rendered_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "mode": mode,
           "duration_s": round(float(duration_s), 2) if duration_s else None,
           "sig": compute_sig(sigs), "frames": sigs, "gates": gates or {}}
    p = manifest_path(comp_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    (renders_dir(comp_dir) / ".done").unlink(missing_ok=True)   # the manifest supersedes it
    return man


def clear(comp_dir) -> None:
    """Drop the completion signal before a fresh render, so a detached watcher can't false-fire."""
    manifest_path(comp_dir).unlink(missing_ok=True)
    (renders_dir(comp_dir) / ".done").unlink(missing_ok=True)


def is_done(comp_dir) -> bool:
    """Has a render completed? (`.done` is still honoured for comps rendered before the manifest.)"""
    return manifest_path(comp_dir).exists() or (renders_dir(comp_dir) / ".done").exists()


def staleness(comp: str, comp_dir) -> Dict[str, Any]:
    """Is the deliverable current, and if not, WHICH frames moved.

    `unknown` (no manifest) is deliberately distinct from `stale`: one means "we cannot tell", the
    other means "we can, and it isn't". Reporting the first as the second would make every
    pre-manifest comp look broken."""
    m = load(comp_dir)
    if not m:
        return {"state": "unknown", "stale_frames": [], "detail": "no render.json — render to establish a baseline"}
    now = frame_sigs(comp)
    was = m.get("frames") or {}
    changed = sorted(set(now) - set(was)) + sorted(f for f in now if f in was and now[f] != was[f])
    gone = sorted(set(was) - set(now))
    if not changed and not gone:
        return {"state": "current", "stale_frames": [], "detail": f"matches render.json ({m.get('sig')})"}
    bits = []
    if changed:
        bits.append(f"{len(changed)} frame(s) changed since the render: {', '.join(changed)}")
    if gone:
        bits.append(f"{len(gone)} frame(s) removed: {', '.join(gone)}")
    return {"state": "stale", "stale_frames": changed, "removed_frames": gone, "detail": "; ".join(bits)}


def rotate_previous(comp_dir, name: str = DELIVERABLE) -> Optional[Path]:
    """Keep exactly ONE predecessor, for an A/B against the last cut before publishing.

    Not an unbounded `history/`: a past render is RE-DERIVABLE from its specs (the manifest records
    them, and `rollback_batch` restores them), so keeping every ~900 MB derivative would be storing
    what can be recomputed, with nobody owning deletion. `tag()` is the opt-in escape for a cut you
    know you want to keep."""
    cur = renders_dir(comp_dir) / name
    if not cur.exists():
        return None
    prev = renders_dir(comp_dir) / PREVIOUS
    prev.unlink(missing_ok=True)
    try:
        cur.replace(prev)
    except OSError:
        return None
    return prev


def tag(comp_dir, label: str) -> Optional[Path]:
    """Promote the current deliverable to `history/<label>.mp4` — bounded by intent, not by time."""
    src = deliverable(comp_dir)
    if not src or not src.exists():
        return None
    safe = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in label).strip("-") or "cut"
    dst = renders_dir(comp_dir) / "history" / f"{safe}.mp4"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    return dst


def stray_files(comp_dir) -> List[str]:
    """Top-level entries in renders/ that are neither the deliverable nor a declared companion —
    i.e. leaked intermediates or a second deliverable. The honesty test asserts this is empty."""
    rd = renders_dir(comp_dir)
    if not rd.is_dir():
        return []
    return sorted(p.name for p in rd.iterdir() if p.name not in ALLOWED_TOP_LEVEL)


def main():
    """`python -X utf8 -m nolan.hyperframes.manifest <comp> [--clean]` — what the deliverable is,
    whether it is current, and what is loitering in the delivery directory."""
    import argparse
    import shutil
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.manifest",
                                 description="Report (and optionally tidy) a comp's renders/ directory.")
    ap.add_argument("comp")
    ap.add_argument("--clean", action="store_true",
                    help="DELETE the stray entries listed below (intermediates + duplicate "
                         "deliverables). Never touches the deliverable, previous.mp4 or history/.")
    a = ap.parse_args()
    from .edit import _comp_dir
    cd = _comp_dir(a.comp)
    d = deliverable(cd)
    st = staleness(a.comp, cd)
    print(f"comp        {a.comp}")
    print(f"deliverable {d.name if d else '(none)'}"
          + (f"  {d.stat().st_size / 1e6:.0f} MB" if d and d.exists() else ""))
    print(f"state       {st['state']} — {st['detail']}")
    strays = stray_files(cd)
    if not strays:
        print("strays      none")
        return
    print(f"strays      {len(strays)}")
    for s in strays:
        print(f"  · {s}")
    if a.clean:
        for s in strays:
            p = renders_dir(cd) / s
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
        print(f"cleaned {len(strays)} entr(ies)")
    else:
        print("(re-run with --clean to remove them)")


if __name__ == "__main__":
    main()
