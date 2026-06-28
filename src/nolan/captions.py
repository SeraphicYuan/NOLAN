"""Caption/timing generation for NOLAN voiceovers.

Hybrid word-timing: we know the exact script text (it's what we fed to TTS), so
we take Whisper's *timing* and snap it onto our *known words* via sequence
alignment. Result = correct spelling (proper nouns, numbers) + accurate timing,
with no extra dependencies. Produces line-level SRT/VTT (readable captions) and a
word-level JSON (for kinetic captions).
"""

from __future__ import annotations

import difflib
import re
from typing import List, Dict, Any


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def align_words(known_words: List[str], whisper_words: List[Any]) -> List[Dict[str, Any]]:
    """Map Whisper word timings onto the known script words.

    known_words: the true text tokens (kept verbatim in output).
    whisper_words: objects with .word/.start/.end (from transcribe_words).
    Returns [{word, start, end}] in known-word order, gaps interpolated.
    """
    out = [{"word": k, "start": None, "end": None} for k in known_words]
    if not known_words:
        return []
    if not whisper_words:
        # No timing at all — leave for the caller's fill pass below.
        wt = []
    else:
        wt = whisper_words

    Kn = [_norm(k) for k in known_words]
    Wn = [_norm(getattr(x, "word", "")) for x in wt]
    sm = difflib.SequenceMatcher(a=Kn, b=Wn, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for off in range(i2 - i1):
                out[i1 + off]["start"] = wt[j1 + off].start
                out[i1 + off]["end"] = wt[j1 + off].end
        elif j2 > j1 and i2 > i1:
            # replace: spread the matched audio span over the known words
            t0, t1 = wt[j1].start, wt[j2 - 1].end
            n = i2 - i1
            step = (t1 - t0) / n if n else 0.0
            for off in range(n):
                out[i1 + off]["start"] = t0 + step * off
                out[i1 + off]["end"] = t0 + step * (off + 1)
        # 'delete' (known words, no audio) and 'insert' (extra audio) -> fill below

    # Fill any remaining gaps (known words Whisper didn't surface) by spreading
    # them across the time between the previous end and the next known start.
    i = 0
    while i < len(out):
        if out[i]["start"] is None:
            j = i
            while j < len(out) and out[j]["start"] is None:
                j += 1
            prev_end = out[i - 1]["end"] if i > 0 and out[i - 1]["end"] is not None else 0.0
            next_start = out[j]["start"] if j < len(out) else prev_end + 0.3 * (j - i)
            span = max(0.0, next_start - prev_end)
            n = j - i
            step = span / n if n else 0.0
            for k in range(n):
                out[i + k]["start"] = round(prev_end + step * k, 3)
                out[i + k]["end"] = round(prev_end + step * (k + 1), 3)
            i = j
        else:
            out[i]["start"] = round(out[i]["start"], 3)
            out[i]["end"] = round(out[i]["end"], 3)
            i += 1
    # cast to plain floats so the JSON is portable (Whisper may return np.float64)
    for w in out:
        w["start"] = float(w["start"])
        w["end"] = float(w["end"])
    return out


def shift_words(words: List[Dict[str, Any]], offset: float) -> List[Dict[str, Any]]:
    """Return a copy of words shifted by `offset` seconds (for the full timeline)."""
    return [{"word": w["word"], "start": float(round(w["start"] + offset, 3)),
             "end": float(round(w["end"] + offset, 3))} for w in words]


def group_lines(words: List[Dict[str, Any]], max_chars: int = 42, max_words: int = 8,
                max_dur: float = 6.0, max_gap: float = 0.8) -> List[Dict[str, Any]]:
    """Group words into readable caption lines (length/duration/gap/sentence breaks)."""
    lines, cur = [], []

    def flush():
        if cur:
            lines.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                          "text": " ".join(x["word"] for x in cur)})
            cur.clear()

    for w in words:
        if cur:
            text = " ".join(x["word"] for x in cur)
            gap = w["start"] - cur[-1]["end"]
            if (len(text) + 1 + len(w["word"]) > max_chars or len(cur) >= max_words
                    or (w["end"] - cur[0]["start"]) > max_dur or gap > max_gap):
                flush()
        cur.append(w)
        if re.search(r"[.!?][\"')\]]?$", w["word"]):  # break after sentence end
            flush()
    flush()
    return lines


def _ts(t: float, sep: str = ",") -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def words_to_srt(words: List[Dict[str, Any]]) -> str:
    out = []
    for i, l in enumerate(group_lines(words), 1):
        out.append(f"{i}\n{_ts(l['start'])} --> {_ts(l['end'])}\n{l['text']}\n")
    return "\n".join(out)


def words_to_vtt(words: List[Dict[str, Any]]) -> str:
    out = ["WEBVTT", ""]
    for l in group_lines(words):
        out.append(f"{_ts(l['start'], '.')} --> {_ts(l['end'], '.')}\n{l['text']}\n")
    return "\n".join(out)
