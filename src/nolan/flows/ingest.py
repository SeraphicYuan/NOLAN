"""Art-flow ingest (byo-everything) - assemble, don't generate. In-process port of the
former web-video-lab/art_ingest.py.

The art ingest is light: script + voiceover (already word-timestamped) + images exist in the
project, so this reads the project's segments + the authored art-spec (focuses/regions/labels/
images) and writes the render job. No TTS, no Whisper. The heavy generate-from-source path
(extract_figure + TTS + Whisper + gen_spec) is the *explainer* tenant's ingest.

Per beat it reads:
  - <project>/assets/voiceover/segments/segments.json   (segment -> wav -> duration)
  - <project>/assets/voiceover/segments/<seg>.words.json ({word,start,end} list)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())

# fields a beat may carry through to the block's props
_PROP_KEYS = (
    "src", "left", "right", "region", "cards", "hero", "kenBurns", "label", "focuses",
    "headline", "takeaways", "source", "verdict", "kicker", "introHold", "maxZoom", "glide",
    "cols", "rows", "order", "highlight",
)


def _to_win(p) -> str:
    """Any path -> Windows form (D:/...). render.mjs/node always runs on Windows."""
    m = re.match(r"^/mnt/([a-z])/(.*)$", str(p))
    return f"{m.group(1).upper()}:/" + m.group(2) if m else str(p)


def _localize(p) -> str:
    """A path -> the form the CURRENT interpreter can stat (WSL python3 /mnt/d/... or the
    nolan Windows python D:/... - the WebUI/CLI use the latter)."""
    p = str(p)
    if os.name == "nt":
        return _to_win(p)
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/") if m else p


def _resolve_anchors(anchors, words_raw, fps, dur_f):
    """word | '@start' | '@<sec>' -> frames, cursor-matched (first match after the previous),
    so a recurring word ('Death') hits the right occurrence."""
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
            print(f"  [warn] anchor word '{a}' not found in VO - falling back to +1s")
        out.append(hit if hit is not None else (out[-1] + 30 if out else 0))
    return out


def ingest_art(spec_path, job_path, *, quiet: bool = False) -> Path:
    """Assemble the project's VO segments + the art-spec into a render job (in-process)."""
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out = Path(job_path)
    fps = int(spec.get("fps", 30))
    proj = Path(_localize(spec["project"]))                  # localized to the running interpreter
    win = _to_win(spec.get("winProject") or spec["project"])  # Windows path render.mjs stages from
    segdir = proj / "assets" / "voiceover" / "segments"
    durs = {s["file"]: s["duration"]
            for s in json.loads((segdir / "segments.json").read_text(encoding="utf-8"))["segments"]}

    steps = []
    for b in spec["beats"]:
        seg = b["segment"]                                   # stem, e.g. "04_the-ploughman"
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
            "props": {k: v for k, v in b.items() if k in _PROP_KEYS},
        })
        if not quiet:
            print(f"{seg:28} {dur_f:5}f  {len(words):3} words  {len(b.get('focuses', []))} focuses")

    job = {"out": spec["out"], "theme": spec.get("theme", "midnight-press"),
           "captions": spec.get("captions", False), "props": {"steps": steps}}
    if spec.get("fx"):
        job["fx"] = spec["fx"]
    out.write_text(json.dumps(job, indent=2), encoding="utf-8")
    if not quiet:
        print(f"-> {out}  (total {sum(s['durationInFrames'] for s in steps)} frames)")
    return out


# ---------------------------------------------------------------- explainer ingest (generate)
# In-process port of web-video-lab/gen_spec.py: an anchor-based chapter spec + per-step Whisper
# word timestamps -> the render job (computed revealFrames + durations + script-relabeled
# captions). This is the byo-script explainer ingest (assemble a generated spec).
import difflib as _difflib
import wave as _wave

# number-word <-> digit, so anchor "two"/"thousand" matches whisper's digit token "2"/"1000".
_NUM = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
        "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
        "thirteen": "13", "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
        "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
        "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
        "hundred": "100", "thousand": "1000", "million": "1000000"}


def _canon(s: str) -> str:
    n = _norm(s)
    return _NUM.get(n, n)


def _wav_seconds(p) -> float:
    with _wave.open(str(p), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _relabel_captions(words, text, fps):
    """Carry the authoritative script spelling onto whisper's timing (matched runs 1:1; rewritten
    runs distribute the script tokens across that run's time span). Falls back to raw whisper."""
    def _frames(toks):
        return [{"text": t["text"], "startFrame": round(t["start"] * fps),
                 "endFrame": round(t["end"] * fps)} for t in toks]
    raw = [{"text": w["word"], "start": w["start"], "end": w["end"]} for w in words]
    script = text.split() if text else []
    if not words or not script:
        return _frames(raw)
    wc = [_canon(w["word"]) for w in words]
    sc = [_canon(t) for t in script]
    out = []
    for tag, i1, i2, j1, j2 in _difflib.SequenceMatcher(a=wc, b=sc, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                w = words[i1 + k]
                out.append({"text": script[j1 + k], "start": w["start"], "end": w["end"]})
            continue
        stoks = script[j1:j2]
        if not stoks:
            continue
        wrun = words[i1:i2]
        if wrun:
            t0, t1 = wrun[0]["start"], wrun[-1]["end"]
        else:
            t0 = out[-1]["end"] if out else (words[i1]["start"] if i1 < len(words) else 0.0)
            t1 = words[i1]["start"] if i1 < len(words) else t0
        span = max(t1 - t0, 1e-3)
        n = len(stoks)
        for k, tok in enumerate(stoks):
            out.append({"text": tok, "start": t0 + span * k / n, "end": t0 + span * (k + 1) / n})
    return _frames(out)


def _resolve_explainer_anchor(anchor, words, cursor, fps, dur_frames):
    """(frame, new_cursor). word/phrase | '@start' | '@<sec>' | '@f<frac>'."""
    a = str(anchor).strip()
    if a in ("", "@start"):
        return 0, cursor
    if a.startswith("@f"):
        return round(float(a[2:]) * dur_frames), cursor
    if a.startswith("@"):
        return round(float(a[1:]) * fps), cursor
    token = _canon(a.split()[0])
    for i in range(cursor, len(words)):
        wn = _canon(words[i]["word"])
        if wn and (wn == token or (len(token) >= 3 and len(wn) >= 3 and (token in wn or wn in token))):
            return round(words[i]["start"] * fps), i + 1
    return None, cursor


def ingest_explainer(spec_path, job_path, *, quiet: bool = False) -> Path:
    """Assemble a generated explainer chapter spec (steps + anchors + word-timestamps) into the
    render job (in-process port of gen_spec). Paths localized for the running interpreter."""
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out = Path(job_path)
    fps = int(spec.get("fps", 30))
    cache = (json.loads(Path(_localize(spec["wordsCache"])).read_text(encoding="utf-8"))
             if spec.get("wordsCache") else {})
    wav_dir = Path(_localize(spec["wavDir"]))
    audio_dir = _to_win(spec["audioDir"])                    # node-side path for audioSrc
    seg_text = {}
    if spec.get("segments"):
        for s in json.loads(Path(_localize(spec["segments"])).read_text(encoding="utf-8")):
            seg_text[int(s["step"])] = s["text"]

    steps_out = []
    for idx, st in enumerate(spec["steps"], start=1):
        words = cache.get(st["wav"], [])
        dur_frames = round(_wav_seconds(wav_dir / f"{st['wav']}.wav") * fps)
        reveal, cur = [], 0
        for anc in st.get("anchors", []):
            f, cur = _resolve_explainer_anchor(anc, words, cur, fps, dur_frames)
            reveal.append(f if f is not None else (reveal[-1] + 15 if reveal else 0))
        words_frames = [{"text": w["word"], "startFrame": round(w["start"] * fps),
                         "endFrame": round(w["end"] * fps)} for w in words]
        caption_words = _relabel_captions(words, seg_text.get(st.get("step", idx), ""), fps)
        steps_out.append({
            "block": st["block"],
            "audioSrc": f"{audio_dir}/{st['audio']}",
            "durationInFrames": dur_frames,
            "revealFrames": reveal,
            "words": words_frames,
            "captionWords": caption_words,
            "props": st.get("props", {}),
        })
        if not quiet:
            print(f"{st['block']:16} {dur_frames:4}f  reveals {reveal}  <- {st.get('anchors', [])}")

    job = {"out": spec["out"], "theme": spec.get("theme", "bold-signal"),
           "captions": spec.get("captions", False), "props": {"steps": steps_out}}
    if spec.get("fx"):
        job["fx"] = spec["fx"]
    out.write_text(json.dumps(job, indent=2), encoding="utf-8")
    if not quiet:
        print(f"-> {out}  (total {sum(s['durationInFrames'] for s in steps_out)} frames)")
    return out
