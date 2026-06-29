"""Spec generator: an anchor-based chapter spec + per-step word timestamps ->
the Remotion render job (computed revealFrames + durations). This is the piece
that makes the chapter render from data instead of hand-tuned frame numbers.

Per step the author writes a block + props + a list of `anchors` (one per reveal
point). An anchor is:
  - a word/phrase in the narration  -> reveal at that word's start time
  - "@start" or ""                  -> frame 0
  - "@2.5"  (absolute seconds)      -> frame round(2.5*fps)
  - "@f0.5" (fraction of duration)  -> frame round(0.5*durationInFrames)
We resolve each anchor against that step's word timestamps; durations come from
the wav files. Output is the exact JSON render.mjs consumes.

Usage: python gen_spec.py <chapter.spec.json> <out.job.json>
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import wave
from pathlib import Path


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


# Number-word <-> digit, because TTS narration says "two thousand" but whisper
# transcribes the spoken number as a digit ("2,000"). Canonicalizing both sides
# lets an anchor word like "two"/"ten" match the digit token "2"/"10".
_NUM = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
    "hundred": "100", "thousand": "1000", "million": "1000000",
}


def _canon(s: str) -> str:
    n = _norm(s)
    return _NUM.get(n, n)


def _wav_seconds(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _relabel_captions(words: list[dict], text: str, fps: int) -> list[dict]:
    """Carry the *authoritative script* spelling onto *whisper's* timing.

    Whisper transcribes the TTS audio for exact per-word timestamps, but mangles
    technical tokens ("BLEU"->"BLU", "28.4"->"28 .4", "two"->"2"). The script is
    the source of truth for what was *said*. We align the two token streams
    (canonicalized) and emit caption words that read like the script but are
    timed like the audio: matched runs map 1:1 (exact timing); rewritten runs
    distribute the script tokens evenly across that run's whisper time span.
    Falls back to raw whisper words when no script text is available.
    """
    def _frames(toks):  # [{text,start,end}] -> [{text,startFrame,endFrame}]
        return [{"text": t["text"], "startFrame": round(t["start"] * fps),
                 "endFrame": round(t["end"] * fps)} for t in toks]

    raw = [{"text": w["word"], "start": w["start"], "end": w["end"]} for w in words]
    script = text.split() if text else []
    if not words or not script:
        return _frames(raw)

    wc = [_canon(w["word"]) for w in words]
    sc = [_canon(t) for t in script]
    out: list[dict] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=wc, b=sc, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                w = words[i1 + k]
                out.append({"text": script[j1 + k], "start": w["start"], "end": w["end"]})
            continue
        stoks = script[j1:j2]
        if not stoks:  # whisper had tokens the script doesn't -> drop them
            continue
        wrun = words[i1:i2]
        if wrun:
            t0, t1 = wrun[0]["start"], wrun[-1]["end"]
        else:  # pure insertion: borrow the gap between neighbors
            t0 = out[-1]["end"] if out else (words[i1]["start"] if i1 < len(words) else 0.0)
            t1 = words[i1]["start"] if i1 < len(words) else t0
        span = max(t1 - t0, 1e-3)
        n = len(stoks)
        for k, tok in enumerate(stoks):
            out.append({"text": tok, "start": t0 + span * k / n, "end": t0 + span * (k + 1) / n})
    return _frames(out)


def _resolve(anchor: str, words: list[dict], cursor: int, fps: int, dur_frames: int):
    """Return (frame, new_cursor). Scans words from `cursor` forward."""
    a = anchor.strip()
    if a in ("", "@start"):
        return 0, cursor
    if a.startswith("@f"):
        return round(float(a[2:]) * dur_frames), cursor
    if a.startswith("@"):
        return round(float(a[1:]) * fps), cursor
    token = _canon(a.split()[0])
    for i in range(cursor, len(words)):
        wn = _canon(words[i]["word"])
        # exact match (incl. number-word<->digit), or substring only when both
        # tokens are >=3 chars (so tiny words like "a"/"i" don't match inside a
        # longer anchor).
        if wn and (wn == token or (len(token) >= 3 and len(wn) >= 3 and (token in wn or wn in token))):
            return round(words[i]["start"] * fps), i + 1
    return None, cursor  # not found — caller falls back


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    fps = int(spec.get("fps", 30))
    cache = json.loads(Path(spec["wordsCache"]).read_text(encoding="utf-8")) if spec.get("wordsCache") else {}
    wav_dir = Path(spec["wavDir"])
    # Optional authoritative narration text per step (for clean captions).
    seg_text: dict[int, str] = {}
    if spec.get("segments"):
        for s in json.loads(Path(spec["segments"]).read_text(encoding="utf-8")):
            seg_text[int(s["step"])] = s["text"]

    steps_out = []
    for idx, st in enumerate(spec["steps"], start=1):
        words = cache.get(st["wav"], [])
        dur_frames = round(_wav_seconds(wav_dir / f"{st['wav']}.wav") * fps)
        reveal, cur = [], 0
        for anc in st.get("anchors", []):
            f, cur = _resolve(anc, words, cur, fps, dur_frames)
            reveal.append(f if f is not None else (reveal[-1] + 15 if reveal else 0))
        # Full per-word timeline (step-relative frames) — library blocks use
        # `revealFrames`; bespoke/Raw blocks can sync motion to individual words.
        words_frames = [{"text": w["word"], "startFrame": round(w["start"] * fps),
                         "endFrame": round(w["end"] * fps)} for w in words]
        # Captions read like the script but stay timed to the audio; falls back
        # to the raw whisper words when no script segment text is provided.
        caption_words = _relabel_captions(words, seg_text.get(st.get("step", idx), ""), fps)
        steps_out.append({
            "block": st["block"],
            "audioSrc": f"{spec['audioDir']}/{st['audio']}",
            "durationInFrames": dur_frames,
            "revealFrames": reveal,
            "words": words_frames,
            "captionWords": caption_words,
            "props": st.get("props", {}),
        })
        print(f"{st['block']:16} {dur_frames:4}f  reveals {reveal}  <- {st.get('anchors', [])}")

    job = {"out": spec["out"], "theme": spec.get("theme", "bold-signal"),
           "captions": spec.get("captions", False), "props": {"steps": steps_out}}
    if spec.get("fx"):  # optional global post-processing (grade/bloom/grain/vignette)
        job["fx"] = spec["fx"]
    out.write_text(json.dumps(job, indent=2), encoding="utf-8")
    print(f"-> {out}  (total {sum(s['durationInFrames'] for s in steps_out)} frames)")


if __name__ == "__main__":
    main()
