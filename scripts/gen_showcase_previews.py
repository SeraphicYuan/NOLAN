"""Batch-render a short preview clip for every showcase effect.

Renders each effect from the render service (:3010) using its default params,
then copies the output mp4 into render-service/public/previews/<name>.mp4 so the
/showcase page thumbnails load.

Run with the Windows env python so 127.0.0.1:3010 is reachable:
    D:\\env\\nolan\\python.exe -X utf8 scripts/gen_showcase_previews.py
Optional: pass effect ids to render only those, e.g. `... quote-dramatic title-card`.
"""
import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:3010"
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "render-service" / "public" / "previews"
W, H = 640, 360           # small = fast; page thumbs are tiny anyway
MAX_WAIT = 120            # seconds per effect
POLL = 1.5


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return json.load(r)


def _post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _resolve(video_path):
    """Turn a render-service video_path into a real local file."""
    if not video_path:
        return None
    p = Path(video_path)
    if p.exists():
        return p
    # try common roots
    for root in (ROOT / "render-service", ROOT / "render-service" / "output", ROOT):
        cand = root / video_path.lstrip("/\\")
        if cand.exists():
            return cand
        cand = root / p.name
        if cand.exists():
            return cand
    return None


def render_one(eff):
    eid = eff["id"]
    preview = eff.get("preview") or f"/previews/{eid}.mp4"
    dest = OUT_DIR / Path(preview).name
    params = dict(eff.get("defaults") or {})
    params.update({"width": W, "height": H})
    try:
        job = _post(f"/effects/{eid}/render", {"params": params})
    except Exception as ex:
        return eid, "submit-error", str(ex)[:120]
    jid = job.get("job_id")
    if not jid:
        return eid, "no-job", str(job)[:120]
    waited = 0.0
    while waited < MAX_WAIT:
        time.sleep(POLL)
        waited += POLL
        try:
            st = _get(f"/render/status/{jid}")
        except Exception as ex:
            return eid, "status-error", str(ex)[:120]
        s = st.get("status")
        if s == "done":
            res = _get(f"/render/result/{jid}")
            src = _resolve(res.get("video_path"))
            if not src:
                return eid, "no-output", str(res.get("video_path"))[:120]
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            return eid, "ok", dest.name
        if s == "error":
            return eid, "render-error", str(st.get("error"))[:120]
    return eid, "timeout", f"{MAX_WAIT}s"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    d = _get("/effects")
    effs = d if isinstance(d, list) else d.get("effects", d)
    want = set(sys.argv[1:])
    if want:
        effs = [e for e in effs if e["id"] in want]
    print(f"[previews] rendering {len(effs)} effects -> {OUT_DIR}", flush=True)
    tally = {}
    for i, eff in enumerate(effs, 1):
        eid, status, detail = render_one(eff)
        tally[status] = tally.get(status, 0) + 1
        print(f"[{i:>2}/{len(effs)}] {eid:<28} {status:<14} {detail}", flush=True)
    print("[previews] done:", json.dumps(tally), flush=True)


if __name__ == "__main__":
    main()
