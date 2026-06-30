"""Art-flow ingest (byo-everything) — assemble, don't generate.

For the art flow the user already has script + voiceover + images in NOLAN, and the
voiceover is ALREADY word-timestamped, so this skips TTS + Whisper entirely: it reads
NOLAN's project files and emits the render job. Read-only against NOLAN (no core changes).

Per beat it reads:
  - <project>/assets/voiceover/segments/segments.json  (segment → wav → duration)
  - <project>/assets/voiceover/segments/<seg>.words.json  ({word,start,end} list)
and pairs them with the authored {image, label, focuses} from the art-spec.

Usage: python web-video-lab/art_ingest.py <art-spec.json> <out.job.json>
Then: pacing_lint.py <job> --profile art ; render.mjs <job>
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())


def _to_win(p) -> str:
    """Any path -> Windows form (D:/...). render.mjs/node always runs on Windows."""
    m = re.match(r"^/mnt/([a-z])/(.*)$", str(p))
    return f"{m.group(1).upper()}:/" + m.group(2) if m else str(p)


def _localize(p) -> str:
    """A path -> the form the CURRENT interpreter can stat (so the ingest runs under either
    WSL python3 (/mnt/d/...) or the nolan Windows python (D:/...) — the WebUI uses the latter)."""
    p = str(p)
    if os.name == "nt":
        return _to_win(p)
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/") if m else p


def _resolve_anchors(anchors, words_raw, fps, dur_f):
    """word | '@start' | '@<sec>' -> frames, cursor-matched (first match after the
    previous), so a recurring word ('Death') hits the right occurrence."""
    out, cur = [], 0
    for a in anchors:
        a = str(a).strip()
        if a in ("", "@start"):
            out.append(0); continue
        if a.startswith("@"):
            out.append(round(float(a[1:]) * fps)); continue
        tok = _norm(a.split()[0]); hit = None
        for j in range(cur, len(words_raw)):
            wn = _norm(words_raw[j]["word"])
            if wn and (wn == tok or (len(tok) >= 3 and len(wn) >= 3 and (tok in wn or wn in tok))):
                hit = round(words_raw[j]["start"] * fps); cur = j + 1; break
        if hit is None and not a.startswith("@") and a not in ("", "@start"):
            print(f"  [warn] anchor word '{a}' not found in VO — falling back to +1s", file=sys.stderr)
        out.append(hit if hit is not None else (out[-1] + 30 if out else 0))
    return out


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    fps = int(spec.get("fps", 30))
    proj = Path(_localize(spec["project"]))            # localized to the running interpreter
    win = _to_win(spec.get("winProject") or spec["project"])   # Windows path render.mjs stages from
    segdir = proj / "assets" / "voiceover" / "segments"
    durs = {s["file"]: s["duration"] for s in json.loads((segdir / "segments.json").read_text())["segments"]}

    steps = []
    for b in spec["beats"]:
        seg = b["segment"]                              # stem, e.g. "04_the-ploughman"
        words_raw = json.loads((segdir / f"{seg}.words.json").read_text(encoding="utf-8"))
        words = [{"text": w["word"], "startFrame": round(w["start"] * fps), "endFrame": round(w["end"] * fps)}
                 for w in words_raw]
        dur_s = durs.get(f"{seg}.wav") or (words_raw[-1]["end"] if words_raw else 1)
        dur_f = max(1, round(dur_s * fps))
        reveal = _resolve_anchors(b["revealWords"], words_raw, fps, dur_f) if b.get("revealWords") else [0]
        steps.append({
            "block": b.get("block", "ArtworkStage"),
            "audioSrc": f"{win}/assets/voiceover/segments/{seg}.wav",
            "durationInFrames": dur_f,
            "revealFrames": reveal,
            "words": words,
            "props": {k: v for k, v in b.items() if k in (
                "src", "left", "right", "region", "cards", "hero", "kenBurns", "label", "focuses",
                "headline", "takeaways", "source", "verdict", "kicker", "introHold", "maxZoom", "glide")},
        })
        print(f"{seg:28} {dur_f:5}f  {len(words):3} words  {len(b.get('focuses', []))} focuses")

    job = {"out": spec["out"], "theme": spec.get("theme", "midnight-press"),
           "captions": spec.get("captions", False), "props": {"steps": steps}}
    if spec.get("fx"):
        job["fx"] = spec["fx"]
    out.write_text(json.dumps(job, indent=2), encoding="utf-8")
    print(f"-> {out}  (total {sum(s['durationInFrames'] for s in steps)} frames)")


if __name__ == "__main__":
    main()
